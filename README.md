# hifisampler

Portable multiplatform fork of hifisampler focused on simple setup with ONNX inference.

No PyTorch required. No YAML editing. No admin permissions. Clear errors when something is missing.

## Supported Platforms

| Platform | CPU | GPU |
|---|---|---|
| Windows | Y | DirectML |
| Linux | Yes | - |
| macOS (Apple Silicon) | Y | CoreML |

## Quick Start

### Windows

1. Download `hifisampler-portable-windows-<version>.zip` from Releases.
2. Extract to a user-writable folder, e.g. `Documents\hifisampler`.
3. Run `HifisamplerManager.exe`, click `Prepare Portable`, then `Start Server`.
4. Click `Install to OpenUTAU`.

### Linux

1. Download `hifisampler-portable-linux-<version>.tar.gz` from Releases.
2. Extract: `tar xzf hifisampler-portable-linux-*.tar.gz`
3. Run `./HifisamplerManager`, click `Prepare Portable`, then `Start Server`.
4. Click `Install to OpenUTAU`.

### macOS

1. Download `hifisampler-portable-macos-<version>.tar.gz` from Releases.
2. Extract: `tar xzf hifisampler-portable-macos-*.tar.gz`
3. Run `./HifisamplerManager`, click `Prepare Portable`, then `Start Server`.
4. Click `Install to OpenUTAU`.

No admin permissions are required on any platform.

## Package Layout

```
hifisampler-portable-{os}-<version>/
├── hifisampler{ext}          
├── HifisamplerManager{ext}   
├── hifiserver.py            
├── config.py backend/ util/ hnsep/  
├── runtime/                  
├── models/
│   ├── pc_nsf/model.onnx
│   ├── lofi_vocoder/model.onnx
│   └── hnsep/vr/model.onnx + config.yaml
├── start.{bat,sh}           
├── prepare_portable.{bat,sh}
├── check_environment.{bat,sh}
├── config.yaml
└── README.md
```

## Acceleration

Set `acceleration` in `config.yaml` or via the manager GUI:

| Platform | Options |
|---|---|
| Windows | `cpu`, `directml` |
| Linux | `cpu` |
| macOS | `cpu`, `coreml` |

When DirectML is selected, choose the GPU adapter from the device dropdown.

## Dependencies

The portable releases bundle everything. For development:

```bash
# Core deps (CPU inference, all platforms)
uv sync

# Windows GPU (DirectML)
uv sync --extra directml

# Optional: PyTorch for ckpt/pt model loading
uv sync --extra torch
```

Run the server from a development checkout:

```bash
uv run python hifiserver.py
```

Run the manager:

```bash
uv run python portable/manager/gui.py
```

## Build Releases

```bash
# Windows
python3 scripts/build_release.py --os windows --version dev

# Linux
python3 scripts/build_release.py --os linux --version dev

# macOS
python3 scripts/build_release.py --os macos --version dev
```

The multiplatform CI workflow runs on every `v*` tag. See `docs/RELEASING.md`.

## Fallback Scripts

For troubleshooting without the GUI:

```
Windows: START_HIFISAMPLER.bat  PREPARE_PORTABLE.bat  CHECK_ENVIRONMENT.bat
Linux/macOS: start.sh  prepare_portable.sh  check_environment.sh
```

## OpenUTAU Setup

Use the `Install to OpenUTAU` button in the manager. It copies the client binary into `<OpenUTAU folder>/Resamplers/` and creates the folder if missing.

## Model Profiles

```
PC-NSF HiFiGAN (CPU or DirectML)
LoFiVocoder (CPU only)
```

Expected model layout:

```
models/
  pc_nsf/model.onnx
  lofi_vocoder/model.onnx
  hnsep/vr/model.onnx + config.yaml
```

## Troubleshooting

### Server Does Not Start

Run `Check Environment` and check `logs/server.log`.

### Model Missing

Run `Check Environment`. Release packages include models; dev builds need them placed manually.

### Slow Speed

Check acceleration setting. Switch to DirectML (Windows) or CoreML (macOS) if available.

## Implemented Flags

- **g:** Adjust gender/formants. Range: -600 to 600, default: 0
- **Hb:** Adjust breath/noise. Range: 0 to 500, default: 100
- **Hv:** Adjust voice/harmonic. Range: 0 to 150, default: 100
- **HG:** Vocal fry/growl. Range: 0 to 100, default: 0
- **P:** Normalize loudness at note level (-16 LUFS). Requires `wave_norm: true` in config. Range: 0 to 100, default: 100
- **t:** Shift pitch in cents. Range: -1200 to 1200, default: 0
- **Ht:** Adjust tension. Range: -100 to 100, default: 0
- **A:** Modulate amplitude based on pitch variations. Range: -100 to 100, default: 0
- **G:** Force feature cache regeneration. No value needed
- **He:** Enable Mel spectrum loop mode. No value needed

Flags `B` and `V` were renamed to `Hb` and `Hv` to avoid conflicts with other UTAU flags.

## Credits

This fork is based on hifisampler, which was modified from [straycatresampler](https://github.com/UtaUtaUtau/straycat), replacing WORLD with pc-nsf-hifigan.

- [yjzxkxdn](https://github.com/yjzxkxdn)
- [openvpi](https://github.com/openvpi) for pc-nsf-hifigan
- [MinaminoTenki](https://github.com/Lanhuace-Wan)
- [Linkzerosss](https://github.com/Linkzerosss)
- [MUTED64](https://github.com/MUTED64)
- [mili-tan](https://github.com/mili-tan)
