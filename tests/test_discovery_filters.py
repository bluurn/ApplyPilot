from applypilot.discovery.filters import (
    location_is_allowed,
    title_is_excluded,
    title_matches_queries,
)


def test_title_is_excluded_is_case_insensitive() -> None:
    assert title_is_excluded("Senior Freelance Backend Engineer", ["freelance"])


def test_title_is_excluded_ignores_empty_patterns() -> None:
    assert not title_is_excluded("Backend Engineer", ["", "junior"])


def test_title_is_excluded_keeps_missing_titles() -> None:
    assert not title_is_excluded(None, ["freelance"])


def test_title_matches_queries_ignores_seniority_and_word_order() -> None:
    assert title_matches_queries(
        "Senior Software Engineer, Backend",
        ["Senior Backend Engineer"],
    )


def test_title_matches_queries_rejects_partial_role_match() -> None:
    assert not title_matches_queries("Backend Product Manager", ["Backend Engineer"])


def test_location_is_allowed_accepts_remote_and_explicit_places() -> None:
    assert location_is_allowed("Remote - Europe", ["Germany"], ["United States"])
    assert location_is_allowed("Berlin, Germany", ["Germany"], ["United States"])


def test_location_is_allowed_rejects_incompatible_non_remote_location() -> None:
    assert not location_is_allowed(
        "Austin, United States",
        ["Germany"],
        ["United States"],
    )
