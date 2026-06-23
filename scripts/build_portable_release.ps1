param(
    [string]$Version = "dev",
    [string]$OutputRoot = "dist",
    [string]$PcNsfUrl = "https://github.com/openvpi/vocoders/releases/download/pc-nsf-hifigan-44.1k-hop512-128bin-2025.02/pc_nsf_hifigan_44.1k_hop512_128bin_2025.02.oudep",
    [string]$LoFiVocoderUrl = "https://huggingface.co/usamireko/LoFiVocoder/resolve/main/LoFiVocoder-20260203.zip",
    [string]$HnsepUrl = "https://github.com/yxlllc/vocal-remover/releases/download/hnsep_240512/hnsep_240512.zip"
)

$ErrorActionPreference = "Stop"

function Resolve-RepoRoot {
    return (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

function Reset-Directory {
    param([string]$Path)
    if (Test-Path $Path) {
        Remove-Item -LiteralPath $Path -Recurse -Force
    }
    New-Item -ItemType Directory -Force -Path $Path | Out-Null
}

function Download-And-Extract {
    param(
        [string]$Url,
        [string]$ZipPath,
        [string]$Destination
    )

    Write-Host "Downloading $Url"
    New-Item -ItemType Directory -Force -Path (Split-Path $ZipPath -Parent) | Out-Null
    Invoke-WebRequest -Uri $Url -OutFile $ZipPath
    Reset-Directory $Destination
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [System.IO.Compression.ZipFile]::ExtractToDirectory($ZipPath, $Destination)
}

function Copy-FirstFile {
    param(
        [string]$SearchRoot,
        [string[]]$Patterns,
        [string]$Destination,
        [switch]$PreferLargest
    )

    $files = @()
    foreach ($pattern in $Patterns) {
        $files += Get-ChildItem -Path $SearchRoot -Recurse -File -Filter $pattern
    }
    $files = $files | Sort-Object -Property Length -Descending

    if (-not $PreferLargest) {
        $files = $files | Sort-Object -Property FullName
    }

    $source = $files | Select-Object -First 1
    if (-not $source) {
        throw "No file found in '$SearchRoot' matching: $($Patterns -join ', ')"
    }

    New-Item -ItemType Directory -Force -Path (Split-Path $Destination -Parent) | Out-Null
    Copy-Item -LiteralPath $source.FullName -Destination $Destination -Force
    Write-Host "Copied $($source.FullName) -> $Destination"
}

function Copy-DirectoryClean {
    param(
        [string]$Source,
        [string]$Destination
    )
    Reset-Directory $Destination
    Copy-Item -Path (Join-Path $Source "*") -Destination $Destination -Recurse -Force
}

function Copy-IfExists {
    param(
        [string]$Source,
        [string]$Destination
    )

    if (Test-Path $Source) {
        Copy-Item -LiteralPath $Source -Destination $Destination -Force
        Write-Host "Copied $Source -> $Destination"
    }
    else {
        Write-Host "Skipping missing optional file: $Source"
    }
}

function Get-PythonInstallRoot {
    if ($env:pythonLocation -and (Test-Path (Join-Path $env:pythonLocation "python.exe"))) {
        return $env:pythonLocation
    }

    $pythonExe = (Get-Command python).Source
    return (Split-Path $pythonExe -Parent)
}

$repoRoot = Resolve-RepoRoot
$buildRoot = Join-Path $repoRoot "build\portable-release"
$downloadRoot = Join-Path $buildRoot "downloads"
$extractRoot = Join-Path $buildRoot "extract"
$stageRoot = Join-Path $buildRoot "hifisampler-portable-windows-cpu"
$outputRootFull = Join-Path $repoRoot $OutputRoot
$zipPath = Join-Path $outputRootFull "hifisampler-portable-windows-cpu-$Version.zip"

Reset-Directory $buildRoot
New-Item -ItemType Directory -Force -Path $outputRootFull | Out-Null

Push-Location $repoRoot
try {
    Write-Host "Syncing Python environment with uv"
    uv sync
    uv pip install pyinstaller
    uv run python -c "import torch; print(f'Build torch: {torch.__version__}, cuda={torch.version.cuda}'); assert torch.version.cuda is None, 'Expected CPU-only torch in build environment'"

    Write-Host "Building hifisampler.exe"
    dotnet publish .\client\hifisampler.csproj -c Release -r win-x64 /p:PublishAot=true /p:DebugType=none /p:DebugSymbols=false -o .\build\client-win-x64

    Write-Host "Building HifisamplerManager.exe"
    uv run pyinstaller `
        --noconfirm `
        --clean `
        --onefile `
        --noconsole `
        --name HifisamplerManager `
        --paths portable\manager `
        --collect-all customtkinter `
        --distpath build\manager-dist `
        --workpath build\manager-work `
        --specpath build\manager-spec `
        portable\manager\gui.py

    Download-And-Extract `
        -Url $PcNsfUrl `
        -ZipPath (Join-Path $downloadRoot "pc_nsf.oudep") `
        -Destination (Join-Path $extractRoot "pc_nsf")

    Download-And-Extract `
        -Url $LoFiVocoderUrl `
        -ZipPath (Join-Path $downloadRoot "lofi_vocoder.zip") `
        -Destination (Join-Path $extractRoot "lofi_vocoder")

    Download-And-Extract `
        -Url $HnsepUrl `
        -ZipPath (Join-Path $downloadRoot "hnsep.zip") `
        -Destination (Join-Path $extractRoot "hnsep")

    Write-Host "Preparing HNSEP model"
    $hnsepCandidates = @()
    $hnsepCandidates += Get-ChildItem -Path (Join-Path $extractRoot "hnsep") -Recurse -File -Filter "model.pt"
    $hnsepModel = $hnsepCandidates | Sort-Object -Property Length -Descending | Select-Object -First 1
    if (-not $hnsepModel) {
        throw "HNSEP model file not found after extraction. Expected model.pt."
    }
    $hnsepSourceDir = Split-Path $hnsepModel.FullName -Parent
    $hnsepConfig = Join-Path $hnsepSourceDir "config.yaml"
    if (-not (Test-Path $hnsepConfig)) {
        throw "HNSEP config.yaml not found next to model.pt."
    }

    Write-Host "Assembling portable folder"
    Reset-Directory $stageRoot
    Copy-DirectoryClean -Source (Join-Path $repoRoot "portable") -Destination $stageRoot

    Copy-Item -LiteralPath ".\build\manager-dist\HifisamplerManager.exe" -Destination (Join-Path $stageRoot "HifisamplerManager.exe") -Force
    Copy-Item -LiteralPath ".\build\client-win-x64\hifisampler.exe" -Destination (Join-Path $stageRoot "hifisampler.exe") -Force
    Copy-Item -LiteralPath ".\hifiserver.py" -Destination $stageRoot -Force
    Copy-Item -LiteralPath ".\config.py" -Destination $stageRoot -Force
    Copy-Item -LiteralPath ".\README.md" -Destination (Join-Path $stageRoot "README.md") -Force
    Copy-IfExists -Source ".\README_PORTABLE.md" -Destination (Join-Path $stageRoot "README_PORTABLE.md")
    Copy-Item -Path ".\backend" -Destination (Join-Path $stageRoot "backend") -Recurse -Force
    Copy-Item -Path ".\util" -Destination (Join-Path $stageRoot "util") -Recurse -Force
    Copy-Item -Path ".\hnsep" -Destination (Join-Path $stageRoot "hnsep") -Recurse -Force
    if (Test-Path (Join-Path $stageRoot "hnsep\vr")) {
        Remove-Item -LiteralPath (Join-Path $stageRoot "hnsep\vr") -Recurse -Force
    }

    Write-Host "Preparing portable Python runtime"
    Reset-Directory (Join-Path $stageRoot "runtime")
    $pythonRoot = Get-PythonInstallRoot
    Copy-Item -Path (Join-Path $pythonRoot "*") -Destination (Join-Path $stageRoot "runtime") -Recurse -Force
    $runtimePython = Join-Path $stageRoot "runtime\python.exe"
    uv pip install --python $runtimePython --system --index-url https://download.pytorch.org/whl/cpu torch
    uv pip install --python $runtimePython --system --extra-index-url https://download.pytorch.org/whl/cpu -r .\requirements.txt
    & $runtimePython -c "import torch; print(f'Runtime torch: {torch.__version__}, cuda={torch.version.cuda}'); assert torch.version.cuda is None, 'Expected CPU-only torch in portable runtime'"

    Copy-FirstFile `
        -SearchRoot (Join-Path $extractRoot "pc_nsf") `
        -Patterns @("model.onnx", "*.onnx") `
        -Destination (Join-Path $stageRoot "models\pc_nsf_hifigan_44.1k_hop512_128bin_2025.02\model.onnx") `
        -PreferLargest

    Copy-FirstFile `
        -SearchRoot (Join-Path $extractRoot "lofi_vocoder") `
        -Patterns @("model.onnx", "*.onnx") `
        -Destination (Join-Path $stageRoot "models\lofi_vocoder\model.onnx") `
        -PreferLargest

    New-Item -ItemType Directory -Force -Path (Join-Path $stageRoot "models\hnsep\vr") | Out-Null
    Copy-Item -LiteralPath $hnsepModel.FullName -Destination (Join-Path $stageRoot "models\hnsep\vr\model.pt") -Force
    Copy-Item -LiteralPath $hnsepConfig -Destination (Join-Path $stageRoot "models\hnsep\vr\config.yaml") -Force

    Write-Host "Preparing config in staged portable folder"
    & (Join-Path $stageRoot "runtime\python.exe") (Join-Path $stageRoot "manager\prepare_portable.py")
    if ($LASTEXITCODE -ne 0) {
        throw "prepare_portable.py failed in staged portable folder."
    }

    Write-Host "Validating staged portable folder"
    & (Join-Path $stageRoot "runtime\python.exe") (Join-Path $stageRoot "manager\check_environment.py")
    if ($LASTEXITCODE -ne 0) {
        throw "check_environment.py failed in staged portable folder."
    }

    if (Test-Path $zipPath) {
        Remove-Item -LiteralPath $zipPath -Force
    }
    Write-Host "Creating $zipPath"
    Compress-Archive -Path $stageRoot -DestinationPath $zipPath -Force
    Write-Host "Portable release created: $zipPath"
}
finally {
    Pop-Location
}
