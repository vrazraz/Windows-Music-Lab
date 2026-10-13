[CmdletBinding()]
param([string]$StudioUrl='http://localhost:41868/')
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'Writer.Common.ps1')
$uri=[Uri]$StudioUrl
if($uri.Scheme -ne 'http' -or $uri.Host -notin @('localhost','127.0.0.1') -or $uri.Port -ne 41868){throw 'Only the local Studio test origin is allowed.'}
$chrome=Join-Path $env:ProgramFiles 'Google\Chrome\Application\chrome.exe'
$node=Join-Path $env:ProgramFiles 'nodejs\node.exe'
if(-not(Test-Path -LiteralPath $chrome) -or -not(Test-Path -LiteralPath $node)){throw 'Existing Chrome/Node is required; no installer is executed.'}
$state=Get-WriterState
$cache=Join-Path $PSScriptRoot 'cache\writer'
$profile=Join-Path $cache ('browser-test-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path $cache,$profile,$state|Out-Null
$oldTemp=$env:TEMP;$oldTmp=$env:TMP
$browser=$null
try{
    $env:TEMP=$cache;$env:TMP=$cache
    $args=@('--headless=new','--disable-gpu','--mute-audio',
        '--remote-debugging-port=0','--remote-debugging-address=127.0.0.1',
        "--user-data-dir=$profile","--disk-cache-dir=$(Join-Path $profile 'cache')",
        '--disable-background-networking','--disable-component-update','--disable-sync',
        '--no-first-run','--no-default-browser-check','about:blank')
    $launch=@{FilePath=$chrome;ArgumentList=(($args|ForEach-Object {Quote-WriterArgument $_}) -join ' ');WindowStyle='Hidden';PassThru=$true;
        RedirectStandardOutput=(Join-Path $cache 'chrome.stdout.log');RedirectStandardError=(Join-Path $cache 'chrome.stderr.log')}
    $browser=Start-Process @launch
    & $node (Join-Path $PSScriptRoot 'qa-writer.mjs') $profile $state $StudioUrl
    if($LASTEXITCODE -ne 0){throw 'Real browser CORS test failed.'}
}finally{
    if($browser -and -not $browser.HasExited){$browser.Kill();$browser.WaitForExit(5000)|Out-Null}
    $env:TEMP=$oldTemp;$env:TMP=$oldTmp
}
