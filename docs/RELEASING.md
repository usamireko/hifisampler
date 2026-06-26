# Releasing Portable Builds

Portable packages are built by GitHub Actions from tags.

## Recommended Flow

1. Update the version in the repo.
2. Commit the release changes.
3. Create and push a tag:

   ```bash
   git tag v0.0.x
   git push origin v0.0.x
   ```

4. GitHub Actions runs `Build multiplatform release`.
5. The workflow creates or updates the GitHub Release for that tag.
6. The release receives:

   ```
   hifisampler-portable-windows-v0.0.x.zip
   hifisampler-portable-linux-v0.0.x.tar.gz
   hifisampler-portable-macos-v0.0.x.tar.gz
   ```

## Manual Test Builds

Use `workflow_dispatch` from the Actions tab on `Build multiplatform release`
to create build artifacts without creating a GitHub Release.

## Tag and Release Policy

Use tags as the source of truth.

```
v0.0.7
v0.0.8
v0.1.0
```

Avoid manually creating releases first. If a release is created manually,
workflows that only run on tag pushes will not automatically build the
portable packages.

## Portable Package Layout

Each platform package is self-contained:

```
hifisampler-portable-{os}-v0.0.x/
├── hifisampler{ext}          # C# client (dotnet native AOT)
├── HifisamplerManager{ext}   # GUI (PyInstaller)
├── hifiserver.py             # Server entry point
├── config.py backend/ util/ hnsep/   # Python source
├── runtime/                  # Python venv with all deps
├── models/
│   ├── pc_nsf/model.onnx
│   ├── lofi_vocoder/model.onnx
│   └── hnsep/vr/model.onnx + config.yaml
├── start.{bat,sh}            # OS-specific launcher
├── prepare_portable.{bat,sh}
├── check_environment.{bat,sh}
├── config.default.yaml
├── config.yaml               # auto-generated on first run
└── README.md
```

## Runtime

```
Python 3.10 (embedded venv)
onnxruntime: CPU inference (all platforms)
onnxruntime-directml: optional, Windows GPU (uv sync --extra directml)
```

DirectML acceleration is profile-dependent:

```
PC-NSF HiFiGAN: CPU or DirectML
LoFiVocoder: CPU only
```

## Model Sources

The build downloads:

```
PC-NSF:
https://github.com/openvpi/vocoders/releases/download/pc-nsf-hifigan-44.1k-hop512-128bin-2025.02/pc_nsf_hifigan_44.1k_hop512_128bin_2025.02.oudep

LoFiVocoder:
https://huggingface.co/usamireko/LoFiVocoder/resolve/main/LoFiVocoder-20260203.zip

HNSEP:
https://huggingface.co/usamireko/hnsep_onnx/resolve/main/hnsep_onnx.zip
```

HNSEP is copied from the ONNX archive:

```
models/hnsep/vr/model.onnx
```

The PC-NSF `.oudep` file is a ZIP archive and is extracted by the build script.
Model file names are normalized after extraction so the portable config can
rely on stable paths.
