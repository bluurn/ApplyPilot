"""Greenhouse Job Board API discovery.

Fetches public employer boards without authentication, normalizes published
jobs, applies the configured role/location filters, and stores results in the
shared jobs database.
"""

from __future__ import annotations

import html
import json
import logging
import re
import sqlite3
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from html.parser import HTMLParser

from applypilot import config
from applypilot.database import init_db
from applypilot.discovery.filters import (
    evaluate_location,
    title_is_excluded,
    title_matches_queries,
)

log = logging.getLogger(__name__)

API_ROOT = "https://boards-api.greenhouse.io/v1/boards"


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.skip = False

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in ("script", "style"):
            self.skip = True
        elif tag in ("br", "p", "div", "li", "tr", "h1", "h2", "h3"):
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style"):
            self.skip = False
        elif tag in ("p", "div", "li", "tr"):
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.skip:
            self.parts.append(data)


def strip_html(value: str | None) -> str:
    """Convert Greenhouse's escaped HTML content into plain text."""
    if not value:
        return ""
    decoded = html.unescape(html.unescape(value))
    parser = _TextExtractor()
    parser.feed(decoded)
    text = "".join(parser.parts)
    text = re.sub(r"[^\S\n]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def load_boards() -> dict:
    """Load the Greenhouse board mapping from the runtime registry."""
    return config.load_greenhouse_config().get("boards", {})


def fetch_board_jobs(board_token: str, timeout: float = 30) -> list[dict]:
    """Fetch every published job from a public Greenhouse board."""
    token = urllib.parse.quote(board_token, safe="")
    url = f"{API_ROOT}/{token}/jobs?content=true"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "ApplyPilot/0.3 Greenhouse discovery",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = json.loads(response.read())

    jobs = data.get("jobs") if isinstance(data, dict) else None
    if not isinstance(jobs, list):
        raise ValueError("Greenhouse response is missing a jobs list")
    return jobs


def normalize_job(board_key: str, board: dict, raw: dict, now: str) -> dict:
    """Normalize one Greenhouse API job into ApplyPilot's discovery schema."""
    content = strip_html(raw.get("content"))
    location_data = raw.get("location")
    location = location_data.get("name", "") if isinstance(location_data, dict) else ""
    url = raw.get("absolute_url", "")
    return {
        "url": url,
        "title": raw.get("title", ""),
        "salary": None,
        "description": content[:500] or None,
        "location": location,
        "site": board.get("name", board_key),
        "strategy": "greenhouse_api",
        "discovered_at": now,
        "full_description": content or None,
        "application_url": url,
        "detail_scraped_at": now if content else None,
        "detail_error": None,
    }


def filter_jobs(raw_jobs: list[dict], search_cfg: dict) -> list[dict]:
    """Filter prospect posts, irrelevant roles, titles, and locations."""
    max_tier = search_cfg.get("greenhouse_max_tier", 2)
    queries = [
        item["query"]
        for item in search_cfg.get("queries", [])
        if item.get("query") and item.get("tier", 99) <= max_tier
    ]
    exclude_titles = search_cfg.get("exclude_titles", [])
    accept_locations = search_cfg.get("location_accept", [])
    reject_locations = [
        *search_cfg.get("location_reject_non_remote", []),
        *search_cfg.get("location_reject_remote", []),
    ]

    filtered = []
    for job in raw_jobs:
        if job.get("internal_job_id") is None:
            continue
        title = job.get("title")
        location_data = job.get("location")
        location = location_data.get("name") if isinstance(location_data, dict) else None
        if title_is_excluded(title, exclude_titles):
            continue
        if not title_matches_queries(title, queries):
            continue
        decision = evaluate_location(
            location,
            accept_locations,
            reject_locations,
            job.get("content"),
        )
        if not decision.allowed:
            log.debug(
                "Filtered %s location %r: %s",
                job.get("title"),
                location,
                decision.reason,
            )
            continue
        filtered.append(job)
    return filtered


def store_jobs(conn: sqlite3.Connection, jobs: list[dict]) -> tuple[int, int]:
    """Store normalized Greenhouse jobs, deduplicating on canonical URL."""
    new = 0
    existing = 0
    for job in jobs:
        if not job["url"]:
            continue
        try:
            conn.execute(
                """
                INSERT INTO jobs (
                    url, title, salary, description, location, site, strategy,
                    discovered_at, full_description, application_url,
                    detail_scraped_at, detail_error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job["url"],
                    job["title"],
                    job["salary"],
                    job["description"],
                    job["location"],
                    job["site"],
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
    conn.commit()
    return new, existing


def run_greenhouse_discovery(
    boards: dict | None = None,
    workers: int = 8,
    conn: sqlite3.Connection | None = None,
) -> dict:
    """Fetch configured Greenhouse boards with per-employer failure isolation."""
    if boards is None:
        boards = load_boards()
    if not boards:
        log.warning("No Greenhouse boards configured in the runtime registry.")
        return {"found": 0, "new": 0, "existing": 0, "errors": 0, "boards": 0}

    search_cfg = config.load_search_config()
    timeout = search_cfg.get("defaults", {}).get("source_timeout_seconds", 30)
    now = datetime.now(timezone.utc).isoformat()
    if conn is None:
        conn = init_db()

    fetched: dict[str, list[dict]] = {}
    errors = 0
    with ThreadPoolExecutor(max_workers=min(workers, len(boards))) as executor:
        futures = {
            executor.submit(fetch_board_jobs, board["token"], timeout): key
            for key, board in boards.items()
        }
        for future in as_completed(futures):
            key = futures[future]
            try:
                fetched[key] = future.result()
            except Exception as exc:
                errors += 1
                log.error("%s: Greenhouse API error: %s", boards[key]["name"], exc)

    found = 0
    new = 0
    existing = 0
    for key, board in boards.items():
        raw_jobs = fetched.get(key)
        if raw_jobs is None:
            continue
        selected = filter_jobs(raw_jobs, search_cfg)
        normalized = [normalize_job(key, board, raw, now) for raw in selected]
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
