"""Audit binary pip reports against publisher metadata before offline installation.

This helper uses only the Python standard library. It never imports downloaded
packages, sends user files, or uses credentials. Cache and temporary data remain
in the repository's windows/cache directory.
"""
from __future__ import annotations
import argparse, hashlib, json, re, shutil, subprocess, time, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CACHE=ROOT/'windows/cache/validation-runtime'
WHEELS=CACHE/'wheels'
EXPECTED={'torch':('2.11.0+cu128',2753152602),'torchaudio':('2.11.0+cu128',None),'torchvision':('0.26.0+cu128',None)}
RESERVE=50*1024**3
BUDGET=14_000_000_000

def free_space():
    free=shutil.disk_usage(ROOT).free
    if free < RESERVE:
        raise RuntimeError(f'Need 50 GiB free disk; currently {free:,} bytes')
    return free

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(4*1024**2), b''): h.update(block)
    return h.hexdigest()

def read_url(url):
    req=urllib.request.Request(url, headers={'User-Agent':'Windows-Music-Lab-runtime-audit/1.0'})
    with urllib.request.urlopen(req,timeout=90) as response:
        if urllib.parse.urlsplit(response.url).scheme != 'https': raise RuntimeError('Non-HTTPS redirect')
        return response.read()

def official_size(url,filename):
    # CDN forbids HEAD/Range but its regular GET has a trustworthy length.
    headers=CACHE/(filename+'.headers')
    probe=CACHE/(filename+'.probe.part')
    cmd=['curl.exe','--fail','--location','--silent','--show-error','--max-time','3','--limit-rate','1k',
         '--proto','=https','--dump-header',str(headers),'--output',str(probe),url]
    p=subprocess.run(cmd,capture_output=True,text=True)
    text=headers.read_text(encoding='latin1') if headers.is_file() else ''
    lengths=re.findall(r'(?im)^content-length:\s*(\d+)\s*$',text)
    status=re.findall(r'(?im)^HTTP/\S+\s+(\d+)',text)
    if p.returncode not in (0,28) or not lengths or not status or status[-1]!='200':
        raise RuntimeError('Official CUDA wheel GET failed; no CPU/source fallback is allowed')
    return int(lengths[-1])

def audit():
    free_space(); CACHE.mkdir(parents=True,exist_ok=True); WHEELS.mkdir(exist_ok=True)
    seen={}; profiles={}; pypi={}; indexes={}
    metadata_cache=CACHE/'publisher-metadata'; metadata_cache.mkdir(exist_ok=True)
    keys=set()
    for profile in ('core','art'):
        report=json.loads((CACHE/f'report-{profile}.json').read_text(encoding='utf8'))
        for item in report['install']:
            name=re.sub('[-_.]+','-',item['metadata']['name']).lower()
            if name not in EXPECTED: keys.add((name,item['metadata']['version']))
    def publisher(key):
        name,version=key; path=metadata_cache/f'{name}-{version}.json'
        if path.is_file(): data=json.loads(path.read_text(encoding='utf8'))
        else:
            raw=read_url(f'https://pypi.org/pypi/{name}/{version}/json'); data=json.loads(raw)
            path.write_bytes(raw)
        return key,data
    with ThreadPoolExecutor(max_workers=8) as pool:
        for key,data in pool.map(publisher,sorted(keys)):
            pypi[key]=data
    print(f'Publisher JSON audited: {len(pypi)} PyPI versions; checking CUDA publishers.',flush=True)
    for profile in ('core','art'):
        report=json.loads((CACHE/f'report-{profile}.json').read_text(encoding='utf8'))
        entries=[]
        for item in report['install']:
            meta=item['metadata']; name=re.sub('[-_.]+','-',meta['name']).lower(); version=meta['version']
            info=item['download_info']; url=info['url']; parsed=urllib.parse.urlsplit(url)
            filename=urllib.parse.unquote(Path(parsed.path).name)
            digest=info['archive_info'].get('hashes',{}).get('sha256')
            if not digest:
                digest=info['archive_info'].get('hash','').removeprefix('sha256=')
            if parsed.scheme!='https' or parsed.username or parsed.password or parsed.query or not filename.endswith('.whl') or not re.fullmatch('[0-9a-f]{64}',digest):
                raise RuntimeError(f'Invalid wheel or non-pinned source for {name}')
            if name in EXPECTED:
                pin,size=EXPECTED[name]
                if version!=pin or 'cp310-cp310-win_amd64.whl' not in filename or parsed.hostname not in ('download.pytorch.org','download-r2.pytorch.org'):
                    raise RuntimeError(f'Wrong CUDA Windows wheel for {name}')
                if name not in indexes:
                    index_url=f'https://download.pytorch.org/whl/cu128/{name}/'
                    indexes[name]=read_url(index_url).decode()
                    (CACHE/f'{name}-cu128-index.html').write_text(indexes[name],encoding='utf8')
                links=re.findall(r'<a href="([^"]+)"',indexes[name])
                exact=url+'#sha256='+digest
                if exact not in links: raise RuntimeError(f'CUDA wheel digest not found in official index: {name}')
                size=size or official_size(url,filename)
                license_text=meta.get('license') or 'Publisher license bundled in wheel'
            else:
                if parsed.hostname not in ('files.pythonhosted.org','download.pytorch.org','download-r2.pytorch.org'):
                    raise RuntimeError(f'Unapproved publisher host for {name}')
                key=(name,version)
                if key not in pypi:
                    pypi[key]=json.loads(read_url(f'https://pypi.org/pypi/{name}/{version}/json'))
                files=[f for f in pypi[key]['urls'] if f['filename']==filename and f['digests']['sha256']==digest
                       and (parsed.hostname!='files.pythonhosted.org' or f['url']==url)]
                if len(files)!=1: raise RuntimeError(f'PyPI hash/URL mismatch for {name}')
                file=files[0]
                # pip may choose PyTorch's copy of a generic package. Rebind only
                # a byte-identical filename/SHA256 to the canonical PyPI publisher.
                url=file['url']
                if urllib.parse.urlsplit(url).hostname!='files.pythonhosted.org': raise RuntimeError('Unexpected PyPI file host')
                size=int(file['size']); license_text=pypi[key]['info'].get('license_expression') or meta.get('license') or ''
            entry={'name':name,'version':version,'filename':filename,'url':url,'sha256':digest,'size':size,'license':license_text}
            if filename in seen and seen[filename]!=entry: raise RuntimeError('Different metadata for the same wheel')
            seen[filename]=entry; entries.append(entry)
        profiles[profile]=entries
    total=sum(e['size'] for e in seen.values())+114768076
    if total>BUDGET: raise RuntimeError(f'Runtime transfer plan {total:,} exceeds approved 14 GB budget')
    if free_space()-sum(e['size'] for e in seen.values())<RESERVE: raise RuntimeError('Download would reduce free disk below reserve')
    manifest={'schema':1,'python':'3.10-win64','profiles':profiles,'unique_wheels':list(seen.values()),'runtime_download_bytes':total,
              'reserve_bytes':RESERVE,'runtime_budget_bytes':BUDGET,'sources':'PyPI publisher SHA256 / official PyTorch cu128 index','audit_unix':int(time.time())}
    (CACHE/'audited-runtime.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf8')
    for profile,entries in profiles.items():
        lines=['# Hash-locked binary validation profile; generated from audited publisher metadata.']
        lines += [f"{e['name']}=={e['version']} --hash=sha256:{e['sha256']}" for e in sorted(entries,key=lambda x:x['name'])]
        (ROOT/f'windows/requirements-validation-{profile}.lock.txt').write_text('\n'.join(lines)+'\n',encoding='utf8')
    print(json.dumps({'audit':'passed','unique_wheels':len(seen),'profile_counts':{k:len(v) for k,v in profiles.items()},'runtime_download_bytes':total}))

def download(skip_names=(),workers=1):
    manifest=json.loads((CACHE/'audited-runtime.json').read_text(encoding='utf8')); free_space()
    remaining=sum(e['size'] for e in manifest['unique_wheels'] if not (WHEELS/e['filename']).is_file())
    if remaining+114768076>BUDGET or free_space()-remaining<RESERVE: raise RuntimeError('Download budget/reserve exceeded')
    def one(e):
        if e['name'] in skip_names:
            print('coordinated skip; previously verified owner:',e['name'],flush=True); return
        dest=WHEELS/e['filename']; part=Path(str(dest)+'.part')
        if dest.is_file():
            if dest.stat().st_size!=e['size'] or sha(dest)!=e['sha256']: raise RuntimeError(f'Invalid cached wheel kept unchanged: {dest.name}')
            print('verified cached:',dest.name,flush=True); return
        free_space(); print(f"download {e['size']:,} bytes: {dest.name}",flush=True)
        p=subprocess.run(['curl.exe','--fail','--location','--silent','--show-error',
                          '--proto','=https','--proto-redir','=https','--continue-at','-',
                          '--max-time','1800','--speed-time','60','--speed-limit','1024',
                          '--output',str(part),e['url']])
        if p.returncode: raise RuntimeError(f'Download failed ({p.returncode}); partial preserved: {part.name}')
        if part.stat().st_size!=e['size'] or sha(part)!=e['sha256']: raise RuntimeError(f'Wheel size/SHA256 mismatch: {part.name}')
        part.rename(dest); free_space(); print('verified downloaded:',dest.name,flush=True)
    with ThreadPoolExecutor(max_workers=max(1,min(8,workers))) as pool:
        list(pool.map(one,manifest['unique_wheels']))
    print('Requested audited wheels verified; skipped downloads remain pending.' if skip_names else 'All audited wheels have verified size/SHA256.')

def main():
    p=argparse.ArgumentParser(); p.add_argument('phase',choices=['audit','download']); p.add_argument('--skip-download',action='append',default=[]); p.add_argument('--workers',type=int,default=1); args=p.parse_args()
    if args.phase=='audit': audit()
    else: download(args.skip_download,args.workers)
if __name__=='__main__': main()