[CmdletBinding()]
param(
    [ValidateSet('Preflight','Source','Models','Build','All')][string]$Stage='All',
    [long]$PendingReservedBytes=0,
    [string]$PythonPath
)
$ErrorActionPreference='Stop'
$writerRoot=Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'Common.ps1')
. (Join-Path $PSScriptRoot 'Writer.Common.ps1')
$writerCache=Join-Path $PSScriptRoot 'cache\writer'
New-Item -ItemType Directory -Force -Path $writerCache | Out-Null
function Invoke-WriterPython {
    param([string[]]$Arguments)
    $helper=Join-Path $PSScriptRoot 'writer_setup.py'
    if($PythonPath){Invoke-RuachNative -Executable $PythonPath -Arguments (@($helper)+$Arguments)}
    else{Invoke-RuachNative -Executable 'py.exe' -Arguments (@('-3.10',$helper)+$Arguments)}
}
function Invoke-WriterBuild {
    param([string]$Executable,[string[]]$Arguments,[string]$BuildPath,[string]$LogName)
    $stdout=Join-Path $writerCache ($LogName+'.log')
    $stderr=Join-Path $writerCache ($LogName+'.stderr.log')
    $commandLine=($Arguments|ForEach-Object {Quote-WriterArgument ([string]$_)}) -join ' '
    $launch=@{FilePath=$Executable;ArgumentList=$commandLine;WorkingDirectory=$writerRoot;WindowStyle='Hidden';PassThru=$true;
        RedirectStandardOutput=$stdout;RedirectStandardError=$stderr}
    $process=$null
    try{
        $process=Start-Process @launch
        $null=$process.Handle
        $next=[DateTime]::MinValue
        while(-not $process.HasExited){
            if([DateTime]::UtcNow -ge $next){
                $drive=Get-PSDrive -Name ([IO.Path]::GetPathRoot($writerRoot).Substring(0,1))
                if($drive.Free - $PendingReservedBytes -lt 50GB){throw 'Build paused to retain the approved 50 GiB disk reserve.'}
                $total=[long]0
                if(Test-Path -LiteralPath $BuildPath){
                    Get-ChildItem -LiteralPath $BuildPath -File -Recurse -ErrorAction SilentlyContinue|ForEach-Object {$total+=$_.Length}
                }
                if($total -gt 2GB){throw 'CPU build exceeded the 2 GiB phase working budget.'}
                $memory=Get-CimInstance Win32_PerfFormattedData_PerfOS_Memory
                $headroom=[long]$memory.CommitLimit-[long]$memory.CommittedBytes
                if($memory.AvailableBytes -lt 6GB -or $headroom -lt 4GB){throw 'CPU build memory guard paused its owned process tree.'}
                Write-Host "$($LogName): one build job, files $total B, commit headroom $headroom B"
                $next=[DateTime]::UtcNow.AddSeconds(10)
            }
            Start-Sleep -Milliseconds 300
        }
        $process.WaitForExit()
        if($process.ExitCode -ne 0){throw "$LogName failed; see $stdout and $stderr"}
        Get-Content -LiteralPath $stdout -Tail 8
    }finally{
        if($process -and -not $process.HasExited){
            & taskkill.exe /PID $process.Id /T /F | Out-Null
            $process.WaitForExit(5000)|Out-Null
        }
    }
}

$oldTemp=$env:TEMP;$oldTmp=$env:TMP;$oldLocation=Get-Location
try {
    $env:TEMP=$writerCache;$env:TMP=$writerCache
    Set-Location -LiteralPath $writerRoot
    $preflight=if($Stage -eq 'Preflight'){'preflight'}elseif($Stage -eq 'Build'){'preflight-build'}else{'preflight-files'}
    Invoke-WriterPython -Arguments @($preflight,'--root',$writerRoot,'--pending-bytes',[string]$PendingReservedBytes)
    if($Stage -eq 'Preflight'){return}
    if($Stage -in 'Source','All'){Invoke-WriterPython -Arguments @('source','--root',$writerRoot,'--pending-bytes',[string]$PendingReservedBytes)}
    if($Stage -in 'Models','All'){Invoke-WriterPython -Arguments @('models','--root',$writerRoot,'--pending-bytes',[string]$PendingReservedBytes)}
    if($Stage -in 'Build','All'){
        Invoke-WriterPython -Arguments @('preflight-build','--root',$writerRoot,'--pending-bytes',[string]$PendingReservedBytes)
        $source=Join-Path $writerRoot 'vendor\llama.cpp'
        $proofPath=Join-Path $source 'source-pin.json'
        if(-not(Test-Path -LiteralPath $proofPath)){throw 'Verified source provenance is missing; no build executed.'}
        $proof=Get-Content -LiteralPath $proofPath -Raw -Encoding UTF8|ConvertFrom-Json
        if($proof.revision -ne '8345f333951c661d166b00e6f9362e553768f292' -or $proof.verified_blob_count -ne 3687){throw 'Unexpected source provenance.'}
        Invoke-WriterPython -Arguments @('source','--root',$writerRoot,'--pending-bytes',[string]$PendingReservedBytes)
        $disk=Get-PSDrive -Name ([IO.Path]::GetPathRoot($writerRoot).Substring(0,1))
        if($disk.Free - $PendingReservedBytes - 2GB -lt 50GB){throw 'CPU build would reduce the approved 50 GiB disk reserve.'}
        $vs=Join-Path ([Environment]::GetFolderPath('ProgramFilesX86')) 'Microsoft Visual Studio\2022\BuildTools'
        $cmake=Join-Path $vs 'Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe'
        if(-not(Test-Path -LiteralPath $cmake)){throw 'Existing Visual Studio CMake absent; no installer ran.'}
        $build=Join-Path $PSScriptRoot 'build\writer-cpu'
        $args=@(
            '-S',$source,'-B',$build,'-G','Visual Studio 17 2022','-A','x64',
            '-DGGML_CUDA=OFF','-DGGML_VULKAN=OFF','-DGGML_RPC=OFF','-DGGML_OPENMP=OFF',
            '-DBUILD_SHARED_LIBS=OFF','-DLLAMA_BUILD_IS_DEV=OFF',
            '-DLLAMA_BUILD_COMMIT=8345f333951c661d166b00e6f9362e553768f292','-DLLAMA_BUILD_NUMBER=0',
            '-DLLAMA_BUILD_COMMON=ON','-DLLAMA_BUILD_SERVER=ON','-DLLAMA_BUILD_TOOLS=ON',
            '-DLLAMA_BUILD_TESTS=OFF','-DLLAMA_BUILD_EXAMPLES=OFF','-DLLAMA_BUILD_APP=OFF',
            '-DLLAMA_BUILD_UI=OFF','-DLLAMA_USE_PREBUILT_UI=OFF',
            '-DLLAMA_OPENSSL=OFF','-DLLAMA_BUILD_BORINGSSL=OFF','-DLLAMA_BUILD_LIBRESSL=OFF',
            '-DLLAMA_LLGUIDANCE=OFF','-DLLAMA_SUBPROCESS=OFF',
            '-DFETCHCONTENT_FULLY_DISCONNECTED=ON'
        )
        Invoke-WriterBuild -Executable $cmake -Arguments $args -BuildPath $build -LogName 'configure'
        Invoke-WriterBuild -Executable $cmake -Arguments @('--build',$build,'--config','Release','--target','llama-server','--parallel','1') -BuildPath $build -LogName 'build'
        $exe=Join-Path $build 'bin\Release\llama-server.exe'
        if(-not(Test-Path -LiteralPath $exe)){throw 'Writer build produced no expected binary.'}
        Invoke-RuachNative -Executable $exe -Arguments @('--version')
        Save-WriterJson (Join-Path $writerCache 'build-proof.json') @{
            schema_version=1;source_revision=$proof.revision;
            binary='windows/build/writer-cpu/bin/Release/llama-server.exe';
            binary_bytes=(Get-Item -LiteralPath $exe).Length;binary_sha256=(Get-RuachSha256 $exe);
            version_execution_passed=$true;cpu_only=$true;built_utc=[DateTime]::UtcNow.ToString('o')
        }
        Write-Host "Writer CPU binary: $exe"
    }
} finally {
    Set-Location -LiteralPath $oldLocation.Path
    $env:TEMP=$oldTemp;$env:TMP=$oldTmp
}