from applypilot.discovery.filters import title_is_excluded


def test_title_is_excluded_is_case_insensitive() -> None:
    assert title_is_excluded("Senior Freelance Backend Engineer", ["freelance"])


def test_title_is_excluded_ignores_empty_patterns() -> None:
    assert not title_is_excluded("Backend Engineer", ["", "junior"])


def test_title_is_excluded_keeps_missing_titles() -> None:
    assert not title_is_excluded(None, ["freelance"])
