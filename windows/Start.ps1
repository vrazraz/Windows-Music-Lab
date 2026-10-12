[CmdletBinding()]
param([ValidateRange(1024,65535)][int]$Port = 41867, [string]$CudaRoot)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'Common.ps1')
$root = Get-RuachRoot
$CudaRoot = Get-RuachCudaRoot -CudaRoot $CudaRoot
$binary = Join-Path $PSScriptRoot 'build\yue-server.exe'
$page = Join-Path $PSScriptRoot 'ui\index.html'
foreach ($file in @($binary, $page, (Join-Path $CudaRoot 'bin'))) {
    if (-not (Test-Path -LiteralPath $file)) { throw "Missing file or directory: $file" }
}
if (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue) {
    throw "Port $Port is already in use. Existing processes were left running."
}
# Download only missing models; every existing or downloaded weight must pass SHA256.
# Any failure terminates this script before yue-server is invoked.
Initialize-RuachModels
$state = Join-Path $PSScriptRoot 'state'
New-Item -ItemType Directory -Force -Path $state | Out-Null
$oldPath = $env:PATH
$oldPage = $env:RUACH_PAGE
$oldBackend = $env:GGML_BACKEND
$oldCudaCache = $env:CUDA_CACHE_PATH
$oldTemp = $env:TEMP
$oldTmp = $env:TMP
$cache = Join-Path $PSScriptRoot 'cache'
New-Item -ItemType Directory -Force -Path (Join-Path $cache 'cuda'), (Join-Path $cache 'tmp') | Out-Null
try {
    $env:PATH = (Join-Path $PSScriptRoot 'build') + ';' + (Join-Path $CudaRoot 'bin') + ';' + $oldPath
    $env:RUACH_PAGE = $page
    $env:GGML_BACKEND = 'CUDA0'
    $env:CUDA_CACHE_PATH = Join-Path $cache 'cuda'
    $env:TEMP = Join-Path $cache 'tmp'
    $env:TMP = $env:TEMP
    Write-Host "Windows Music Lab: http://localhost:$Port"
    Write-Host 'Keep this console open. Press Ctrl+C to stop the server.'
    Invoke-RuachNative -Executable $binary -Arguments @(
        '--host', '127.0.0.1', '--port', [string]$Port,
        '--model', ('Q8_0=' + (Join-Path $root 'models\YuE2-3B-Q8_0.gguf')),
        '--vae', ('standard=' + (Join-Path $root 'models\YuE2-Vae-F32.gguf')),
        '--outputs', (Join-Path $root 'outputs'),
        '--settings', (Join-Path $state 'engine-settings.json'),
        '--max-batch', '1', '--max-seq', '12288', '--vae-core', '512'
    )
} finally {
    $env:PATH = $oldPath
    $env:RUACH_PAGE = $oldPage
    $env:GGML_BACKEND = $oldBackend
    $env:CUDA_CACHE_PATH = $oldCudaCache
    $env:TEMP = $oldTemp
    $env:TMP = $oldTmp
}
