[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
. (Join-Path (Split-Path -Parent $PSScriptRoot) 'Writer.Common.ps1')
$script:tests=0
function Assert-Identity {
    param([bool]$Condition,[string]$Name)
    if(-not $Condition){throw "Identity test failed: $Name"}
    $script:tests++
}
$script:instant=[DateTime]::ParseExact('2026-10-12T19:49:10.7908947Z','o',[Globalization.CultureInfo]::InvariantCulture,[Globalization.DateTimeStyles]::RoundtripKind)
$script:expectedExe=Join-Path (Get-WriterRoot) 'windows\build\writer-cpu\bin\Release\llama-server.exe'
$script:fakePath=$script:expectedExe
$script:fakeStart=$script:instant
# Only a synthetic process is returned; no model, real process or state file is touched.
function Get-Process {
    [CmdletBinding()]
    param([int]$Id)
    if($Id -ne 424242){throw 'Synthetic process ID mismatch.'}
    [pscustomobject]@{Id=$Id;Path=$script:fakePath;StartTime=$script:fakeStart}
}
function New-IdentityRecord {
    param($Start)
    [pscustomobject]@{schema_version=1;instance='0123456789abcdef0123456789abcdef';server_pid=424242;server_exe=$script:expectedExe;server_start_utc=$Start}
}
$iso=$script:instant.ToString('o')
$json=New-IdentityRecord $iso|ConvertTo-Json -Compress
$decoded=$json|ConvertFrom-Json
Assert-Identity ([bool](Get-WriterChild $decoded)) 'actual ConvertFrom-Json date representation'
Assert-Identity ([bool](Get-WriterChild (New-IdentityRecord $iso))) 'round-trip string UTC'
Assert-Identity ([bool](Get-WriterChild (New-IdentityRecord $script:instant))) 'typed UTC DateTime'
Assert-Identity ([bool](Get-WriterChild (New-IdentityRecord $script:instant.ToLocalTime()))) 'typed local DateTime'
$offset=([DateTimeOffset]$script:instant).ToOffset([TimeSpan]::FromHours(3))
Assert-Identity ([bool](Get-WriterChild (New-IdentityRecord $offset))) 'typed DateTimeOffset'
Assert-Identity ([bool](Get-WriterChild (New-IdentityRecord $offset.ToString('o')))) 'round-trip offset string'
$oldCulture=[Threading.Thread]::CurrentThread.CurrentCulture
try{
    [Threading.Thread]::CurrentThread.CurrentCulture=[Globalization.CultureInfo]::GetCultureInfo('ru-RU')
    Assert-Identity ([bool](Get-WriterChild $decoded)) 'regional display does not change instant'
}finally{[Threading.Thread]::CurrentThread.CurrentCulture=$oldCulture}
$bad=@($null,'garbage','2026-10-12T19:49:10.7908947','2026-13-12T19:49:10.7908947Z',123,$script:instant.AddTicks(1),[DateTime]::SpecifyKind($script:instant,[DateTimeKind]::Unspecified))
foreach($stamp in $bad){Assert-Identity (-not (Get-WriterChild (New-IdentityRecord $stamp))) 'invalid, ambiguous or wrong instant rejected'}
$r=New-IdentityRecord $iso;$r.schema_version=2
Assert-Identity (-not (Get-WriterChild $r)) 'wrong schema rejected'
$r=New-IdentityRecord $iso;$r.instance='wrong'
Assert-Identity (-not (Get-WriterChild $r)) 'wrong instance rejected'
$r=New-IdentityRecord $iso;$r.server_pid=424243
Assert-Identity (-not (Get-WriterChild $r)) 'wrong PID rejected'
$r=New-IdentityRecord $iso;$r.server_exe='C:\foreign\llama-server.exe'
Assert-Identity (-not (Get-WriterChild $r)) 'foreign record executable rejected'
$script:fakePath='C:\foreign\llama-server.exe'
Assert-Identity (-not (Get-WriterChild (New-IdentityRecord $iso))) 'foreign actual executable rejected'
$script:fakePath=$script:expectedExe;$script:fakeStart=$script:instant.AddTicks(1)
Assert-Identity (-not (Get-WriterChild (New-IdentityRecord $iso))) 'actual process start differs by one tick'
$script:fakeStart=$script:instant
@{passed=$true;tests=$script:tests;powerShell=$PSVersionTable.PSVersion.ToString();jsonTimestampType=$decoded.server_start_utc.GetType().FullName;syntheticOnly=$true}|ConvertTo-Json -Compress
