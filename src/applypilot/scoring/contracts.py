"""Typed contracts for model-produced tailoring drafts.

This module is intentionally runtime-light. It defines the boundary that a
future BAML client will implement, while keeping final factual validation and
resume assembly in Python.
"""

from typing import NotRequired, TypedDict


class ExperienceDraft(TypedDict):
    header: str
    subtitle: NotRequired[str]
    bullets: list[str]


class ProjectDraft(TypedDict):
    header: str
    subtitle: NotRequired[str]
    bullets: list[str]


class TailoredDraft(TypedDict):
    title: str
    summary: str
    skills: dict[str, str]
    experience: list[ExperienceDraft]
    projects: list[ProjectDraft]
    education: str


def is_tailored_draft(value: object) -> bool:
    """Return whether a parsed model response has the expected outer shape."""
    if not isinstance(value, dict):
        return False
    required = {"title", "summary", "skills", "experience", "projects", "education"}
    return required.issubset(value) and isinstance(value["skills"], dict) and isinstance(
        value["experience"], list
    ) and isinstance(value["projects"], list)
