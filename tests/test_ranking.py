import json

from applypilot.database import get_jobs_by_stage, init_db
from applypilot.scoring.ranking import (
    explain_signals,
    rank_job,
    run_discovery_ranking,
)


def _config() -> dict:
    return {
        "watchlist": ["JetBrains"],
        "ranking": {
            "weights": {
                "python": 3,
                "backend": 3,
                "germany": 3,
                "europe": 2,
                "remote": 2,
                "relocation": 1.5,
                "salary": 1,
                "watchlist": 2,
            }
        }
    }


def test_ranking_groups_related_signals_without_double_counting() -> None:
    result = rank_job(
        {
            "title": "Senior Python Backend Engineer",
            "location": "Berlin, Germany (Remote)",
            "full_description": "Python APIs. Relocation assistance available.",
            "salary": "€90K - €110K",
            "is_watchlist": 1,
        },
        _config(),
    )

    assert result["signals"]["python"]
    assert result["signals"]["backend"]
    assert result["signals"]["germany"]
    assert result["signals"]["europe"]
    assert result["signals"]["remote"]
    assert result["signals"]["contributions"]["technical_fit"] == 3
    assert result["signals"]["contributions"]["geography_fit"] == 3
    assert result["score"] == 10.5
    assert explain_signals(result["signals"]) == (
        "technical +3, geography +3, relocation +1.5, salary +1, watchlist +2"
    )


def test_ranking_does_not_reward_denied_relocation() -> None:
    result = rank_job(
        {
            "title": "Backend Engineer",
            "location": "London",
            "full_description": (
                "We do not offer relocation assistance or visa sponsorship."
            ),
        },
        _config(),
    )

    assert not result["signals"]["relocation"]
    assert result["signals"]["contributions"]["relocation"] == 0


def test_api_signal_does_not_match_inside_unrelated_words() -> None:
    result = rank_job(
        {
            "title": "Financial Analyst",
            "location": "Paris, France",
            "full_description": "Analyze capital markets and rapid changes.",
        },
        _config(),
    )

    assert not result["signals"]["backend"]


def test_run_ranking_persists_score_signals_and_timestamp(tmp_path) -> None:
    conn = init_db(tmp_path / "jobs.db")
    conn.execute(
        """
        INSERT INTO jobs (
            url, title, location, full_description, salary, is_watchlist
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            "job",
            "Python Backend Engineer",
            "Berlin, Germany",
            "Build Python APIs.",
            "€90K",
            1,
        ),
    )
    conn.commit()

    assert run_discovery_ranking(conn, _config()) == {"ranked": 1}

    row = conn.execute(
        """
        SELECT discovery_score, discovery_signals, ranked_at, fit_score
        FROM jobs WHERE url = ?
        """,
        ("job",),
    ).fetchone()
    assert row["discovery_score"] == 9
    assert json.loads(row["discovery_signals"])["watchlist"] is True
    assert row["ranked_at"]
    assert row["fit_score"] is None


def test_run_ranking_backfills_legacy_watchlist_rows_from_site(tmp_path) -> None:
    conn = init_db(tmp_path / "jobs.db")
    conn.execute(
        "INSERT INTO jobs (url, title, site) VALUES (?, ?, ?)",
        ("legacy", "Backend Engineer", "JetBrains"),
    )
    conn.commit()

    run_discovery_ranking(conn, _config())

    row = conn.execute(
        """
        SELECT company, is_watchlist, watchlist_name
        FROM jobs WHERE url = ?
        """,
        ("legacy",),
    ).fetchone()
    assert tuple(row) == ("JetBrains", 1, "JetBrains")


def test_stage_results_order_by_watchlist_then_discovery_rank(tmp_path) -> None:
    conn = init_db(tmp_path / "jobs.db")
    conn.executemany(
        """
        INSERT INTO jobs (
            url, title, is_watchlist, discovery_score, fit_score
        ) VALUES (?, ?, ?, ?, ?)
        """,
        [
            ("llm", "High LLM", 0, 2, 10),
            ("ranked", "High Rank", 0, 8, 5),
            ("watched", "Watched", 1, 1, 1),
        ],
    )
    conn.commit()

    rows = get_jobs_by_stage(conn=conn, stage="discovered")

    assert [row["url"] for row in rows] == ["watched", "ranked", "llm"]
