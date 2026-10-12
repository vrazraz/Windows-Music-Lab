[CmdletBinding()]
param([ValidateRange(1024,65535)][int]$Port = 41867, [ValidateRange(5,60)][int]$Seconds = 10, [int]$TimeoutSeconds = 900)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'Common.ps1')
$root = Get-RuachRoot
$url = "http://127.0.0.1:$Port"
$health = Invoke-RestMethod -Uri ($url + '/health') -TimeoutSec 10
if ($health.status -ne 'ok') { throw 'Health check failed.' }
$page = (Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 10).Content
if ($page -notmatch 'Windows Music Lab') { throw 'The Windows UI was not served.' }
$hardware = Invoke-RestMethod -Uri ($url + '/hardware') -TimeoutSec 15
if (-not @($hardware.gpus | Where-Object { $_.name -match '^CUDA' }).Count) { throw 'No CUDA GPU reported by the engine.' }
Write-Host ('CUDA device: ' + ($hardware.gpus | Where-Object { $_.name -match '^CUDA' } | Select-Object -First 1).description)
$body = @{
    title = 'Тест Windows'; style = 'Instrumental, solo piano, calm, no vocals'
    lyrics = '[instrumental]'; cot = 'off'; duration = $Seconds
    seed = 20261012; lm_seed = 20261012; steps = 16
    lm_batch_size = 1; synth_batch_size = 1; output_format = 'wav16'
} | ConvertTo-Json -Compress
$job = Invoke-RestMethod -Uri ($url + '/synth') -Method Post -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($body)) -TimeoutSec 30
if (-not $job.id) { throw 'The engine did not return a job id.' }
Write-Host "Real GPU generation submitted: $($job.id)"
$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 2
    $status = Invoke-RestMethod -Uri ($url + '/job?id=' + $job.id) -TimeoutSec 15
    if ($status.status -eq 'done') { break }
    if ($status.status -in @('failed','cancelled')) { throw ("Generation failed: " + $status.error) }
    Write-Host ("Job {0}: {1}" -f $job.id, $status.status)
}
if ($status.status -ne 'done') { throw "Generation timed out; inspect the UI before retrying job $($job.id)." }
if (-not $status.takes -or @($status.takes).Count -ne 1) { throw 'No single saved take was returned.' }
$take = [string]$status.takes[0]
if ($take -match '[\\/]|\.\.') { throw 'Unexpected take name.' }
$audio = Join-Path $root ('outputs\' + $take + '\audio.wav')
if (-not (Test-Path -LiteralPath $audio) -or (Get-Item -LiteralPath $audio).Length -lt 10000) { throw 'Generated audio is missing or too short.' }
$stream = [IO.File]::OpenRead($audio)
try {
    $bytes = New-Object byte[] 12
    if ($stream.Read($bytes, 0, 12) -ne 12 -or [Text.Encoding]::ASCII.GetString($bytes,0,4) -ne 'RIFF' -or [Text.Encoding]::ASCII.GetString($bytes,8,4) -ne 'WAVE') { throw 'Generated file is not WAV.' }
} finally { $stream.Dispose() }
Write-Host "PASS: live server, Windows UI, real generation, saved WAV. Listen to: $audio"
