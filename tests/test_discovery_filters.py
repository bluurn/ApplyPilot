from applypilot.discovery.filters import (
    evaluate_location,
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


def test_remote_role_restricted_to_incompatible_country_is_rejected() -> None:
    decision = evaluate_location(
        "Remote - US only",
        ["Germany", "Europe"],
        ["US", "Canada"],
    )

    assert decision == (False, "remote_restricted")


def test_remote_role_with_unspecified_eligibility_is_preserved() -> None:
    decision = evaluate_location(
        "Remote",
        ["Germany", "Europe"],
        ["US", "Canada"],
    )

    assert decision == (True, "remote_eligibility_unspecified")


def test_multi_location_role_keeps_any_compatible_location() -> None:
    decision = evaluate_location(
        "Berlin, Germany; Austin, US",
        ["Germany", "Europe"],
        ["US"],
    )

    assert decision == (True, "location_accepted")


def test_relocation_support_preserves_otherwise_incompatible_role() -> None:
    decision = evaluate_location(
        "London, United Kingdom",
        ["Germany", "Europe"],
        ["United Kingdom"],
        "Visa sponsorship and relocation assistance are available.",
    )

    assert decision == (True, "relocation_supported")


def test_relocation_or_sponsorship_denial_does_not_preserve_role() -> None:
    decision = evaluate_location(
        "London, United Kingdom",
        ["Germany", "Europe"],
        ["United Kingdom"],
        "We do not offer relocation assistance or visa sponsorship.",
    )

    assert decision == (False, "location_rejected")


def test_short_location_pattern_does_not_match_inside_another_word() -> None:
    decision = evaluate_location("Austria", ["US"], ["Australia"])

    assert decision == (False, "location_not_accepted")
