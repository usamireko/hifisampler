from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path
from typing import Any

from model_profiles import apply_profile_to_config, get_active_profile_id, get_profile


PORTABLE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = PORTABLE_ROOT / "config.default.yaml"
CONFIG = PORTABLE_ROOT / "config.yaml"
MODELS_DIR = PORTABLE_ROOT / "models"
LOGS_DIR = PORTABLE_ROOT / "logs"


def find_app_root() -> Path:
    for candidate in (PORTABLE_ROOT, PORTABLE_ROOT.parent):
        if (candidate / "hifiserver.py").exists() and (candidate / "config.py").exists():
            return candidate
    return PORTABLE_ROOT


def load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml
    except ImportError:
        raise RuntimeError("PyYAML is required to prepare config.yaml. Use the full portable package or install requirements.")

    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise RuntimeError(f"{path} does not contain a YAML object.")
    return data


def dump_yaml(path: Path, data: dict[str, Any]) -> None:
    import yaml

    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(data, handle, sort_keys=False, allow_unicode=False)


def merge_missing(current: dict[str, Any], default: dict[str, Any]) -> dict[str, Any]:
    for key, value in default.items():
        if isinstance(value, dict):
            current_value = current.get(key)
            if not isinstance(current_value, dict):
                current_value = {}
            current[key] = merge_missing(current_value, value)
        elif key not in current:
            current[key] = value
    return current


def prepare_config(path: Path, default_path: Path, app_root: Path) -> None:
    if not default_path.exists():
        raise RuntimeError(f"Default config missing: {default_path}")

    if not path.exists():
        shutil.copy2(default_path, path)

    default_data = load_yaml(default_path)
    data = merge_missing(load_yaml(path), default_data)

    data.setdefault("env", {})

    if isinstance(data["env"], dict):
        server_path = app_root / "hifiserver.py"
        data["env"]["python_script_path"] = str(server_path.resolve()).replace("\\", "/")

    active_profile_id = get_active_profile_id(data)
    data = apply_profile_to_config(data, get_profile(active_profile_id))

    dump_yaml(path, data)


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare the portable hifisampler folder.")
    parser.parse_args()

    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        app_root = find_app_root()
        prepare_config(CONFIG, DEFAULT_CONFIG, app_root)
    except Exception as exc:
        print(f"ERROR: portable preparation failed: {exc}")
        return 1

    print("OK: portable config prepared")
    print(f"OK: logs folder ready: {LOGS_DIR}")
    print(f"OK: model folder: {MODELS_DIR}")
    print(f"OK: active model profile: {get_active_profile_id(load_yaml(CONFIG))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
