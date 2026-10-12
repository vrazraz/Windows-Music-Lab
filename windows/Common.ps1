Set-StrictMode -Version Latest

function Get-RuachRoot { Split-Path -Parent $PSScriptRoot }

function Invoke-RuachNative {
    param([string]$Executable, [string[]]$Arguments)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Executable exited with code $LASTEXITCODE." }
}

function Get-RuachCudaRoot {
    param([string]$CudaRoot)
    if ($CudaRoot) { return [IO.Path]::GetFullPath($CudaRoot) }
    $root = Get-RuachRoot
    $local = Join-Path $root 'toolchain\cuda-12.8.1'
    $legacy = Join-Path (Split-Path -Parent $root) 'toolchain\cuda-12.8.1'
    if (Test-Path -LiteralPath $local) { return $local }
    if (Test-Path -LiteralPath $legacy) { return $legacy }
    return $local
}

function Get-RuachToolchain {
    param([string]$CudaRoot)
    $root = Get-RuachRoot
    $CudaRoot = Get-RuachCudaRoot -CudaRoot $CudaRoot
    $editions = @(
        (Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\2022\BuildTools'),
        (Join-Path $env:ProgramFiles 'Microsoft Visual Studio\2022\Community'),
        (Join-Path $env:ProgramFiles 'Microsoft Visual Studio\2022\Professional'),
        (Join-Path $env:ProgramFiles 'Microsoft Visual Studio\2022\Enterprise')
    )
    $vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
    if (Test-Path -LiteralPath $vswhere) {
        $found = & $vswhere -latest -version '[17.0,18.0)' -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
        if ($found) { $editions = $editions + @($found) }
    }
    $vs = $editions | Where-Object { Test-Path -LiteralPath (Join-Path $_ 'VC\Auxiliary\Build\vcvars64.bat') } | Select-Object -First 1
    if (-not $vs) { throw 'Visual Studio 2022 C++ Build Tools were not found.' }
    $cmakeCommand = Get-Command cmake.exe -ErrorAction SilentlyContinue
    $ninjaCommand = Get-Command ninja.exe -ErrorAction SilentlyContinue
    $cmake = if ($cmakeCommand) { $cmakeCommand.Source } else { Join-Path $vs 'Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe' }
    $ninja = if ($ninjaCommand) { $ninjaCommand.Source } else { Join-Path $vs 'Common7\IDE\CommonExtensions\Microsoft\CMake\Ninja\ninja.exe' }
    foreach ($file in @($cmake, $ninja, (Join-Path $CudaRoot 'bin\nvcc.exe'))) {
        if (-not (Test-Path -LiteralPath $file)) { throw "Missing tool: $file" }
    }
    [pscustomobject]@{ CudaRoot = [IO.Path]::GetFullPath($CudaRoot); CMake = $cmake; Ninja = $ninja; Vcvars = Join-Path $vs 'VC\Auxiliary\Build\vcvars64.bat' }
}

function Import-RuachCompiler {
    param($Tools)
    $env:VSLANG = '1033'
    $start = New-Object Diagnostics.ProcessStartInfo
    $start.FileName = $env:ComSpec
    $start.Arguments = '/d /u /s /c "call "' + $Tools.Vcvars + '" >nul && set"'
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    $start.StandardOutputEncoding = [Text.Encoding]::Unicode
    $process = [Diagnostics.Process]::Start($start)
    $output = $process.StandardOutput.ReadToEnd()
    $errorText = $process.StandardError.ReadToEnd()
    $process.WaitForExit()
    if ($process.ExitCode -ne 0) { throw "vcvars64.bat failed: $errorText" }
    $lines = $output -split '\r?\n'
    foreach ($line in $lines) {
        if ($line -match '^([^=]+)=(.*)$') { [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2], 'Process') }
    }
    $env:PATH = (Split-Path -Parent $Tools.Ninja) + ';' + (Join-Path $Tools.CudaRoot 'bin') + ';' + $env:PATH
    $env:CUDA_PATH = $Tools.CudaRoot
    $env:CUDAToolkit_ROOT = $Tools.CudaRoot
}

function Get-RuachSha256 {
    param([string]$Path)
    $stream = [IO.File]::OpenRead($Path)
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($sha.ComputeHash($stream))).Replace('-', '').ToLowerInvariant() }
    finally { $sha.Dispose(); $stream.Dispose() }
}

function Receive-RuachFile {
    param([string]$Url, [string]$Destination, [long]$Size, [string]$Sha256)
    if ($Size -le 0 -or $Sha256 -notmatch '^[0-9a-fA-F]{64}$') { throw 'Invalid pinned size or SHA256.' }
    if (Test-Path -LiteralPath $Destination) {
        Write-Host "Verifying SHA256: $Destination"
        if ((Get-Item -LiteralPath $Destination).Length -eq $Size -and
            (Get-RuachSha256 -Path $Destination) -eq $Sha256) {
            Write-Host "Verified existing file; no download: $Destination"
            return
        }
        throw "Existing file does not match the pinned checksum; kept unchanged. Move it aside and retry: $Destination"
    }
    $parent = Split-Path -Parent $Destination
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
    $part = $Destination + '.part'
    # A complete verified .part can be finalized without another HTTP request.
    $completePart = (Test-Path -LiteralPath $part) -and (Get-Item -LiteralPath $part).Length -eq $Size
    if (-not $completePart) {
        Write-Host ("Downloading {0:N2} GiB: {1} (resuming any .part file)" -f ($Size / 1GB), (Split-Path -Leaf $Destination))
        Invoke-RuachNative -Executable 'curl.exe' -Arguments @(
            '--fail', '--location', '--progress-bar', '--show-error', '--retry', '3',
            '--retry-delay', '5', '--continue-at', '-', '--proto', '=https', '--proto-redir', '=https',
            '--output', $part, $Url
        )
    }
    if ((Get-Item -LiteralPath $part).Length -ne $Size) { throw "Incorrect download size; engine will not start. Partial file kept for retry: $part" }
    Write-Host "Verifying downloaded SHA256: $part"
    if ((Get-RuachSha256 -Path $part) -ne $Sha256) {
        throw "SHA256 mismatch; engine will not start. Move the .part file aside and retry: $part"
    }
    Move-Item -LiteralPath $part -Destination $Destination
    Write-Host "SHA256 verified: $Destination"
}

function Initialize-RuachModels {
    param([string]$ModelsRoot, $Manifest)
    if (-not $ModelsRoot) { $ModelsRoot = Join-Path (Get-RuachRoot) 'models' }
    if (-not $Manifest) { $Manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'downloads.json') -Raw | ConvertFrom-Json }
    $expected = @('YuE2-3B-Q8_0.gguf', 'YuE2-Vae-F32.gguf')
    if (@($Manifest.models).Count -ne 2) { throw 'The model manifest must contain exactly the backbone and VAE.' }
    $seen = @()
    # Validate every entry before starting any download or touching a destination.
    foreach ($item in $Manifest.models) {
        if ($item.filename -notin $expected -or $item.filename -in $seen) { throw 'Unexpected or duplicate model filename.' }
        $seen += $item.filename
        $uri = [Uri]$item.url
        $pinnedPath = '/Serveurperso/YuE2-GGUF/resolve/64b030e3deb6e8150d2b7c0db641ef5a17eca8a3/' + $item.filename
        if ($uri.Scheme -ne 'https' -or $uri.Host -ne 'huggingface.co' -or $uri.AbsolutePath -ne $pinnedPath -or $uri.Query -or $uri.UserInfo) {
            throw 'Unexpected model source: only the pinned public Hugging Face revision is allowed.'
        }
        if ([long]$item.size -le 0 -or [string]$item.sha256 -notmatch '^[0-9a-fA-F]{64}$') { throw 'Invalid model size or SHA256.' }
    }
    foreach ($item in $Manifest.models) {
        Receive-RuachFile -Url $item.url -Destination (Join-Path $ModelsRoot $item.filename) -Size $item.size -Sha256 $item.sha256
    }
    Write-Host 'Both pinned GGUF models are complete and SHA256 verified.'
}
