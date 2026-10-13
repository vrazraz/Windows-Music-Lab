[CmdletBinding()]
param(
    [ValidateSet('Status', 'Download', 'Verify', 'Build', 'Fixture', 'Pilot')][string]$Mode = 'Status',
    [long]$PendingCoreBytes = 0,
    [long]$AdditionalAiReserveBytes = 3221225472
)
$ErrorActionPreference = 'Stop'
if ($PendingCoreBytes -lt 0 -or $AdditionalAiReserveBytes -lt 0) { throw 'Resource reserves must not be negative.' }
. (Join-Path $PSScriptRoot 'Common.ps1')
$listenerRoot = Get-RuachRoot
$listenerPython = Join-Path $listenerRoot '.venv\Scripts\python.exe'
function Invoke-ListenerPython {
    param([string]$Script, [string[]]$Arguments)
    if (Test-Path -LiteralPath $listenerPython -PathType Leaf) {
        Invoke-RuachNative -Executable $listenerPython -Arguments (@($Script) + $Arguments)
    } else {
        Invoke-RuachNative -Executable 'py.exe' -Arguments (@('-3.10', $Script) + $Arguments)
    }
}
if ($Mode -in @('Status','Download','Verify')) {
    $listenerArgs = @('--pending-core-bytes', "$PendingCoreBytes", '--additional-ai-reserve-bytes', "$AdditionalAiReserveBytes")
    if ($Mode -eq 'Download') { $listenerArgs += '--download' }
    if ($Mode -eq 'Verify') { $listenerArgs += '--verify' }
    Invoke-ListenerPython -Script (Join-Path $PSScriptRoot 'listener_download.py') -Arguments $listenerArgs
    return
}
if ($Mode -in @('Fixture','Pilot')) {
    $listenerArgs = @('--pending-core-bytes', "$PendingCoreBytes")
    if ($Mode -eq 'Fixture') { $listenerArgs += '--prepare-only' }
    Invoke-ListenerPython -Script (Join-Path $PSScriptRoot 'listener_pilot.py') -Arguments $listenerArgs
    return
}
# Explicit Build/Pilot invocation is coordinated with the parent; no automatic all-stage route.
$listenerSource = Join-Path $listenerRoot 'vendor\llama.cpp'
$listenerProofPath = Join-Path $listenerSource 'source-pin.json'
if (-not (Test-Path -LiteralPath $listenerProofPath -PathType Leaf)) { throw 'Shared verified source is missing; no clone/build performed.' }
$listenerProof = Get-Content -LiteralPath $listenerProofPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($listenerProof.revision -ne '8345f333951c661d166b00e6f9362e553768f292' -or $listenerProof.verified_blob_count -ne 3687) {
    throw 'Shared source provenance does not match the approved pin.'
}
# Reuse Writer ledger/API metadata to verify every Git blob; this never duplicates source checkout.
Invoke-ListenerPython -Script (Join-Path $PSScriptRoot 'writer_setup.py') -Arguments @('source', '--root', $listenerRoot, '--pending-bytes', "$PendingCoreBytes")
$listenerFree = (Get-PSDrive -Name ([IO.Path]::GetPathRoot($listenerRoot).Substring(0,1))).Free
if ($listenerFree - $PendingCoreBytes - 3GB -lt 50GB) { throw 'CUDA build would reduce the required 50 GiB disk reserve.' }
Invoke-ListenerPython -Script (Join-Path $PSScriptRoot 'listener_resources.py') -Arguments @()
Write-Host ('CUDA compile: one job, sm86, f16-f16 FA only; disk free={0:N0} bytes. Machine-wide memory admission above is6GiB RAM /4GiB commit, not a hard cap; live critical floors4GiB RAM /2GiB commit stop only the owned build tree.' -f $listenerFree)
$listenerTools = Get-RuachToolchain
$listenerBuild = Join-Path $listenerRoot 'windows\build\listener-cuda'
$listenerCache = Join-Path $PSScriptRoot 'cache\listener'
New-Item -ItemType Directory -Force -Path $listenerCache | Out-Null
$listenerOldTemp=$env:TEMP; $listenerOldTmp=$env:TMP; $listenerOldLocation=Get-Location
try {
    Import-RuachCompiler -Tools $listenerTools
    $env:TEMP=Join-Path $listenerCache 'build-temp'; $env:TMP=$env:TEMP
    $env:CUDA_CACHE_PATH=Join-Path $listenerCache 'cuda'
    New-Item -ItemType Directory -Force -Path $env:TEMP, $env:CUDA_CACHE_PATH | Out-Null
    Set-Location -LiteralPath $listenerRoot
    $listenerArgs = @(
        '-S', $listenerSource, '-B', $listenerBuild, '-G', 'Ninja',
        '-DCMAKE_BUILD_TYPE=Release', "-DCMAKE_MAKE_PROGRAM=$($listenerTools.Ninja)",
        "-DCMAKE_CUDA_COMPILER=$(Join-Path $listenerTools.CudaRoot 'bin\nvcc.exe')",
        "-DCUDAToolkit_ROOT=$($listenerTools.CudaRoot)", '-DCMAKE_CUDA_ARCHITECTURES=86',
        '-DGGML_CUDA=ON', '-DGGML_CUDA_NCCL=OFF', '-DGGML_CUDA_CCCL_VERSION=',
        '-DGGML_CUDA_FA=ON', '-DGGML_CUDA_FA_QUANTS=f16-f16',
        '-DGGML_OPENMP=OFF', '-DGGML_VULKAN=OFF', '-DGGML_RPC=OFF', '-DBUILD_SHARED_LIBS=OFF',
        '-DLLAMA_BUILD_IS_DEV=OFF', '-DLLAMA_BUILD_COMMON=ON', '-DLLAMA_BUILD_TOOLS=ON',
        '-DLLAMA_BUILD_COMMIT=8345f333951c661d166b00e6f9362e553768f292', '-DLLAMA_BUILD_NUMBER=0',
        '-DLLAMA_BUILD_SERVER=OFF', '-DLLAMA_BUILD_TESTS=OFF', '-DLLAMA_BUILD_EXAMPLES=OFF',
        '-DLLAMA_BUILD_APP=OFF', '-DLLAMA_BUILD_UI=OFF', '-DLLAMA_USE_PREBUILT_UI=OFF',
        '-DLLAMA_OPENSSL=OFF', '-DLLAMA_BUILD_BORINGSSL=OFF', '-DLLAMA_BUILD_LIBRESSL=OFF',
        '-DLLAMA_LLGUIDANCE=OFF', '-DLLAMA_SUBPROCESS=OFF', '-DFETCHCONTENT_FULLY_DISCONNECTED=ON'
    )
    & $listenerTools.CMake @listenerArgs 2>&1 | Tee-Object -FilePath (Join-Path $listenerCache 'configure.log')
    if ($LASTEXITCODE -ne 0) { throw 'Listener configure failed; no new dependency fallback.' }
    Invoke-ListenerPython -Script (Join-Path $PSScriptRoot 'listener_resources.py') -Arguments @('--cmake', $listenerTools.CMake, '--build', $listenerBuild)
    $listenerCli=Join-Path $listenerBuild 'bin\llama-mtmd-cli.exe'
    if (-not (Test-Path -LiteralPath $listenerCli -PathType Leaf)) { throw 'Listener build produced no expected CLI.' }
    Invoke-RuachNative -Executable $listenerCli -Arguments @('--version')
    & $listenerCli --help 2>&1 | Set-Content -LiteralPath (Join-Path $listenerCache 'cli-help.txt') -Encoding UTF8
    if ($LASTEXITCODE -ne 0) { throw 'Built CLI --help failed.' }
    Write-Host "Listener CUDA binary built: $listenerCli. Real inference remains a separately coordinated Pilot stage."
} finally {
    Set-Location -LiteralPath $listenerOldLocation.Path
    $env:TEMP=$listenerOldTemp; $env:TMP=$listenerOldTmp
}
