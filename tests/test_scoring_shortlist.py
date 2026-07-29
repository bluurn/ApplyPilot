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
