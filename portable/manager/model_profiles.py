from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PORTABLE_ROOT = Path(__file__).resolve().parents[1]
CONFIG = PORTABLE_ROOT / "config.yaml"
DEFAULT_CONFIG = PORTABLE_ROOT / "config.default.yaml"
MODELS_DIR = PORTABLE_ROOT / "models"
DEFAULT_PROFILE_ID = "pc_nsf"


@dataclass(frozen=True)
class ModelProfile:
    profile_id: str
    name: str
    path: Path
    data: dict[str, Any]


def load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml
    except ImportError:
        raise RuntimeError("PyYAML is required to manage model profiles.")

    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise RuntimeError(f"{path} does not contain a YAML object.")
    return data


def dump_yaml(path: Path, data: dict[str, Any]) -> None:
    import yaml

    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(data, handle, sort_keys=False, allow_unicode=False)


def list_profiles() -> list[ModelProfile]:
    profiles: list[ModelProfile] = []
    for path in sorted(MODELS_DIR.glob("*/model.profile.yaml")):
        data = load_yaml(path)
        profile_id = str(data.get("id") or path.parent.name)
        name = str(data.get("name") or profile_id)
        profiles.append(ModelProfile(profile_id=profile_id, name=name, path=path, data=data))
    return profiles


def get_profile(profile_id: str) -> ModelProfile:
    for profile in list_profiles():
        if profile.profile_id == profile_id:
            return profile
    raise RuntimeError(f"Unknown model profile: {profile_id}")


def load_config() -> dict[str, Any]:
    if not CONFIG.exists():
        if DEFAULT_CONFIG.exists():
            return load_yaml(DEFAULT_CONFIG)
        return {}
    return load_yaml(CONFIG)


def get_active_profile_id(config: dict[str, Any] | None = None) -> str:
    config = config if config is not None else load_config()
    portable = config.get("portable", {}) if isinstance(config.get("portable"), dict) else {}
    active = portable.get("active_model_profile")
    if active:
        return str(active)

    profiles = list_profiles()
    if any(profile.profile_id == DEFAULT_PROFILE_ID for profile in profiles):
        return DEFAULT_PROFILE_ID
    if profiles:
        return profiles[0].profile_id
    return DEFAULT_PROFILE_ID


def resolve_portable_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return PORTABLE_ROOT / path


def portable_path_string(value: str) -> str:
    return str(resolve_portable_path(value).resolve()).replace("\\", "/")


def apply_profile_to_config(config: dict[str, Any], profile: ModelProfile) -> dict[str, Any]:
    config.setdefault("portable", {})
    config.setdefault("model", {})
    config.setdefault("audio", {})

    if isinstance(config["portable"], dict):
        config["portable"]["active_model_profile"] = profile.profile_id

    profile_model = profile.data.get("model", {})
    if isinstance(profile_model, dict) and isinstance(config["model"], dict):
        for key, value in profile_model.items():
            if key.endswith("_path") and isinstance(value, str):
                config["model"][key] = portable_path_string(value)
            else:
                config["model"][key] = value

    profile_audio = profile.data.get("audio", {})
    if isinstance(profile_audio, dict) and isinstance(config["audio"], dict):
        config["audio"].update(profile_audio)

    return config


def apply_profile(profile_id: str) -> ModelProfile:
    profile = get_profile(profile_id)
    config = load_config()
    config = apply_profile_to_config(config, profile)
    dump_yaml(CONFIG, config)
    return profile


def validate_profile(profile: ModelProfile) -> list[str]:
    errors: list[str] = []
    model = profile.data.get("model", {})
    if not isinstance(model, dict):
        return [f"{profile.name}: missing model section"]

    for key in ("vocoder_path", "hnsep_model_path"):
        value = model.get(key)
        if not isinstance(value, str) or not value:
            errors.append(f"{profile.name}: missing {key}")
            continue
        path = resolve_portable_path(value)
        if not path.exists():
            errors.append(f"{profile.name}: model file missing: {path}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage portable hifisampler model profiles.")
    parser.add_argument("--list", action="store_true", help="List available model profiles.")
    parser.add_argument("--active", action="store_true", help="Print the active model profile id.")
    parser.add_argument("--apply", metavar="PROFILE_ID", help="Apply a model profile to config.yaml.")
    parser.add_argument("--validate", action="store_true", help="Validate model files for all profiles.")
    args = parser.parse_args()

    try:
        if args.list:
            for profile in list_profiles():
                print(f"{profile.profile_id}\t{profile.name}")
        if args.active:
            print(get_active_profile_id())
        if args.apply:
            profile = apply_profile(args.apply)
            print(f"OK: active model profile set to {profile.name}")
        if args.validate:
            ok = True
            for profile in list_profiles():
                errors = validate_profile(profile)
                if errors:
                    ok = False
                    for error in errors:
                        print(f"ERROR: {error}")
                else:
                    print(f"OK: model profile ready: {profile.name}")
            return 0 if ok else 1
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1

    if not (args.list or args.active or args.apply or args.validate):
        parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
