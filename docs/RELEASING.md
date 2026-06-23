# Releasing Portable Builds

The portable Windows packages are built by GitHub Actions from tags.

## Recommended Flow

1. Update the version in the repo.
2. Commit the release changes.
3. Create and push a tag:

   ```bash
   git tag v0.0.x
   git push origin v0.0.x
   ```

4. GitHub Actions runs `Build portable Windows release`.
5. The workflow creates or updates the GitHub Release for that tag.
6. The release receives:

   ```text
   hifisampler-portable-windows-v0.0.x.zip
   ```

## Manual Test Builds

Use `workflow_dispatch` from the Actions tab to create a build artifact without creating a GitHub Release.

Manual builds are useful for testing download links, model normalization, PyInstaller, and package layout before tagging.

## Tag and Release Policy

Use tags as the source of truth.

```text
v0.0.7
v0.0.8
v0.1.0
```

Avoid manually creating releases first. If a release is created manually, workflows that only run on tag pushes will not automatically build the portable zip for that release.

## Runtime

The portable package includes CPU execution and DirectML support in one zip:

```text
torch: CPU wheel
onnxruntime-directml: DirectML package with CPU fallback
```

DirectML acceleration is profile-dependent:

```text
PC-NSF HiFiGAN: CPU or DirectML
LoFiVocoder: CPU only
```

## Model Sources

The build downloads:

```text
PC-NSF:
https://github.com/openvpi/vocoders/releases/download/pc-nsf-hifigan-44.1k-hop512-128bin-2025.02/pc_nsf_hifigan_44.1k_hop512_128bin_2025.02.oudep

LoFiVocoder:
https://huggingface.co/usamireko/LoFiVocoder/resolve/main/LoFiVocoder-20260203.zip

HNSEP:
https://huggingface.co/usamireko/hnsep_onnx/resolve/main/hnsep_onnx.zip
```

HNSEP is copied from the ONNX archive:

```text
models/hnsep/vr/model.onnx
```

The PC-NSF `.oudep` file is a ZIP archive and is extracted by the build script.
Model file names are normalized after extraction so the portable config can rely on stable paths.
