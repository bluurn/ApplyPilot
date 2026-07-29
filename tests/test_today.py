from datetime import datetime, timedelta, timezone

from applypilot import today
from applypilot.database import init_db


def test_today_report_surfaces_new_best_watchlist_companies_and_applied(
    tmp_path,
    monkeypatch,
) -> None:
    conn = init_db(tmp_path / "jobs.db")
    now = datetime(2026, 7, 29, 12, tzinfo=timezone.utc)
    recent = (now - timedelta(hours=2)).isoformat()
    old = (now - timedelta(days=5)).isoformat()
    conn.executemany(
        """
        INSERT INTO jobs (
            url, title, company, site, location, salary, full_description,
            is_watchlist, watchlist_name, discovered_at, applied_at, fit_score,
            application_url
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                "jetbrains",
                "Python Backend Engineer",
                "JetBrains",
                "JetBrains",
                "Berlin, Germany",
                "€100K",
                "Build Python backend APIs.",
                1,
                "JetBrains",
                recent,
                None,
                5,
                "https://jetbrains.example/apply",
            ),
            (
                "ordinary",
                "Backend Engineer",
                "Ordinary",
                "Ordinary",
                "Paris, France",
                None,
                "Build backend services.",
                0,
                None,
                old,
                recent,
                9,
                "https://ordinary.example/apply",
            ),
        ],
    )
    conn.commit()
    monkeypatch.setattr(
        today,
        "load_watchlist_report",
        lambda: {
            "configured": ["JetBrains", "Canonical"],
            "present": ["JetBrains"],
            "missing": ["Canonical"],
        },
    )

    report = today.build_today_report(conn, now=now, days=1, limit=10)

    assert [job["url"] for job in report["new_jobs"]] == ["jetbrains"]
    assert report["best_matches"][0]["url"] == "ordinary"
    assert report["watchlist_jobs"][0]["watchlist_name"] == "JetBrains"
    assert report["new_companies"][0]["company"] == "JetBrains"
    assert report["applied"][0]["url"] == "ordinary"
    assert report["watchlist"]["missing"] == ["Canonical"]
    assert "technical +" in report["best_matches"][0]["discovery_explanation"]
    assert report["new_jobs"][0]["application_url"].endswith("/apply")
