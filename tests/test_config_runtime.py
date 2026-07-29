from pathlib import Path

import yaml

import applypilot.config as config


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def test_sites_config_uses_selected_profile_and_user_overrides(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = tmp_path / "package"
    user_dir = tmp_path / "user"
    searches = tmp_path / "searches.yaml"

    _write(
        package_dir / "profiles.yaml",
        {"profiles": {"eu": {"sites": ["global", "eu"]}}},
    )
    _write(package_dir / "sites" / "global.yaml", {"blocked_sso": ["global.example"]})
    _write(package_dir / "sites" / "eu.yaml", {"blocked_sso": ["eu.example"]})
    _write(user_dir / "sites" / "eu.yaml", {"blocked_sso": ["personal.example"]})
    _write(user_dir / "profiles.yaml", {"profiles": {"eu": {"sites": ["eu"]}}})
    _write(searches, {"search_profile": "eu"})

    monkeypatch.setattr(config, "CONFIG_DIR", package_dir)
    monkeypatch.setattr(config, "USER_CONFIG_DIR", user_dir)
    monkeypatch.setattr(config, "SEARCH_CONFIG_PATH", searches)

    assert config.load_blocked_sso() == [
        "global.example",
        "eu.example",
        "personal.example",
    ]


def test_employers_config_accepts_personal_legacy_override(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = tmp_path / "package"
    user_dir = tmp_path / "user"
    searches = tmp_path / "searches.yaml"

    _write(
        package_dir / "employers.yaml",
        {"employers": {"shared": {"name": "Package"}}},
    )
    _write(
        user_dir / "employers.yaml",
        {"employers": {"shared": {"name": "Personal"}}},
    )
    _write(searches, {})

    monkeypatch.setattr(config, "CONFIG_DIR", package_dir)
    monkeypatch.setattr(config, "USER_CONFIG_DIR", user_dir)
    monkeypatch.setattr(config, "SEARCH_CONFIG_PATH", searches)

    result = config.load_employers_config()

    assert result["employers"]["shared"]["name"] == "Personal"
