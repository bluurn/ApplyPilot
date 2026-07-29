"""Profile-aware loaders for package-shipped YAML registries.

The loader preserves the current single-file behaviour by default. When a user
selects ``search_profile`` or ``search_profiles`` in searches.yaml and the
profile manifest exists, registry fragments are merged in manifest order.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _unique_list(left: list[Any], right: list[Any]) -> list[Any]:
    """Merge lists while preserving order and removing equivalent entries."""
    result = list(left)
    seen = {json.dumps(item, sort_keys=True, default=str) for item in result}
    for item in right:
        marker = json.dumps(item, sort_keys=True, default=str)
        if marker not in seen:
            result.append(item)
            seen.add(marker)
    return result


def _deep_merge(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge registry dictionaries.

    Later fragments override scalar values and dictionary keys. Lists are
    appended with stable de-duplication, which is suitable for site registries,
    blocked-domain lists, and similar package configuration.
    """
    merged = dict(left)
    for key, value in right.items():
        current = merged.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            merged[key] = _deep_merge(current, value)
        elif isinstance(current, list) and isinstance(value, list):
            merged[key] = _unique_list(current, value)
        else:
            merged[key] = value
    return merged


def _selected_profiles(search_config: dict[str, Any] | None) -> list[str]:
    if not search_config:
        return []
    selected = search_config.get("search_profiles", search_config.get("search_profile"))
    if isinstance(selected, str):
        return [selected]
    if isinstance(selected, list):
        return [str(item) for item in selected if item]
    return []


def load_registry(
    config_dir: Path,
    registry: str,
    search_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Load a legacy registry or merge profile fragments.

    Expected optional layout::

        config/profiles.yaml
        config/employers/global.yaml
        config/employers/eu.yaml
        config/sites/global.yaml
        config/sites/eu.yaml

    ``profiles.yaml`` maps profile names to fragment names, for example::

        profiles:
          eu:
            employers: [global, eu]
            sites: [global, eu]

    If no profile is selected, the manifest is absent, or no matching fragments
    are found, ``config/<registry>.yaml`` is loaded exactly as before.
    """
    legacy = _load_yaml(config_dir / f"{registry}.yaml")
    selected = _selected_profiles(search_config)
    if not selected:
        return legacy

    manifest = _load_yaml(config_dir / "profiles.yaml").get("profiles", {})
    if not isinstance(manifest, dict):
        return legacy

    fragments: list[str] = []
    for profile_name in selected:
        profile = manifest.get(profile_name, {})
        if not isinstance(profile, dict):
            continue
        configured = profile.get(registry, [])
        if isinstance(configured, str):
            configured = [configured]
        if isinstance(configured, list):
            for fragment in configured:
                fragment_name = str(fragment)
                if fragment_name not in fragments:
                    fragments.append(fragment_name)

    merged: dict[str, Any] = {}
    loaded_any = False
    for fragment in fragments:
        path = config_dir / registry / f"{fragment}.yaml"
        if path.exists():
            merged = _deep_merge(merged, _load_yaml(path))
            loaded_any = True

    return merged if loaded_any else legacy
