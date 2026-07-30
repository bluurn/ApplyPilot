from applypilot import pipeline


def test_sequential_pipeline_passes_shortlist_to_tailoring(monkeypatch) -> None:
    received = {}

    def runner(**kwargs):
        received.update(kwargs)
        return {"status": "ok"}

    monkeypatch.setitem(pipeline._STAGE_RUNNERS, "tailor", runner)

    result = pipeline._run_sequential(
        ["tailor"],
        min_score=8,
        validation_mode="strict",
        shortlist_only=True,
    )

    assert result["errors"] == {}
    assert received == {
        "min_score": 8,
        "validation_mode": "strict",
        "shortlist_only": True,
    }
