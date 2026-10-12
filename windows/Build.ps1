[CmdletBinding()]
param([string]$CudaRoot, [ValidateRange(1,8)][int]$Jobs = 1, [ValidatePattern('^[0-9]+(;[0-9]+)*$')][string]$CudaArchitecture = '86')
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'Common.ps1')
$root = Get-RuachRoot
$env:TEMP = Join-Path $PSScriptRoot 'cache\tmp'
$env:TMP = $env:TEMP
$env:CUDA_CACHE_PATH = Join-Path $PSScriptRoot 'cache\cuda'
New-Item -ItemType Directory -Force -Path $env:TEMP, $env:CUDA_CACHE_PATH | Out-Null
$tools = Get-RuachToolchain -CudaRoot $CudaRoot
Import-RuachCompiler -Tools $tools
$build = Join-Path $PSScriptRoot 'build'
Invoke-RuachNative -Executable $tools.CMake -Arguments @(
    '-S', (Join-Path $root 'build'), '-B', $build, '-G', 'Ninja',
    '-DCMAKE_BUILD_TYPE=Release', "-DCMAKE_MAKE_PROGRAM=$($tools.Ninja)",
    "-DCMAKE_CUDA_COMPILER=$(Join-Path $tools.CudaRoot 'bin\nvcc.exe')",
    "-DCUDAToolkit_ROOT=$($tools.CudaRoot)", "-DCMAKE_CUDA_ARCHITECTURES=$CudaArchitecture",
    '-DGGML_CUDA=ON', '-DGGML_CUDA_FA=ON', '-DGGML_CUDA_FA_QUANTS=f16-f16', '-DGGML_CUDA_NCCL=OFF',
    '-DGGML_BUILD_TESTS=OFF', '-DGGML_BUILD_EXAMPLES=OFF',
    '-DHTTPLIB_REQUIRE_OPENSSL=OFF', '-DHTTPLIB_USE_OPENSSL_IF_AVAILABLE=OFF',
    '-DHTTPLIB_USE_ZLIB_IF_AVAILABLE=OFF', '-DHTTPLIB_USE_BROTLI_IF_AVAILABLE=OFF'
)
Invoke-RuachNative -Executable $tools.CMake -Arguments @('--build', $build, '--target', 'yue-server', '--parallel', [string]$Jobs)
if (-not (Test-Path -LiteralPath (Join-Path $build 'yue-server.exe'))) { throw 'The server executable was not produced.' }
Write-Host "Build completed. Run windows\Start.ps1 in a new PowerShell session."
