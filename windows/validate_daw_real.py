"""Real local compressed-audio DAW export using only the root synthetic DSP fixture."""
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import sys
import wave
from xml.etree import ElementTree as ET
import zipfile

ROOT=Path(__file__).resolve().parents[1]
if Path(sys.executable).resolve() != (ROOT/'.venv/Scripts/python.exe').resolve():
    raise SystemExit('Use the verified isolated core venv')
sys.path.insert(0,str(ROOT/'lab'))
import platform_runtime as runtime
os.environ['WINDOWS_MUSIC_LAB_LOCAL_ONLY']=os.environ['RUACH_OFFLINE']='1'
runtime.configure_runtime(ROOT)
import rpp
import dawproject
import soundfile as sf

cache=ROOT/'windows/cache/real-daw'
outputs=cache/'library'
take=outputs/'synthetic-buzz'
take.mkdir(parents=True,exist_ok=True)
fixture=ROOT/'windows/cache/real-audio/synthetic-clean.flac'
dsp=json.loads((ROOT/'windows/cache/real-audio/dsp-report.json').read_text(encoding='utf-8'))
if not dsp['passed'] or hashlib.sha256(fixture.read_bytes()).hexdigest()!=dsp['tests']['dsp']['outputSha256']:
    raise SystemExit('Synthetic DSP fixture provenance differs')
shutil.copyfile(fixture,take/'audio.flac')
(take/'meta.json').write_text(json.dumps({'title':'Synthetic audio export','seconds':5,'created':1}),encoding='utf-8')
(take/'request.json').write_text(json.dumps({'style':'synthetic,90 bpm','lyrics':'[Verse]\nSynthetic fixture'}),encoding='utf-8')
report={'syntheticOnly':True,'externalInference':False,'ffmpegActual':True,'tests':{}}
try:
    for name,module in [('reaper',rpp),('dawproject',dawproject)]:
        archive,info=module.build(ROOT,outputs,take.name,cache=cache/'timing')
        archive=Path(archive)
        with zipfile.ZipFile(archive) as z:
            assert z.testzip() is None
            assert all(not x.startswith('/') and '\\' not in x and '..' not in x.split('/') for x in z.namelist())
            audio=next(x for x in z.namelist() if x.endswith('.wav'))
            # FFmpeg uses WAVE_FORMAT_EXTENSIBLE for24bitPCM, supported by libsndfile.
            # Python3.10 wave only recognizes the earlier PCM format tag.
            f=sf.info(io.BytesIO(z.read(audio)))
            assert (f.channels,f.subtype,f.samplerate,f.frames)==(2,'PCM_24',48000,240000)
            if name=='dawproject':
                for member in ('project.xml','metadata.xml'):
                    ET.fromstring(z.read(member))
            else:
                project=next(x for x in z.namelist() if x.endswith('.RPP'))
                text=z.read(project).decode('utf-8')
                assert 'FILE "audio/00-mix.wav"' in text and 'TEMPO 90' in text
        report['tests'][name]={'passed':True,'path':str(archive),'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'info':info,'audioFormat':'stereo48kHz24bitPCM','audioSeconds':5}
    report['passed']=True
except Exception as e:
    report['passed']=False;report['error']=str(e)
    raise
finally:
    (cache/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'passed':report.get('passed'),'report':str(cache/'report.json')}))
