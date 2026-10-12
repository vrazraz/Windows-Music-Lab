[CmdletBinding()]
param(
    [ValidateSet('Resolve','Audit','Download','Install','Validate','FFmpeg','All')]
    [string]$Phase = 'Resolve',
    [ValidateSet('core','art')][string[]]$InstallProfiles = @('core','art'),
    [switch]$CheckCuda
)
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$cache=Join-Path $PSScriptRoot 'cache\validation-runtime'
$wheels=Join-Path $cache 'wheels'
$old=@{}
foreach ($key in @('TEMP','TMP','PIP_CACHE_DIR','PIP_CONFIG_FILE','PIP_DISABLE_PIP_VERSION_CHECK','HF_HOME','HF_HUB_OFFLINE','HF_HUB_DISABLE_TELEMETRY','TRANSFORMERS_OFFLINE','DIFFUSERS_OFFLINE','PYTHONUTF8','PYTHONIOENCODING')) {
    $old[$key]=[Environment]::GetEnvironmentVariable($key,'Process')
}
function Assert-Disk {
    $drive=New-Object IO.DriveInfo([IO.Path]::GetPathRoot($root))
    if ($drive.AvailableFreeSpace -lt 50GB) { throw 'At least 50 GiB free disk is required.' }
}
function Run-Native {
    param([string]$Exe,[string[]]$ArgList)
    & $Exe @ArgList
    if ($LASTEXITCODE -ne 0) { throw "$Exe failed with exit code $LASTEXITCODE." }
}
function Python-For([string]$profile) {
    $name=if ($profile -eq 'art') { '.venv-art' } else { '.venv' }
    Join-Path $root "$name\Scripts\python.exe"
}
function Prepare-FFmpeg {
    Assert-Disk
    . (Join-Path $PSScriptRoot 'Common.ps1')
    $archives=Join-Path $root 'toolchain\archives'
    $archive=Join-Path $archives 'ffmpeg-9.0.2-essentials_build.zip'
    Receive-RuachFile -Url 'https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-9.0.2-essentials_build.zip' -Destination $archive -Size 114768076 -Sha256 '60f467265b1e312373dbcd92200c2618a74850f98d3d078e94296bb3fa2047ba'
    $staging=Join-Path $root 'toolchain\ffmpeg-9.0.2-extracted'
    $destination=Join-Path $root 'toolchain\ffmpeg9.0.2'
    $alias=Join-Path $root 'toolchain\ffmpeg'
    if (-not (Test-Path -LiteralPath (Join-Path $destination 'bin\ffmpeg.exe'))) {
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        $zip=[IO.Compression.ZipFile]::OpenRead($archive)
        try {
            $boundary=[IO.Path]::GetFullPath($staging).TrimEnd('\')+'\'
            foreach ($entry in $zip.Entries) {
                if ([IO.Path]::IsPathRooted($entry.FullName) -or $entry.FullName.Contains(':')) { throw 'Rooted/ADS ZIP path rejected.' }
                $candidate=[IO.Path]::GetFullPath((Join-Path $staging $entry.FullName))
                if (-not $candidate.StartsWith($boundary,[StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe ZIP path rejected.' }
            }
        } finally { $zip.Dispose() }
        if (Test-Path -LiteralPath $staging) { throw 'Existing extraction directory kept unchanged; inspect it before retry.' }
        Expand-Archive -LiteralPath $archive -DestinationPath $staging
        $contents=Join-Path $staging 'ffmpeg-9.0.2-essentials_build'
        if (-not (Test-Path -LiteralPath (Join-Path $contents 'bin\ffmpeg.exe'))) { throw 'Unexpected FFmpeg archive layout.' }
        if (Test-Path -LiteralPath $destination) { throw 'Existing FFmpeg directory kept unchanged.' }
        # Verified absolute paths remain under this repository's own toolchain.
        $toolBoundary=[IO.Path]::GetFullPath((Join-Path $root 'toolchain')).TrimEnd('\')+'\'
        foreach ($path in @($contents,$destination)) {
            if (-not [IO.Path]::GetFullPath($path).StartsWith($toolBoundary,[StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe move destination.' }
        }
        Move-Item -LiteralPath $contents -Destination $destination
    }
    if (-not (Test-Path -LiteralPath $alias)) { New-Item -ItemType Junction -Path $alias -Target $destination | Out-Null }
    foreach ($name in @('ffmpeg','ffprobe')) { Run-Native (Join-Path $alias "bin\$name.exe") @('-version') }
    Assert-Disk
}
try {
    Push-Location $root
    Assert-Disk
    foreach ($path in @($cache,$wheels,(Join-Path $cache 'tmp'),(Join-Path $cache 'pip'),(Join-Path $cache 'huggingface'))) { New-Item -ItemType Directory -Force -Path $path | Out-Null }
    $env:TEMP=Join-Path $cache 'tmp'; $env:TMP=$env:TEMP
    $env:PIP_CACHE_DIR=Join-Path $cache 'pip'; $env:PIP_CONFIG_FILE='NUL'; $env:PIP_DISABLE_PIP_VERSION_CHECK='1'
    $env:PYTHONUTF8='1'; $env:PYTHONIOENCODING='utf-8'; $env:HF_HOME=Join-Path $cache 'huggingface'; $env:HF_HUB_DISABLE_TELEMETRY='1'
    foreach ($profile in @('core','art')) {
        $python=Python-For $profile
        if (-not (Test-Path -LiteralPath $python)) {
            $name=if ($profile -eq 'art') { '.venv-art' } else { '.venv' }
            Run-Native 'py.exe' @('-3.10','-m','venv',(Join-Path $root $name))
        }
    }
    if ($Phase -in @('Resolve','All')) {
        foreach ($profile in @('core','art')) {
            Run-Native (Python-For $profile) @((Join-Path $PSScriptRoot 'resolve_validation_runtime.py'),$profile)
        }
    }
    if ($Phase -in @('Audit','All')) { Run-Native 'py.exe' @('-3.10',(Join-Path $PSScriptRoot 'audit_validation_runtime.py'),'audit') }
    if ($Phase -in @('Download','All')) { Run-Native 'py.exe' @('-3.10',(Join-Path $PSScriptRoot 'audit_validation_runtime.py'),'download') }
    if ($Phase -in @('Install','All')) {
        if (-not (Test-Path -LiteralPath (Join-Path $cache 'audited-runtime.json'))) { throw 'Run the publisher metadata audit first.' }
        foreach ($profile in $InstallProfiles) {
            Assert-Disk
            Run-Native (Python-For $profile) @('-m','pip','install','--no-index','--find-links',$wheels,'--only-binary=:all:','--require-hashes','--no-deps',
                '-r',(Join-Path $PSScriptRoot "requirements-validation-$profile.lock.txt"))
            Run-Native (Python-For $profile) @('-m','pip','check')
            $snapshot=& (Python-For $profile) -m pip list --format=json
            if ($LASTEXITCODE -ne 0) { throw 'Installed package snapshot failed.' }
            [IO.File]::WriteAllText((Join-Path $cache "installed-$profile.json"),($snapshot -join "`n"),[Text.UTF8Encoding]::new($false))
        }
        Assert-Disk
    }
    if ($Phase -in @('FFmpeg','All')) { Prepare-FFmpeg }
    if ($Phase -in @('Validate','All')) {
        $env:HF_HUB_OFFLINE='1'; $env:TRANSFORMERS_OFFLINE='1'; $env:DIFFUSERS_OFFLINE='1'
        foreach ($profile in @('core','art')) {
            Run-Native (Python-For $profile) @((Join-Path $PSScriptRoot 'validate_validation_runtime.py'),$profile)
        }
        $ffmpeg=Join-Path $root 'toolchain\ffmpeg9.0.2\bin\ffmpeg.exe'
        $version=& $ffmpeg -version
        if ($LASTEXITCODE -ne 0 -or ($version -join "`n") -notmatch 'ffmpeg version 9\.0\.2') { throw 'Approved FFmpeg version validation failed.' }
        $ready=[ordered]@{
            schemaVersion=1; completed=$true; completedUtc=[DateTime]::UtcNow.ToString('o')
            profiles=[ordered]@{
                core=(Get-Content -LiteralPath (Join-Path $cache 'validated-core.json') -Raw -Encoding UTF8 | ConvertFrom-Json)
                art=(Get-Content -LiteralPath (Join-Path $cache 'validated-art.json') -Raw -Encoding UTF8 | ConvertFrom-Json)
            }
            ffmpeg=[ordered]@{version=($version | Select-Object -First 1); pathRelative='toolchain/ffmpeg9.0.2/bin/ffmpeg.exe'; sha256=(Get-FileHash -LiteralPath $ffmpeg -Algorithm SHA256).Hash.ToLowerInvariant()}
        }
        $readyPath=Join-Path $cache 'ready.json'
        $readyPart=$readyPath+'.part'
        [IO.File]::WriteAllText($readyPart,($ready | ConvertTo-Json -Depth 8),[Text.UTF8Encoding]::new($false))
        Move-Item -LiteralPath $readyPart -Destination $readyPath -Force
        Write-Host 'Validated runtime ready marker written; no inference ran.'
        if ($CheckCuda) { Run-Native (Python-For 'core') @('-c','import torch; assert torch.cuda.is_available(); print(torch.cuda.get_device_name(0),torch.cuda.get_device_properties(0).total_memory)') }
    }
} finally {
    Pop-Location
    foreach ($key in $old.Keys) { [Environment]::SetEnvironmentVariable($key,$old[$key],'Process') }
}