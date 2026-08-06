"""Ashby public Job Postings API discovery."""

from __future__ import annotations

import json
import logging
import sqlite3
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from applypilot import config
from applypilot.database import init_db
from applypilot.discovery.filters import (
    company_is_excluded,
    evaluate_location,
    title_is_excluded,
    title_matches_queries,
)
from applypilot.discovery.watchlist import (
    prioritize_registry,
    update_existing_watchlist,
    watchlist_fields,
)

log = logging.getLogger(__name__)

API_ROOT = "https://api.ashbyhq.com/posting-api/job-board"


def load_boards() -> dict:
    """Load the Ashby board mapping from the runtime registry."""
    return config.load_ashby_config().get("boards", {})


def fetch_board_jobs(board_name: str, timeout: float = 30) -> list[dict]:
    """Fetch all public listed jobs and compensation from an Ashby board."""
    board = urllib.parse.quote(board_name, safe="")
    url = f"{API_ROOT}/{board}?includeCompensation=true"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "ApplyPilot/0.3 Ashby discovery",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = json.loads(response.read())
    jobs = data.get("jobs") if isinstance(data, dict) else None
    if not isinstance(jobs, list):
        raise ValueError("Ashby response is missing a jobs list")
    return jobs


def _location(raw: dict) -> str:
    locations = []
    primary = raw.get("location")
    if primary:
        locations.append(str(primary))
    for secondary in raw.get("secondaryLocations", []):
        if not isinstance(secondary, dict):
            continue
        value = secondary.get("location")
        if value and value not in locations:
            locations.append(str(value))

    location = "; ".join(locations)
    if raw.get("isRemote") and "remote" not in location.casefold():
        location = f"{location} (Remote)" if location else "Remote"
    return location


def _has_explicit_geography(raw: dict) -> bool:
    address = raw.get("address")
    if isinstance(address, dict):
        postal = address.get("postalAddress")
        if isinstance(postal, dict) and postal.get("addressCountry"):
            return True
    for secondary in raw.get("secondaryLocations", []):
        if not isinstance(secondary, dict):
            continue
        address = secondary.get("address")
        if isinstance(address, dict) and address.get("addressCountry"):
            return True
    return False


def _salary(raw: dict) -> str | None:
    compensation = raw.get("compensation")
    if not isinstance(compensation, dict):
        return None
    value = (
        compensation.get("scrapeableCompensationSalarySummary")
        or compensation.get("compensationTierSummary")
    )
    return str(value).strip() if value else None


def normalize_job(
    board_key: str,
    board: dict,
    raw: dict,
    now: str,
    watchlist: list[str] | None = None,
) -> dict:
    """Normalize one Ashby posting into ApplyPilot's database schema."""
    description = str(raw.get("descriptionPlain") or "").strip()
    url = raw.get("jobUrl", "")
    company = board.get("name", board_key)
    is_watchlist, watchlist_name = watchlist_fields(company, watchlist)
    return {
        "url": url,
        "title": raw.get("title", ""),
        "salary": _salary(raw),
        "description": description[:500] or None,
        "location": _location(raw),
        "site": company,
        "company": company,
        "is_watchlist": is_watchlist,
        "watchlist_name": watchlist_name,
        "strategy": "ashby_api",
        "discovered_at": now,
        "full_description": description or None,
        "application_url": raw.get("applyUrl") or url,
        "detail_scraped_at": now if description else None,
        "detail_error": None,
    }


def _is_freelance_contract(raw: dict) -> bool:
    employment_type = str(raw.get("employmentType") or "").casefold().strip()
    return employment_type in {
        "contract",
        "contractor",
        "freelance",
        "b2b",
        "temporary",
    }


def filter_jobs(raw_jobs: list[dict], search_cfg: dict) -> list[dict]:
    """Apply listing, role, engagement, title, and location policy."""
    max_tier = search_cfg.get("ashby_max_tier", 2)
    queries = [
        item["query"]
        for item in search_cfg.get("queries", [])
        if item.get("query") and item.get("tier", 99) <= max_tier
    ]
    excluded_titles = search_cfg.get("exclude_titles", [])
    accepted_locations = search_cfg.get("location_accept", [])
    rejected_locations = [
        *search_cfg.get("location_reject_non_remote", []),
        *search_cfg.get("location_reject_remote", []),
    ]

    filtered = []
    for raw in raw_jobs:
        title = raw.get("title")
        if raw.get("isListed") is False:
            continue
        if _is_freelance_contract(raw):
            log.debug("Filtered %s: freelance_or_contract", title)
            continue
        if title_is_excluded(title, excluded_titles):
            continue
        if not title_matches_queries(title, queries):
            continue
        location = _location(raw)
        decision = evaluate_location(
            location,
            accepted_locations,
            rejected_locations,
            raw.get("descriptionPlain"),
            explicit_geography=_has_explicit_geography(raw),
        )
        if not decision.allowed:
            log.debug("Filtered %s location %r: %s", title, location, decision.reason)
            continue
        filtered.append(raw)
    return filtered


def store_jobs(conn: sqlite3.Connection, jobs: list[dict]) -> tuple[int, int]:
    """Store normalized Ashby jobs, deduplicating on job URL."""
    new = 0
    existing = 0
    for job in jobs:
        if not job["url"]:
            continue
        try:
            conn.execute(
                """
                INSERT INTO jobs (
                    url, title, salary, description, location, site, company,
                    is_watchlist, watchlist_name, strategy,
                    discovered_at, full_description, application_url,
                    detail_scraped_at, detail_error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job["url"],
                    job["title"],
                    job["salary"],
                    job["description"],
                    job["location"],
                    job["site"],
                    job["company"],
                    job["is_watchlist"],
                    job["watchlist_name"],
                    job["strategy"],
                    job["discovered_at"],
                    job["full_description"],
                    job["application_url"],
                    job["detail_scraped_at"],
                    job["detail_error"],
                ),
            )
            new += 1
        except sqlite3.IntegrityError:
            existing += 1
            update_existing_watchlist(
                conn,
                job["url"],
                job["company"],
                job["is_watchlist"],
                job["watchlist_name"],
            )
    conn.commit()
    return new, existing


def run_ashby_discovery(
    boards: dict | None = None,
    workers: int = 8,
    conn: sqlite3.Connection | None = None,
) -> dict:
    """Fetch configured Ashby boards with per-employer failure isolation."""
    if boards is None:
        boards = load_boards()
    if not boards:
        log.warning("No Ashby boards configured in the runtime registry.")
        return {"found": 0, "new": 0, "existing": 0, "errors": 0, "boards": 0}

    search_cfg = config.load_search_config()
    watchlist = search_cfg.get("watchlist", [])
    boards = prioritize_registry(boards, watchlist)
    timeout = search_cfg.get("defaults", {}).get("source_timeout_seconds", 30)
    now = datetime.now(timezone.utc).isoformat()
    if conn is None:
        conn = init_db()

    fetched: dict[str, list[dict]] = {}
    errors = 0
    with ThreadPoolExecutor(max_workers=min(workers, len(boards))) as executor:
        futures = {
            executor.submit(fetch_board_jobs, board["board"], timeout): key
            for key, board in boards.items()
        }
        for future in as_completed(futures):
            key = futures[future]
            try:
                fetched[key] = future.result()
            except Exception as exc:
                errors += 1
                log.error("%s: Ashby API error: %s", boards[key]["name"], exc)

    exclude_companies = search_cfg.get("exclude_companies", [])
    found = 0
    new = 0
    existing = 0
    for key, board in boards.items():
        if company_is_excluded(board.get("name"), exclude_companies):
            log.info("%s: skipped (excluded company)", board.get("name"))
            continue
        raw_jobs = fetched.get(key)
        if raw_jobs is None:
            continue
        selected = filter_jobs(raw_jobs, search_cfg)
        normalized = [
            normalize_job(key, board, raw, now, watchlist) for raw in selected
        ]
        board_new, board_existing = store_jobs(conn, normalized)
        found += len(normalized)
        new += board_new
        existing += board_existing
        log.info(
            "%s: %d/%d relevant jobs, %d new, %d existing",
            board["name"],
            len(normalized),
            len(raw_jobs),
            board_new,
            board_existing,
        )

    return {
        "found": found,
        "new": new,
        "existing": existing,
        "errors": errors,
        "boards": len(boards),
    }
