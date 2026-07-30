"""Transparent deterministic discovery ranking."""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone

from applypilot import config
from applypilot.database import get_connection
from applypilot.discovery.watchlist import match_watchlist

DEFAULT_WEIGHTS = {
    "python": 3.0,
    "ruby": 3.0,
    "elixir": 3.0,
    "go": 3.0,
    "rust": 3.0,
    "typescript_javascript": 3.0,
    "unpreferred_language": -2.0,
    "backend": 3.0,
    "germany": 3.0,
    "europe": 2.0,
    "remote": 2.0,
    "relocation": 1.5,
    "salary": 1.0,
    "watchlist": 2.0,
}

PREFERRED_LANGUAGE_MARKERS = {
    "python": ("python", "django", "fastapi"),
    "ruby": ("ruby", "rails", "ruby on rails"),
    "elixir": ("elixir", "phoenix"),
    "go": ("golang", "go developer", "go engineer"),
    "rust": ("rust",),
    "typescript_javascript": ("typescript", "javascript", "node.js", "nodejs"),
}
UNPREFERRED_LANGUAGE_MARKERS = (
    "java",
    "kotlin",
    "c#",
    ".net",
    "dotnet",
    "sap",
    "abap",
)

GERMANY_MARKERS = (
    "germany",
    "deutschland",
    "berlin",
    "munich",
    "münchen",
    "hamburg",
    "frankfurt",
    "cologne",
    "köln",
    "düsseldorf",
)
EUROPE_MARKERS = (
    "europe",
    "emea",
    "eu remote",
    "austria",
    "belgium",
    "bulgaria",
    "croatia",
    "cyprus",
    "czech",
    "denmark",
    "estonia",
    "finland",
    "france",
    "greece",
    "hungary",
    "ireland",
    "italy",
    "latvia",
    "lithuania",
    "luxembourg",
    "malta",
    "netherlands",
    "norway",
    "poland",
    "portugal",
    "romania",
    "slovakia",
    "slovenia",
    "spain",
    "sweden",
    "switzerland",
)
REMOTE_MARKERS = ("remote", "anywhere", "work from home", "distributed")
RELOCATION_MARKERS = (
    "relocation assistance",
    "relocation support",
    "relocation package",
    "visa sponsorship",
    "sponsorship available",
)
RELOCATION_DENIALS = (
    "no relocation",
    "do not offer relocation",
    "relocation is not available",
    "no visa sponsorship",
    "unable to sponsor",
    "cannot sponsor",
    "do not sponsor",
)


def _contains_word(text: str, word: str) -> bool:
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(word)}(?![a-z0-9])", text))


def _weights(search_cfg: dict) -> dict[str, float]:
    configured = search_cfg.get("ranking", {}).get("weights", {})
    return {
        name: float(configured.get(name, default))
        for name, default in DEFAULT_WEIGHTS.items()
    }


def rank_job(job: dict, search_cfg: dict | None = None) -> dict:
    """Calculate independent signals and grouped contributions for one job."""
    if search_cfg is None:
        search_cfg = config.load_search_config()
    weights = _weights(search_cfg)
    title = str(job.get("title") or "").casefold()
    description = str(
        job.get("full_description") or job.get("description") or ""
    ).casefold()
    location = str(job.get("location") or "").casefold()
    text = f"{title}\n{description}"

    language_signals = {
        name: any(marker in text for marker in markers)
        for name, markers in PREFERRED_LANGUAGE_MARKERS.items()
    }
    preferred_language = any(language_signals.values())
    unpreferred_language = (
        not preferred_language
        and any(marker in text for marker in UNPREFERRED_LANGUAGE_MARKERS)
    )
    python = language_signals["python"]
    backend = (
        "backend" in text
        or "back-end" in text
        or _contains_word(text, "api")
        or "distributed system" in text
    )
    germany = any(marker in location for marker in GERMANY_MARKERS)
    europe = germany or any(marker in location for marker in EUROPE_MARKERS)
    remote = any(marker in location for marker in REMOTE_MARKERS)
    offers_relocation = any(marker in text for marker in RELOCATION_MARKERS)
    denies_relocation = any(marker in text for marker in RELOCATION_DENIALS)
    relocation = offers_relocation and not denies_relocation
    salary = bool(job.get("salary"))
    watchlist = bool(job.get("is_watchlist"))

    # Closely related signals are grouped with max(), preventing a Python
    # backend title or Germany-remote location from being counted repeatedly.
    technical_contribution = max(
        *(weights[name] if active else 0 for name, active in language_signals.items()),
        weights["backend"] if backend else 0,
    )
    geography_contribution = max(
        weights["germany"] if germany else 0,
        weights["europe"] if europe else 0,
        weights["remote"] if remote else 0,
    )
    contributions = {
        "technical_fit": technical_contribution,
        "language_penalty": weights["unpreferred_language"] if unpreferred_language else 0,
        "geography_fit": geography_contribution,
        "relocation": weights["relocation"] if relocation else 0,
        "salary": weights["salary"] if salary else 0,
        "watchlist": weights["watchlist"] if watchlist else 0,
    }
    signals = {
        "python": python,
        "languages": language_signals,
        "unpreferred_language": unpreferred_language,
        "backend": backend,
        "germany": germany,
        "europe": europe,
        "remote": remote,
        "relocation": relocation,
        "salary": salary,
        "watchlist": watchlist,
        "contributions": contributions,
    }
    return {
        "score": round(sum(contributions.values()), 2),
        "signals": signals,
    }


def explain_signals(signals: dict) -> str:
    """Render active signal contributions in a compact inspectable form."""
    labels = {
        "technical_fit": "technical",
        "geography_fit": "geography",
        "relocation": "relocation",
        "salary": "salary",
        "watchlist": "watchlist",
        "language_penalty": "language penalty",
    }
    parts = [
        f"{labels[name]} {value:+g}"
        for name, value in signals.get("contributions", {}).items()
        if value
    ]
    return ", ".join(parts) if parts else "no positive deterministic signals"


def run_discovery_ranking(
    conn: sqlite3.Connection | None = None,
    search_cfg: dict | None = None,
) -> dict:
    """Rank every stored job, allowing enrichment and config changes to backfill."""
    if conn is None:
        conn = get_connection()
    if search_cfg is None:
        search_cfg = config.load_search_config()
    rows = conn.execute("SELECT * FROM jobs").fetchall()
    now = datetime.now(timezone.utc).isoformat()
    watchlist = search_cfg.get("watchlist", [])
    for row in rows:
        job = dict(row)
        matched = match_watchlist(job.get("company") or job.get("site"), watchlist)
        if matched:
            job["company"] = job.get("company") or job.get("site")
            job["is_watchlist"] = 1
            job["watchlist_name"] = matched
        result = rank_job(job, search_cfg)
        conn.execute(
            """
            UPDATE jobs
            SET company = COALESCE(company, ?),
                is_watchlist = MAX(COALESCE(is_watchlist, 0), ?),
                watchlist_name = COALESCE(watchlist_name, ?),
                discovery_score = ?, discovery_signals = ?, ranked_at = ?
            WHERE url = ?
            """,
            (
                job.get("company"),
                job.get("is_watchlist", 0),
                job.get("watchlist_name"),
                result["score"],
                json.dumps(result["signals"], sort_keys=True),
                now,
                job["url"],
            ),
        )
    conn.commit()
    return {"ranked": len(rows)}
