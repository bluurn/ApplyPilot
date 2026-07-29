"""Shared configurable filters for discovered jobs."""


def title_is_excluded(title: str | None, patterns: list[str]) -> bool:
    """Return whether a title contains a configured exclusion pattern."""
    if not title:
        return False
    normalized = title.casefold()
    return any(pattern.casefold() in normalized for pattern in patterns if pattern)
