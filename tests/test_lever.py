import json
from pathlib import Path

from applypilot.database import init_db
from applypilot.discovery import lever


def _raw_job(
    *,
    job_id: int = 1,
    title: str = "Senior Backend Engineer",
    location: str = "Berlin, Germany",
    commitment: str = "Full-time",
    workplace_type: str = "hybrid",
    country: str = "DE",
) -> dict:
    return {
        "id": str(job_id),
        "text": title,
        "categories": {
            "location": location,
            "allLocations": [location],
            "commitment": commitment,
            "team": "Engineering",
        },
        "workplaceType": workplace_type,
        "country": country,
        "descriptionPlain": "Build reliable Python APIs and backend services.",
        "lists": [
            {
                "text": "What you bring",
                "content": "<li>Strong distributed systems experience</li>",
            }
        ],
        "additionalPlain": "Work with a kind team.",
        "hostedUrl": f"https://jobs.lever.co/example/{job_id}",
        "applyUrl": f"https://jobs.lever.co/example/{job_id}/apply",
        "salaryRange": {
            "currency": "EUR",
            "interval": "year",
            "min": 80000,
            "max": 100000,
        },
    }


def _search_config() -> dict:
    return {
        "queries": [{"query": "Senior Backend Engineer", "tier": 1}],
        "exclude_titles": ["freelance"],
        "location_accept": ["Germany", "Europe"],
        "location_reject_non_remote": ["United States"],
        "location_reject_remote": ["US", "Canada"],
        "lever_max_tier": 2,
        "defaults": {"source_timeout_seconds": 5},
    }


def test_load_sites_delegates_to_runtime_registry(monkeypatch) -> None:
    sites = {"example": {"name": "Example", "site": "example"}}
    monkeypatch.setattr(
        lever.config,
        "load_lever_config",
        lambda: {"sites": sites},
    )

    assert lever.load_sites() is sites


def test_fetch_site_jobs_uses_selected_public_instance(monkeypatch) -> None:
    payload = json.dumps([_raw_job()]).encode()

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self) -> bytes:
            return payload

    def urlopen(request, timeout: float):
        assert request.full_url == (
            "https://api.eu.lever.co/v0/postings/example?mode=json"
        )
        assert timeout == 12
        return Response()

    monkeypatch.setattr(lever.urllib.request, "urlopen", urlopen)

    assert lever.fetch_site_jobs("example", "eu", timeout=12) == [_raw_job()]


def test_normalize_job_preserves_description_locations_salary_and_apply_url() -> None:
    raw = _raw_job()
    raw["categories"]["allLocations"] = ["Berlin, Germany", "Paris, France"]
    job = lever.normalize_job(
        "example",
        {"name": "Example"},
        raw,
        "2026-07-29T00:00:00+00:00",
    )

    assert job["location"] == "Berlin, Germany; Paris, France"
    assert "Strong distributed systems experience" in job["full_description"]
    assert job["salary"] == "EUR 80,000-100,000/year"
    assert job["strategy"] == "lever_api"
    assert job["application_url"].endswith("/apply")


def test_filter_jobs_applies_role_engagement_title_and_location_rules() -> None:
    jobs = [
        _raw_job(job_id=1),
        _raw_job(job_id=2, commitment="Contract"),
        _raw_job(job_id=3, title="Senior Freelance Backend Engineer"),
        _raw_job(job_id=4, title="Product Manager"),
        _raw_job(
            job_id=5,
            location="Remote - US only",
            workplace_type="remote",
            country="US",
        ),
        _raw_job(
            job_id=6,
            location="Europe",
            workplace_type="remote",
        ),
        _raw_job(
            job_id=7,
            location="Colombia",
            workplace_type="remote",
            country="CO",
        ),
    ]

    selected = lever.filter_jobs(jobs, _search_config())

    assert [job["id"] for job in selected] == ["1", "6"]


def test_permanent_contract_is_not_treated_as_freelance() -> None:
    assert not lever._is_freelance_contract(
        _raw_job(commitment="Permanent contract")
    )


def test_run_lever_discovery_isolates_site_failures_and_deduplicates(
    tmp_path: Path,
    monkeypatch,
) -> None:
    sites = {
        "broken": {"name": "Broken", "site": "broken", "instance": "eu"},
        "healthy": {"name": "Healthy", "site": "healthy"},
    }

    def fetch_site_jobs(
        site_name: str,
        instance: str,
        timeout: float,
    ) -> list[dict]:
        assert timeout == 5
        if site_name == "broken":
            assert instance == "eu"
            raise TimeoutError("deadline")
        return [_raw_job()]

    monkeypatch.setattr(lever, "fetch_site_jobs", fetch_site_jobs)
    monkeypatch.setattr(lever.config, "load_search_config", _search_config)
    conn = init_db(tmp_path / "jobs.db")

    result = lever.run_lever_discovery(sites=sites, workers=2, conn=conn)

    assert result == {
        "found": 1,
        "new": 1,
        "existing": 0,
        "errors": 1,
        "sites": 2,
    }
    stored = conn.execute(
        "SELECT title, site, strategy, full_description FROM jobs"
    ).fetchone()
    assert tuple(stored) == (
        "Senior Backend Engineer",
        "Healthy",
        "lever_api",
        (
            "Build reliable Python APIs and backend services.\n\n"
            "What you bring\nStrong distributed systems experience\n\n"
            "Work with a kind team."
        ),
    )

    repeated = lever.run_lever_discovery(
        sites={"healthy": sites["healthy"]},
        workers=1,
        conn=conn,
    )
    assert repeated["new"] == 0
    assert repeated["existing"] == 1
