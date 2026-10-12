# Offline tests of the actual download helper AND Start.ps1 launch gate.
# Only tiny files in windows/cache are created. curl and the engine are mocked.
[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'Common.ps1')
$suite=Join-Path $PSScriptRoot ('cache\model-tests\'+[Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $suite -Force | Out-Null
$utf8=New-Object Text.UTF8Encoding($true)
$data=[byte[]](1..64)
$hash=([BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash($data))).Replace('-','').ToLowerInvariant()
$names=@('YuE2-3B-Q8_0.gguf','YuE2-Vae-F32.gguf')
$sourceCommon=[IO.File]::ReadAllText((Join-Path $PSScriptRoot 'Common.ps1'))
$sourceStart=[IO.File]::ReadAllText((Join-Path $PSScriptRoot 'Start.ps1'))
$mock=@'

function Get-NetTCPConnection { param($State,$LocalPort,$ErrorAction) return $null }
function Invoke-RuachNative {
    param([string]$Executable,[string[]]$Arguments)
    $fixture=Get-RuachRoot
    if($Executable -eq 'curl.exe') {
        Add-Content -LiteralPath (Join-Path $fixture 'curl-calls.txt') -Value 'curl' -Encoding ASCII
        foreach($required in @('--fail','--continue-at','--progress-bar','--proto','--proto-redir')) {
            if($required -notin $Arguments){throw "Missing download flag: $required"}
        }
        if($Arguments -notcontains '=https'){throw 'HTTPS restriction missing'}
        $mode='__MODE__'
        if($mode -eq 'network-error'){throw 'Mock network failure'}
        $output=$Arguments[[Array]::IndexOf($Arguments,'--output')+1]
        $bytes=[byte[]](1..64)
        if($mode -eq 'bad-hash'){$bytes=[byte[]](1..63)+[byte]255}
        if($mode -eq 'bad-size'){$bytes=[byte[]](1..5)}
        [IO.File]::WriteAllBytes($output,$bytes)
        return
    }
    if($Executable -ne (Join-Path $PSScriptRoot 'build\yue-server.exe')){throw 'Unexpected native invocation in test'}
    [IO.File]::WriteAllText((Join-Path $fixture 'engine-called.txt'),'verified launch gate reached')
}
'@
$cases=@(
    @{name='missing-both';setup='missing';mode='ok';pass=$true;downloads=2},
    @{name='valid-reuse';setup='valid';mode='ok';pass=$true;downloads=0},
    @{name='missing-one';setup='one';mode='ok';pass=$true;downloads=1},
    @{name='partial-resume';setup='partial';mode='ok';pass=$true;downloads=1},
    @{name='complete-part-reuse';setup='complete';mode='ok';pass=$true;downloads=0},
    @{name='corrupt-final-size';setup='corrupt-size';mode='ok';pass=$false;downloads=0;error='Existing file'},
    @{name='corrupt-final-hash';setup='corrupt-hash';mode='ok';pass=$false;downloads=0;error='Existing file'},
    @{name='corrupt-complete-part';setup='corrupt-part';mode='ok';pass=$false;downloads=0;error='SHA256 mismatch'},
    @{name='download-bad-hash';setup='one';mode='bad-hash';pass=$false;downloads=1;error='SHA256 mismatch'},
    @{name='download-bad-size';setup='one';mode='bad-size';pass=$false;downloads=1;error='Incorrect download size'},
    @{name='network-error';setup='one';mode='network-error';pass=$false;downloads=1;error='Mock network failure'},
    @{name='manifest-path-rejected';setup='invalid-path';mode='ok';pass=$false;downloads=0;error='Unexpected or duplicate'},
    @{name='manifest-host-rejected';setup='invalid-host';mode='ok';pass=$false;downloads=0;error='Unexpected model source'}
)
$results=@()
foreach($case in $cases){
    $root=Join-Path $suite $case.name
    $win=Join-Path $root 'windows'
    $models=Join-Path $root 'models'
    foreach($dir in @($win,$models,(Join-Path $win 'build'),(Join-Path $win 'ui'),(Join-Path $root 'toolchain\cuda-12.8.1\bin'))){New-Item -ItemType Directory -Force -Path $dir | Out-Null}
    [IO.File]::WriteAllText((Join-Path $win 'Common.ps1'),$sourceCommon+"`n"+$mock.Replace('__MODE__',$case.mode),$utf8)
    [IO.File]::WriteAllText((Join-Path $win 'Start.ps1'),$sourceStart,$utf8)
    [IO.File]::WriteAllText((Join-Path $win 'build\yue-server.exe'),'fixture only')
    [IO.File]::WriteAllText((Join-Path $win 'ui\index.html'),'fixture only')
    $items=@($names | ForEach-Object { @{filename=$_;url=('https://huggingface.co/Serveurperso/YuE2-GGUF/resolve/64b030e3deb6e8150d2b7c0db641ef5a17eca8a3/'+$_);size=$data.Length;sha256=$hash} })
    if($case.setup -eq 'invalid-path'){$items[0].filename='../escape.gguf'}
    if($case.setup -eq 'invalid-host'){$items[0].url='https://example.invalid/model.gguf'}
    [IO.File]::WriteAllText((Join-Path $win 'downloads.json'),(@{models=$items}|ConvertTo-Json -Depth 5),$utf8)
    $backbone=Join-Path $models $names[0]
    $vae=Join-Path $models $names[1]
    if($case.setup -ne 'missing'){[IO.File]::WriteAllBytes($vae,$data)}
    switch($case.setup){
        'valid' {[IO.File]::WriteAllBytes($backbone,$data)}
        'partial' {[IO.File]::WriteAllBytes($backbone+'.part',[byte[]](1..17))}
        'complete' {[IO.File]::WriteAllBytes($backbone+'.part',$data)}
        'corrupt-size' {[IO.File]::WriteAllBytes($backbone,[byte[]](1..5))}
        'corrupt-hash' {[IO.File]::WriteAllBytes($backbone,([byte[]](1..63)+[byte]255))}
        'corrupt-part' {[IO.File]::WriteAllBytes($backbone+'.part',([byte[]](1..63)+[byte]255))}
    }
    $beforeHash=if(Test-Path -LiteralPath $backbone){(Get-RuachSha256 -Path $backbone)}else{''}
    $failed=''
    try { & (Join-Path $win 'Start.ps1') -Port 49123 } catch {$failed=$_.Exception.Message}
    $engine=Test-Path -LiteralPath (Join-Path $root 'engine-called.txt')
    $calls=Join-Path $root 'curl-calls.txt'
    $count=if(Test-Path -LiteralPath $calls){@(Get-Content -LiteralPath $calls).Count}else{0}
    if($case.pass){
        if($failed -or -not $engine){throw ($case.name+': valid setup did not reach launch: '+$failed)}
        foreach($name in $names){if((Get-RuachSha256 -Path (Join-Path $models $name)) -ne $hash){throw ($case.name+': final hash wrong')}}
    }else{
        if(-not $failed -or $engine -or $failed -notmatch $case.error){throw ($case.name+': failure did not block engine: '+$failed)}
    }
    if($count -ne $case.downloads){throw ($case.name+': unexpected number of downloads '+$count)}
    if($beforeHash -and (Get-RuachSha256 -Path $backbone) -ne $beforeHash){throw ($case.name+': existing model was modified')}
    $results += [pscustomobject]@{name=$case.name;passed=$true;downloads=$count;engineInvoked=$engine}
    Write-Host ('PASS '+$case.name)
}
$report=[pscustomobject]@{passed=$true;cases=$results;checkedAt=[DateTime]::UtcNow.ToString('o');networkUsed=$false;realModelsTouched=$false}
$report | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $suite 'results.json') -Encoding UTF8
Write-Host ("All {0} offline tests passed. Report: {1}" -f $results.Count,(Join-Path $suite 'results.json'))