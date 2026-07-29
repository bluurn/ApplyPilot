import sqlite3

from applypilot.database import get_jobs_by_stage, get_stats, init_db
from applypilot.discovery.watchlist import (
    match_watchlist,
    prioritize_registry,
    registry_watchlist_report,
    update_existing_watchlist,
    watchlist_fields,
)


def test_company_matching_is_exact_after_punctuation_normalization() -> None:
    watchlist = ["JetBrains", "Grafana Labs"]

    assert match_watchlist("JetBrains", watchlist) == "JetBrains"
    assert match_watchlist("Grafana-Labs", watchlist) == "Grafana Labs"
    assert match_watchlist("Grafana", watchlist) is None


def test_prioritize_registry_preserves_relative_order_within_groups() -> None:
    registry = {
        "ordinary_one": {"name": "Ordinary One"},
        "jetbrains": {"name": "JetBrains"},
        "ordinary_two": {"name": "Ordinary Two"},
        "gitlab": {"name": "GitLab"},
    }

    ordered = prioritize_registry(registry, ["JetBrains", "GitLab"])

    assert list(ordered) == [
        "jetbrains",
        "gitlab",
        "ordinary_one",
        "ordinary_two",
    ]


def test_watchlist_fields_preserve_configured_spelling() -> None:
    assert watchlist_fields("grafana-labs", ["Grafana Labs"]) == (
        1,
        "Grafana Labs",
    )
    assert watchlist_fields("Other", ["Grafana Labs"]) == (0, None)


def test_registry_report_keeps_missing_companies_visible() -> None:
    report = registry_watchlist_report(
        ["JetBrains", "Canonical", "GitLab"],
        [
            {
                "jetbrains": {"name": "JetBrains"},
                "gitlab": {"name": "GitLab"},
            }
        ],
    )

    assert report == {
        "configured": ["JetBrains", "Canonical", "GitLab"],
        "present": ["JetBrains", "GitLab"],
        "missing": ["Canonical"],
    }


def test_database_migrates_and_prioritizes_watchlist_jobs(tmp_path) -> None:
    path = tmp_path / "jobs.db"
    legacy = sqlite3.connect(path)
    legacy.execute("CREATE TABLE jobs (url TEXT PRIMARY KEY, title TEXT)")
    legacy.commit()
    legacy.close()

    conn = init_db(path)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(jobs)")}
    assert {"company", "is_watchlist", "watchlist_name"} <= columns

    conn.execute(
        """
        INSERT INTO jobs (
            url, title, company, is_watchlist, watchlist_name, discovered_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("ordinary", "Ordinary", "Other", 0, None, "2026-07-29T02:00:00"),
    )
    conn.execute(
        """
        INSERT INTO jobs (
            url, title, company, is_watchlist, watchlist_name, discovered_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            "priority",
            "Priority",
            "JetBrains",
            1,
            "JetBrains",
            "2026-07-29T01:00:00",
        ),
    )
    conn.commit()

    jobs = get_jobs_by_stage(conn, limit=0)
    assert [job["url"] for job in jobs] == ["priority", "ordinary"]
    assert get_stats(conn)["watchlist"] == 1


def test_existing_job_is_promoted_when_company_becomes_watchlisted(tmp_path) -> None:
    conn = init_db(tmp_path / "jobs.db")
    conn.execute(
        "INSERT INTO jobs (url, title, site) VALUES (?, ?, ?)",
        ("existing", "Backend Engineer", "linkedin"),
    )

    update_existing_watchlist(
        conn,
        "existing",
        "JetBrains",
        1,
        "JetBrains",
    )
    conn.commit()

    row = conn.execute(
        "SELECT company, is_watchlist, watchlist_name FROM jobs WHERE url = ?",
        ("existing",),
    ).fetchone()
    assert tuple(row) == ("JetBrains", 1, "JetBrains")
