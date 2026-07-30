import json

from applypilot.database import init_db
from applypilot.scoring import tailor
from applypilot.scoring.tailor import tailor_resume
from applypilot.scoring.validator import validate_json_fields


def _profile() -> dict:
    return {
        "skills_boundary": {"languages": ["Python", "Elixir", "Git", "Nix"]},
        "resume_facts": {
            "preserved_companies": [],
            "preserved_projects": [],
            "preserved_school": "",
            "real_metrics": [],
        },
        "personal": {},
        "experience": {},
    }


def _resume_json(skills: str = "Python", projects: list | None = None) -> dict:
    return {
        "title": "Senior Backend Engineer",
        "summary": "Backend engineer building Python services.",
        "skills": {"Languages": skills},
        "experience": [
            {
                "header": "Backend Engineer at Example",
                "subtitle": "Python | 2020-present",
                "bullets": ["Built Python services."],
            }
        ],
        "projects": projects or [],
        "education": "Example University",
    }


def test_validator_accepts_verified_profile_skill_absent_from_original_resume() -> None:
    result = validate_json_fields(
        _resume_json("Python, Elixir"),
        _profile(),
        original_text="Python backend engineer. Built an API Service.",
    )

    assert result["passed"] is True


def test_validator_accepts_common_skill_alias_from_original_resume() -> None:
    result = validate_json_fields(
        _resume_json("Golang, Ruby on Rails"),
        _profile(),
        original_text="Go backend engineer. Built Ruby on Rails services.",
    )

    assert result["passed"] is True


def test_validator_rejects_unlisted_skill() -> None:
    result = validate_json_fields(
        _resume_json("Python, Django"),
        _profile(),
        original_text="Python backend engineer.",
    )

    assert result["passed"] is False
    assert "Fabricated skill: 'django'" in result["errors"]


def test_validator_rejects_invented_projects_when_source_has_no_projects() -> None:
    result = validate_json_fields(
        _resume_json(
            projects=[
                {
                    "header": "Invented Project",
                    "subtitle": "Tech | Dates",
                    "bullets": ["Invented work."],
                }
            ]
        ),
        _profile(),
        original_text="Python backend engineer. Built an API Service.",
    )

    assert result["passed"] is False
    assert any("Projects are not grounded" in error for error in result["errors"])


def test_validator_rejects_project_placeholders() -> None:
    result = validate_json_fields(
        _resume_json(
            projects=[
                {
                    "header": "API Service",
                    "subtitle": "Tech | Dates",
                    "bullets": ["Built an API service."],
                }
            ]
        ),
        _profile(),
        original_text="PROJECTS\nAPI Service\nPython | 2020",
    )

    assert result["passed"] is False
    assert any("Placeholder project metadata" in error for error in result["errors"])


def test_normal_tailoring_blocks_a_failed_judge(monkeypatch) -> None:
    class FakeClient:
        def chat(self, *args, **kwargs) -> str:
            return json.dumps(_resume_json())

    monkeypatch.setattr(tailor, "get_client", lambda: FakeClient())
    monkeypatch.setattr(
        tailor,
        "judge_tailored_resume",
        lambda *args, **kwargs: {
            "passed": False,
            "verdict": "FAIL",
            "issues": "Invented project.",
            "raw": "VERDICT: FAIL\nISSUES: Invented project.",
        },
    )

    _, report = tailor_resume(
        "Python backend engineer. Built an API Service.",
        {
            "title": "Senior Backend Engineer",
            "site": "Example",
            "location": "Germany",
            "full_description": "Build Python services.",
        },
        _profile(),
        max_retries=0,
        validation_mode="normal",
    )

    assert report["status"] == "failed_judge"


def test_judge_skill_false_positive_is_reconciled(monkeypatch) -> None:
    class FakeClient:
        def chat(self, *args, **kwargs) -> str:
            return 'VERDICT: FAIL\nISSUES: Added "Elixir" to Technical Skills.'

    monkeypatch.setattr(tailor, "get_client", lambda: FakeClient())

    result = tailor.judge_tailored_resume(
        "Elixir/Phoenix backend engineer.",
        "TECHNICAL SKILLS\nLanguages: Elixir",
        "Senior Backend Engineer",
        _profile(),
    )

    assert result["passed"] is True
    assert "reconciled" in result["issues"]


def test_lenient_tailoring_is_an_unvalidated_draft(monkeypatch) -> None:
    class FakeClient:
        def chat(self, *args, **kwargs) -> str:
            return json.dumps(_resume_json())

    monkeypatch.setattr(tailor, "get_client", lambda: FakeClient())

    _, report = tailor_resume(
        "Python backend engineer. Built an API Service.",
        {
            "title": "Senior Backend Engineer",
            "site": "Example",
            "location": "Germany",
            "full_description": "Build Python services.",
        },
        _profile(),
        max_retries=0,
        validation_mode="lenient",
    )

    assert report["status"] == "unvalidated"


def test_failed_judge_is_not_persisted_as_ready(monkeypatch, tmp_path) -> None:
    conn = init_db(tmp_path / "jobs.db")
    conn.execute(
        """
        INSERT INTO jobs (
            url, title, company, site, location, full_description, fit_score,
            eligibility_allowed, is_shortlisted
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "https://example.com/job",
            "Senior Backend Engineer",
            "Example",
            "Example",
            "Germany",
            "Build Python services.",
            9,
            1,
            1,
        ),
    )
    conn.commit()
    resume_path = tmp_path / "resume.txt"
    resume_path.write_text("Python backend engineer.", encoding="utf-8")

    monkeypatch.setattr(tailor, "RESUME_PATH", resume_path)
    monkeypatch.setattr(tailor, "TAILORED_DIR", tmp_path / "tailored")
    monkeypatch.setattr(tailor, "load_profile", _profile)
    monkeypatch.setattr(tailor, "get_connection", lambda: conn)
    monkeypatch.setattr(
        tailor,
        "tailor_resume",
        lambda *args, **kwargs: (
            "unsafe draft",
            {
                "status": "failed_judge",
                "attempts": 1,
                "validator": {"passed": True, "errors": [], "warnings": []},
                "judge": {
                    "passed": False,
                    "verdict": "FAIL",
                    "issues": "Invented project.",
                },
            },
        ),
    )

    result = tailor.run_tailoring(shortlist_only=True)

    row = conn.execute(
        "SELECT tailored_resume_path, tailor_attempts FROM jobs"
    ).fetchone()
    assert result["approved"] == 0
    assert result["failed"] == 1
    assert row["tailored_resume_path"] is None
    assert row["tailor_attempts"] == 1
    assert not list((tmp_path / "tailored").glob("*.pdf"))
