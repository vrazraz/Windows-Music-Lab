[CmdletBinding()]
param([switch]$StopAfter,[string]$StudioUrl='http://localhost:41868/')
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'Common.ps1')
. (Join-Path $PSScriptRoot 'Writer.Common.ps1')
$root=Get-WriterRoot;$state=Get-WriterState;$cache=Join-Path $PSScriptRoot 'cache\writer'
$recordPath=Join-Path $state 'processes.json'
if(-not(Test-Path -LiteralPath $recordPath)){throw 'Start the approved owned Writer before this test.'}
$record=Get-Content -LiteralPath $recordPath -Raw -Encoding UTF8|ConvertFrom-Json
$server=Get-WriterChild $record
if(-not $server -or $record.port -ne 41872 -or $record.studio_port -ne 41868){throw 'Expected owned Writer identity/ports absent.'}
$exe=Join-Path $PSScriptRoot 'build\writer-cpu\bin\Release\llama-server.exe'
if($server.Path -ne $exe){throw 'Unexpected Writer executable; no test requests sent.'}
$bound=@(Get-NetTCPConnection -State Listen -LocalPort 41872 -ErrorAction Stop)
if(-not $bound.Count -or @($bound|Where-Object {$_.LocalAddress -ne '127.0.0.1' -or $_.OwningProcess -ne $record.server_pid}).Count){throw 'Writer is not bound exclusively to owned IPv4 loopback.'}
$readyPath=Join-Path $state 'ready.json'
# Invalidate stale readiness before a fresh test; only this feature's marker is affected.
if(Test-Path -LiteralPath $readyPath){Save-WriterJson $readyPath @{schema_version=1;verified=$false;status='testing';tested_utc=[DateTime]::UtcNow.ToString('o')}}
$qa=$null;$peakWorking=[long]0;$peakPrivate=[long]0
# Preserve earlier owned synthetic QA logs before a fresh native redirection.
$history=Join-Path $cache ('http-test-history\'+[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfff'))
foreach($name in @('http-qa.stdout.log','http-qa.stderr.log')){
    $oldLog=Join-Path $cache $name
    if((Test-Path -LiteralPath $oldLog) -and (Get-Item -LiteralPath $oldLog).Length -gt 0){
        New-Item -ItemType Directory -Force -Path $history|Out-Null
        Copy-Item -LiteralPath $oldLog -Destination (Join-Path $history $name)
    }
}
try{
    $launch=@{FilePath='py.exe';ArgumentList=(('-3.10',(Join-Path $PSScriptRoot 'qa_writer_http.py'),'--root',$root|ForEach-Object {Quote-WriterArgument $_}) -join ' ');
        WorkingDirectory=$root;WindowStyle='Hidden';PassThru=$true;RedirectStandardOutput=(Join-Path $cache 'http-qa.stdout.log');RedirectStandardError=(Join-Path $cache 'http-qa.stderr.log')}
    $qa=Start-Process @launch
    $null=$qa.Handle
    $deadline=[DateTime]::UtcNow.AddMinutes(5)
    do{
        $server=Get-WriterChild $record
        if(-not $server){throw 'Owned Writer exited during synthetic HTTP test.'}
        $peakWorking=[Math]::Max($peakWorking,$server.WorkingSet64);$peakPrivate=[Math]::Max($peakPrivate,$server.PrivateMemorySize64)
        if([DateTime]::UtcNow -gt $deadline){throw 'Synthetic HTTP test timed out.'}
        Start-Sleep -Milliseconds 400
    }while(-not $qa.HasExited)
    $qa.WaitForExit()
    if($qa.ExitCode -ne 0){throw 'Synthetic HTTP/quality test failed; see Writer cache logs.'}
    & (Join-Path $PSScriptRoot 'Check-Writer.ps1') -StudioUrl $StudioUrl
    $firstBrowser=Get-Content -LiteralPath (Join-Path $state 'browser-check.json') -Raw -Encoding UTF8|ConvertFrom-Json
    $otherOrigin=if(([Uri]$StudioUrl).Host -eq 'localhost'){'http://127.0.0.1:41868/'}else{'http://localhost:41868/'}
    & (Join-Path $PSScriptRoot 'Check-Writer.ps1') -StudioUrl $otherOrigin
    $secondBrowser=Get-Content -LiteralPath (Join-Path $state 'browser-check.json') -Raw -Encoding UTF8|ConvertFrom-Json
    $http=Get-Content -LiteralPath (Join-Path $state 'http-check.json') -Raw -Encoding UTF8|ConvertFrom-Json
    if(-not $http.passed -or -not $firstBrowser.passed -or -not $secondBrowser.passed){throw 'Writer test artifacts did not pass.'}
    $browser=@{schema_version=1;passed=$true;browserCorsPost=$true;syntheticOnly=$true;
        origins=@($firstBrowser.origin,$secondBrowser.origin);checks=@($firstBrowser,$secondBrowser);testedUtc=[DateTime]::UtcNow.ToString('o')}
    Save-WriterJson (Join-Path $state 'browser-check.json') $browser
    if(-not(Get-WriterChild $record)){throw 'Writer identity changed during browser test.'}
    $proof=Get-Content -LiteralPath (Join-Path $root 'vendor\llama.cpp\source-pin.json') -Raw -Encoding UTF8|ConvertFrom-Json
    if($proof.revision -ne '8345f333951c661d166b00e6f9362e553768f292' -or $proof.verified_blob_count -ne 3687){throw 'Unexpected source proof.'}
    $model=Join-Path $root 'models\writer\Qwen3-4B-Q4_K_M.gguf'
    $modelHash=Get-RuachSha256 $model
    if((Get-Item -LiteralPath $model).Length -ne 2497280256 -or $modelHash -ne '7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5'){throw 'Pinned model integrity changed.'}
    $cpuCache=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'build\writer-cpu\CMakeCache.txt') -Raw -Encoding UTF8
    if($cpuCache -notmatch '(?m)^GGML_CUDA:BOOL=OFF\r?$'){throw 'CPU-only build cache not verified.'}
    $stopVerified=$false
    if($StopAfter){
        & (Join-Path $PSScriptRoot 'Stop-Writer.ps1')
        if(Get-WriterChild $record){throw 'Owned-stop lifecycle check failed.'}
        $stopVerified=$true
    }
    $report=@{schema_version=1;verified=$stopVerified;status=$(if($stopVerified){'verified'}else{'http-browser-verified-stop-pending'});source_revision=$proof.revision;
        binary='windows/build/writer-cpu/bin/Release/llama-server.exe';binary_sha256=(Get-RuachSha256 $exe);
        model='models/writer/Qwen3-4B-Q4_K_M.gguf';model_sha256=$modelHash;model_bytes=2497280256;
        endpoint='http://127.0.0.1:41872/v1';alias='Windows-Music-Lab-Writer';quality_scope='Valid structured Russian four-line synthetic draft; literary quality, rhyme and long Muse/Idea prompts not established.';tested_utc=[DateTime]::UtcNow.ToString('o');
        tests=@{http=$true;browser_cors=$true;browser_origins=@($firstBrowser.origin,$secondBrowser.origin);untrusted_and_lookalike_origins_not_granted=$true;russian_writer_json=$true;max_tokens=256;owned_stop=$stopVerified;cpu_only=$true};
        cors=@{mode='localhost';allowed_hosts=@('localhost','127.0.0.1','::1');any_loopback_port=$true;credentials=$false};
        resources=@{peak_working_set_bytes=$peakWorking;peak_private_bytes=$peakPrivate;threads=4;context=8192;parallel=1};
        evidence=@('windows/state/writer/http-check.json','windows/state/writer/browser-check.json',
                   'vendor/llama.cpp/source-pin.json','windows/cache/writer/configure.log','windows/cache/writer/build.log')}
    Save-WriterJson $readyPath $report
    Write-Host "Writer verified: $readyPath"
}finally{
    if($qa -and -not $qa.HasExited){$qa.Kill();$qa.WaitForExit(5000)|Out-Null}
}
