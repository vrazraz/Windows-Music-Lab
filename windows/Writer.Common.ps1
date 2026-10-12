function Get-WriterRoot { Split-Path -Parent $PSScriptRoot }
function Get-WriterState { Join-Path $PSScriptRoot 'state\writer' }
function Save-WriterJson {
    param([string]$Path,$Value)
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Path)|Out-Null
    $part=$Path+'.'+[guid]::NewGuid().ToString('N')+'.part'
    try{
        [IO.File]::WriteAllText($part,($Value|ConvertTo-Json -Depth 12),[Text.UTF8Encoding]::new($false))
        for($attempt=0;$attempt -lt 25;$attempt++){
            try{Move-Item -LiteralPath $part -Destination $Path -Force;break}
            catch{if($attempt -eq 24){throw};Start-Sleep -Milliseconds 20}
        }
    }
    finally{if(Test-Path -LiteralPath $part){Remove-Item -LiteralPath $part}}
}
function Quote-WriterArgument {
    param([string]$Value)
    if($Value -notmatch '[\s"]'){return $Value}
    '"'+[regex]::Replace([regex]::Replace($Value,'(\\*)"','$1$1\"'),'(\\+)$','$1$1')+'"'
}
function Get-WriterUtcTicks {
    param($Value)
    if($Value -is [DateTimeOffset]){return $Value.UtcDateTime.Ticks}
    if($Value -is [DateTime]){
        if($Value.Kind -eq [DateTimeKind]::Unspecified){throw 'Writer timestamp has no timezone.'}
        return $Value.ToUniversalTime().Ticks
    }
    if($Value -isnot [string] -or $Value -notmatch '(Z|[+-]\d{2}:\d{2})$'){throw 'Invalid Writer timestamp.'}
    $parsed=[DateTime]::MinValue
    if(-not [DateTime]::TryParseExact($Value,'o',[Globalization.CultureInfo]::InvariantCulture,[Globalization.DateTimeStyles]::RoundtripKind,[ref]$parsed)){
        throw 'Invalid Writer round-trip timestamp.'
    }
    if($parsed.Kind -eq [DateTimeKind]::Unspecified){throw 'Writer timestamp has no timezone.'}
    return $parsed.ToUniversalTime().Ticks
}
function Get-WriterChild {
    param($Record)
    try{
        $expected=Join-Path (Get-WriterRoot) 'windows\build\writer-cpu\bin\Release\llama-server.exe'
        if($Record.schema_version -ne 1 -or $Record.instance -notmatch '^[a-f0-9]{32}$' -or [string]$Record.server_exe -ne $expected){return $null}
        $p=Get-Process -Id ([int]$Record.server_pid) -ErrorAction Stop
        if($p.Path -ne [string]$Record.server_exe -or $p.StartTime.ToUniversalTime().Ticks -ne (Get-WriterUtcTicks $Record.server_start_utc)){return $null}
        return $p
    }catch{return $null}
}
function Get-WriterLicenseBlob {
    param([string]$Path)
    $bytes=[IO.File]::ReadAllBytes($Path)
    $prefix=[Text.Encoding]::ASCII.GetBytes('blob '+$bytes.Length+[char]0)
    $hash=[Security.Cryptography.SHA1]::Create()
    try{[BitConverter]::ToString($hash.ComputeHash([byte[]]($prefix+$bytes))).Replace('-','').ToLowerInvariant()}
    finally{$hash.Dispose()}
}
