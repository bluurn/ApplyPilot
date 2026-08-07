"""BAML backend adapter for all LLM call sites.

Set APPLYPILOT_TAILOR_BACKEND=baml to activate. Falls back to the direct
LLMClient path automatically if BAML is unavailable or raises an error.

Provider detection mirrors llm.py: reads GEMINI_API_KEY / OPENAI_API_KEY /
LLM_URL and sets BAML_BASE_URL, BAML_API_KEY, BAML_MODEL before each call
so the generated BAML clients pick up the right endpoint.
"""

import os
from typing import Any


def enabled() -> bool:
    return os.getenv("APPLYPILOT_TAILOR_BACKEND", "").lower() == "baml"


def _setup_env() -> None:
    """Populate BAML_* env vars from the same provider env vars as llm.py."""
    gemini_key = os.environ.get("GEMINI_API_KEY", "")
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    local_url = os.environ.get("LLM_URL", "")
    model_override = os.environ.get("LLM_MODEL", "")

    if gemini_key and not local_url:
        os.environ.setdefault("BAML_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai")
        os.environ.setdefault("BAML_API_KEY", gemini_key)
        os.environ.setdefault("BAML_MODEL", model_override or "gemini-2.0-flash")
    elif openai_key and not local_url:
        os.environ.setdefault("BAML_BASE_URL", "https://api.openai.com/v1")
        os.environ.setdefault("BAML_API_KEY", openai_key)
        os.environ.setdefault("BAML_MODEL", model_override or "gpt-4o-mini")
    elif local_url:
        os.environ.setdefault("BAML_BASE_URL", local_url.rstrip("/"))
        os.environ.setdefault("BAML_API_KEY", os.environ.get("LLM_API_KEY", "local"))
        os.environ.setdefault("BAML_MODEL", model_override or "local-model")


def _b():
    from .generated_baml.baml_client.sync_client import b
    _setup_env()
    return b


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def score_job(system_prompt: str, resume: str, job: str) -> dict[str, Any]:
    result = _b().ScoreJob(system_prompt, resume, job)
    d = result.model_dump()
    d["score"] = max(1, min(10, int(d.get("score") or 0)))
    return d


def judge_tailored_resume(
    system_prompt: str,
    job_title: str,
    original: str,
    tailored: str,
) -> dict[str, Any]:
    result = _b().JudgeTailoredResume(system_prompt, job_title, original, tailored)
    return result.model_dump()


# ---------------------------------------------------------------------------
# Tailoring
# ---------------------------------------------------------------------------

def rewrite_tailored_resume(system_prompt: str, resume: str, job: str) -> dict[str, Any]:
    result = _b().RewriteTailoredResume(system_prompt, resume, job)
    return result.model_dump()


# ---------------------------------------------------------------------------
# Cover letter
# ---------------------------------------------------------------------------

def generate_cover_letter(system_prompt: str, resume: str, job: str) -> str:
    return _b().GenerateCoverLetter(system_prompt, resume, job)


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def select_strategy(system_prompt: str, briefing: str) -> dict[str, Any]:
    result = _b().SelectStrategy(system_prompt, briefing)
    return result.model_dump()


def generate_selectors(system_prompt: str, page_html: str) -> dict[str, Any]:
    result = _b().GenerateSelectors(system_prompt, page_html)
    return result.model_dump()


def judge_api_response(system_prompt: str, api_summary: str) -> dict[str, Any]:
    result = _b().JudgeApiResponse(system_prompt, api_summary)
    return result.model_dump()


# ---------------------------------------------------------------------------
# Enrichment
# ---------------------------------------------------------------------------

def extract_detail(system_prompt: str, content: str) -> dict[str, Any]:
    result = _b().ExtractDetail(system_prompt, content)
    return result.model_dump()
