from applypilot.database import get_jobs_by_stage, get_stats, init_db
from applypilot.shortlist import add_job, list_jobs, remove_job


def _seed(conn) -> None:
    conn.executemany(
        """
        INSERT INTO jobs (
            url, application_url, title, company, location, full_description,
            fit_score, discovery_score, eligibility_allowed, duplicate_of
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                "canonical",
                "https://example.com/apply",
                "Senior Backend Engineer",
                "Example",
                "Germany (Remote)",
                "Build Python services.",
                9,
                8,
                1,
                None,
            ),
            (
                "variant",
                None,
                "Senior Backend Engineer | Spain | Remote",
                "Example",
                "Spain (Remote)",
                "Build Python services.",
                9,
                7,
                1,
                "canonical",
            ),
            (
                "other",
                None,
                "Backend Engineer",
                "Other",
                "Berlin, Germany",
                "Build APIs.",
                8,
                6,
                1,
                None,
            ),
            (
                "rejected",
                None,
                "Backend Engineer",
                "Rejected",
                "Remote, India",
                "Build APIs.",
                9,
                9,
                0,
                None,
            ),
        ],
    )
    conn.commit()


def test_shortlist_resolves_application_and_duplicate_urls(tmp_path) -> None:
    conn = init_db(tmp_path / "jobs.db")
    _seed(conn)

    status, job = add_job(conn, "variant")

    assert status == "added"
    assert job["url"] == "canonical"
    assert add_job(conn, "https://example.com/apply")[0] == "already_added"
    assert [job["url"] for job in list_jobs(conn)] == ["canonical"]
    assert get_stats(conn)["shortlisted"] == 1

    status, job = remove_job(conn, "https://example.com/apply")

    assert status == "removed"
    assert job["url"] == "canonical"
    assert list_jobs(conn) == []


def test_shortlist_rejects_ineligible_and_filters_tailoring(tmp_path) -> None:
    conn = init_db(tmp_path / "jobs.db")
    _seed(conn)

    assert add_job(conn, "rejected")[0] == "ineligible"
    assert add_job(conn, "canonical")[0] == "added"

    jobs = get_jobs_by_stage(
        conn,
        stage="pending_tailor",
        min_score=7,
        limit=20,
        shortlisted_only=True,
    )

    assert [job["url"] for job in jobs] == ["canonical"]
    stats = get_stats(conn)
    assert stats["untailored_eligible"] == 2
    assert stats["untailored_shortlisted"] == 1
