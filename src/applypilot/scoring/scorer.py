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
from applypilot.scoring import baml_adapter

log = logging.getLogger(__name__)


def _normalized(value: str | None) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", (value or "").casefold()))


def _has_explicit_geography(location: str | None) -> bool:
    normalized = _normalized(location)
    generic = {"", "remote", "worldwide", "anywhere", "distributed"}
    return normalized not in generic


def _canonical_role_title(title: str | None) -> str:
    """Remove ATS country variants while preserving the actual role title."""
    value = (title or "").replace("\xa0", " ").strip()
    match = re.match(
        r"^(.*?)\s*\|\s*([^|]+?)\s*\|\s*remote\s*$",
        value,
        re.IGNORECASE,
    )
    if not match:
        return value
    location = _normalized(match.group(2))
    country_suffixes = {
        "austria", "belgium", "czech republic", "denmark", "finland",
        "france", "germany", "greece", "ireland", "italy", "netherlands",
        "norway", "poland", "portugal", "republic of ireland", "spain",
        "sweden", "switzerland", "united kingdom", "uk", "europe",
    }
    return match.group(1).strip() if location in country_suffixes else value


def _title_is_preferred(title: str | None, scoring_cfg: dict) -> bool:
    normalized = _normalized(title)
    phrases = scoring_cfg.get(
        "preferred_title_phrases",
        [
            "backend",
            "python",
            "full stack",
            "fullstack",
            "software engineer",
            "software developer",
            "product engineer",
            "platform engineer",
            "infrastructure engineer",
            "site reliability engineer",
            "devops engineer",
            "technical lead",
            "software architect",
        ],
    )
    return any(_normalized(phrase) in normalized for phrase in phrases if phrase)


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

    relocation_eligible = search_cfg.get("relocation_eligible", True)
    for job in rows:
        decision = evaluate_location(
            job.get("location"),
            accept,
            reject,
            job.get("full_description") or job.get("description"),
            explicit_geography=_has_explicit_geography(job.get("location")),
            relocation_eligible=relocation_eligible,
        )
        conn.execute(
            """
            UPDATE jobs
            SET eligibility_allowed = ?, eligibility_reason = ?,
                eligibility_audited_at = ?, duplicate_of = NULL,
                scoring_eligible = 0, scoring_eligibility_reason = ?
            WHERE url = ?
            """,
            (
                int(decision.allowed),
                decision.reason,
                now,
                decision.reason if not decision.allowed else "pending_audit",
                job["url"],
            ),
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
                _normalized(_canonical_role_title(job.get("title"))),
            )
        ].append(job)

    duplicate_count = 0
    for group in groups.values():
        if len(group) < 2:
            continue
        ordered = sorted(
            group,
            key=lambda job: (
                job.get("fit_score") is not None,
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

    scoring_cfg = search_cfg.get("scoring", {})
    threshold = float(scoring_cfg.get("min_discovery_score", 5))
    refreshed = [dict(row) for row in conn.execute("SELECT * FROM jobs").fetchall()]
    candidate_count = 0
    for job in refreshed:
        if not job.get("eligibility_allowed"):
            allowed = False
            reason = job.get("eligibility_reason") or "geography_rejected"
        elif job.get("duplicate_of"):
            allowed = False
            reason = "duplicate_posting"
        elif job.get("is_watchlist"):
            allowed = True
            reason = "watchlist"
        elif float(job.get("discovery_score") or 0) < threshold:
            allowed = False
            reason = "rank_below_threshold"
        elif not _title_is_preferred(job.get("title"), scoring_cfg):
            allowed = False
            reason = "title_not_preferred"
        else:
            allowed = True
            reason = "preferred_title"
        conn.execute(
            """
            UPDATE jobs
            SET scoring_eligible = ?, scoring_eligibility_reason = ?
            WHERE url = ?
            """,
            (int(allowed), reason, job["url"]),
        )
        candidate_count += int(allowed)
    conn.execute(
        """
        UPDATE jobs
        SET fit_score = (
                SELECT canonical.fit_score FROM jobs AS canonical
                WHERE canonical.url = jobs.duplicate_of
            ),
            score_reasoning = (
                SELECT canonical.score_reasoning FROM jobs AS canonical
                WHERE canonical.url = jobs.duplicate_of
            ),
            scored_at = (
                SELECT canonical.scored_at FROM jobs AS canonical
                WHERE canonical.url = jobs.duplicate_of
            )
        WHERE duplicate_of IS NOT NULL
          AND EXISTS (
              SELECT 1 FROM jobs AS canonical
              WHERE canonical.url = jobs.duplicate_of
                AND canonical.fit_score IS NOT NULL
          )
        """
    )
    conn.execute(
        """
        UPDATE jobs AS canonical
        SET is_shortlisted = 1,
            shortlisted_at = COALESCE(
                canonical.shortlisted_at,
                (
                    SELECT MIN(duplicate.shortlisted_at)
                    FROM jobs AS duplicate
                    WHERE duplicate.duplicate_of = canonical.url
                      AND duplicate.is_shortlisted = 1
                )
            )
        WHERE EXISTS (
            SELECT 1 FROM jobs AS duplicate
            WHERE duplicate.duplicate_of = canonical.url
              AND duplicate.is_shortlisted = 1
        )
        """
    )
    conn.execute(
        """
        UPDATE jobs
        SET is_shortlisted = 0, shortlisted_at = NULL
        WHERE duplicate_of IS NOT NULL AND is_shortlisted = 1
        """
    )
    conn.commit()
    return {
        "eligible": eligible,
        "rejected": rejected,
        "duplicates": duplicate_count,
        "scoring_candidates": candidate_count,
    }


# ── Scoring Prompt ────────────────────────────────────────────────────────

# Criteria shared between the direct and BAML paths.
_SCORE_CRITERIA = """You are a job fit evaluator. Given a candidate's resume and a job description, score how well the candidate fits the role.

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
- If the job's primary required tech stack is Java, Kotlin, PHP, C#, .NET, SAP, or ABAP, reduce the score by 2-3 points -- the candidate's strengths are in Python/Ruby/Elixir/Go/Rust/TypeScript and a role centered on these languages is a fundamental mismatch. Do not apply this penalty if they appear only as secondary tools or nice-to-haves."""

# Full prompt for the direct (non-BAML) path — includes explicit text format.
SCORE_PROMPT = _SCORE_CRITERIA + """

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
                match = re.search(r"\d+", line)
                if match:
                    score = max(1, min(10, int(match.group())))
            except ValueError:
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

    try:
        if baml_adapter.enabled():
            return baml_adapter.score_job(_SCORE_CRITERIA, resume_text, job_text)

        messages = [
            {"role": "system", "content": SCORE_PROMPT},
            {"role": "user", "content": f"RESUME:\n{resume_text}\n\n---\n\nJOB POSTING:\n{job_text}"},
        ]
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
              AND scoring_eligible = 1
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
              AND scoring_eligible = 1
            ORDER BY is_watchlist DESC, discovery_score DESC, discovered_at DESC
            LIMIT ?
            """,
            (shortlist_limit,),
        ).fetchall()
        pending_total = conn.execute(
            """
            SELECT COUNT(*) FROM jobs
            WHERE full_description IS NOT NULL AND fit_score IS NULL
              AND scoring_eligible = 1
            """
        ).fetchone()[0]
        if pending_total > len(jobs):
            log.info(
                "Shortlisted %d/%d eligible canonical jobs "
                "(preferred title at rank >= %.1f or watchlist).",
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
        reasoning = f"{r['keywords']}\n{r['reasoning']}"
        conn.execute(
            "UPDATE jobs SET fit_score = ?, score_reasoning = ?, scored_at = ? WHERE url = ?",
            (r["score"], reasoning, now, r["url"]),
        )
        conn.execute(
            """
            UPDATE jobs
            SET fit_score = ?, score_reasoning = ?, scored_at = ?
            WHERE duplicate_of = ?
            """,
            (r["score"], reasoning, now, r["url"]),
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
