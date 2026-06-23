from __future__ import annotations

import importlib.util
import platform
import sys
from pathlib import Path
from typing import Any

from model_profiles import get_active_profile_id, get_profile, validate_profile


PORTABLE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PORTABLE_ROOT.parent
CONFIG = PORTABLE_ROOT / "config.yaml"

PACKAGE_IMPORTS = {
    "numpy": "numpy",
    "scipy": "scipy",
    "pyyaml": "yaml",
    "pathlib": "pathlib",
    "torch": "torch",
    "librosa": "librosa",
    "soundfile": "soundfile",
    "resampy": "resampy",
    "onnxruntime": "onnxruntime",
    "pyloudnorm": "pyloudnorm",
    "tomli": "tomli",
    "filelock": "filelock",
    "ruamel.yaml": "ruamel.yaml",
    "aiohttp": "aiohttp",
    "praat-parselmouth": "parselmouth",
    "customtkinter": "customtkinter",
}


def status(ok: bool, ok_message: str, error_message: str) -> bool:
    print(("OK: " if ok else "ERROR: ") + (ok_message if ok else error_message))
    return ok


def warning(message: str) -> None:
    print(f"WARNING: {message}")


def find_file(name: str) -> Path | None:
    for root in (PORTABLE_ROOT, REPO_ROOT):
        candidate = root / name
        if candidate.exists():
            return candidate
    return None


def load_config() -> dict[str, Any]:
    try:
        import yaml
    except ImportError:
        return {}
    if not CONFIG.exists():
        return {}
    with CONFIG.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return data if isinstance(data, dict) else {}


def resolve_config_path(value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(value)
    if path.is_absolute():
        return path
    return PORTABLE_ROOT / path


def check_python() -> bool:
    version = sys.version_info
    ok = version >= (3, 10)
    return status(
        ok,
        f"Python found: {platform.python_version()}",
        f"Python 3.10+ required, found {platform.python_version()}",
    )


def check_packages() -> bool:
    ok = True
    for package, import_name in PACKAGE_IMPORTS.items():
        try:
            found = importlib.util.find_spec(import_name) is not None
        except ModuleNotFoundError:
            found = False
        ok = status(found, f"package found: {package}", f"package missing: {package}") and ok
    return ok


def check_onnxruntime() -> bool:
    try:
        import onnxruntime as ort
    except ImportError:
        print("ERROR: ONNXRuntime not available")
        return False
    providers = ort.get_available_providers()
    print(f"OK: ONNXRuntime available: {', '.join(providers) if providers else 'no providers reported'}")
    return True


def check_runtime(config: dict[str, Any]) -> bool:
    runtime = config.get("runtime", {}) if isinstance(config.get("runtime"), dict) else {}
    acceleration = str(runtime.get("acceleration", "cpu")).lower()
    directml_device_id = runtime.get("directml_device_id", 0)

    if acceleration == "cpu":
        print("OK: acceleration mode: CPU")
        return True

    if acceleration != "directml":
        print(f"ERROR: unknown acceleration mode: {acceleration}")
        return False

    try:
        import onnxruntime as ort
    except ImportError:
        print("ERROR: DirectML requested but ONNXRuntime is not available")
        return False

    providers = ort.get_available_providers()
    if "DmlExecutionProvider" not in providers:
        print("ERROR: DirectML requested but DmlExecutionProvider is not available")
        print(f"OK: selected DirectML device id: {directml_device_id}")
        return False

    print("OK: acceleration mode: DirectML")
    print(f"OK: selected DirectML device id: {directml_device_id}")
    return True


def check_cuda(config: dict[str, Any]) -> bool:
    model = config.get("model", {}) if isinstance(config.get("model"), dict) else {}
    model_type = str(model.get("model_type", "onnx")).lower()
    gpu_expected = model_type in {"ckpt", "pt", "torch"}

    try:
        import torch
    except ImportError:
        if gpu_expected:
            print("ERROR: torch missing for GPU model type")
            return False
        warning("CUDA not checked because torch is not installed")
        return True

    cuda_ok = bool(torch.cuda.is_available())
    if cuda_ok:
        print(f"OK: CUDA available: {torch.cuda.get_device_name(0)}")
    elif gpu_expected:
        print("ERROR: CUDA not available for GPU model type")
        return False
    else:
        warning("CUDA not available, using CPU")
    return True


def check_models(config: dict[str, Any]) -> bool:
    try:
        active_profile = get_profile(get_active_profile_id(config))
        print(f"OK: active model profile: {active_profile.name}")
        profile_errors = validate_profile(active_profile)
        if profile_errors:
            for error in profile_errors:
                print(f"ERROR: {error}")
            return False
    except Exception as exc:
        print(f"ERROR: active model profile invalid: {exc}")
        return False

    model = config.get("model", {}) if isinstance(config.get("model"), dict) else {}
    paths = [
        ("vocoder", resolve_config_path(model.get("vocoder_path"))),
        ("hnsep", resolve_config_path(model.get("hnsep_model_path"))),
    ]
    ok = True
    for label, path in paths:
        if path is None:
            print(f"ERROR: model path missing: {label}")
            ok = False
        elif path.exists():
            print(f"OK: model file found: {path}")
        else:
            print(f"ERROR: model file missing: {path}")
            ok = False
    return ok


def main() -> int:
    checks_ok = True
    checks_ok = check_python() and checks_ok
    checks_ok = status(CONFIG.exists(), "config.yaml found", f"config.yaml missing: {CONFIG}") and checks_ok

    config = load_config()
    checks_ok = status(find_file("hifisampler.exe") is not None, "hifisampler.exe found", "hifisampler.exe missing") and checks_ok
    checks_ok = status(find_file("hifiserver.py") is not None, "hifiserver.py found", "hifiserver.py missing") and checks_ok
    checks_ok = check_packages() and checks_ok
    checks_ok = check_onnxruntime() and checks_ok
    checks_ok = check_runtime(config) and checks_ok
    checks_ok = check_cuda(config) and checks_ok
    checks_ok = check_models(config) and checks_ok

    return 0 if checks_ok else 1


if __name__ == "__main__":
    sys.exit(main())
