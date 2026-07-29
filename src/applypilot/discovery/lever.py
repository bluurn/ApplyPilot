"""Lever Postings API discovery."""

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

API_ROOTS = {
    "global": "https://api.lever.co/v0/postings",
    "eu": "https://api.eu.lever.co/v0/postings",
}


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in ("br", "p", "div", "li", "tr", "h1", "h2", "h3"):
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("p", "div", "li", "tr"):
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def strip_html(value: str | None) -> str:
    """Convert Lever list content into plain text."""
    if not value:
        return ""
    parser = _TextExtractor()
    parser.feed(html.unescape(value))
    text = "".join(parser.parts)
    text = re.sub(r"[^\S\n]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def load_sites() -> dict:
    """Load the Lever site mapping from the runtime registry."""
    return config.load_lever_config().get("sites", {})


def fetch_site_jobs(
    site_name: str,
    instance: str = "global",
    timeout: float = 30,
) -> list[dict]:
    """Fetch all published jobs from a public Lever site."""
    try:
        root = API_ROOTS[instance]
    except KeyError as exc:
        raise ValueError(f"Unknown Lever instance: {instance}") from exc

    site = urllib.parse.quote(site_name, safe="")
    url = f"{root}/{site}?mode=json"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "ApplyPilot/0.3 Lever discovery",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = json.loads(response.read())
    if not isinstance(data, list):
        raise ValueError("Lever response is not a jobs list")
    return data


def _location(raw: dict) -> str:
    categories = raw.get("categories")
    if not isinstance(categories, dict):
        categories = {}
    values = categories.get("allLocations")
    if not isinstance(values, list) or not values:
        values = [categories.get("location", "")]

    locations = []
    for value in values:
        if isinstance(value, dict):
            value = value.get("name", "")
        if value and value not in locations:
            locations.append(str(value))

    location = "; ".join(locations)
    if raw.get("workplaceType") == "remote" and "remote" not in location.casefold():
        location = f"{location} (Remote)" if location else "Remote"
    return location


def _description(raw: dict) -> str:
    parts = [raw.get("descriptionPlain", "")]
    for item in raw.get("lists", []):
        if not isinstance(item, dict):
            continue
        heading = item.get("text", "")
        content = strip_html(item.get("content"))
        parts.append("\n".join(part for part in (heading, content) if part))
    parts.append(raw.get("additionalPlain", ""))
    return "\n\n".join(str(part).strip() for part in parts if part).strip()


def _salary(raw: dict) -> str | None:
    description = raw.get("salaryDescriptionPlain")
    if description:
        return str(description).strip()
    salary_range = raw.get("salaryRange")
    if not isinstance(salary_range, dict):
        return None
    minimum = salary_range.get("min")
    maximum = salary_range.get("max")
    if minimum is None and maximum is None:
        return None
    currency = salary_range.get("currency", "")
    interval = salary_range.get("interval", "")
    values = "-".join(f"{value:,}" for value in (minimum, maximum) if value is not None)
    suffix = f"/{interval}" if interval else ""
    return f"{currency} {values}{suffix}".strip()


def normalize_job(site_key: str, site: dict, raw: dict, now: str) -> dict:
    """Normalize one Lever posting into ApplyPilot's database schema."""
    description = _description(raw)
    url = raw.get("hostedUrl", "")
    return {
        "url": url,
        "title": raw.get("text", ""),
        "salary": _salary(raw),
        "description": description[:500] or None,
        "location": _location(raw),
        "site": site.get("name", site_key),
        "strategy": "lever_api",
        "discovered_at": now,
        "full_description": description or None,
        "application_url": raw.get("applyUrl") or url,
        "detail_scraped_at": now if description else None,
        "detail_error": None,
    }


def _is_freelance_contract(raw: dict) -> bool:
    categories = raw.get("categories")
    commitment = categories.get("commitment", "") if isinstance(categories, dict) else ""
    normalized = str(commitment).casefold().strip()
    return normalized in {"contract", "contractor", "freelance", "b2b"}


def filter_jobs(raw_jobs: list[dict], search_cfg: dict) -> list[dict]:
    """Apply configured role, engagement, title, and location policy."""
    max_tier = search_cfg.get("lever_max_tier", 2)
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
        title = raw.get("text")
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
            _description(raw),
            explicit_geography=bool(raw.get("country")),
        )
        if not decision.allowed:
            log.debug("Filtered %s location %r: %s", title, location, decision.reason)
            continue
        filtered.append(raw)
    return filtered


def store_jobs(conn: sqlite3.Connection, jobs: list[dict]) -> tuple[int, int]:
    """Store normalized Lever jobs, deduplicating on hosted URL."""
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


def run_lever_discovery(
    sites: dict | None = None,
    workers: int = 8,
    conn: sqlite3.Connection | None = None,
) -> dict:
    """Fetch configured Lever sites with per-employer failure isolation."""
    if sites is None:
        sites = load_sites()
    if not sites:
        log.warning("No Lever sites configured in the runtime registry.")
        return {"found": 0, "new": 0, "existing": 0, "errors": 0, "sites": 0}

    search_cfg = config.load_search_config()
    timeout = search_cfg.get("defaults", {}).get("source_timeout_seconds", 30)
    now = datetime.now(timezone.utc).isoformat()
    if conn is None:
        conn = init_db()

    fetched: dict[str, list[dict]] = {}
    errors = 0
    with ThreadPoolExecutor(max_workers=min(workers, len(sites))) as executor:
        futures = {
            executor.submit(
                fetch_site_jobs,
                site["site"],
                site.get("instance", "global"),
                timeout,
            ): key
            for key, site in sites.items()
        }
        for future in as_completed(futures):
            key = futures[future]
            try:
                fetched[key] = future.result()
            except Exception as exc:
                errors += 1
                log.error("%s: Lever API error: %s", sites[key]["name"], exc)

    found = 0
    new = 0
    existing = 0
    for key, site in sites.items():
        raw_jobs = fetched.get(key)
        if raw_jobs is None:
            continue
        selected = filter_jobs(raw_jobs, search_cfg)
        normalized = [normalize_job(key, site, raw, now) for raw in selected]
        site_new, site_existing = store_jobs(conn, normalized)
        found += len(normalized)
        new += site_new
        existing += site_existing
        log.info(
            "%s: %d/%d relevant jobs, %d new, %d existing",
            site["name"],
            len(normalized),
            len(raw_jobs),
            site_new,
            site_existing,
        )

    return {
        "found": found,
        "new": new,
        "existing": existing,
        "errors": errors,
        "sites": len(sites),
    }
