[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
$state=Join-Path $PSScriptRoot 'state\full'
$record=Get-Content -LiteralPath (Join-Path $state 'processes.json') -Raw | ConvertFrom-Json
if($record.PSObject.Properties['stopped'] -and $record.stopped){throw 'The supervised full studio is already stopped.'}
if($record.root -ne (Split-Path -Parent $PSScriptRoot)){throw 'Supervisor state belongs to a different project.'}
@{instance=$record.instance;requested=[DateTime]::UtcNow.ToString('o')} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $state 'stop.requested') -Encoding UTF8
Write-Host 'Stop requested for this supervised studio. No unrelated process was killed.'
