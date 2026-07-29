from pathlib import Path

import yaml

from applypilot.config_registry import load_registry


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data), encoding="utf-8")


def test_uses_legacy_registry_without_selected_profile(tmp_path: Path) -> None:
    _write(tmp_path / "employers.yaml", {"employers": {"legacy": {"name": "Legacy"}}})

    result = load_registry(tmp_path, "employers", {})

    assert result["employers"]["legacy"]["name"] == "Legacy"


def test_merges_profile_fragments_in_manifest_order(tmp_path: Path) -> None:
    _write(
        tmp_path / "profiles.yaml",
        {
            "profiles": {
                "eu": {
                    "employers": ["global", "eu"],
                    "sites": ["global", "eu"],
                }
            }
        },
    )
    _write(
        tmp_path / "employers" / "global.yaml",
        {"employers": {"shared": {"name": "Global"}, "global": {"name": "Global only"}}},
    )
    _write(
        tmp_path / "employers" / "eu.yaml",
        {"employers": {"shared": {"name": "EU override"}, "eu": {"name": "EU only"}}},
    )

    result = load_registry(tmp_path, "employers", {"search_profile": "eu"})

    assert list(result["employers"]) == ["shared", "global", "eu"]
    assert result["employers"]["shared"]["name"] == "EU override"


def test_falls_back_to_legacy_when_profile_fragments_are_missing(tmp_path: Path) -> None:
    _write(tmp_path / "sites.yaml", {"sites": [{"name": "Legacy", "url": "https://example.com"}]})
    _write(tmp_path / "profiles.yaml", {"profiles": {"eu": {"sites": ["global", "eu"]}}})

    result = load_registry(tmp_path, "sites", {"search_profiles": ["eu"]})

    assert result["sites"][0]["name"] == "Legacy"
