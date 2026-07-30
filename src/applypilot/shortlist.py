"""Persistent, canonical job shortlist management."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone


def resolve_job(conn: sqlite3.Connection, url: str) -> dict | None:
    """Resolve a source/application/duplicate URL to its canonical job."""
    row = conn.execute(
        "SELECT * FROM jobs WHERE url = ? OR application_url = ? LIMIT 1",
        (url, url),
    ).fetchone()
    if row is None:
        return None
    job = dict(row)
    if job.get("duplicate_of"):
        canonical = conn.execute(
            "SELECT * FROM jobs WHERE url = ?",
            (job["duplicate_of"],),
        ).fetchone()
        if canonical is not None:
            job = dict(canonical)
    return job


def add_job(conn: sqlite3.Connection, url: str) -> tuple[str, dict | None]:
    """Add a canonical eligible job to the shortlist."""
    job = resolve_job(conn, url)
    if job is None:
        return "not_found", None
    if job.get("eligibility_allowed") == 0:
        return "ineligible", job
    if job.get("is_shortlisted"):
        return "already_added", job
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE jobs SET is_shortlisted = 1, shortlisted_at = ? WHERE url = ?",
        (now, job["url"]),
    )
    conn.commit()
    job["is_shortlisted"] = 1
    job["shortlisted_at"] = now
    return "added", job


def remove_job(conn: sqlite3.Connection, url: str) -> tuple[str, dict | None]:
    """Remove a canonical job from the shortlist."""
    job = resolve_job(conn, url)
    if job is None:
        return "not_found", None
    if not job.get("is_shortlisted"):
        return "not_shortlisted", job
    conn.execute(
        "UPDATE jobs SET is_shortlisted = 0, shortlisted_at = NULL WHERE url = ?",
        (job["url"],),
    )
    conn.commit()
    job["is_shortlisted"] = 0
    job["shortlisted_at"] = None
    return "removed", job


def list_jobs(conn: sqlite3.Connection) -> list[dict]:
    """Return shortlisted canonical jobs in application priority order."""
    return [
        dict(row)
        for row in conn.execute(
            """
            SELECT * FROM jobs
            WHERE is_shortlisted = 1
              AND eligibility_allowed IS NOT 0
              AND duplicate_of IS NULL
            ORDER BY fit_score DESC NULLS LAST,
                     is_watchlist DESC,
                     discovery_score DESC NULLS LAST,
                     shortlisted_at ASC
            """
        ).fetchall()
    ]
