"""Real loopback HTTP tests of the full stdlib lab; no inference/dependency installs."""
import json, os, pathlib, subprocess, sys, time, urllib.request, urllib.error, uuid

root = pathlib.Path(sys.argv[1])
port = int(sys.argv[2]) if len(sys.argv)>2 else 41871
scope='windows-audit-'+uuid.uuid4().hex
cache=root/'windows/cache/full-api-test'
cache.mkdir(parents=True,exist_ok=True)
env=os.environ.copy()
env.update(LAB_PORT=str(port),LAB_HOST='127.0.0.1',YUE2CPP_PORT='41868',WINDOWS_MUSIC_LAB_LOCAL_ONLY='1',RUACH_OFFLINE='1',PYTHONUTF8='1',PYTHONIOENCODING='utf-8',PYTHONUNBUFFERED='1',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',TEMP=str(cache),TMP=str(cache))
def call(path,body=None,headers=None,expected=200):
    data=json.dumps(body,ensure_ascii=False).encode() if body is not None else None
    request=urllib.request.Request(f'http://127.0.0.1:{port}'+path,data=data,headers={'Content-Type':'application/json',**(headers or {})})
    try:
        with urllib.request.urlopen(request,timeout=5) as response: status=response.status; content=response.read()
    except urllib.error.HTTPError as error:
        status=error.code;content=error.read()
    assert status==expected,(path,status,content[:300])
    return json.loads(content)
results=[]
with (cache/'lab.log').open('wb') as stdout,(cache/'lab-error.log').open('wb') as stderr:
    child=subprocess.Popen([sys.executable,'-X','utf8',str(root/'lab/lab.py')],cwd=str(root/'lab'),env=env,stdout=stdout,stderr=stderr,creationflags=getattr(subprocess,'CREATE_NEW_PROCESS_GROUP',0))
    try:
        deadline=time.time()+20
        while True:
            try: health=call('/health');break
            except urllib.error.URLError:
                if child.poll() is not None or time.time()>deadline:raise RuntimeError('Lab startup failed; inspect ignored lab-error.log')
                time.sleep(.2)
        assert health.get('ok') is True and health['local_only'] is True
        results.append('real stdlib HTTP startup in local-only mode')
        query='?scope='+scope
        assert call('/writer'+query)['docs']==[]
        doc=call('/writer'+query,{'op':'put','title':'Синтетический документ Windows','style':'piano','lyrics':'Строка теста','notes':'Без пользовательских данных'})
        saved=call('/writer'+query+'&id='+doc['id'])
        assert saved['title']==doc['title'] and saved['lyrics']=='Строка теста'
        snap=call('/writer'+query,{'op':'snapshot','id':doc['id'],'label':'Тестовая версия'})
        assert len(snap['versions'])>=1
        results.append('Unicode Writer save/read/version through actual HTTP routes')
        backup=call('/writer'+query,{'op':'export'})
        assert len(backup['docs'])==1
        call('/writer'+query,{'op':'delete','id':doc['id']})
        assert call('/writer'+query)['docs']==[]
        results.append('Writer backup and trash without deleting originals')
        for path in ('/catalog','/artist/painters','/train/datasets','/daw'):
            value=call(path)
            assert isinstance(value,(dict,list)),path
        results.append('actual catalog/Artist metadata/dataset/DAW APIs without ML dependencies')
        call('/writer'+query,{'op':'put','title':'Forbidden'},headers={'Origin':'https://example.invalid'},expected=403)
        call('/writer'+query,headers={'Host':'localhost.example.invalid:'+str(port)},expected=403)
        call('/writer'+query,headers={'Sec-Fetch-Site':'cross-site'},expected=403)
        results.append('cross-origin, rebinding and cross-site requests blocked before mutation')
        assert call('/writer'+query)['docs']==[]
        report={'passed':True,'checks':results,'inferenceRequests':0,'externalRequests':0,'scope':scope,'port':port}
        (cache/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report,ensure_ascii=True))
    finally:
        if child.poll() is None:
            child.terminate()
            try:child.wait(timeout=5)
            except subprocess.TimeoutExpired:child.kill();child.wait(timeout=5)
