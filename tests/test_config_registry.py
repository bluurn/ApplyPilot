from pathlib import Path

import yaml

from applypilot import config
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

    assert set(result["employers"]) == {"shared", "global", "eu"}
    assert result["employers"]["shared"]["name"] == "EU override"


def test_selected_profile_extends_legacy_package_defaults(tmp_path: Path) -> None:
    _write(
        tmp_path / "employers.yaml",
        {"employers": {"base": {"name": "Base"}, "shared": {"name": "Base"}}},
    )
    _write(
        tmp_path / "profiles.yaml",
        {"profiles": {"eu": {"employers": ["eu"]}}},
    )
    _write(
        tmp_path / "employers" / "eu.yaml",
        {"employers": {"eu": {"name": "EU"}, "shared": {"name": "EU"}}},
    )

    result = load_registry(tmp_path, "employers", {"search_profile": "eu"})

    assert set(result["employers"]) == {"base", "shared", "eu"}
    assert result["employers"]["shared"]["name"] == "EU"


def test_packaged_eu_profile_includes_base_and_europe_employers() -> None:
    result = load_registry(
        config.CONFIG_DIR,
        "employers",
        {"search_profile": "eu"},
    )

    employers = result["employers"]
    assert "deutsche_bank" in employers
    assert {
        "gea",
        "guidehouse",
        "zendesk",
        "sony",
        "zalando",
        "sandvik",
        "jll",
        "oclc",
        "relx",
        "santander",
        "intrum",
        "brunswick",
        "mehilainen",
        "pfizer",
        "adtran",
        "dow_jones",
        "sanofi",
        "autodesk",
        "visa",
        "guidewire",
        "pgim",
        "workhuman",
        "astemo",
        "blackrock",
        "rakuten_kobo",
        "fidelity",
        "redhat",
    } <= employers.keys()

    assert employers["redhat"] == {
        "name": "Red Hat",
        "tenant": "redhat",
        "site_id": "jobs",
        "base_url": "https://redhat.wd5.myworkdayjobs.com",
    }


def test_packaged_eu_profile_includes_greenhouse_boards() -> None:
    result = load_registry(
        config.CONFIG_DIR,
        "greenhouse",
        {"search_profile": "eu"},
    )

    assert {
        "jetbrains",
        "gitlab",
        "grafana_labs",
        "cloudflare",
        "elastic",
        "datadog",
        "contentful",
        "sumup",
        "n26",
        "celonis",
        "canonical",
        "wolt",
        "miro",
        "personio",
        "aiven",
        "remote",
        "mongodb",
        "confluent",
        "hashicorp",
        "netlify",
        "fastly",
        "intercom",
        "criteo",
    } <= result["boards"].keys()


def test_packaged_eu_profile_includes_lever_sites() -> None:
    result = load_registry(
        config.CONFIG_DIR,
        "lever",
        {"search_profile": "eu"},
    )

    assert {
        "prismic",
        "finn",
        "quantco",
        "kpler",
        "spotify",
        "palantir",
        "kraken",
        "qonto",
        "algolia",
        "doctolib",
        "contentsquare",
        "aircall",
        "back_market",
        "payfit",
        "klarna",
        "spendesk",
        "dataiku",
        "leboncoin",
    } <= result["sites"].keys()


def test_packaged_eu_profile_includes_ashby_boards() -> None:
    result = load_registry(
        config.CONFIG_DIR,
        "ashby",
        {"search_profile": "eu"},
    )

    assert {
        "openai",
        "posthog",
        "clickhouse",
        "supabase",
        "pleo",
        "synthesia",
        "elevenlabs",
        "n8n",
        "temporal",
        "pennylane",
        "dbt_labs",
        "retool",
        "prefect",
        "dagster",
        "modal",
        "turso",
    } <= result["boards"].keys()


def test_falls_back_to_legacy_when_profile_fragments_are_missing(tmp_path: Path) -> None:
    _write(tmp_path / "sites.yaml", {"sites": [{"name": "Legacy", "url": "https://example.com"}]})
    _write(tmp_path / "profiles.yaml", {"profiles": {"eu": {"sites": ["global", "eu"]}}})

    result = load_registry(tmp_path, "sites", {"search_profiles": ["eu"]})

    assert result["sites"][0]["name"] == "Legacy"


def test_user_legacy_registry_overrides_package_data(tmp_path: Path) -> None:
    package_dir = tmp_path / "package"
    user_dir = tmp_path / "user"
    _write(
        package_dir / "employers.yaml",
        {"employers": {"shared": {"name": "Package"}, "package": {"name": "Package only"}}},
    )
    _write(
        user_dir / "employers.yaml",
        {"employers": {"shared": {"name": "Personal"}, "personal": {"name": "Personal only"}}},
    )

    result = load_registry(package_dir, "employers", {}, user_dir)

    assert result["employers"]["shared"]["name"] == "Personal"
    assert result["employers"]["package"]["name"] == "Package only"
    assert result["employers"]["personal"]["name"] == "Personal only"


def test_user_profile_fragments_extend_selected_profile(tmp_path: Path) -> None:
    package_dir = tmp_path / "package"
    user_dir = tmp_path / "user"
    manifest = {"profiles": {"eu": {"sites": ["global", "eu"]}}}
    _write(package_dir / "profiles.yaml", manifest)
    _write(user_dir / "profiles.yaml", manifest)
    _write(package_dir / "sites" / "global.yaml", {"blocked_sso": ["package.example"]})
    _write(package_dir / "sites" / "eu.yaml", {"blocked_sso": ["eu.example"]})
    _write(user_dir / "sites" / "eu.yaml", {"blocked_sso": ["personal.example"]})

    result = load_registry(
        package_dir,
        "sites",
        {"search_profile": "eu"},
        user_dir,
    )

    assert result["blocked_sso"] == [
        "package.example",
        "eu.example",
        "personal.example",
    ]
