# Same pinned approved file; HTTP206 chunks and persistent tail resume.
[CmdletBinding()]
param([Parameter(Mandatory)][string]$Url,[Parameter(Mandatory)][string]$Destination,[Parameter(Mandatory)][long]$Size,[Parameter(Mandatory)][string]$Sha256,[ValidateRange(1,6)][int]$Parallel=6)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$root=Split-Path -Parent $PSScriptRoot;$full=[IO.Path]::GetFullPath($Destination);$u=[Uri]$Url
if(-not $full.StartsWith(($root+'\'),[StringComparison]::OrdinalIgnoreCase) -or $u.Scheme -ne 'https' -or $u.Host -ne 'huggingface.co' -or $u.UserInfo -or $u.Query -or $Size -le 0 -or $Sha256 -notmatch '^[a-f0-9]{64}$'){throw 'Unsafe range parameters'}
$part=$full+'.part'
function Length-File([string]$p){if(-not(Test-Path -LiteralPath $p)){return 0L};$s=[IO.File]::Open($p,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::ReadWrite);try{return $s.Length}finally{$s.Dispose()}}
function Header-OK([string]$p,[long]$s,[long]$e){
 if(-not(Test-Path -LiteralPath $p)){return $false};$t=[IO.File]::ReadAllText($p);$m=@([regex]::Matches($t,'(?im)^content-range:\s*bytes\s+(\d+)-(\d+)/(\d+)\s*$'))
 return $m.Count -eq 1 -and [long]$m[0].Groups[1].Value -eq $s -and [long]$m[0].Groups[2].Value -eq $e -and [long]$m[0].Groups[3].Value -eq $Size -and $t -match '(?im)^HTTP/\S+ 206\b'
}
function Append-Segment([string]$from,[string]$to){
 $safe=[IO.Path]::GetFullPath($from);if(-not $safe.StartsWith(($cache+'\'),[StringComparison]::OrdinalIgnoreCase)){throw 'Unsafe generated segment path'}
 $i=[IO.File]::OpenRead($safe);$o=[IO.File]::Open($to,[IO.FileMode]::Append,[IO.FileAccess]::Write,[IO.FileShare]::Read)
 try{$i.CopyTo($o,1MB);$o.Flush($true)}finally{$o.Dispose();$i.Dispose()};Remove-Item -LiteralPath $safe
}
if(Test-Path -LiteralPath $full){return};$offset=Length-File $part;if($offset -gt $Size){throw 'Oversized partial retained'};if($offset -eq $Size){return}
$cache=Join-Path $PSScriptRoot ('cache\validation-models\ranges-'+$Sha256.Substring(0,12));New-Item -ItemType Directory -Path $cache -Force|Out-Null
$originFile=Join-Path $cache 'origin.txt'
if(Test-Path -LiteralPath $originFile){$origin=[long]([IO.File]::ReadAllText($originFile).Trim())}else{
 $old=@(Get-ChildItem -LiteralPath $cache -File -Filter '*.body'|ForEach-Object {if($_.Name -match '^(\d+)-\d+\.body$'){[long]$Matches[1]}})
 $origin=if($old.Count){[long](($old|Measure-Object -Minimum).Minimum)}else{$offset};[IO.File]::WriteAllText($originFile,[string]$origin)
}
$stepFile=Join-Path $cache 'step.txt'
# Preserve the existing64MiB partition; new files use smaller16MiB requests.
if(Test-Path -LiteralPath $stepFile){$step=[long]([IO.File]::ReadAllText($stepFile).Trim())}else{
 $legacy=@(Get-ChildItem -LiteralPath $cache -File -Filter '*.headers').Count -gt 0
 $step=if($legacy){64MB}else{16MB}
 [IO.File]::WriteAllText($stepFile,[string]$step)
}
if($step -notin @(16MB,64MB)){throw 'Unexpected retained range partition'}
$chunks=@();$active=@()
for($at=$origin;$at -lt $Size;$at+=$step){$end=[Math]::Min($at+$step-1,$Size-1);if($end -lt $offset){continue};if($at -lt $offset){throw 'Assembly offset inside range; retained'};$name=[string]$at+'-'+[string]$end;$base=Join-Path $cache $name
 $chunks += [pscustomobject]@{start=$at;end=$end;size=$end-$at+1;body=$base+'.body';headers=$base+'.headers';tail=$base+'.tail';tailHeaders=$base+'.tail.headers';result=$base+'.result';errors=$base+'.errors';process=$null;outTask=$null;errTask=$null;requestStart=0L;requestBody='';requestHeaders=''}
}
function Chunk-OK($c){return (Length-File $c.body) -eq $c.size -and (Header-OK $c.headers $c.start $c.end)}
try{
 foreach($c in $chunks){
  $written=Length-File $c.body;if($written -gt $c.size){throw 'Oversized cached range retained'}
  if($written -gt 0 -and -not(Header-OK $c.headers $c.start $c.end)){throw 'Existing partial range header mismatch; retained'}
  $tail=Length-File $c.tail;if($tail){if($written+$tail -gt $c.size -or -not(Header-OK $c.tailHeaders ($c.start+$written) $c.end)){throw 'Earlier tail header mismatch; retained'};Append-Segment $c.tail $c.body;$written=Length-File $c.body}
  if(Chunk-OK $c){continue}
  while(@($active|Where-Object {-not $_.HasExited}).Count -ge $Parallel){Start-Sleep -Milliseconds 500}
  $disk=New-Object IO.DriveInfo([IO.Path]::GetPathRoot($root));if($disk.AvailableFreeSpace -lt 50GB+$step){throw 'Range paused to preserve50GiB free'}
  $c.requestStart=$c.start+$written;$c.requestBody=if($written){$c.tail}else{$c.body};$c.requestHeaders=if($written){$c.tailHeaders}else{$c.headers};$need=$c.end-$c.requestStart+1
  $a=@('--fail','--location','--silent','--show-error','--range',($c.requestStart.ToString()+'-'+$c.end.ToString()),'--max-filesize',$need.ToString(),'--max-time','1200','--proto','=https','--proto-redir','=https','--dump-header',$c.requestHeaders,'--output',$c.requestBody,'--write-out','HTTP=%{http_code} BODY=%{size_download}',$Url)
  $psi=New-Object Diagnostics.ProcessStartInfo;$psi.FileName=(Get-Command curl.exe).Source;$psi.Arguments=(@($a|ForEach-Object {'"'+$_.Replace('"','\"')+'"'})) -join ' '
  $psi.UseShellExecute=$false;$psi.CreateNoWindow=$true;$psi.RedirectStandardOutput=$true;$psi.RedirectStandardError=$true
  $c.process=[Diagnostics.Process]::Start($psi);$c.outTask=$c.process.StandardOutput.ReadToEndAsync();$c.errTask=$c.process.StandardError.ReadToEndAsync();$active+=$c.process
  Write-Host ('Range started '+$c.requestStart+'-'+$c.end+' PID'+$c.process.Id)
 }
 foreach($c in $chunks){
  if($c.process){$c.process.WaitForExit();[IO.File]::WriteAllText($c.result,$c.outTask.GetAwaiter().GetResult());[IO.File]::WriteAllText($c.errors,$c.errTask.GetAwaiter().GetResult())
   if(-not(Header-OK $c.requestHeaders $c.requestStart $c.end)){throw 'Returned range mismatch; retained'}
   if($c.requestBody -eq $c.tail -and (Length-File $c.tail)){Append-Segment $c.tail $c.body}
   if(($null -ne $c.process.ExitCode -and $c.process.ExitCode -ne 0) -or -not(Chunk-OK $c)){throw ('Range incomplete; prefix retained '+$c.start+' exit'+$c.process.ExitCode)}
  }
  if(-not(Chunk-OK $c)){throw 'HTTP206 range/size mismatch; retained'};if((Length-File $part) -ne $c.start){throw 'Partial changed while assembling; retained'}
  Append-Segment $c.body $part;Write-Host ('Assembled '+(Length-File $part)+'/'+$Size+' bytes')
 }
}finally{foreach($p in $active){if(-not $p.HasExited){Stop-Process -Id $p.Id -ErrorAction SilentlyContinue}}}
if((Length-File $part) -ne $Size){throw 'Range assembly incomplete'}
Write-Host 'Complete partial assembled; caller must verify pinned SHA256 before selecting it.'
