"""Exact, inspectable company watchlist helpers."""

from __future__ import annotations

import re
import sqlite3


def normalize_company(value: str | None) -> str:
    """Normalize punctuation and spacing without fuzzy or semantic matching."""
    return re.sub(r"[^a-z0-9]+", "", (value or "").casefold())


def match_watchlist(
    company: str | None,
    watchlist: list[str] | None,
) -> str | None:
    """Return the configured watchlist spelling for an exact normalized match."""
    normalized = normalize_company(company)
    if not normalized:
        return None
    for configured_name in watchlist or []:
        if normalize_company(configured_name) == normalized:
            return configured_name
    return None


def watchlist_fields(
    company: str | None,
    watchlist: list[str] | None,
) -> tuple[int, str | None]:
    """Return database-ready watchlist marker fields."""
    matched = match_watchlist(company, watchlist)
    return (1, matched) if matched else (0, None)


def update_existing_watchlist(
    conn: sqlite3.Connection,
    url: str,
    company: str | None,
    is_watchlist: int,
    watchlist_name: str | None,
) -> None:
    """Promote an existing deduplicated row when it becomes watchlisted."""
    conn.execute(
        """
        UPDATE jobs
        SET company = COALESCE(company, ?),
            is_watchlist = MAX(COALESCE(is_watchlist, 0), ?),
            watchlist_name = COALESCE(watchlist_name, ?)
        WHERE url = ?
        """,
        (company, is_watchlist, watchlist_name, url),
    )


def prioritize_registry(registry: dict, watchlist: list[str] | None) -> dict:
    """Return registry entries with exact watchlist companies first."""
    priority = []
    regular = []
    for key, value in registry.items():
        target = priority if match_watchlist(value.get("name"), watchlist) else regular
        target.append((key, value))
    return dict(priority + regular)


def registry_watchlist_report(watchlist: list[str], registries: list[dict]) -> dict:
    """Report which configured companies have a first-class registry entry."""
    names = [
        value.get("name")
        for registry in registries
        for value in registry.values()
        if value.get("name")
    ]
    present = [
        configured
        for configured in watchlist
        if any(
            normalize_company(configured) == normalize_company(name)
            for name in names
        )
    ]
    missing = [name for name in watchlist if name not in present]
    return {"configured": watchlist, "present": present, "missing": missing}


def load_watchlist_report() -> dict:
    """Load configured first-class registries and report watchlist coverage."""
    from applypilot import config

    watchlist = config.load_search_config().get("watchlist", [])
    registries = [
        config.load_employers_config().get("employers", {}),
        config.load_greenhouse_config().get("boards", {}),
        config.load_lever_config().get("sites", {}),
        config.load_ashby_config().get("boards", {}),
    ]
    return registry_watchlist_report(watchlist, registries)
