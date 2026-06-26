from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


PORTABLE_ROOT = Path(__file__).resolve().parents[1]
CLIENT_NAME = "hifisampler.exe" if sys.platform == "win32" else "hifisampler"


def find_hifisampler() -> Path | None:
    for candidate in (PORTABLE_ROOT / CLIENT_NAME, PORTABLE_ROOT.parent / CLIENT_NAME):
        if candidate.exists():
            return candidate
    return None


def prompt_openutau_path() -> Path:
    while True:
        raw = input("Enter your OpenUTAU folder path: ").strip().strip('"')
        if not raw:
            print("ERROR: OpenUTAU folder path is required.")
            continue
        return Path(raw).expanduser()


def validate_openutau_folder(path: Path) -> Path:
    if path.exists() and not path.is_dir():
        raise RuntimeError(f"Not a folder: {path}")
    path.mkdir(parents=True, exist_ok=True)
    resamplers = path / "Resamplers"
    resamplers.mkdir(parents=True, exist_ok=True)
    return resamplers


def main() -> int:
    parser = argparse.ArgumentParser(description=f"Copy {CLIENT_NAME} into OpenUTAU Resamplers.")
    parser.add_argument("openutau_folder", nargs="?", help="Path to the OpenUTAU folder.")
    args = parser.parse_args()

    source = find_hifisampler()
    if source is None:
        print(f"ERROR: {CLIENT_NAME} was not found in the portable folder or parent folder.")
        return 1

    try:
        openutau_folder = Path(args.openutau_folder).expanduser() if args.openutau_folder else prompt_openutau_path()
        resamplers = validate_openutau_folder(openutau_folder)
        destination = resamplers / CLIENT_NAME
        shutil.copy2(source, destination)
    except Exception as exc:
        print(f"ERROR: install failed: {exc}")
        return 1

    print(f"OK: {CLIENT_NAME} installed")
    print(f"Installed to: {destination}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
