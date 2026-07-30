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
            ("strong", "Backend Engineer", "x" * 300, 8, 0),
            ("weak", "Marketing Manager", "x" * 300, 8, 0),
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
    assert scored_titles == ["Watched", "Backend Engineer"]
    assert conn.execute(
        "SELECT fit_score FROM jobs WHERE url = 'weak'"
    ).fetchone()[0] is None
    assert conn.execute(
        "SELECT scoring_eligibility_reason FROM jobs WHERE url = 'weak'"
    ).fetchone()[0] == "title_not_preferred"


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


def test_scoring_collapses_country_variants_and_shares_score(
    tmp_path,
    monkeypatch,
) -> None:
    conn = init_db(tmp_path / "jobs.db")
    description = "Build distributed Python backend services. " * 20
    conn.executemany(
        """
        INSERT INTO jobs (
            url, title, company, location, full_description,
            discovery_score, is_watchlist
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                "germany",
                "Senior Backend Engineer | Germany | Remote",
                "Grafana Labs",
                "Germany (Remote)",
                description,
                8,
                1,
            ),
            (
                "spain",
                "Senior Backend Engineer | Spain | Remote",
                "Grafana Labs",
                "Spain (Remote)",
                description,
                7,
                1,
            ),
        ],
    )
    conn.execute(
        "UPDATE jobs SET is_shortlisted = 1 WHERE url = 'spain'"
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
            "location_accept": ["Germany", "Spain"],
            "scoring": {"min_discovery_score": 5, "shortlist_limit": 10},
        },
    )
    scored = []
    monkeypatch.setattr(
        scorer,
        "score_job",
        lambda _resume, job: (
            scored.append(job["url"])
            or {"score": 9, "keywords": "Python", "reasoning": "strong"}
        ),
    )

    result = scorer.run_scoring()

    assert result["scored"] == 1
    assert scored == ["germany"]
    assert conn.execute(
        "SELECT duplicate_of FROM jobs WHERE url = 'spain'"
    ).fetchone()[0] == "germany"
    assert conn.execute(
        "SELECT fit_score FROM jobs WHERE url = 'spain'"
    ).fetchone()[0] == 9
    assert conn.execute(
        "SELECT is_shortlisted FROM jobs WHERE url = 'germany'"
    ).fetchone()[0] == 1
    assert conn.execute(
        "SELECT is_shortlisted FROM jobs WHERE url = 'spain'"
    ).fetchone()[0] == 0
