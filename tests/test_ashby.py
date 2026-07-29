import json
from pathlib import Path

from applypilot.database import init_db
from applypilot.discovery import ashby


def _raw_job(
    *,
    job_id: int = 1,
    title: str = "Senior Backend Engineer",
    location: str = "Berlin, Germany",
    employment_type: str = "FullTime",
    remote: bool = False,
    country: str = "Germany",
) -> dict:
    return {
        "title": title,
        "location": location,
        "secondaryLocations": [],
        "isListed": True,
        "isRemote": remote,
        "workplaceType": "Remote" if remote else "Hybrid",
        "descriptionPlain": "Build reliable Python APIs and backend services.",
        "employmentType": employment_type,
        "address": {
            "postalAddress": {
                "addressLocality": location,
                "addressCountry": country,
            }
        },
        "jobUrl": f"https://jobs.ashbyhq.com/example/{job_id}",
        "applyUrl": f"https://jobs.ashbyhq.com/example/{job_id}/application",
        "compensation": {
            "compensationTierSummary": "€80K – €100K",
            "scrapeableCompensationSalarySummary": "€80K - €100K",
        },
    }


def _search_config() -> dict:
    return {
        "queries": [{"query": "Senior Backend Engineer", "tier": 1}],
        "exclude_titles": ["freelance"],
        "location_accept": ["Germany", "Europe"],
        "location_reject_non_remote": ["United States"],
        "location_reject_remote": ["US", "Canada"],
        "ashby_max_tier": 2,
        "defaults": {"source_timeout_seconds": 5},
    }


def test_load_boards_delegates_to_runtime_registry(monkeypatch) -> None:
    boards = {"example": {"name": "Example", "board": "Example"}}
    monkeypatch.setattr(
        ashby.config,
        "load_ashby_config",
        lambda: {"boards": boards},
    )

    assert ashby.load_boards() is boards


def test_fetch_board_jobs_requests_compensation(monkeypatch) -> None:
    payload = json.dumps({"apiVersion": "1", "jobs": [_raw_job()]}).encode()

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self) -> bytes:
            return payload

    def urlopen(request, timeout: float):
        assert request.full_url == (
            "https://api.ashbyhq.com/posting-api/job-board/"
            "Example?includeCompensation=true"
        )
        assert timeout == 12
        return Response()

    monkeypatch.setattr(ashby.urllib.request, "urlopen", urlopen)

    assert ashby.fetch_board_jobs("Example", timeout=12) == [_raw_job()]


def test_normalize_job_preserves_secondary_locations_salary_and_apply_url() -> None:
    raw = _raw_job()
    raw["secondaryLocations"] = [
        {
            "location": "Paris, France",
            "address": {"addressCountry": "France"},
        }
    ]
    job = ashby.normalize_job(
        "example",
        {"name": "Example"},
        raw,
        "2026-07-29T00:00:00+00:00",
    )

    assert job["location"] == "Berlin, Germany; Paris, France"
    assert job["full_description"] == (
        "Build reliable Python APIs and backend services."
    )
    assert job["salary"] == "€80K - €100K"
    assert job["strategy"] == "ashby_api"
    assert job["application_url"].endswith("/application")


def test_filter_jobs_applies_listing_role_contract_title_and_location_rules() -> None:
    unlisted = _raw_job(job_id=2)
    unlisted["isListed"] = False
    jobs = [
        _raw_job(job_id=1),
        unlisted,
        _raw_job(job_id=3, employment_type="Contract"),
        _raw_job(job_id=4, title="Senior Freelance Backend Engineer"),
        _raw_job(job_id=5, title="Product Manager"),
        _raw_job(
            job_id=6,
            location="Remote - US only",
            remote=True,
            country="United States",
        ),
        _raw_job(
            job_id=7,
            location="Europe",
            remote=True,
            country="",
        ),
        _raw_job(
            job_id=8,
            location="Colombia",
            remote=True,
            country="Colombia",
        ),
    ]

    selected = ashby.filter_jobs(jobs, _search_config())

    assert [job["jobUrl"].rsplit("/", 1)[-1] for job in selected] == ["1", "7"]


def test_run_ashby_discovery_isolates_board_failures_and_deduplicates(
    tmp_path: Path,
    monkeypatch,
) -> None:
    boards = {
        "broken": {"name": "Broken", "board": "Broken"},
        "healthy": {"name": "Healthy", "board": "Healthy"},
    }

    def fetch_board_jobs(board_name: str, timeout: float) -> list[dict]:
        assert timeout == 5
        if board_name == "Broken":
            raise TimeoutError("deadline")
        return [_raw_job()]

    monkeypatch.setattr(ashby, "fetch_board_jobs", fetch_board_jobs)
    monkeypatch.setattr(ashby.config, "load_search_config", _search_config)
    conn = init_db(tmp_path / "jobs.db")

    result = ashby.run_ashby_discovery(boards=boards, workers=2, conn=conn)

    assert result == {
        "found": 1,
        "new": 1,
        "existing": 0,
        "errors": 1,
        "boards": 2,
    }
    stored = conn.execute(
        "SELECT title, site, strategy, salary, full_description FROM jobs"
    ).fetchone()
    assert tuple(stored) == (
        "Senior Backend Engineer",
        "Healthy",
        "ashby_api",
        "€80K - €100K",
        "Build reliable Python APIs and backend services.",
    )

    repeated = ashby.run_ashby_discovery(
        boards={"healthy": boards["healthy"]},
        workers=1,
        conn=conn,
    )
    assert repeated["new"] == 0
    assert repeated["existing"] == 1
