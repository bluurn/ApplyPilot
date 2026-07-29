"""Shared configurable filters for discovered jobs."""

import re


def title_is_excluded(title: str | None, patterns: list[str]) -> bool:
    """Return whether a title contains a configured exclusion pattern."""
    if not title:
        return False
    normalized = title.casefold()
    return any(pattern.casefold() in normalized for pattern in patterns if pattern)


def title_matches_queries(title: str | None, queries: list[str]) -> bool:
    """Match query terms in any order while ignoring seniority qualifiers."""
    if not title or not queries:
        return False

    ignored = {"mid", "senior", "staff", "lead"}
    title_terms = set(re.findall(r"[a-z0-9]+", title.casefold()))
    for query in queries:
        query_terms = {
            term
            for term in re.findall(r"[a-z0-9]+", query.casefold())
            if term not in ignored
        }
        if query_terms and query_terms <= title_terms:
            return True
    return False


def location_is_allowed(
    location: str | None,
    accept: list[str],
    reject_non_remote: list[str],
) -> bool:
    """Apply the shared explicit location policy used by discovery sources."""
    if not location:
        return True

    normalized = location.casefold()
    remote_markers = ("remote", "anywhere", "work from home", "wfh", "distributed")
    if any(marker in normalized for marker in remote_markers):
        return True
    if any(pattern.casefold() in normalized for pattern in reject_non_remote):
        return False
    return any(pattern.casefold() in normalized for pattern in accept)
