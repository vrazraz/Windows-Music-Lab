[CmdletBinding()]
param([string]$BackendBuild, [string]$CudaRoot, [switch]$RunTests)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'Common.ps1')
$root = Get-RuachRoot
if (-not $BackendBuild) {
    $candidates = @((Join-Path $PSScriptRoot 'build'), (Join-Path (Split-Path -Parent $root) 'source\windows\build'))
    $BackendBuild = $candidates | Where-Object { Test-Path -LiteralPath (Join-Path $_ 'ggml-cuda.dll') } | Select-Object -First 1
}
if (-not $BackendBuild) { throw 'No native backend build. Run windows\Build.ps1 first, or pass -BackendBuild <existing-build-directory>.' }
$BackendBuild = [IO.Path]::GetFullPath($BackendBuild)
$build = Join-Path $PSScriptRoot 'build\full-engine'
if ($BackendBuild.TrimEnd('\') -eq $build.TrimEnd('\')) { throw 'Backend input and full-engine output must differ.' }
$cache = Get-Content -LiteralPath (Join-Path $BackendBuild 'CMakeCache.txt') -Raw
if ($cache -notmatch '(?m)^GGML_CUDA:BOOL=ON\r?$' -or $cache -notmatch '(?m)^CMAKE_BUILD_TYPE:STRING=Release\r?$') {
    throw 'Fast full-engine build requires the existing Release CUDA backend built by windows\Build.ps1.'
}
# One CPU compiler at a time, no NVCC compilation. Reject memory pressure early.
$system = Get-CimInstance Win32_OperatingSystem
if ([long]$system.FreeVirtualMemory -lt 2GB / 1KB -or [long]$system.FreePhysicalMemory -lt 2GB / 1KB) {
    throw 'Need at least 2 GiB free RAM and commit headroom; close heavy applications first.'
}
$env:TEMP = Join-Path $PSScriptRoot 'cache\full-engine-tmp'
$env:TMP = $env:TEMP
New-Item -ItemType Directory -Force -Path $env:TEMP | Out-Null
$tools = Get-RuachToolchain -CudaRoot $CudaRoot
Import-RuachCompiler -Tools $tools
Invoke-RuachNative -Executable $tools.CMake -Arguments @('-S', (Join-Path $PSScriptRoot 'native-engine'), '-B', $build,
    '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release', "-DCMAKE_MAKE_PROGRAM=$($tools.Ninja)", "-DWML_BACKEND_BUILD=$BackendBuild")
Invoke-RuachNative -Executable $tools.CMake -Arguments @('--build', $build, '--parallel', '1')
if ($RunTests) {
    $env:PATH = (Join-Path $tools.CudaRoot 'bin') + ';' + $env:PATH
    Invoke-RuachNative -Executable (Join-Path $build 'engine-boundary-tests.exe') -Arguments @()
}
Write-Host "Full engine built: $(Join-Path $build 'yue-server.exe')"
Write-Host 'Existing backend input, baseline executable, models and outputs were not changed.'
