"""Daily job-search review report."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta

from applypilot.database import get_connection
from applypilot.discovery.watchlist import load_watchlist_report
from applypilot.scoring.ranking import explain_signals, run_discovery_ranking


def _rows(conn: sqlite3.Connection, query: str, params: tuple = ()) -> list[dict]:
    return [dict(row) for row in conn.execute(query, params).fetchall()]


def _decorate(jobs: list[dict]) -> list[dict]:
    for job in jobs:
        try:
            signals = json.loads(job.get("discovery_signals") or "{}")
        except json.JSONDecodeError:
            signals = {}
        job["discovery_explanation"] = explain_signals(signals)
    return jobs


def build_today_report(
    conn: sqlite3.Connection | None = None,
    *,
    now: datetime | None = None,
    days: int = 1,
    limit: int = 20,
) -> dict:
    """Build a daily brief without mutating applications or LLM scores."""
    if conn is None:
        conn = get_connection()
    if now is None:
        now = datetime.now().astimezone()
    since = now - timedelta(days=days)
    since_value = since.isoformat()
    limit_value = max(1, limit)

    run_discovery_ranking(conn)

    select = """
        SELECT url, title, company, site, location, salary, discovered_at,
               fit_score, discovery_score, discovery_signals, is_watchlist,
               watchlist_name, applied_at, application_url
        FROM jobs
    """
    discovery_order = """
        ORDER BY is_watchlist DESC,
                 discovery_score DESC NULLS LAST,
                 fit_score DESC NULLS LAST,
                 discovered_at DESC
        LIMIT ?
    """
    fit_order = """
        ORDER BY fit_score DESC NULLS LAST,
                 discovery_score DESC NULLS LAST,
                 is_watchlist DESC,
                 discovered_at DESC
        LIMIT ?
    """
    new_jobs = _decorate(
        _rows(
            conn,
            select
            + """
              WHERE datetime(discovered_at) >= datetime(?)
                AND eligibility_allowed IS NOT 0
                AND duplicate_of IS NULL
            """
            + discovery_order,
            (since_value, limit_value),
        )
    )
    best_matches = _decorate(
        _rows(
            conn,
            select
            + """
              WHERE eligibility_allowed IS NOT 0
                AND duplicate_of IS NULL
            """
            + fit_order,
            (limit_value,),
        )
    )
    watchlist_jobs = _decorate(
        _rows(
            conn,
            select
            + """
              WHERE is_watchlist = 1
                AND eligibility_allowed IS NOT 0
                AND duplicate_of IS NULL
            """
            + fit_order,
            (limit_value,),
        )
    )
    applied = _decorate(
        _rows(
            conn,
            select
            + " WHERE datetime(applied_at) >= datetime(?) "
            + "ORDER BY applied_at DESC LIMIT ?",
            (since_value, limit_value),
        )
    )
    new_companies = _rows(
        conn,
        """
        SELECT company, MIN(discovered_at) AS first_seen, COUNT(*) AS jobs
        FROM jobs
        WHERE company IS NOT NULL AND company != ''
          AND eligibility_allowed IS NOT 0
          AND duplicate_of IS NULL
        GROUP BY company
        HAVING datetime(first_seen) >= datetime(?)
        ORDER BY first_seen DESC
        LIMIT ?
        """,
        (since_value, limit_value),
    )
    return {
        "since": since_value,
        "new_jobs": new_jobs,
        "best_matches": best_matches,
        "watchlist_jobs": watchlist_jobs,
        "new_companies": new_companies,
        "applied": applied,
        "watchlist": load_watchlist_report(),
    }
