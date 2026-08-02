from applypilot.apply import chrome


def test_setup_worker_profile_allows_clean_chromium_installation(tmp_path, monkeypatch) -> None:
    worker_dir = tmp_path / "chrome-workers"
    missing_source = tmp_path / "missing-google-chrome"
    monkeypatch.setattr(chrome.config, "CHROME_WORKER_DIR", worker_dir)
    monkeypatch.setattr(chrome.config, "get_chrome_user_data", lambda: missing_source)

    profile = chrome.setup_worker_profile(0)

    assert profile == worker_dir / "worker-0"
    assert profile.is_dir()
    assert not (profile / "Default").exists()
