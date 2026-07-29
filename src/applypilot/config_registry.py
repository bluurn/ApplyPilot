"""Profile-aware YAML registry loading.

Package registries provide sensible defaults. A user can select one or more
profiles in searches.yaml and override the resulting registry from
``$APPLYPILOT_DIR/config`` without modifying the installed package.
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
    """Recursively merge dictionaries, with values from ``right`` winning."""
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


def _load_profiled_registry(
    config_dir: Path,
    registry: str,
    selected: list[str],
) -> tuple[dict[str, Any], bool]:
    manifest = _load_yaml(config_dir / "profiles.yaml").get("profiles", {})
    if not isinstance(manifest, dict):
        return {}, False

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
    return merged, loaded_any


def load_registry(
    config_dir: Path,
    registry: str,
    search_config: dict[str, Any] | None = None,
    user_config_dir: Path | None = None,
) -> dict[str, Any]:
    """Load a package registry and apply optional user overrides.

    Package loading order:

    1. selected profile fragments when available;
    2. otherwise ``config/<registry>.yaml``.

    User loading order, when ``user_config_dir`` is provided:

    1. matching profile fragments under ``user_config_dir``;
    2. ``user_config_dir/<registry>.yaml`` as a final override.

    This keeps the installed package immutable while allowing personal sites,
    employers, blocks, and URL mappings to live under the ApplyPilot data dir.
    """
    selected = _selected_profiles(search_config)
    package_data, loaded_profiles = _load_profiled_registry(
        config_dir, registry, selected
    )
    if not loaded_profiles:
        package_data = _load_yaml(config_dir / f"{registry}.yaml")

    if user_config_dir is None:
        return package_data

    result = package_data
    user_profile_data, loaded_user_profiles = _load_profiled_registry(
        user_config_dir, registry, selected
    )
    if loaded_user_profiles:
        result = _deep_merge(result, user_profile_data)

    user_legacy = _load_yaml(user_config_dir / f"{registry}.yaml")
    if user_legacy:
        result = _deep_merge(result, user_legacy)

    return result
