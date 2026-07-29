from applypilot.discovery import workday


def test_load_employers_delegates_to_runtime_registry(monkeypatch) -> None:
    employers = {"example": {"name": "Example"}}
    calls = 0

    def load_employers_config() -> dict:
        nonlocal calls
        calls += 1
        return {"employers": employers}

    monkeypatch.setattr(workday.config, "load_employers_config", load_employers_config)

    assert workday.load_employers() is employers
    assert calls == 1


def test_check_employer_health_accepts_cxs_response(monkeypatch) -> None:
    employer = {
        "name": "Example",
        "tenant": "example",
        "site_id": "Careers",
        "base_url": "https://example.wd1.myworkdayjobs.com",
    }
    call = {}

    def workday_search(*_args, **kwargs) -> dict:
        call.update(kwargs)
        return {"total": 12, "jobPostings": []}

    monkeypatch.setattr(workday, "workday_search", workday_search)

    assert workday.check_employer_health("example", employer) == {
        "key": "example",
        "name": "Example",
        "status": "ok",
        "detail": "12 open jobs",
    }
    assert call["limit"] == 20


def test_check_employer_health_reports_missing_configuration() -> None:
    result = workday.check_employer_health("example", {"name": "Example"})

    assert result["status"] == "invalid_config"
    assert result["detail"] == "missing: tenant, site_id, base_url"


def test_check_employer_health_rejects_non_cxs_response(monkeypatch) -> None:
    employer = {
        "name": "Example",
        "tenant": "example",
        "site_id": "Careers",
        "base_url": "https://example.wd1.myworkdayjobs.com",
    }
    monkeypatch.setattr(
        workday,
        "workday_search",
        lambda *_args, **_kwargs: {"error": "not found"},
    )

    result = workday.check_employer_health("example", employer)

    assert result["status"] == "invalid_response"


def test_check_registry_health_preserves_registry_order(monkeypatch) -> None:
    employers = {
        "first": {"name": "First"},
        "second": {"name": "Second"},
    }

    def check_employer_health(key: str, employer: dict) -> dict:
        return {
            "key": key,
            "name": employer["name"],
            "status": "ok",
            "detail": "",
        }

    monkeypatch.setattr(workday, "check_employer_health", check_employer_health)

    results = workday.check_registry_health(employers, workers=2)

    assert [result["key"] for result in results] == ["first", "second"]


def test_search_employer_applies_title_exclusions(monkeypatch) -> None:
    employer = {
        "name": "Example",
        "tenant": "example",
        "site_id": "Careers",
        "base_url": "https://example.wd1.myworkdayjobs.com",
    }
    monkeypatch.setattr(
        workday,
        "workday_search",
        lambda *_args, **_kwargs: {
            "total": 2,
            "jobPostings": [
                {
                    "title": "Senior Freelance Backend Engineer",
                    "externalPath": "/freelance",
                },
                {
                    "title": "Senior Backend Engineer",
                    "externalPath": "/employee",
                },
            ],
        },
    )

    jobs = workday.search_employer(
        "example",
        employer,
        "backend engineer",
        location_filter=False,
        exclude_titles=["freelance"],
    )

    assert [job["title"] for job in jobs] == ["Senior Backend Engineer"]
