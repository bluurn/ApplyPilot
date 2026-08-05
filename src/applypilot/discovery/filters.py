"""Shared configurable filters for discovered jobs."""

import re
from typing import NamedTuple


class LocationDecision(NamedTuple):
    """An inspectable discovery eligibility decision."""

    allowed: bool
    reason: str


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


def _contains_pattern(value: str, pattern: str) -> bool:
    """Match configured phrases without short-token substring false positives."""
    normalized_pattern = pattern.casefold().strip()
    if not normalized_pattern:
        return False
    if len(normalized_pattern) <= 3 and normalized_pattern.isalnum():
        return bool(
            re.search(
                rf"(?<![a-z0-9]){re.escape(normalized_pattern)}(?![a-z0-9])",
                value,
            )
        )
    return normalized_pattern in value


def evaluate_location(
    location: str | None,
    accept: list[str],
    reject_non_remote: list[str],
    context: str | None = None,
    explicit_geography: bool = False,
    relocation_eligible: bool = True,
) -> LocationDecision:
    """Evaluate explicit geography, remote restrictions, and relocation signals."""
    if not location:
        return LocationDecision(True, "location_unknown")

    normalized = location.casefold()
    combined = f"{normalized}\n{(context or '').casefold()}"
    remote_markers = ("remote", "work from home", "wfh", "distributed")
    worldwide_markers = ("anywhere", "worldwide", "world-wide", "global remote")
    relocation_markers = (
        "relocation assistance",
        "relocation support",
        "relocation package",
        "visa sponsorship",
        "sponsorship available",
        "relocate to",
    )
    relocation_denials = (
        "no relocation",
        "without relocation",
        "do not offer relocation",
        "does not offer relocation",
        "relocation is not available",
        "no visa sponsorship",
        "without visa sponsorship",
        "unable to sponsor",
        "cannot sponsor",
        "can't sponsor",
        "do not sponsor",
        "does not sponsor",
    )

    is_remote = any(marker in normalized for marker in remote_markers)
    accepted = any(_contains_pattern(normalized, pattern) for pattern in accept)
    rejected = any(
        _contains_pattern(normalized, pattern) for pattern in reject_non_remote
    )

    # A role with at least one viable office/location remains useful even when
    # the same posting lists additional incompatible locations.
    # For non-remote jobs, a specific reject pattern (e.g. "Berlin") overrides
    # a broad accept match (e.g. "Germany") so "Berlin, Germany" office jobs
    # don't slip through via the "Germany" accept entry.
    if accepted and (is_remote or not rejected):
        reason = "remote_compatible" if is_remote else "location_accepted"
        return LocationDecision(True, reason)

    if relocation_eligible:
        offers_relocation = any(marker in combined for marker in relocation_markers)
        denies_relocation = any(marker in combined for marker in relocation_denials)
        if offers_relocation and not denies_relocation:
            return LocationDecision(True, "relocation_supported")

    if is_remote:
        if rejected:
            return LocationDecision(False, "remote_restricted")
        if any(marker in normalized for marker in worldwide_markers):
            return LocationDecision(True, "remote_worldwide")
        if explicit_geography:
            return LocationDecision(False, "remote_location_not_accepted")
        return LocationDecision(True, "remote_eligibility_unspecified")

    if rejected:
        return LocationDecision(False, "location_rejected")
    return LocationDecision(False, "location_not_accepted")


def location_is_allowed(
    location: str | None,
    accept: list[str],
    reject_non_remote: list[str],
    context: str | None = None,
    explicit_geography: bool = False,
) -> bool:
    """Return the boolean form of :func:`evaluate_location`."""
    return evaluate_location(
        location,
        accept,
        reject_non_remote,
        context,
        explicit_geography,
    ).allowed
