#!/usr/bin/env python3
"""Cross-platform portable release builder.

Usage:
  python scripts/build_release.py --version v0.0.7 [--os windows|linux|macos]

Creates a self-contained portable package for the target OS.
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
import tarfile
from pathlib import Path


MODEL_URLS = {
    "pc_nsf": "https://github.com/openvpi/vocoders/releases/download/pc-nsf-hifigan-44.1k-hop512-128bin-2025.02/pc_nsf_hifigan_44.1k_hop512_128bin_2025.02.oudep",
    "lofi_vocoder": "https://huggingface.co/usamireko/LoFiVocoder/resolve/main/LoFiVocoder-20260203.zip",
    "hnsep": "https://huggingface.co/usamireko/hnsep_onnx/resolve/main/hnsep_onnx.zip",
}

PLATFORM_CONFIG = {
    "windows": {
        "rid": "win-x64",
        "ext": ".exe",
        "package": "zip",
        "client_name": "hifisampler.exe",
        "manager_name": "HifisamplerManager.exe",
        "runtime_paths": ["Scripts/python.exe", "python.exe"],
        "python_bin": "python.exe",
    },
    "linux": {
        "rid": "linux-x64",
        "ext": "",
        "package": "tar.gz",
        "client_name": "hifisampler",
        "manager_name": "HifisamplerManager",
        "runtime_paths": ["bin/python3", "bin/python"],
        "python_bin": "python3",
    },
    "macos": {
        "rid": "osx-arm64",
        "ext": "",
        "package": "tar.gz",
        "client_name": "hifisampler",
        "manager_name": "HifisamplerManager",
        "runtime_paths": ["bin/python3", "bin/python"],
        "python_bin": "python3",
    },
}


def run(cmd, **kwargs):
    print(f"  RUN: {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    result = subprocess.run(cmd, check=True, **kwargs)
    return result


def download_file(url, dest):
    import urllib.request
    print(f"  DOWNLOAD: {url}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(url, dest)


def extract_zip(zip_path, dest_dir):
    print(f"  EXTRACT: {zip_path} -> {dest_dir}")
    shutil.rmtree(dest_dir, ignore_errors=True)
    dest_dir.mkdir(parents=True)
    if zipfile.is_zipfile(zip_path):
        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(dest_dir)
    else:
        # .oudep is a zip file with a different extension
        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(dest_dir)


def find_file(search_root, patterns):
    """Find the first file matching patterns, prefer largest."""
    files = []
    for pattern in patterns:
        files.extend(Path(search_root).rglob(pattern))
    if not files:
        raise FileNotFoundError(f"No file found in {search_root} matching {patterns}")
    return max(files, key=lambda f: f.stat().st_size)


def build(args):
    repo = Path(__file__).resolve().parents[1]
    platform = PLATFORM_CONFIG[args.os]
    stage_name = f"hifisampler-portable-{args.os}"
    stage = Path(args.output_dir) / stage_name
    build_dir = Path(args.output_dir) / "build"
    download_dir = build_dir / "downloads"
    extract_dir = build_dir / "extract"

    shutil.rmtree(build_dir, ignore_errors=True)
    shutil.rmtree(stage, ignore_errors=True)
    build_dir.mkdir(parents=True)
    stage.mkdir(parents=True)
    download_dir.mkdir(parents=True)
    extract_dir.mkdir(parents=True)

    print("\n[1/7] Syncing Python deps...")
    run(["uv", "sync"], cwd=repo)

    print(f"\n[2/7] Building .NET client for {platform['rid']}...")
    run([
        "dotnet", "publish",
        "client/hifisampler.csproj",
        "-c", "Release",
        "-r", platform["rid"],
        "/p:PublishAot=true",
        "/p:DebugType=none",
        "/p:DebugSymbols=false",
        "-o", str(build_dir / "client"),
    ], cwd=repo)

    print("\n[3/7] Building GUI (PyInstaller)...")
    run(["uv", "pip", "install", "pyinstaller"], cwd=repo)
    run([
        "uv", "run", "pyinstaller",
        "--noconfirm", "--clean", "--onefile",
        "--name", "HifisamplerManager",
        "--paths", "portable/manager",
        "--collect-all", "customtkinter",
        "--distpath", str(build_dir / "manager-dist"),
        "--workpath", str(build_dir / "manager-work"),
        "--specpath", str(build_dir / "manager-spec"),
        "portable/manager/gui.py",
    ], cwd=repo)

    print("\n[4/7] Downloading ONNX models...")
    for name, url in MODEL_URLS.items():
        zip_path = download_dir / f"{name}.zip"
        download_file(url, zip_path)
        extract_zip(zip_path, extract_dir / name)

    print("\n[5/7] Assembling portable folder...")

    shutil.copytree(repo / "portable", stage, dirs_exist_ok=True)
    shutil.copy2(repo / "hifiserver.py", stage)
    shutil.copy2(repo / "config.py", stage)
    shutil.copy2(repo / "README.md", stage)
    shutil.copytree(repo / "backend", stage / "backend", dirs_exist_ok=True)
    shutil.copytree(repo / "util", stage / "util", dirs_exist_ok=True)
    shutil.copytree(repo / "hnsep", stage / "hnsep", dirs_exist_ok=True)
    if (stage / "hnsep" / "vr").exists():
        shutil.rmtree(stage / "hnsep" / "vr")

    shutil.copy2(build_dir / "client" / platform["client_name"], stage)
    shutil.copy2(
        build_dir / "manager-dist" / platform["manager_name"], stage
    )

    print("\n[6/7] Preparing venv...")
    runtime_dir = stage / "runtime"
    if runtime_dir.exists():
        shutil.rmtree(runtime_dir)
    run([
        "uv", "venv", "--python", "3.10", str(runtime_dir)
    ], cwd=repo)

    runtime_python = None
    for rp in platform["runtime_paths"]:
        candidate = runtime_dir / rp
        if candidate.exists():
            runtime_python = candidate
            break
    if not runtime_python:
        run([str(runtime_dir / "bin" / "python3" if args.os != "windows" else runtime_dir / "Scripts" / "python.exe"),
             "-m", "ensurepip"], cwd=repo)
        runtime_python = runtime_dir / platform["runtime_paths"][0]

    run([
        "uv", "pip", "install",
        "--python", str(runtime_python),
        "-r", str(repo / "requirements.txt"),
    ], cwd=repo)

    models_dir = stage / "models"
    models_dir.mkdir(exist_ok=True)

    pc_nsf_src = find_file(extract_dir / "pc_nsf", ["*.onnx", "model.onnx"])
    (models_dir / "pc_nsf").mkdir(exist_ok=True)
    shutil.copy2(pc_nsf_src, models_dir / "pc_nsf" / "model.onnx")

    lofi_src = find_file(extract_dir / "lofi_vocoder", ["*.onnx", "model.onnx"])
    (models_dir / "lofi_vocoder").mkdir(exist_ok=True)
    shutil.copy2(lofi_src, models_dir / "lofi_vocoder" / "model.onnx")

    hnsep_model_src = find_file(extract_dir / "hnsep", ["*.onnx", "model.onnx"])
    hnsep_config_src = find_file(extract_dir / "hnsep", ["config.yaml"])
    hnsep_out = models_dir / "hnsep" / "vr"
    hnsep_out.mkdir(parents=True, exist_ok=True)
    shutil.copy2(hnsep_model_src, hnsep_out / "model.onnx")
    shutil.copy2(hnsep_config_src, hnsep_out / "config.yaml")

    print("  Running prepare_portable.py...")
    run([str(runtime_python), str(stage / "manager" / "prepare_portable.py")],
        cwd=stage)

    print("  Running check_environment.py...")
    run([str(runtime_python), str(stage / "manager" / "check_environment.py")],
        cwd=stage)

    print(f"\n[7/7] Packaging as {platform['package']}...")
    os.makedirs(args.output_dir, exist_ok=True)

    if platform["package"] == "zip":
        archive_path = Path(args.output_dir) / f"{stage_name}-{args.version}.zip"
        if archive_path.exists():
            archive_path.unlink()
        shutil.make_archive(
            str(archive_path.with_suffix("")), "zip",
            root_dir=stage.parent, base_dir=stage_name
        )
    else:
        archive_path = Path(args.output_dir) / f"{stage_name}-{args.version}.tar.gz"
        if archive_path.exists():
            archive_path.unlink()
        with tarfile.open(archive_path, "w:gz") as tar:
            tar.add(stage, arcname=stage_name)

    print(f"\n  Release created: {archive_path}")
    print(f"  Size: {archive_path.stat().st_size / 1024 / 1024:.0f} MB")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Build portable hifisampler release")
    parser.add_argument("--version", default="dev", help="Version label")
    parser.add_argument("--os", choices=["windows", "linux", "macos"],
                       default="linux", help="Target OS")
    parser.add_argument("--output-dir", default="dist", help="Output directory")
    args = parser.parse_args()

    try:
        return build(args)
    except subprocess.CalledProcessError as e:
        print(f"\nERROR: Command failed: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"\nERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
