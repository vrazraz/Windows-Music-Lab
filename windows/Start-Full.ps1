# Native full studio supervisor; process-scoped settings only (2026-10-12).
[CmdletBinding()]
param(
    [ValidateRange(1024,65535)][int]$Port=41868,
    [ValidateRange(1024,65535)][int]$LabPort=41871,
    [string]$EnginePath,
    [string]$ModelsRoot,
    [string]$PythonPath,
    [string]$CudaRoot,
    [ValidateRange(0,15)][int]$Gpu=0,
    [switch]$StdlibOnly,
    [switch]$WithoutWriter
)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'Common.ps1')
$root=Get-RuachRoot
if($Port -eq $LabPort){throw 'Engine and lab ports must differ.'}
if($Port -eq 41872 -or $LabPort -eq 41872){throw 'Port41872 is reserved for the local Writer. Choose different Studio/Lab ports.'}
foreach($number in @($Port,$LabPort)){
    if(Get-NetTCPConnection -State Listen -LocalPort $number -ErrorAction SilentlyContinue){throw "Port $number is already occupied; existing processes were left running."}
}
if(-not $EnginePath){$EnginePath=Join-Path $PSScriptRoot 'build\full-engine\yue-server.exe';if(-not(Test-Path -LiteralPath $EnginePath)){$EnginePath=Join-Path $PSScriptRoot 'build\yue-server.exe'}}
if(-not $ModelsRoot){
    $ModelsRoot=Join-Path $root 'models'
    $existing=Join-Path (Split-Path -Parent $root) 'source\models'
    if(-not(Test-Path -LiteralPath (Join-Path $ModelsRoot 'YuE2-3B-Q8_0.gguf')) -and (Test-Path -LiteralPath (Join-Path $existing 'YuE2-3B-Q8_0.gguf'))){$ModelsRoot=$existing}
}
if(-not $PythonPath){$PythonPath=Join-Path $root '.venv\Scripts\python.exe'}
$CudaRoot=Get-RuachCudaRoot -CudaRoot $CudaRoot
foreach($path in @($EnginePath,$PythonPath,(Join-Path $CudaRoot 'bin'))){if(-not(Test-Path -LiteralPath $path)){throw "Required local tool is absent: $path. No installer was run."}}
$EnginePath=[IO.Path]::GetFullPath($EnginePath)
$PythonPath=[IO.Path]::GetFullPath($PythonPath)
$ModelsRoot=[IO.Path]::GetFullPath($ModelsRoot)
if(-not $StdlibOnly -and $PythonPath -ne [IO.Path]::GetFullPath((Join-Path $root '.venv\Scripts\python.exe'))){throw 'Full runtime must use the isolated project venv. Use -StdlibOnly for approved core API tests.'}
if(-not $StdlibOnly){
    $readyPath=Join-Path $PSScriptRoot 'cache\validation-runtime\ready.json'
    if(-not(Test-Path -LiteralPath $readyPath)){throw 'Isolated ML installation is not yet verified. Wait for ready.json or use explicit -StdlibOnly.'}
    $ready=Get-Content -LiteralPath $readyPath -Raw | ConvertFrom-Json
    if($ready.schemaVersion -ne 1 -or $ready.completed -ne $true){throw 'Isolated ML runtime completion marker is invalid.'}
    foreach($profile in @('core','art')){
        $r=$ready.profiles.$profile
        $expected=if($profile -eq 'core'){'.venv/Scripts/python.exe'}else{'.venv-art/Scripts/python.exe'}
        if($r.importChecksPassed -ne $true -or $r.cudaBuild -notlike '*+cu128*' -or $r.pythonRelativePath.Replace('\','/') -ne $expected){throw "Unverified runtime profile: $profile"}
        foreach($rel in @($r.pythonRelativePath,$r.installedSnapshotRelativePath)){
            $full=[IO.Path]::GetFullPath((Join-Path $root $rel))
            if(-not $full.StartsWith(($root+'\'),[StringComparison]::OrdinalIgnoreCase) -or -not(Test-Path -LiteralPath $full)){throw 'Runtime evidence escaped project or is missing.'}
        }
    }
    $ff=[IO.Path]::GetFullPath((Join-Path $root $ready.ffmpeg.pathRelative))
    if($ready.ffmpeg.version -notlike '*9.0.2*' -or -not $ff.StartsWith(($root+'\'),[StringComparison]::OrdinalIgnoreCase) -or -not(Test-Path -LiteralPath $ff)){throw 'Verified local FFmpeg is missing.'}
}
$manifest=Get-Content (Join-Path $PSScriptRoot 'downloads.json') -Raw | ConvertFrom-Json
foreach($item in $manifest.models){
    $file=Join-Path $ModelsRoot $item.filename
    if(-not(Test-Path -LiteralPath $file) -or (Get-Item -LiteralPath $file).Length -ne $item.size -or (Get-RuachSha256 -Path $file) -ne $item.sha256){throw "Required previously approved base model missing or invalid: $file. No model download was started."}
}
$os=Get-CimInstance Win32_OperatingSystem
if($os.FreeVirtualMemory -lt 1MB){throw 'Less than 1GiB commit headroom; close heavy applications before starting.'}
$state=Join-Path $PSScriptRoot 'state\full'
$cache=Join-Path $PSScriptRoot 'cache\full'
New-Item -ItemType Directory -Force -Path $state,$cache,(Join-Path $cache 'tmp'),(Join-Path $cache 'cuda') | Out-Null
$page=Join-Path $PSScriptRoot 'cache\full-ui\index.html'
& $PythonPath (Join-Path $PSScriptRoot 'build_full_ui.py') $page
if($LASTEXITCODE -ne 0){throw 'The full UI did not assemble.'}
$instance=[Guid]::NewGuid().ToString('N')
$variables=@('PATH','RUACH_PAGE','GGML_BACKEND','LAB_PORT','LAB_HOST','YUE2CPP_PORT','RUACH_FULL_SUPERVISED','RUACH_FULL_STATE_DIR','RUACH_FULL_INSTANCE','RUACH_FULL_GPU','WINDOWS_MUSIC_LAB_LOCAL_ONLY','RUACH_OFFLINE','PYTHONUTF8','PYTHONIOENCODING','PYTHONUNBUFFERED','HF_HUB_OFFLINE','TRANSFORMERS_OFFLINE','DIFFUSERS_GGUF_CUDA_KERNELS','HF_HOME','TORCH_HOME','TEMP','TMP','CUDA_CACHE_PATH','LAB_PY','RUACH_GPU_MUTEX','RUACH_WDDM_MEMORY_POLICY','RUACH_MODELS_DIR')
$old=@{}
foreach($name in $variables){$old[$name]=[Environment]::GetEnvironmentVariable($name,'Process')}
$record=$null
$engine=$null
$lab=$null
$writer=$null
$writerShell=(Get-Command powershell.exe).Source
function Start-OwnedEngine {
    $args=@('--host','127.0.0.1','--port',[string]$Port,'--model',('Q8_0='+(Join-Path $ModelsRoot 'YuE2-3B-Q8_0.gguf')),'--vae',('standard='+(Join-Path $ModelsRoot 'YuE2-Vae-F32.gguf')),'--outputs',(Join-Path $root 'outputs'),'--settings',(Join-Path $root 'settings.json'),'--max-batch','1','--max-seq','12288','--vae-core','512','--loras',(Join-Path $root 'loras'))
    foreach($extra in @('legacy','blend')){ $vae=Join-Path $ModelsRoot "YuE2-Vae-$extra-F32.gguf"; if(Test-Path -LiteralPath $vae){$args+=@('--vae',($extra+'='+$vae))} }
    $transcriber=Join-Path $ModelsRoot 'SheetSage2-Q8_0.gguf'
    if(-not(Test-Path -LiteralPath $transcriber)){$transcriber=Join-Path $root 'models\SheetSage2-Q8_0.gguf'}
    if(Test-Path -LiteralPath $transcriber){$args+=@('--transcriber',$transcriber)}
    if(Get-ChildItem (Join-Path $root 'sliders') -Filter '*.gguf' -File -ErrorAction SilentlyContinue){$args+=@('--sliders',(Join-Path $root 'sliders'))}
    # Start-Process does not quote argument arrays. Preserve Unicode and space-containing paths.
    $quoted=@($args | ForEach-Object { '"'+$_.Replace('"','\"')+'"' })
    Start-Process -FilePath $EnginePath -ArgumentList $quoted -WorkingDirectory $root -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $cache 'engine.log') -RedirectStandardError (Join-Path $cache 'engine-error.log')
}
function Stop-OwnedProcess($Process,[string]$ExpectedPath){
    if(-not $Process -or $Process.HasExited){return}
    $actual=Get-CimInstance Win32_Process -Filter ('ProcessId='+$Process.Id)
    if(-not $actual -or $actual.ExecutablePath -ne $ExpectedPath){throw "Owned process identity changed: $($Process.Id)"}
    # Only the supervisor-created process tree is stopped; never scan/kill other apps.
    & taskkill.exe /PID $Process.Id /T /F 2>$null | Out-Null
    if($LASTEXITCODE -ne 0 -and -not $Process.HasExited){throw "Could not stop owned process $($Process.Id)"}
}
function Wait-LocalHealth([int]$Number,$Process){
    $deadline=(Get-Date).AddSeconds(30)
    while((Get-Date) -lt $deadline){
        if($Process.HasExited){throw "Child exited before health: PID $($Process.Id); see $cache"}
        try{$answer=Invoke-RestMethod -Uri "http://127.0.0.1:$Number/health" -TimeoutSec 1;if(($answer.PSObject.Properties['status'] -and $answer.status -eq 'ok') -or ($answer.PSObject.Properties['ok'] -and $answer.ok)){return}}catch{}
        Start-Sleep -Milliseconds 500
    }
    throw "Port $Number did not become healthy; see $cache"
}
function Read-OwnedRequest([string]$Name){
    $path=Join-Path $state $Name
    if(-not(Test-Path -LiteralPath $path)){return $false}
    try{$request=Get-Content -LiteralPath $path -Raw | ConvertFrom-Json;return $request.instance -eq $instance}catch{return $false}
}
function Start-VerifiedWriter {
    if($StdlibOnly -or $WithoutWriter){return}
    $path=Join-Path $PSScriptRoot 'state\writer\ready.json'
    if(-not(Test-Path -LiteralPath $path)){Write-Host 'Writer is not yet verified; see windows/WRITER.md.';return}
    $w=Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
    if($w.schema_version -ne 1 -or $w.verified -ne $true -or $w.source_revision -ne '8345f333951c661d166b00e6f9362e553768f292' -or $w.endpoint -ne 'http://127.0.0.1:41872/v1'){Write-Host 'Writer verification is pending; see windows/WRITER.md.';return}
    if(Get-NetTCPConnection -State Listen -LocalPort 41872 -ErrorAction SilentlyContinue){Write-Host 'Writer port41872 is already in use. Its process was left running.';return}
    . (Join-Path $PSScriptRoot 'Writer.Common.ps1')
    $script=Join-Path $PSScriptRoot 'Start-Writer.ps1'
    $p=Start-Process -FilePath $writerShell -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File',('"'+$script+'"'),'-NoBrowser','-StudioPort',[string]$Port,'-PendingReservedBytes','0') -WorkingDirectory $root -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $cache 'writer.log') -RedirectStandardError (Join-Path $cache 'writer-error.log')
    $script:writer=$p
    $deadline=(Get-Date).AddMinutes(3)
    while((Get-Date) -lt $deadline -and -not $p.HasExited -and -not(Read-OwnedRequest 'stop.requested')){
        try{
            $h=Invoke-RestMethod 'http://127.0.0.1:41872/health' -TimeoutSec 1
            $ownerPath=Join-Path $PSScriptRoot 'state\writer\processes.json'
            if($h.status -eq 'ok' -and (Test-Path -LiteralPath $ownerPath)){
                $owner=Get-Content -LiteralPath $ownerPath -Raw -Encoding UTF8 | ConvertFrom-Json
                if($owner.schema_version -eq 1 -and $owner.supervisor_pid -eq $p.Id -and $owner.port -eq 41872 -and $owner.studio_port -eq $Port -and $owner.instance -match '^[0-9a-f]{32}$'){
                    $server=Get-WriterChild $owner
                    $bound=@(Get-NetTCPConnection -State Listen -LocalPort 41872 -ErrorAction SilentlyContinue)
                    if($server -and $bound.Count -eq 1 -and $bound[0].LocalAddress -eq '127.0.0.1' -and $bound[0].OwningProcess -eq $owner.server_pid){Write-Host 'Owned local Writer: http://127.0.0.1:41872/v1';return}
                }
            }
        }catch{}
        Start-Sleep -Milliseconds 400
    }
    if(-not(Read-OwnedRequest 'stop.requested')){Write-Warning 'Writer did not start; studio remains available. See windows/cache/full/writer-error.log and windows/WRITER.md.'}
    Stop-OwnedProcess $p $writerShell
}
function Stop-OwnedWriter {
    if(-not $writer -or $writer.HasExited){return}
    $path=Join-Path $PSScriptRoot 'state\writer\processes.json'
    if(Test-Path -LiteralPath $path){
        $w=Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
        if($w.supervisor_pid -eq $writer.Id){& (Join-Path $PSScriptRoot 'Stop-Writer.ps1')}
    }
    Stop-OwnedProcess $writer $writerShell
}
try{
    $env:PATH=(Split-Path -Parent $EnginePath)+';'+(Join-Path $CudaRoot 'bin')+';'+$old.PATH
    $env:RUACH_PAGE=$page
    $env:GGML_BACKEND="CUDA$Gpu"
    $env:RUACH_MODELS_DIR=$ModelsRoot;$env:LAB_PORT=[string]$LabPort; $env:LAB_HOST='127.0.0.1'; $env:YUE2CPP_PORT=[string]$Port
    $env:RUACH_FULL_SUPERVISED='1';$env:RUACH_FULL_STATE_DIR=$state;$env:RUACH_FULL_INSTANCE=$instance;$env:RUACH_FULL_GPU=[string]$Gpu;$env:RUACH_GPU_MUTEX='Local\WindowsMusicLab-GPU'+$Gpu;$env:RUACH_WDDM_MEMORY_POLICY='aggregate'
    $env:WINDOWS_MUSIC_LAB_LOCAL_ONLY='1';$env:RUACH_OFFLINE='1';$env:HF_HUB_OFFLINE='1';$env:TRANSFORMERS_OFFLINE='1'
    $env:PYTHONUTF8='1';$env:PYTHONIOENCODING='utf-8';$env:PYTHONUNBUFFERED='1';$env:DIFFUSERS_GGUF_CUDA_KERNELS='0'
    $env:HF_HOME=Join-Path $cache 'huggingface';$env:TORCH_HOME=Join-Path $cache 'torch';$env:TEMP=Join-Path $cache 'tmp';$env:TMP=$env:TEMP;$env:CUDA_CACHE_PATH=Join-Path $cache 'cuda'
    # LAB_PY remains the project venv: stdlib-only mode must not silently run heavy jobs globally.
    $env:LAB_PY=Join-Path $root '.venv\Scripts\python.exe'
    $lab=Start-Process -FilePath $PythonPath -ArgumentList ('-X utf8 "'+(Join-Path $root 'lab\lab.py')+'"') -WorkingDirectory (Join-Path $root 'lab') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $cache 'lab.log') -RedirectStandardError (Join-Path $cache 'lab-error.log')
    Wait-LocalHealth $LabPort $lab
    $engine=Start-OwnedEngine
    Wait-LocalHealth $Port $engine
    $record=@{instance=$instance;root=$root;supervisor=$PID;engine=$engine.Id;lab=$lab.Id;port=$Port;labPort=$LabPort;stdlibOnly=[bool]$StdlibOnly;started=[DateTime]::UtcNow.ToString('o')}
    $record | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $state 'processes.json') -Encoding UTF8
    Write-Host "Windows Music Lab Full: http://localhost:$Port; local lab :$LabPort"
    if($StdlibOnly){Write-Host 'STDLIB-ONLY: Writer/library/export core. Model-backed jobs require separately approved local dependencies and weights.'}
    Write-Host 'Ctrl+C stops only this studio. Stop-Full.ps1 sends a supervised stop request.'
    try{Start-VerifiedWriter}catch{Write-Warning ('Optional Writer startup failed: '+$_.Exception.Message);try{Stop-OwnedWriter}catch{Write-Warning $_.Exception.Message}}
    while(-not $lab.HasExited -and -not $engine.HasExited){
        if(Read-OwnedRequest 'stop.requested'){break}
        if(Read-OwnedRequest 'restart.requested'){
            $hardware=Invoke-RestMethod "http://127.0.0.1:$Port/hardware" -TimeoutSec 5
            if(-not $hardware.busy -and -not $hardware.waiting_gpu -and [int]$hardware.queued_jobs -eq 0){
                Stop-OwnedProcess $engine $EnginePath
                $engine=Start-OwnedEngine
                Wait-LocalHealth $Port $engine
                $record.engine=$engine.Id
                $record | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $state 'processes.json') -Encoding UTF8
                # The contained marker is ours; no runtime/user data is removed.
                [IO.File]::WriteAllText((Join-Path $state 'restart.requested'),'{"instance":"consumed"}')
            }
        }
        Start-Sleep -Milliseconds 500
    }
    if(-not(Read-OwnedRequest 'stop.requested') -and ($lab.HasExited -or $engine.HasExited)){throw "A child stopped unexpectedly; see $cache"}
}finally{
    try{Stop-OwnedWriter}catch{Write-Warning $_.Exception.Message}
    try{Stop-OwnedProcess $engine $EnginePath}catch{Write-Warning $_.Exception.Message}
    try{Stop-OwnedProcess $lab $PythonPath}catch{Write-Warning $_.Exception.Message}
    foreach($name in $variables){[Environment]::SetEnvironmentVariable($name,$old[$name],'Process')}
    if($record -and (Test-Path -LiteralPath (Join-Path $state 'processes.json'))){
        $record.stopped=[DateTime]::UtcNow.ToString('o')
        $record | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $state 'processes.json') -Encoding UTF8
    }
}
