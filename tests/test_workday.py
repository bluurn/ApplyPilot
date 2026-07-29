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
