import json
from pathlib import Path

from applypilot.database import init_db
from applypilot.discovery import greenhouse


def _raw_job(
    *,
    job_id: int = 1,
    title: str = "Senior Software Engineer, Backend",
    location: str = "Berlin, Germany",
) -> dict:
    return {
        "id": job_id,
        "internal_job_id": job_id + 100,
        "title": title,
        "location": {"name": location},
        "absolute_url": f"https://example.com/jobs/{job_id}",
        "content": "&lt;p&gt;Build reliable APIs and backend services.&lt;/p&gt;",
    }


def _search_config() -> dict:
    return {
        "queries": [{"query": "Senior Backend Engineer", "tier": 1}],
        "exclude_titles": ["freelance"],
        "location_accept": ["Germany"],
        "location_reject_non_remote": ["United States"],
        "greenhouse_max_tier": 2,
        "defaults": {"source_timeout_seconds": 5},
    }


def test_load_boards_delegates_to_runtime_registry(monkeypatch) -> None:
    boards = {"example": {"name": "Example", "token": "example"}}
    monkeypatch.setattr(
        greenhouse.config,
        "load_greenhouse_config",
        lambda: {"boards": boards},
    )

    assert greenhouse.load_boards() is boards


def test_fetch_board_jobs_uses_public_api_with_content(monkeypatch) -> None:
    payload = json.dumps({"jobs": [_raw_job()]}).encode()

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self) -> bytes:
            return payload

    def urlopen(request, timeout: float):
        assert request.full_url.endswith("/example/jobs?content=true")
        assert timeout == 12
        return Response()

    monkeypatch.setattr(greenhouse.urllib.request, "urlopen", urlopen)

    assert greenhouse.fetch_board_jobs("example", timeout=12) == [_raw_job()]


def test_normalize_job_decodes_content() -> None:
    job = greenhouse.normalize_job(
        "example",
        {"name": "Example"},
        _raw_job(),
        "2026-07-29T00:00:00+00:00",
    )

    assert job["title"] == "Senior Software Engineer, Backend"
    assert job["location"] == "Berlin, Germany"
    assert job["full_description"] == "Build reliable APIs and backend services."
    assert job["strategy"] == "greenhouse_api"
    assert job["application_url"] == job["url"]


def test_filter_jobs_applies_role_title_and_location_rules() -> None:
    jobs = [
        _raw_job(job_id=1),
        _raw_job(job_id=2, title="Senior Freelance Backend Engineer"),
        _raw_job(job_id=3, title="Product Manager"),
        _raw_job(job_id=4, location="Austin, United States"),
        {**_raw_job(job_id=5), "internal_job_id": None},
    ]

    selected = greenhouse.filter_jobs(jobs, _search_config())

    assert [job["id"] for job in selected] == [1]


def test_run_greenhouse_discovery_isolates_board_failures(
    tmp_path: Path,
    monkeypatch,
) -> None:
    boards = {
        "broken": {"name": "Broken", "token": "broken"},
        "healthy": {"name": "Healthy", "token": "healthy"},
    }

    def fetch_board_jobs(token: str, timeout: float) -> list[dict]:
        assert timeout == 5
        if token == "broken":
            raise TimeoutError("deadline")
        return [_raw_job()]

    monkeypatch.setattr(greenhouse, "fetch_board_jobs", fetch_board_jobs)
    monkeypatch.setattr(
        greenhouse.config,
        "load_search_config",
        _search_config,
    )
    conn = init_db(tmp_path / "jobs.db")

    result = greenhouse.run_greenhouse_discovery(
        boards=boards,
        workers=2,
        conn=conn,
    )

    assert result == {
        "found": 1,
        "new": 1,
        "existing": 0,
        "errors": 1,
        "boards": 2,
    }
    stored = conn.execute(
        "SELECT title, site, strategy, full_description FROM jobs"
    ).fetchone()
    assert tuple(stored) == (
        "Senior Software Engineer, Backend",
        "Healthy",
        "greenhouse_api",
        "Build reliable APIs and backend services.",
    )

    repeated = greenhouse.run_greenhouse_discovery(
        boards={"healthy": boards["healthy"]},
        workers=1,
        conn=conn,
    )
    assert repeated["new"] == 0
    assert repeated["existing"] == 1
