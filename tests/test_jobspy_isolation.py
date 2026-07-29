from applypilot.discovery import jobspy


def test_scrape_sources_retains_success_after_board_failure(monkeypatch) -> None:
    calls = []
    successful_result = object()

    def scrape_with_retry(kwargs: dict, **options):
        calls.append((kwargs, options))
        if kwargs["site_name"] == ["indeed"]:
            raise TimeoutError("source deadline")
        return successful_result

    monkeypatch.setattr(jobspy, "_scrape_with_retry", scrape_with_retry)

    results, errors = jobspy._scrape_sources(
        search={
            "query": "Backend Engineer",
            "location": "Hamburg, Germany",
            "remote": False,
        },
        sites=["indeed", "linkedin"],
        results_per_site=10,
        hours_old=72,
        proxy_config=None,
        defaults={
            "country_indeed": "germany",
            "source_timeout_seconds": 12,
        },
        max_retries=0,
        glassdoor_map={},
        label="smoke",
    )

    assert results == [successful_result]
    assert errors == 1
    assert [call[0]["site_name"] for call in calls] == [["indeed"], ["linkedin"]]
    assert all(call[1]["timeout_seconds"] == 12 for call in calls)
