from applypilot.database import init_db
from applypilot.discovery import jobspy, smartextract, workday


def test_jobspy_uses_worldwide_for_linkedin_europe(monkeypatch) -> None:
    captured = {}

    def scrape(kwargs, **_options):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(jobspy, "_scrape_with_retry", scrape)

    frames, errors = jobspy._scrape_sources(
        {"query": "Backend Engineer", "location": "Europe", "remote": True},
        ["linkedin"],
        10,
        72,
        None,
        {"country_indeed": "germany"},
        0,
        {},
        "test",
    )

    assert errors == 0
    assert frames == [[]]
    assert captured["location"] == "Worldwide"
    assert captured["country_indeed"] == "worldwide"


def test_smart_extract_skips_disabled_sites() -> None:
    targets = smartextract.build_scrape_targets(
        sites=[
            {
                "name": "Noisy",
                "url": "https://example.test?q={query_encoded}",
                "type": "search",
                "enabled": False,
            },
            {
                "name": "Useful",
                "url": "https://useful.test?q={query_encoded}",
                "type": "search",
            },
        ],
        search_cfg={"queries": [{"query": "Backend Engineer"}]},
    )

    assert [target["name"] for target in targets] == ["Useful"]


def test_smart_extract_continues_after_target_failure(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        smartextract,
        "init_db",
        lambda: init_db(tmp_path / "jobs.db"),
    )

    def run_site(name: str, _url: str, _cache: dict) -> dict:
        if name == "Broken":
            raise TimeoutError("browser timeout")
        return {
            "name": name,
            "status": "PASS",
            "strategy": "json_ld",
            "total": 0,
            "titles": 0,
            "jobs": [],
        }

    monkeypatch.setattr(smartextract, "_run_one_site", run_site)
    result = smartextract._run_all(
        [
            {"name": "Broken", "url": "https://broken.test", "query": None},
            {"name": "Healthy", "url": "https://healthy.test", "query": None},
        ],
        [],
        [],
        [],
    )

    assert result["total"] == 2
    assert result["passed"] == 1


def test_cached_smart_extract_selectors_are_reusable() -> None:
    jobs = smartextract.apply_css_selectors(
        """
        <article class="job">
          <a class="title" href="/jobs/1">Backend Engineer</a>
          <span class="location">Berlin, Germany</span>
        </article>
        """,
        {
            "job_card": "article.job",
            "title": "a.title",
            "salary": None,
            "description": None,
            "location": "span.location",
            "url": "a.title",
        },
    )

    assert jobs == [
        {
            "title": "Backend Engineer",
            "salary": None,
            "description": None,
            "location": "Berlin, Germany",
            "url": "/jobs/1",
        }
    ]


def test_workday_skips_details_for_seen_source_id(monkeypatch) -> None:
    employers = {
        "example": {
            "name": "Example",
            "base_url": "https://example.test",
            "site_id": "Careers",
        }
    }
    monkeypatch.setattr(
        workday,
        "search_employer",
        lambda *_args, **_kwargs: [
            {
                "employer_key": "example",
                "employer_name": "Example",
                "external_path": "/job/1",
                "title": "Backend Engineer",
            }
        ],
    )
    monkeypatch.setattr(
        workday,
        "fetch_details",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("details should not be fetched")
        ),
    )

    result = workday._process_one(
        "example",
        employers,
        "Backend Engineer",
        False,
        [],
        [],
        [],
        {"example:/job/1"},
    )

    assert result == {
        "employer": "Example",
        "query": "Backend Engineer",
        "found": 1,
        "new": 0,
        "existing": 1,
    }
