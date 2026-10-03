from pathlib import Path
from typing import Any

import yaml


def load_country_config(base_dir: Path, country: str) -> dict[str, Any]:
    config_path = base_dir / "country_config" / f"{country}.yaml"
    if not config_path.exists():
        raise FileNotFoundError(
            f"No country config at {config_path}. "
            f"Run /diaries-bootstrap --country {country} first."
        )
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def merge_with_defaults(country_config: dict, defaults_path: Path) -> dict[str, Any]:
    defaults: dict[str, Any] = {}
    if defaults_path.exists():
        with open(defaults_path, encoding="utf-8") as f:
            defaults = yaml.safe_load(f) or {}
    merged = {**defaults}
    _deep_merge(merged, country_config)
    return merged


def _deep_merge(base: dict, override: dict) -> None:
    for key, val in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(val, dict):
            _deep_merge(base[key], val)
        else:
            base[key] = val
