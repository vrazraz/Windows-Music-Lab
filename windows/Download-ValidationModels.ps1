[CmdletBinding()]
param([switch]$PlanOnly,[switch]$UseRanges)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'Common.ps1')
$root=Get-RuachRoot
$items=@()
$audio=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'full-audio-models.json') -Raw | ConvertFrom-Json
$whisper=@($audio.models | Where-Object profile -eq 'whisper')
foreach($f in $whisper){
 if($f.repo -ne 'Systran/faster-whisper-large-v3' -or $f.revision -ne 'edaa852ec7e145841d8ffdb056a99866b5f0a478' -or $f.destination -ne ('whisper/whisper-large-v3-ct2-float16/'+$f.file)){throw 'Unexpected Whisper manifest'}
 $items += [pscustomobject]@{destination=$f.destination;url=$f.url;size=[long]$f.size;sha256=$f.sha256;remote=('/Systran/faster-whisper-large-v3/resolve/'+$f.revision+'/'+$f.file)}
}
if($whisper.Count -ne 5 -or [long](($items|Measure-Object size -Sum).Sum) -ne 3090835702){throw 'Approved model set or byte budget changed'}
$seen=@{}
foreach($f in $items){
 if($f.destination -notmatch '^[A-Za-z0-9_./-]+$' -or @($f.destination.Split('/')|Where-Object {$_ -in @('','..','.')}).Count -or $seen.ContainsKey($f.destination)){throw 'Unsafe or duplicate model destination'}
 $seen[$f.destination]=$true
 $full=[IO.Path]::GetFullPath((Join-Path $root $f.destination))
 if(-not $full.StartsWith(($root+'\'),[StringComparison]::OrdinalIgnoreCase)){throw 'Model destination escaped this worktree'}
 $u=[Uri]$f.url
 if($u.Scheme -ne 'https' -or $u.Host -ne 'huggingface.co' -or $u.AbsolutePath -ne $f.remote -or $u.Query -or $u.UserInfo -or $f.size -le 0 -or $f.sha256 -notmatch '^[a-f0-9]{64}$'){throw 'Unexpected pinned public model source'}
 $f|Add-Member -NotePropertyName full -NotePropertyValue $full
}
$total=[long](($items|Measure-Object size -Sum).Sum)
if($total+14000000000 -gt 25000000000){throw 'Approved runtime plus model download budget exceeded'}
function Assert-DiskReserve {
 $remaining=0L
 foreach($x in $items){
  if(Test-Path -LiteralPath $x.full){continue}
  $part=$x.full+'.part'; $written=if(Test-Path -LiteralPath $part){(Get-Item -LiteralPath $part).Length}else{0L}
  $remaining += [Math]::Max(0L,$x.size-$written)
 }
 $disk=New-Object IO.DriveInfo([IO.Path]::GetPathRoot($root))
 if($disk.AvailableFreeSpace-$remaining -lt 50GB){throw 'Download refused: retain at least 50 GiB free after remaining model bytes'}
 return $disk.AvailableFreeSpace
}
$free=Assert-DiskReserve
$plan=[pscustomobject]@{root=$root;files=$items.Count;modelBytes=$total;runtimeBudgetBytes=14000000000;combinedBudgetBytes=($total+14000000000);freeBytes=$free;reserveBytes=50GB;profiles=@('whisper')}
$plan|ConvertTo-Json
if($PlanOnly){return}
$logDir=Join-Path $PSScriptRoot 'cache\validation-models'
New-Item -ItemType Directory -Path $logDir -Force|Out-Null
$done=@()
foreach($f in $items){
 Assert-DiskReserve|Out-Null
 if($UseRanges -and $f.size -ge 512MB -and -not(Test-Path -LiteralPath $f.full)){& (Join-Path $PSScriptRoot 'Receive-RangeModel.ps1') -Url $f.url -Destination $f.full -Size $f.size -Sha256 $f.sha256}
 Receive-RuachFile -Url $f.url -Destination $f.full -Size $f.size -Sha256 $f.sha256
 $done += [pscustomobject]@{path=$f.destination;size=$f.size;sha256=$f.sha256;verified=[DateTime]::UtcNow.ToString('o')}
 [IO.File]::WriteAllText((Join-Path $logDir 'verified-whisper.json'),($done|ConvertTo-Json -Depth 5),(New-Object Text.UTF8Encoding($false)))
}
Assert-DiskReserve|Out-Null
Write-Host 'Approved Whisper files verified by SHA256; no inference was run.'
