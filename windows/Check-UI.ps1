[CmdletBinding()]
param([ValidateRange(1024,65535)][int]$Port=41867, [switch]$Tags)
$ErrorActionPreference='Stop'
$chrome=Join-Path $env:ProgramFiles 'Google\Chrome\Application\chrome.exe'
if(-not (Test-Path -LiteralPath $chrome)){throw 'Installed Google Chrome was not found.'}
$qa=Join-Path $PSScriptRoot 'cache\qa'
$profile=Join-Path $qa ('profile-'+(Get-Date -Format 'yyyyMMdd-HHmmss'))
$tmp=Join-Path $PSScriptRoot 'cache\tmp'
New-Item -ItemType Directory -Force -Path $qa,$profile,$tmp | Out-Null
$env:TEMP=$tmp
$env:TMP=$tmp
$arguments=@(
    '--headless=new','--disable-gpu','--mute-audio',
    '--remote-debugging-port=0','--remote-debugging-address=127.0.0.1',
    ('--user-data-dir="'+$profile+'"'),('--disk-cache-dir="'+(Join-Path $profile 'cache')+'"'),
    '--disable-background-networking','--disable-component-update','--disable-sync',
    '--no-first-run','--no-default-browser-check','--window-size=1440,1100','about:blank'
)
$browser=Start-Process -FilePath $chrome -ArgumentList $arguments -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $qa 'chrome-stdout.log') -RedirectStandardError (Join-Path $qa 'chrome-stderr.log')
try {
    $qaScript=if($Tags){'qa-tags.mjs'}else{'qa-ui.mjs'}
    & node (Join-Path $PSScriptRoot $qaScript) $profile $qa "http://127.0.0.1:$Port"
    if($LASTEXITCODE -ne 0){throw 'The live UI check failed.'}
} finally {
    if(-not $browser.HasExited){Stop-Process -Id $browser.Id -ErrorAction SilentlyContinue}
}
