[CmdletBinding()]
param(
    [ValidateRange(1024,65535)][int]$Port=41872,
    [ValidateRange(1024,65535)][int]$StudioPort=41868,
    [long]$PendingReservedBytes=0,
    [switch]$NoBrowser
)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'Common.ps1')
. (Join-Path $PSScriptRoot 'Writer.Common.ps1')
$root=Get-WriterRoot;$state=Get-WriterState;$cache=Join-Path $PSScriptRoot 'cache\writer'
New-Item -ItemType Directory -Force -Path $state,$cache|Out-Null
$recordPath=Join-Path $state 'processes.json';$stopPath=Join-Path $state 'stop.request.json'
if(Test-Path -LiteralPath $recordPath){
    $old=Get-Content -LiteralPath $recordPath -Raw -Encoding UTF8|ConvertFrom-Json
    if(Get-WriterChild $old){throw 'An owned Writer is already running; no duplicate was started.'}
}
if(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue){throw 'Writer port occupied; existing process untouched.'}
Invoke-RuachNative -Executable 'py.exe' -Arguments @('-3.10',(Join-Path $PSScriptRoot 'writer_setup.py'),'preflight','--root',$root,'--pending-bytes',[string]$PendingReservedBytes)
$exe=Join-Path $PSScriptRoot 'build\writer-cpu\bin\Release\llama-server.exe'
$model=Join-Path $root 'models\writer\Qwen3-4B-Q4_K_M.gguf'
$license=Join-Path $root 'models\writer\LICENSE-Qwen3.txt'
$buildProofPath=Join-Path $cache 'build-proof.json'
$proofPath=Join-Path $root 'vendor\llama.cpp\source-pin.json'
foreach($p in @($exe,$model,$license,$proofPath,$buildProofPath)){if(-not(Test-Path -LiteralPath $p)){throw "Required approved artifact absent: $p"}}
$proof=Get-Content -LiteralPath $proofPath -Raw -Encoding UTF8|ConvertFrom-Json
if($proof.revision -ne '8345f333951c661d166b00e6f9362e553768f292' -or $proof.verified_blob_count -ne 3687){throw 'Writer source pin differs.'}
$buildProof=Get-Content -LiteralPath $buildProofPath -Raw -Encoding UTF8|ConvertFrom-Json
if($buildProof.source_revision -ne $proof.revision -or -not $buildProof.version_execution_passed -or
   $buildProof.binary -ne 'windows/build/writer-cpu/bin/Release/llama-server.exe' -or
   (Get-Item -LiteralPath $exe).Length -ne $buildProof.binary_bytes -or (Get-RuachSha256 $exe) -ne $buildProof.binary_sha256){throw 'Writer binary provenance/integrity differs; nothing started.'}
if((Get-Item -LiteralPath $model).Length -ne 2497280256 -or (Get-RuachSha256 $model) -ne '7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5'){throw 'Writer model not verified; nothing started.'}
if((Get-Item -LiteralPath $license).Length -ne 11544 -or (Get-WriterLicenseBlob $license) -ne '6f9739bb281a3d2ade8fb5f6dd6dde597a739c80'){throw 'Pinned Apache-2.0 model license not verified; nothing started.'}
$instance=[guid]::NewGuid().ToString('N')
$variables=@('TEMP','TMP','LLAMA_CACHE','HF_HOME','HF_HUB_OFFLINE','TRANSFORMERS_OFFLINE','HF_HUB_DISABLE_TELEMETRY','NO_PROXY','LLAMA_ARG_TOOLS','LLAMA_ARG_MCP_SERVERS_CONFIG','LLAMA_ARG_MCP_SERVERS_JSON','LLAMA_ARG_TOOLS_RUNTIME','AIP_MODE')
$variables+=@([Environment]::GetEnvironmentVariables('Process').Keys|Where-Object {$_ -like 'LLAMA_*'})
$variables=@($variables|Select-Object -Unique)
$oldEnv=@{};foreach($v in $variables){$oldEnv[$v]=[Environment]::GetEnvironmentVariable($v,'Process')}
$child=$null
try{
    $env:TEMP=$cache;$env:TMP=$cache;$env:LLAMA_CACHE=Join-Path $cache 'llama-cache';$env:HF_HOME=Join-Path $cache 'hf'
    $env:AIP_MODE='0';$env:HF_HUB_OFFLINE='1';$env:TRANSFORMERS_OFFLINE='1';$env:HF_HUB_DISABLE_TELEMETRY='1';$env:NO_PROXY='localhost,127.0.0.1,::1'
    foreach($v in $variables|Where-Object {$_ -like 'LLAMA_*' -and $_ -ne 'LLAMA_CACHE'}){[Environment]::SetEnvironmentVariable($v,$null,'Process')}
    $args=@('-m',$model,'--alias','Windows-Music-Lab-Writer','--host','127.0.0.1','--port',[string]$Port,
      '--device','none','--n-gpu-layers','0','--no-kv-offload','--ctx-size','8192','--parallel','1',
      '--threads','4','--threads-batch','4','--batch-size','256','--ubatch-size','128',
      '--cache-type-k','f16','--cache-type-v','f16','--jinja','--reasoning','off','--reasoning-budget','0',
      '--offline','--no-agent','--no-ui','--no-ui-mcp-proxy','--no-cors-credentials',
      '--cors-origins','localhost','--cors-methods','GET,POST,OPTIONS','--cors-headers','Content-Type',
      '--temp','0.7','--top-p','0.8','--top-k','20','--min-p','0','--presence-penalty','1.5','--log-verbosity','2')
    $argLine=($args|ForEach-Object {Quote-WriterArgument ([string]$_)}) -join ' '
    $launch=@{FilePath=$exe;ArgumentList=$argLine;WorkingDirectory=$root;WindowStyle='Hidden';PassThru=$true;RedirectStandardOutput=(Join-Path $cache 'server.stdout.log');RedirectStandardError=(Join-Path $cache 'server.stderr.log')}
    $child=Start-Process @launch
    $record=@{schema_version=1;instance=$instance;supervisor_pid=$PID;server_pid=$child.Id;server_exe=$exe;server_start_utc=$child.StartTime.ToUniversalTime().ToString('o');port=$Port;studio_port=$StudioPort;endpoint="http://127.0.0.1:$Port/v1";status='starting';started_utc=[DateTime]::UtcNow.ToString('o')}
    Save-WriterJson $recordPath $record
    $deadline=[DateTime]::UtcNow.AddMinutes(3)
    $health=$null
    do{
        if($child.HasExited){throw "Writer exited $($child.ExitCode); see $cache"}
        try{$health=Invoke-RestMethod "http://127.0.0.1:$Port/health" -TimeoutSec 2;if($health.status -eq 'ok'){break}}catch{}
        Start-Sleep -Milliseconds 300
    }while([DateTime]::UtcNow -lt $deadline)
    if(-not $health -or $health.status -ne 'ok'){throw 'Writer health timeout; owned child will stop.'}
    $record.status='running';Save-WriterJson $recordPath $record
    Write-Host "Writer CPU ready: $($record.endpoint). Ctrl+C or Stop-Writer.ps1 stops only this Writer."
    while(-not $child.HasExited){
        if(Test-Path -LiteralPath $stopPath){
            $request=Get-Content -LiteralPath $stopPath -Raw -Encoding UTF8|ConvertFrom-Json
            if($request.instance -eq $instance){break}
        }
        Start-Sleep -Milliseconds 300
    }
}finally{
    if($child -and -not $child.HasExited){$child.Kill();$child.WaitForExit(5000)|Out-Null}
    if(Test-Path -LiteralPath $recordPath){
        $saved=Get-Content -LiteralPath $recordPath -Raw -Encoding UTF8|ConvertFrom-Json
        if($saved.instance -eq $instance){$saved.status='stopped';$saved|Add-Member -NotePropertyName stopped_utc -NotePropertyValue ([DateTime]::UtcNow.ToString('o')) -Force;Save-WriterJson $recordPath $saved}
    }
    if(Test-Path -LiteralPath $stopPath){$request=Get-Content -LiteralPath $stopPath -Raw -Encoding UTF8|ConvertFrom-Json;if($request.instance -eq $instance){Remove-Item -LiteralPath $stopPath}}
    foreach($v in $variables){[Environment]::SetEnvironmentVariable($v,$oldEnv[$v],'Process')}
}