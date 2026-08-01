from applypilot.enrichment import urls


def test_resolve_url_handles_relative_board_job_links(monkeypatch) -> None:
    monkeypatch.setattr(
        urls,
        "_load_base_urls",
        lambda: {
            "4DayWeek": "https://4dayweek.io",
            "Working Nomads": "https://www.workingnomads.com/jobs/",
        },
    )

    assert urls.resolve_url("/job/example-role", "4DayWeek") == (
        "https://4dayweek.io/job/example-role"
    )
    assert urls.resolve_url(
        "backend-engineer-example-123", "Working Nomads"
    ) == "https://www.workingnomads.com/jobs/backend-engineer-example-123"


def test_resolve_url_rejects_board_navigation_links(monkeypatch) -> None:
    monkeypatch.setattr(
        urls,
        "_load_base_urls",
        lambda: {
            "4DayWeek": "https://4dayweek.io",
            "Working Nomads": "https://www.workingnomads.com/jobs/",
        },
    )

    assert urls.resolve_url("/jobs", "4DayWeek") is None
    assert urls.resolve_url("/jobs/", "Working Nomads") is None
