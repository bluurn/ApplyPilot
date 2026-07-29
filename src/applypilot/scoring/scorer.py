"""Job fit scoring: LLM-powered evaluation of candidate-job match quality.

Scores jobs on a 1-10 scale by comparing the user's resume against each
job description. All personal data is loaded at runtime from the user's
profile and resume file.
"""

import logging
import re
import time
from collections import defaultdict
from datetime import datetime, timezone
from difflib import SequenceMatcher

from applypilot import config
from applypilot.config import RESUME_PATH
from applypilot.database import get_connection
from applypilot.discovery.filters import evaluate_location
from applypilot.llm import get_client

log = logging.getLogger(__name__)


def _normalized(value: str | None) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", (value or "").casefold()))


def _has_explicit_geography(location: str | None) -> bool:
    normalized = _normalized(location)
    generic = {"", "remote", "worldwide", "anywhere", "distributed"}
    return normalized not in generic


def audit_scoring_candidates(conn, search_cfg: dict) -> dict:
    """Persist current eligibility and semantic duplicate decisions."""
    accept = search_cfg.get("location_accept", [])
    reject = [
        *search_cfg.get("location_reject_non_remote", []),
        *search_cfg.get("location_reject_remote", []),
    ]
    rows = [dict(row) for row in conn.execute("SELECT * FROM jobs").fetchall()]
    now = datetime.now(timezone.utc).isoformat()
    eligible = 0
    rejected = 0

    for job in rows:
        decision = evaluate_location(
            job.get("location"),
            accept,
            reject,
            job.get("full_description") or job.get("description"),
            explicit_geography=_has_explicit_geography(job.get("location")),
        )
        conn.execute(
            """
            UPDATE jobs
            SET eligibility_allowed = ?, eligibility_reason = ?,
                eligibility_audited_at = ?, duplicate_of = NULL
            WHERE url = ?
            """,
            (int(decision.allowed), decision.reason, now, job["url"]),
        )
        if decision.allowed:
            eligible += 1
        else:
            rejected += 1

    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for job in rows:
        groups[
            (
                _normalized(job.get("company") or job.get("site")),
                _normalized(job.get("title")),
            )
        ].append(job)

    duplicate_count = 0
    for group in groups.values():
        if len(group) < 2:
            continue
        ordered = sorted(
            group,
            key=lambda job: (
                bool(job.get("is_watchlist")),
                float(job.get("discovery_score") or 0),
                bool(job.get("application_url")),
            ),
            reverse=True,
        )
        canonical: list[dict] = []
        for job in ordered:
            text = _normalized(
                job.get("full_description") or job.get("description")
            )[:6000]
            duplicate_of = None
            for candidate in canonical:
                candidate_text = _normalized(
                    candidate.get("full_description")
                    or candidate.get("description")
                )[:6000]
                if text and candidate_text and SequenceMatcher(
                    None, text, candidate_text
                ).ratio() >= 0.9:
                    duplicate_of = candidate["url"]
                    break
            if duplicate_of:
                conn.execute(
                    "UPDATE jobs SET duplicate_of = ? WHERE url = ?",
                    (duplicate_of, job["url"]),
                )
                duplicate_count += 1
            else:
                canonical.append(job)
    conn.commit()
    return {
        "eligible": eligible,
        "rejected": rejected,
        "duplicates": duplicate_count,
    }


# ── Scoring Prompt ────────────────────────────────────────────────────────

SCORE_PROMPT = """You are a job fit evaluator. Given a candidate's resume and a job description, score how well the candidate fits the role.

SCORING CRITERIA:
- 9-10: Perfect match. Candidate has direct experience in nearly all required skills and qualifications.
- 7-8: Strong match. Candidate has most required skills, minor gaps easily bridged.
- 5-6: Moderate match. Candidate has some relevant skills but missing key requirements.
- 3-4: Weak match. Significant skill gaps, would need substantial ramp-up.
- 1-2: Poor match. Completely different field or experience level.

IMPORTANT FACTORS:
- Weight technical skills heavily (programming languages, frameworks, tools)
- Consider transferable experience (automation, scripting, API work)
- Factor in the candidate's project experience
- Be realistic about experience level vs. job requirements (years of experience, seniority)

RESPOND IN EXACTLY THIS FORMAT (no other text):
SCORE: [1-10]
KEYWORDS: [comma-separated ATS keywords from the job description that match or could match the candidate]
REASONING: [2-3 sentences explaining the score]"""


def _parse_score_response(response: str) -> dict:
    """Parse the LLM's score response into structured data.

    Args:
        response: Raw LLM response text.

    Returns:
        {"score": int, "keywords": str, "reasoning": str}
    """
    score = 0
    keywords = ""
    reasoning = response

    for line in response.split("\n"):
        line = line.strip()
        if line.startswith("SCORE:"):
            try:
                score = int(re.search(r"\d+", line).group())
                score = max(1, min(10, score))
            except (AttributeError, ValueError):
                score = 0
        elif line.startswith("KEYWORDS:"):
            keywords = line.replace("KEYWORDS:", "").strip()
        elif line.startswith("REASONING:"):
            reasoning = line.replace("REASONING:", "").strip()

    return {"score": score, "keywords": keywords, "reasoning": reasoning}


def score_job(resume_text: str, job: dict) -> dict:
    """Score a single job against the resume.

    Args:
        resume_text: The candidate's full resume text.
        job: Job dict with keys: title, site, location, full_description.

    Returns:
        {"score": int, "keywords": str, "reasoning": str}
    """
    job_text = (
        f"TITLE: {job['title']}\n"
        f"COMPANY: {job['site']}\n"
        f"LOCATION: {job.get('location', 'N/A')}\n\n"
        f"DESCRIPTION:\n{(job.get('full_description') or '')[:6000]}"
    )

    messages = [
        {"role": "system", "content": SCORE_PROMPT},
        {"role": "user", "content": f"RESUME:\n{resume_text}\n\n---\n\nJOB POSTING:\n{job_text}"},
    ]

    try:
        client = get_client()
        response = client.chat(messages, max_tokens=512, temperature=0.2)
        return _parse_score_response(response)
    except Exception as e:
        log.error("LLM error scoring job '%s': %s", job.get("title", "?"), e)
        return {"score": 0, "keywords": "", "reasoning": f"LLM error: {e}"}


def run_scoring(limit: int = 0, rescore: bool = False) -> dict:
    """Score unscored jobs that have full descriptions.

    Args:
        limit: Maximum number of jobs to score in this run.
        rescore: If True, re-score all jobs (not just unscored ones).

    Returns:
        {"scored": int, "errors": int, "elapsed": float, "distribution": list}
    """
    resume_text = RESUME_PATH.read_text(encoding="utf-8")
    conn = get_connection()
    search_cfg = config.load_search_config()
    audit = audit_scoring_candidates(conn, search_cfg)
    log.info(
        "Eligibility audit: %d eligible, %d rejected, %d duplicates.",
        audit["eligible"],
        audit["rejected"],
        audit["duplicates"],
    )

    if rescore:
        query = """
            SELECT * FROM jobs
            WHERE full_description IS NOT NULL
              AND eligibility_allowed = 1
              AND duplicate_of IS NULL
        """
        if limit > 0:
            query += f" LIMIT {limit}"
        jobs = conn.execute(query).fetchall()
    else:
        scoring_cfg = search_cfg.get("scoring", {})
        min_discovery_score = float(scoring_cfg.get("min_discovery_score", 5))
        shortlist_limit = limit or int(scoring_cfg.get("shortlist_limit", 100))
        jobs = conn.execute(
            """
            SELECT * FROM jobs
            WHERE full_description IS NOT NULL
              AND fit_score IS NULL
              AND eligibility_allowed = 1
              AND duplicate_of IS NULL
              AND (is_watchlist = 1 OR COALESCE(discovery_score, 0) >= ?)
            ORDER BY is_watchlist DESC, discovery_score DESC, discovered_at DESC
            LIMIT ?
            """,
            (min_discovery_score, shortlist_limit),
        ).fetchall()
        pending_total = conn.execute(
            """
            SELECT COUNT(*) FROM jobs
            WHERE full_description IS NOT NULL AND fit_score IS NULL
            """
        ).fetchone()[0]
        if pending_total > len(jobs):
            log.info(
                "Shortlisted %d/%d pending jobs (rank >= %.1f or watchlist).",
                len(jobs),
                pending_total,
                min_discovery_score,
            )

    if not jobs:
        log.info("No unscored jobs with descriptions found.")
        return {"scored": 0, "errors": 0, "elapsed": 0.0, "distribution": []}

    # Convert sqlite3.Row to dicts if needed
    if jobs and not isinstance(jobs[0], dict):
        columns = jobs[0].keys()
        jobs = [dict(zip(columns, row)) for row in jobs]

    log.info("Scoring %d jobs sequentially...", len(jobs))
    t0 = time.time()
    completed = 0
    errors = 0
    results: list[dict] = []

    for job in jobs:
        result = score_job(resume_text, job)
        result["url"] = job["url"]
        completed += 1

        if result["score"] == 0:
            errors += 1

        results.append(result)

        log.info(
            "[%d/%d] score=%d  %s",
            completed, len(jobs), result["score"], job.get("title", "?")[:60],
        )

    # Write scores to DB
    now = datetime.now(timezone.utc).isoformat()
    for r in results:
        conn.execute(
            "UPDATE jobs SET fit_score = ?, score_reasoning = ?, scored_at = ? WHERE url = ?",
            (r["score"], f"{r['keywords']}\n{r['reasoning']}", now, r["url"]),
        )
    conn.commit()

    elapsed = time.time() - t0
    log.info("Done: %d scored in %.1fs (%.1f jobs/sec)", len(results), elapsed, len(results) / elapsed if elapsed > 0 else 0)

    # Score distribution
    dist = conn.execute("""
        SELECT fit_score, COUNT(*) FROM jobs
        WHERE fit_score IS NOT NULL
        GROUP BY fit_score ORDER BY fit_score DESC
    """).fetchall()
    distribution = [(row[0], row[1]) for row in dist]

    return {
        "scored": len(results),
        "errors": errors,
        "elapsed": elapsed,
        "distribution": distribution,
    }
