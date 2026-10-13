[CmdletBinding()]
param([ValidateRange(1,60)][int]$TimeoutSeconds=15)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'Writer.Common.ps1')
$state=Get-WriterState;$recordPath=Join-Path $state 'processes.json'
if(-not(Test-Path -LiteralPath $recordPath)){Write-Host 'No owned Writer state; no process touched.';return}
$record=Get-Content -LiteralPath $recordPath -Raw -Encoding UTF8|ConvertFrom-Json
$child=Get-WriterChild $record
if(-not $child){Write-Host 'Recorded Writer is not running; no process touched.';return}
Save-WriterJson (Join-Path $state 'stop.request.json') @{instance=$record.instance;requested_utc=[DateTime]::UtcNow.ToString('o')}
$deadline=[DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
while([DateTime]::UtcNow -lt $deadline){if(-not(Get-WriterChild $record)){Write-Host 'Owned Writer stopped.';return};Start-Sleep -Milliseconds 200}
$child=Get-WriterChild $record
if($child){$child.Kill();$child.WaitForExit(5000)|Out-Null}
if(Get-WriterChild $record){throw 'Owned Writer did not stop.'}
$saved=Get-Content -LiteralPath $recordPath -Raw -Encoding UTF8|ConvertFrom-Json
if($saved.instance -eq $record.instance){
    $saved.status='stopped'
    $saved|Add-Member -NotePropertyName stopped_utc -NotePropertyValue ([DateTime]::UtcNow.ToString('o')) -Force
    Save-WriterJson $recordPath $saved
}
$stopPath=Join-Path $state 'stop.request.json'
if(Test-Path -LiteralPath $stopPath){
    $request=Get-Content -LiteralPath $stopPath -Raw -Encoding UTF8|ConvertFrom-Json
    if($request.instance -eq $record.instance){Remove-Item -LiteralPath $stopPath}
}
Write-Host 'Owned Writer stopped after supervisor timeout.'