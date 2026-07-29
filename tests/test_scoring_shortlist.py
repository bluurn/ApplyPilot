from applypilot.database import init_db
from applypilot.scoring import scorer


def test_scoring_shortlists_by_rank_and_always_keeps_watchlist(
    tmp_path,
    monkeypatch,
) -> None:
    conn = init_db(tmp_path / "jobs.db")
    conn.executemany(
        """
        INSERT INTO jobs (
            url, title, full_description, discovery_score, is_watchlist
        ) VALUES (?, ?, ?, ?, ?)
        """,
        [
            ("strong", "Strong", "x" * 300, 8, 0),
            ("weak", "Weak", "x" * 300, 2, 0),
            ("watched", "Watched", "x" * 300, 1, 1),
        ],
    )
    conn.commit()
    resume = tmp_path / "resume.md"
    resume.write_text("resume", encoding="utf-8")

    monkeypatch.setattr(scorer, "RESUME_PATH", resume)
    monkeypatch.setattr(scorer, "get_connection", lambda: conn)
    monkeypatch.setattr(
        scorer.config,
        "load_search_config",
        lambda: {
            "location_accept": [],
            "location_reject_remote": [],
            "scoring": {
                "min_discovery_score": 5,
                "shortlist_limit": 10,
            }
        },
    )
    scored_titles = []

    def score_job(_resume: str, job: dict) -> dict:
        scored_titles.append(job["title"])
        return {"score": 7, "keywords": "", "reasoning": "ok"}

    monkeypatch.setattr(scorer, "score_job", score_job)

    result = scorer.run_scoring()

    assert result["scored"] == 2
    assert scored_titles == ["Watched", "Strong"]
    assert conn.execute(
        "SELECT fit_score FROM jobs WHERE url = 'weak'"
    ).fetchone()[0] is None


def test_scoring_audits_location_and_suppresses_semantic_duplicates(
    tmp_path,
    monkeypatch,
) -> None:
    conn = init_db(tmp_path / "jobs.db")
    description = "Build Python APIs and distributed backend services. " * 20
    conn.executemany(
        """
        INSERT INTO jobs (
            url, title, company, location, full_description,
            discovery_score, is_watchlist
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("best", "Senior Backend Engineer", "Acme", "Berlin, Germany", description, 8, 0),
            ("copy", "Senior Backend Engineer", "Acme", "Berlin, Germany", description, 7, 0),
            ("india", "Senior Backend Engineer", "GitLab", "Remote, Bangalore", description, 9, 1),
        ],
    )
    conn.commit()
    resume = tmp_path / "resume.md"
    resume.write_text("resume", encoding="utf-8")
    monkeypatch.setattr(scorer, "RESUME_PATH", resume)
    monkeypatch.setattr(scorer, "get_connection", lambda: conn)
    monkeypatch.setattr(
        scorer.config,
        "load_search_config",
        lambda: {
            "location_accept": ["Germany", "Europe"],
            "location_reject_remote": ["India"],
            "scoring": {"min_discovery_score": 5, "shortlist_limit": 10},
        },
    )
    scored = []
    monkeypatch.setattr(
        scorer,
        "score_job",
        lambda _resume, job: (
            scored.append(job["url"])
            or {"score": 8, "keywords": "", "reasoning": "ok"}
        ),
    )

    result = scorer.run_scoring()

    assert result["scored"] == 1
    assert scored == ["best"]
    assert conn.execute(
        "SELECT duplicate_of FROM jobs WHERE url = 'copy'"
    ).fetchone()[0] == "best"
    assert conn.execute(
        "SELECT eligibility_reason FROM jobs WHERE url = 'india'"
    ).fetchone()[0] == "remote_location_not_accepted"
