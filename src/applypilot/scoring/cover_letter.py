"""Cover letter generation: LLM-powered, profile-driven, with validation.

Generates concise, engineering-voice cover letters tailored to specific job
postings. All personal data (name, skills, achievements) comes from the user's
profile at runtime. No hardcoded personal information.
"""

import logging
import re
import time
from datetime import datetime, timezone

from applypilot.config import COVER_LETTER_DIR, RESUME_PATH, load_profile
from applypilot.database import get_connection
from applypilot.llm import get_client
from applypilot.scoring import baml_adapter
from applypilot.scoring.validator import (
    BANNED_WORDS,
    LLM_LEAK_PHRASES,
    sanitize_text,
    validate_cover_letter,
)

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 5  # max cross-run retries before giving up

_LANG_NAMES: dict[str, str] = {
    "de": "German", "fr": "French", "es": "Spanish",
    "nl": "Dutch", "pl": "Polish", "it": "Italian", "pt": "Portuguese",
}


# ── Language Detection ────────────────────────────────────────────────────

def _detect_language(text: str) -> str:
    """Detect the language of a job posting via a cheap single-shot LLM call.

    Returns an ISO 639-1 code ("en", "de", "fr", ...). Falls back to "en" on
    any error or ambiguous result.
    """
    if not text:
        return "en"
    client = get_client()
    try:
        result = client.chat([
            {"role": "user", "content": (
                "What language is this text written in? "
                "Reply with only the ISO 639-1 code (e.g. 'en', 'de', 'fr'):\n\n"
                + text[:800]
            )},
        ], max_tokens=5, temperature=0.0)
        code = re.sub(r"[^a-z]", "", result.strip().lower())[:2]
        return code if len(code) == 2 else "en"
    except Exception:
        return "en"


# ── Prompt Builder (profile-driven) ──────────────────────────────────────

def _build_cover_letter_prompt(profile: dict, lang: str = "en") -> str:
    """Build the cover letter system prompt from the user's profile.

    All personal data, skills, and sign-off name come from the profile.
    Pass lang (ISO 639-1) to generate a non-English letter when the job
    posting is in another language.
    """
    personal = profile.get("personal", {})
    boundary = profile.get("skills_boundary", {})
    resume_facts = profile.get("resume_facts", {})

    # Use the legal/full name for application documents. A profile nickname is
    # useful for handles and URLs, but should never leak into a signature.
    sign_off_name = personal.get("full_name") or personal.get("preferred_name", "")

    # Flatten all allowed skills
    all_skills: list[str] = []
    for items in boundary.values():
        if isinstance(items, list):
            all_skills.extend(items)
    skills_str = ", ".join(all_skills) if all_skills else "the tools listed in the resume"

    # Real metrics from resume_facts
    real_metrics = resume_facts.get("real_metrics", [])
    preserved_projects = resume_facts.get("preserved_projects", [])

    # Build achievement examples for the prompt
    projects_hint = ""
    if preserved_projects:
        projects_hint = f"\nKnown projects to reference: {', '.join(preserved_projects)}"

    metrics_hint = ""
    if real_metrics:
        metrics_hint = f"\nReal metrics to use: {', '.join(real_metrics)}"

    # Build the full banned list from the validator so the prompt stays in sync
    # with what will actually be rejected -- the validator checks all of these.
    # For non-English letters the banned word check is skipped, but keep the list
    # in the prompt as a quality guide anyway.
    all_banned = ", ".join(f'"{w}"' for w in BANNED_WORDS)
    leak_banned = ", ".join(f'"{p}"' for p in LLM_LEAK_PHRASES)

    lang_name = _LANG_NAMES.get(lang, "English") if lang != "en" else "English"
    word_limit = "300" if lang != "en" else "250"

    if lang == "en":
        greeting_instruction = 'Start DIRECTLY with "Dear Hiring Manager," and end with the full name.'
        signoff_block = f"Close with exactly these two lines, after a blank line:\nBest regards,\n{sign_off_name}"
        language_block = ""
    else:
        greeting_instruction = (
            f'Start DIRECTLY with the appropriate formal {lang_name} greeting '
            f'(e.g. for German: "Sehr geehrte Damen und Herren,"). End with the full name.'
        )
        signoff_block = (
            f"Close with a professional {lang_name} sign-off followed by a blank line and the full name:\n"
            f"{sign_off_name}"
        )
        language_block = (
            f"\n\nLANGUAGE: This job posting is in {lang_name}. Write the ENTIRE cover letter in {lang_name}. "
            f"Use {lang_name} professional conventions for greeting, phrasing, and sign-off. "
            "Do not mix languages."
        )

    return f"""Write a cover letter for {sign_off_name}. The goal is to get an interview.

STRUCTURE: 3 short paragraphs. Under {word_limit} words. Every sentence must earn its place.

PARAGRAPH 1 (3-4 sentences): After the greeting, briefly introduce yourself and name the role you are applying for. Add one specific reason the company's product or problem is relevant to your background, then connect it to a concrete thing YOU built that solves THEIR problem. Avoid generic openings such as "I'm excited about this role" or "This role aligns with my experience."

PARAGRAPH 2 (3-4 sentences): Pick 2 achievements from the resume that are MOST relevant to THIS job. Use numbers ONLY if they appear verbatim in the resume -- do NOT invent percentages, ratios, or quantities (e.g. never write "30% reduction" unless that exact figure is in the resume). Frame as solving their problem, not listing your accomplishments.{projects_hint}{metrics_hint}

PARAGRAPH 3 (1-2 sentences): One specific detail taken VERBATIM or closely paraphrased from the job description provided below -- a named product, a stated technical challenge, or a team detail explicitly mentioned. Do NOT draw on your training-data knowledge of the company; if it is not in the job description text, do not write it.

BANNED WORDS AND PHRASES (do not use even once):
{all_banned}

ALSO BANNED (meta-commentary):
{leak_banned}

BANNED PUNCTUATION: No em dashes (--) or en dashes. Use commas or periods.

VOICE:
- Write like a real engineer emailing someone they respect. Not formal, not casual. Just direct.
- NEVER narrate or explain what you're doing. BAD: "This demonstrates my commitment to X." GOOD: Just state the fact and move on.
- NEVER hedge. BAD: "might address some of your challenges." GOOD: "solves the same problem your team is facing."
- Every sentence should contain either a number, a tool name, or a specific outcome. If it doesn't, cut it.

FABRICATION = INSTANT REJECTION:
The candidate's real tools are ONLY: {skills_str}.
Do NOT mention ANY tool not in this list. If the job asks for tools not listed, talk about the work you did, not the tools.
Do NOT invent any numbers, percentages, or metrics that are not explicitly stated in the resume. If the resume says "led a team of five", you may use "five". If no metric exists, describe the outcome qualitatively.

{signoff_block}

Output ONLY the letter text. No subject lines. No "Here is the cover letter:" preamble. No notes after the sign-off.
{greeting_instruction}{language_block}"""


# ── Helpers ──────────────────────────────────────────────────────────────

def _strip_preamble(text: str) -> str:
    """Remove LLM preamble before 'Dear Hiring Manager,' if present.

    Gemini and other models sometimes output "Here is the cover letter:" or
    similar meta-commentary before the actual letter text. Strip everything
    before the first occurrence of "Dear" so the validator's start-check passes.
    """
    dear_idx = text.lower().find("dear")
    if dear_idx > 0:
        return text[dear_idx:]
    return text


def _ensure_signoff(text: str, profile: dict, lang: str = "en") -> str:
    """Normalize the closing sign-off.

    For English letters, enforces "Best regards,\n{name}".
    For non-English letters, trusts the LLM's sign-off phrase and only ensures
    the candidate's name appears on the final line.
    """
    personal = profile.get("personal", {})
    full_name = personal.get("full_name") or personal.get("preferred_name", "")
    if not full_name:
        return text.rstrip()

    lines = text.rstrip().splitlines()
    # Remove duplicate name line at the end (LLM sometimes repeats it)
    if lines and lines[-1].strip().casefold() in {
        full_name.casefold(),
        str(personal.get("preferred_name", "")).casefold(),
    }:
        lines.pop()

    if lang == "en":
        # Strip any English sign-off phrase and replace with the canonical form
        if lines and lines[-1].strip().rstrip(",:").casefold() in {
            "best regards",
            "kind regards",
            "regards",
            "sincerely",
            "yours sincerely",
        }:
            lines.pop()
        body = "\n".join(lines).rstrip()
        return f"{body}\n\nBest regards,\n{full_name}"
    else:
        # Trust the LLM's language-appropriate sign-off; just ensure name is at end
        body = "\n".join(lines).rstrip()
        return f"{body}\n{full_name}"


# ── Core Generation ──────────────────────────────────────────────────────

def generate_cover_letter(
    resume_text: str, job: dict, profile: dict,
    max_retries: int = 3, validation_mode: str = "normal",
) -> str:
    """Generate a cover letter with fresh context on each retry + auto-sanitize.

    Same design as tailor_resume: fresh conversation per attempt, issues noted
    in the prompt, no conversation history stacking.

    Args:
        resume_text:      The candidate's resume text (base or tailored).
        job:              Job dict with title, site, location, full_description.
        profile:          User profile dict.
        max_retries:      Maximum retry attempts.
        validation_mode:  "strict", "normal", or "lenient".

    Returns:
        The cover letter text (best attempt even if validation failed).
    """
    job_text = (
        f"TITLE: {job['title']}\n"
        f"COMPANY: {job['site']}\n"
        f"LOCATION: {job.get('location', 'N/A')}\n\n"
        f"DESCRIPTION:\n{(job.get('full_description') or '')[:6000]}"
    )

    # Detect language once before the retry loop (cheap single-shot call)
    lang = _detect_language(job.get("full_description", ""))
    if lang != "en":
        log.info("Job posting detected as %s -- generating cover letter in %s",
                 lang, _LANG_NAMES.get(lang, lang))

    avoid_notes: list[str] = []
    letter = ""
    client = get_client()
    cl_prompt_base = _build_cover_letter_prompt(profile, lang=lang)

    for attempt in range(max_retries + 1):
        # Fresh conversation every attempt
        prompt = cl_prompt_base
        if avoid_notes:
            prompt += "\n\n## AVOID THESE ISSUES:\n" + "\n".join(
                f"- {n}" for n in avoid_notes[-5:]
            )

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": (
                f"RESUME:\n{resume_text}\n\n---\n\n"
                f"TARGET JOB:\n{job_text}\n\n"
                "Write the cover letter:"
            )},
        ]

        if baml_adapter.enabled():
            try:
                letter = baml_adapter.generate_cover_letter(prompt, resume_text, job_text)
            except Exception as exc:
                log.warning("BAML cover letter unavailable; falling back to direct client: %s", exc)
                letter = client.chat(messages, max_tokens=1024, temperature=0.7)
        else:
            letter = client.chat(messages, max_tokens=1024, temperature=0.7)
        letter = sanitize_text(letter)  # auto-fix em dashes, smart quotes
        if lang == "en":
            letter = _strip_preamble(letter)  # only relevant for English "Dear" check
        letter = _ensure_signoff(letter, profile, lang=lang)

        validation = validate_cover_letter(letter, mode=validation_mode, lang=lang,
                                           job_text=job_text)
        if validation["passed"]:
            return letter

        avoid_notes.extend(validation["errors"])
        # Warnings never block — only hard errors trigger a retry
        log.debug(
            "Cover letter attempt %d/%d failed: %s",
            attempt + 1, max_retries + 1, validation["errors"],
        )

    return letter  # last attempt even if failed


# ── Batch Entry Point ────────────────────────────────────────────────────

def run_cover_letters(min_score: int = 7, limit: int = 20,
                      validation_mode: str = "normal") -> dict:
    """Generate cover letters for high-scoring jobs that have tailored resumes.

    Args:
        min_score:       Minimum fit_score threshold.
        limit:           Maximum jobs to process.
        validation_mode: "strict", "normal", or "lenient".

    Returns:
        {"generated": int, "errors": int, "elapsed": float}
    """
    profile = load_profile()
    resume_text = RESUME_PATH.read_text(encoding="utf-8")
    conn = get_connection()

    # Fetch jobs that have tailored resumes but no cover letter yet
    jobs = conn.execute(
        "SELECT * FROM jobs "
        "WHERE fit_score >= ? AND tailored_resume_path IS NOT NULL "
        "AND full_description IS NOT NULL "
        "AND (cover_letter_path IS NULL OR cover_letter_path = '') "
        "AND COALESCE(cover_attempts, 0) < ? "
        "ORDER BY fit_score DESC LIMIT ?",
        (min_score, MAX_ATTEMPTS, limit),
    ).fetchall()

    if not jobs:
        log.info("No jobs needing cover letters (score >= %d).", min_score)
        return {"generated": 0, "errors": 0, "elapsed": 0.0}

    # Convert rows to dicts
    if jobs and not isinstance(jobs[0], dict):
        columns = jobs[0].keys()
        jobs = [dict(zip(columns, row)) for row in jobs]

    COVER_LETTER_DIR.mkdir(parents=True, exist_ok=True)
    log.info(
        "Generating cover letters for %d jobs (score >= %d)...",
        len(jobs), min_score,
    )
    t0 = time.time()
    completed = 0
    results: list[dict] = []
    error_count = 0

    from applypilot import cancel
    for job in jobs:
        if cancel.is_set():
            log.info("Cancellation requested, stopping cover stage")
            break
        completed += 1
        try:
            letter = generate_cover_letter(resume_text, job, profile,
                                          validation_mode=validation_mode)

            # Build per-job subfolder with clean recruiter-visible filenames
            personal = profile.get("personal", {})
            full_name = personal.get("full_name") or personal.get("preferred_name", "")
            name_slug = re.sub(r"\s+", "_", full_name).strip() if full_name else "Cover_Letter"

            safe_title = re.sub(r"[^\w\s-]", "", job["title"])[:50].strip().replace(" ", "_")
            safe_site = re.sub(r"[^\w\s-]", "", job["site"])[:20].strip().replace(" ", "_")
            subfolder = COVER_LETTER_DIR / f"{safe_site}_{safe_title}"
            subfolder.mkdir(parents=True, exist_ok=True)

            cl_path = subfolder / f"{name_slug}_Cover_Letter.txt"
            cl_path.write_text(letter, encoding="utf-8")

            # Generate PDF (best-effort)
            pdf_path = None
            try:
                from applypilot.scoring.pdf import convert_to_pdf
                pdf_path = str(convert_to_pdf(cl_path))
            except Exception:
                log.debug("PDF generation failed for %s", cl_path, exc_info=True)

            result = {
                "url": job["url"],
                "path": str(cl_path),
                "pdf_path": pdf_path,
                "title": job["title"],
                "site": job["site"],
            }
            results.append(result)

            elapsed = time.time() - t0
            rate = completed / elapsed if elapsed > 0 else 0
            log.info(
                "%d/%d [OK] | %.1f jobs/min | %s",
                completed, len(jobs), rate * 60, result["title"][:40],
            )
        except Exception as e:
            result = {
                "url": job["url"], "title": job["title"], "site": job["site"],
                "path": None, "pdf_path": None, "error": str(e),
            }
            error_count += 1
            results.append(result)
            log.error("%d/%d [ERROR] %s -- %s", completed, len(jobs), job["title"][:40], e)

    # Persist to DB: increment attempt counter for ALL, save path only for successes
    now = datetime.now(timezone.utc).isoformat()
    saved = 0
    for r in results:
        if r.get("path"):
            conn.execute(
                "UPDATE jobs SET cover_letter_path=?, cover_letter_at=?, "
                "cover_attempts=COALESCE(cover_attempts,0)+1 WHERE url=?",
                (r["path"], now, r["url"]),
            )
            saved += 1
        else:
            conn.execute(
                "UPDATE jobs SET cover_attempts=COALESCE(cover_attempts,0)+1 WHERE url=?",
                (r["url"],),
            )
    conn.commit()

    elapsed = time.time() - t0
    log.info("Cover letters done in %.1fs: %d generated, %d errors", elapsed, saved, error_count)

    return {
        "generated": saved,
        "errors": error_count,
        "elapsed": elapsed,
    }
