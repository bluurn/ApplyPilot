"""Optional BAML backend for the typed tailoring boundary.

The generated client is deliberately optional while the integration is being
validated. Set ``APPLYPILOT_TAILOR_BACKEND=baml`` after running
``baml-cli generate --from baml_src`` to use it; otherwise the existing client
path remains the fallback.
"""

import os
from typing import Any


def enabled() -> bool:
    return os.getenv("APPLYPILOT_TAILOR_BACKEND", "openai").lower() == "baml"


def rewrite(
    original_resume: str,
    target_job: str,
    fixed_experience: str,
    fixed_skills: str,
) -> dict[str, Any]:
    """Call the generated BAML client and return a plain draft mapping."""
    from .generated_baml.baml_client.sync_client import b

    result = b.RewriteTailoredResume(
        original_resume,
        target_job,
        fixed_experience,
        fixed_skills,
    )
    return result.model_dump()
