# hifisampler

Portable Windows fork of hifisampler focused on simple OpenUTAU setup.

This fork packages hifisampler as a user-friendly portable folder: no YAML editing, no symbolic links, no admin permissions, and clear errors when something is missing.

## Starting

Use the latest portable Windows release:

```text
hifisampler-portable-windows-<version>.zip
```

The release package is intended to include:

```text
HifisamplerManager.exe
hifisampler.exe
hifiserver.py
config.yaml
config.default.yaml
backend/
util/
hnsep/
manager/
models/
logs/
runtime/
```

`HifisamplerManager.exe` is the main app. The `.bat` files are kept as fallback/debug tools.

## Quick Start

1. Download the latest `hifisampler-portable-windows-<version>.zip` from Releases.
2. Extract it to a normal user-writable folder, such as `Documents\hifisampler`.
3. Run `HifisamplerManager.exe`.
4. Click `Prepare Portable`.
5. Choose a model profile if needed.
6. Click `Install to OpenUTAU`.
7. Click `Start Server`.
8. Open OpenUTAU.
9. Select `hifisampler` as the resampler.

No admin permissions are required.

## OpenUTAU Setup

The manager copies `hifisampler.exe` into:

```text
<OpenUTAU folder>\Resamplers\hifisampler.exe
```

It creates `Resamplers\` if missing. 
## Model Profiles

The manager can switch models without manual config editing.

Included profiles:

```text
PC-NSF HiFiGAN
LoFiVocoder
```

Expected model layout:

```text
models/
  pc_nsf/
    model.profile.yaml
    model.onnx
  lofi_vocoder/
    model.profile.yaml
    model.onnx
  hnsep/
    vr/
      model.onnx
      config.yaml
```

Use the model selector in `Hifisampler Manager`, then click `Apply Model`. If the server is running, restart it to apply the selected model.

## Acceleration

The manager can switch supported profiles between CPU and DirectML.

```text
PC-NSF HiFiGAN: CPU or DirectML
LoFiVocoder: CPU only
```

When DirectML is selected, choose the GPU adapter from the device dropdown. 


## Manager Actions

`Prepare Portable`

Creates required folders, generates/updates `config.yaml`, normalizes paths, and applies the selected model profile.

`Check Environment`

Checks Python, required packages, ONNXRuntime, CUDA status(not yet), model files, `hifisampler.exe`, `hifiserver.py`, and config.

`Install to OpenUTAU`

Copies `hifisampler.exe` into OpenUTAU's `Resamplers` folder.

`Start Server`

Starts `hifiserver.py` using the bundled runtime when available. Server output is shown in the manager and written to `logs/server.log`.

## Fallback Scripts

These scripts are included for troubleshooting:

```text
START_HIFISAMPLER.bat
PREPARE_PORTABLE.bat
INSTALL_TO_OPENUTAU.bat
CHECK_ENVIRONMENT.bat
REPAIR_CONFIG.bat
```

Normally, users should run `HifisamplerManager.exe`.

## Troubleshooting

### Server Does Not Start

Open `HifisamplerManager.exe` and click `Check Environment`. Also check:

```text
logs/server.log
```

### Python Runtime Missing

Use the full portable release package. Development checkouts can fall back to system Python, but release users should not need to install Python manually.

### Model Missing

Click `Check Environment`. Missing model files are reported as:

```text
ERROR: model file missing: ...
```

For release zips, models should already be included. For development builds, place models under `models/` using the expected model layout above.

### OpenUTAU Cannot See The Resampler

Run `Install to OpenUTAU` again and make sure the selected folder is the OpenUTAU folder that contains or should contain `Resamplers\`.

### Slow Speed

Check if you are using CPU, switch to DirectML and pick your best GPU.

### CUDA Build

CUDA builds should be released as separate assets later. They require compatible NVIDIA drivers and matching CUDA/PyTorch packages.

## Development

Install dependencies with UV:

```bash
uv sync
```

Run the server from a development checkout:

```bash
uv run hifiserver.py
```

Run the manager from a development checkout:

```bash
uv run python portable/manager/gui.py
```

Build a portable release locally on Windows:

```powershell
.\scripts\build_portable_release.ps1 -Version dev
```

The full GitHub release workflow is documented in:

```text
docs/RELEASING.md
```


## Implemented Flags

- **g:** Adjust gender/formants.
  - Range: `-600` to `600` | Default: `0`
- **Hb:** Adjust breath/noise.
  - Range: `0` to `500` | Default: `100`
- **Hv:** Adjust voice/harmonic.
  - Range: `0` to `150` | Default: `100`
- **HG:** Vocal fry/growl.
  - Range: `0` to `100` | Default: `0`
- **P:** Normalize loudness at the note level, targeting -16 LUFS. Enable this with `wave_norm: true` in `config.yaml`.
  - Range: `0` to `100` | Default: `100`
- **t:** Shift pitch in cents. 1 cent = 1/100 of a semitone.
  - Range: `-1200` to `1200` | Default: `0`
- **Ht:** Adjust tension.
  - Range: `-100` to `100` | Default: `0`
- **A:** Modulate amplitude based on pitch variations.
  - Range: `-100` to `100` | Default: `0`
- **G:** Force feature cache regeneration.
  - No value needed
- **He:** Enable Mel spectrum loop mode.
  - No value needed

The flags `B` and `V` were renamed to `Hb` and `Hv` because they conflict with other UTAU flags.

## Credits

This fork is based on hifisampler, which was modified from [straycatresampler](https://github.com/UtaUtaUtau/straycat), replacing WORLD with pc-nsf-hifigan.

Acknowledgments from the original project:

- [yjzxkxdn](https://github.com/yjzxkxdn)
- [openvpi](https://github.com/openvpi) for pc-nsf-hifigan
- [MinaminoTenki](https://github.com/Lanhuace-Wan)
- [Linkzerosss](https://github.com/Linkzerosss)
- [MUTED64](https://github.com/MUTED64)
- [mili-tan](https://github.com/mili-tan)
