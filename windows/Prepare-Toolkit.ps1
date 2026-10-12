[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'Common.ps1')
$root = Get-RuachRoot
$project = Split-Path -Parent (Split-Path -Parent (Get-RuachCudaRoot))
$manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'downloads.json') -Raw | ConvertFrom-Json
$cache = Join-Path $project 'toolchain\archives'
$cuda = Join-Path $project 'toolchain\cuda-12.8.1'
$extract = Join-Path $project 'toolchain\extracted'
New-Item -ItemType Directory -Force -Path $cache, $cuda, $extract | Out-Null
Add-Type -AssemblyName System.IO.Compression.FileSystem
foreach ($item in $manifest.cuda) {
    $zip = Join-Path $cache $item.filename
    Receive-RuachFile -Url $item.url -Destination $zip -Size $item.size -Sha256 $item.sha256
    $stage = Join-Path $extract $item.component
    New-Item -ItemType Directory -Force -Path $stage | Out-Null
    $stageFull = [IO.Path]::GetFullPath($stage).TrimEnd('\') + '\'
    $archive = [IO.Compression.ZipFile]::OpenRead($zip)
    try {
        foreach ($entry in $archive.Entries) {
            $target = [IO.Path]::GetFullPath((Join-Path $stage $entry.FullName))
            if (-not $target.StartsWith($stageFull, [StringComparison]::OrdinalIgnoreCase)) {
                throw "Archive entry escapes its extraction folder: $($entry.FullName)"
            }
        }
    } finally { $archive.Dispose() }
    Expand-Archive -LiteralPath $zip -DestinationPath $stage -Force
    $package = Get-ChildItem -LiteralPath $stage -Directory | Select-Object -First 1
    if (-not $package) { throw "No package directory in $zip" }
    foreach ($folder in @('bin', 'include', 'lib', 'nvvm')) {
        $source = Join-Path $package.FullName $folder
        if (Test-Path -LiteralPath $source) {
            $destination = Join-Path $cuda $folder
            New-Item -ItemType Directory -Force -Path $destination | Out-Null
            foreach ($child in Get-ChildItem -LiteralPath $source -Force) {
                Copy-Item -LiteralPath $child.FullName -Destination $destination -Recurse -Force
            }
        }
    }
}
foreach ($required in @('bin\nvcc.exe', 'include\cuda_runtime.h', 'include\cublas_v2.h', 'include\cub', 'lib\x64\cudart.lib', 'lib\x64\cublas.lib', 'lib\x64\cuda.lib')) {
    if (-not (Test-Path -LiteralPath (Join-Path $cuda $required))) { throw "Portable CUDA is incomplete: $required" }
}
$manifest.cuda | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $cuda 'ruach-components.json') -Encoding UTF8
Write-Host "Portable CUDA prepared at $cuda. No driver or global PATH was changed."
