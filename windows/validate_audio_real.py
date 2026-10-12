"""Approved synthetic audio only; execute with the verified project core venv.

Default is plan-only. --dsp runs CPU spectrum/debuzz. --whisper runs one local
Whisper transcription under the same named GPU mutex used by the studio.
"""
import argparse, hashlib, json, math, os, pathlib, re, struct, subprocess, sys, time, wave
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--dsp', action='store_true')
parser.add_argument('--whisper', action='store_true')
args = parser.parse_args()
if not (args.dsp or args.whisper):
    print(json.dumps({'plan': True, 'inputs': 'generated sine/buzz and installed offline Windows voice only', 'externalInference': False, 'whisperModel': 'whisper/whisper-large-v3-ct2-float16', 'gpuSerial': 'Local\\WindowsMusicLab-GPU0'}))
    raise SystemExit(0)

expected = ROOT / '.venv/Scripts/python.exe'
if pathlib.Path(sys.executable).resolve() != expected.resolve():
    raise SystemExit('Use the isolated verified .venv interpreter')
ready = json.loads((ROOT / 'windows/cache/validation-runtime/ready.json').read_text(encoding='utf-8-sig'))
if not ready.get('completed') or not ready['profiles']['core']['importChecksPassed']:
    raise SystemExit('Runtime imports are not verified')
sys.path.insert(0, str(ROOT / 'lab'))
import platform_runtime as runtime
os.environ['RUACH_GPU_MUTEX'] = r'Local\WindowsMusicLab-GPU0'
os.environ['RUACH_WDDM_MEMORY_POLICY'] = 'aggregate'
os.environ['CUDA_VISIBLE_DEVICES'] = '0'
os.environ['WINDOWS_MUSIC_LAB_LOCAL_ONLY'] = os.environ['RUACH_OFFLINE'] = '1'
runtime.configure_runtime(ROOT)
folder = ROOT / 'windows/cache/real-audio'
folder.mkdir(parents=True, exist_ok=True)
report = {'started': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'syntheticOnly': True, 'externalInference': False, 'python': str(expected), 'tests': {}}

def run(command, timeout=180):
    result = runtime.run_process(command, cwd=ROOT, env=runtime.job_environment(ROOT), capture_output=True, text=True, encoding='utf-8', timeout=timeout)
    if result.returncode:
        raise RuntimeError(f'{command[1]} exit {result.returncode}: {result.stderr[-4000:]}')
    return result

try:
    if args.dsp:
        sample = folder / 'synthetic-buzz.wav'
        rate, seconds = 48000, 5
        with wave.open(str(sample), 'wb') as f:
            f.setparams((2, 2, rate, 0, 'NONE', 'not compressed'))
            data = bytearray()
            for i in range(rate * seconds):
                t = i / rate
                ripple = 1 + .25 * math.cos(2 * math.pi * 25 * t)
                high = .18 * ripple * (math.sin(2*math.pi*6101*t) + .35*math.sin(2*math.pi*9373*t))
                value = int(32767 * (.14 * math.sin(2*math.pi*220*t) + high))
                data.extend(struct.pack('<hh', value, value))
            f.writeframes(data)
        spec = folder / 'synthetic.spec'
        run([str(expected), str(ROOT/'lab/spectrum_job.py'), str(sample), str(spec)])
        raw = spec.read_bytes()
        if raw[:4] != b'HSP1': raise RuntimeError('Spectrum signature differs')
        length = struct.unpack('<I', raw[4:8])[0]
        header = json.loads(raw[8:8+length])
        if header['sr'] != rate or header['seconds'] != seconds or header['bins'] != 1025:
            raise RuntimeError('Spectrum timing/frequency header differs')
        expected_size = 8+length+header['frames']*header['bins']+(header['welchBins']+6)*4
        if len(raw) != expected_size: raise RuntimeError('Spectrum payload is incomplete')
        avg = struct.unpack('<'+'f'*(header['welchBins']+6), raw[-(header['welchBins']+6)*4:])
        if not all(math.isfinite(x) for x in avg): raise RuntimeError('Spectrum has nonfinite values')
        clean = folder / 'synthetic-clean.flac'
        job = run([str(expected), str(ROOT/'lab/debuzz.py'), str(sample), str(clean), '0.8'])
        measure = json.loads(job.stdout.strip().splitlines()[-1])
        import soundfile as sf
        y, sr = sf.read(str(clean), always_2d=True)
        if sr != rate or y.shape != (rate*seconds, 2) or not clean.is_file():
            raise RuntimeError('Debuzz output timing/channels differs')
        if not measure['found'] or measure['after']['frame'] >= measure['before']['frame']:
            raise RuntimeError('Synthetic frame buzz was not reduced')
        report['tests']['dsp'] = {'passed': True, 'spectrum': header, 'debuzz': measure, 'outputSha256': hashlib.sha256(clean.read_bytes()).hexdigest()}
    if args.whisper:
        model = ROOT/'whisper/whisper-large-v3-ct2-float16'
        manifest = json.loads((ROOT/'windows/full-audio-models.json').read_text(encoding='utf-8'))
        for row in manifest['models']:
            if row['profile'] != 'whisper': continue
            file = ROOT / row['destination']
            if not file.is_file() or file.stat().st_size != row['size']:
                raise RuntimeError('Whisper file is missing/incomplete')
            h = hashlib.sha256()
            with file.open('rb') as f:
                for b in iter(lambda:f.read(8*1024*1024), b''): h.update(b)
            if h.hexdigest()!=row['sha256']: raise RuntimeError('Whisper SHA256 differs')
        speech = folder/'synthetic-speech.wav'
        script = folder/'speech-fixture.ps1'
        speech_meta=folder/'speech-fixture.json'
        script.write_text("$ErrorActionPreference='Stop'\nAdd-Type -AssemblyName System.Speech\n$s=New-Object System.Speech.Synthesis.SpeechSynthesizer\ntry {$voices=@($s.GetInstalledVoices()|Where-Object {$_.Enabled}); $voice=$voices|Where-Object {$_.VoiceInfo.Culture.TwoLetterISOLanguageName -eq 'en'}|Select-Object -First 1; if(-not $voice){$voice=$voices|Where-Object {$_.VoiceInfo.Culture.TwoLetterISOLanguageName -eq 'ru'}|Select-Object -First 1}; if(-not $voice){throw 'No installed offline English/Russian voice; no voice package was installed'}; $lang=$voice.VoiceInfo.Culture.TwoLetterISOLanguageName; $text=if($lang -eq 'ru'){'Это локальная проверка звука. Музыка остаётся на этом компьютере.'}else{'This is a local audio test. Music stays on this computer.'}; $s.SelectVoice($voice.VoiceInfo.Name); $s.SetOutputToWaveFile('"+str(speech).replace("'","''")+"'); $s.Speak($text); @{language=$lang;text=$text;voice=$voice.VoiceInfo.Name}|ConvertTo-Json|Set-Content -LiteralPath '"+str(speech_meta).replace("'","''")+"' -Encoding UTF8} finally {$s.Dispose()}\n", encoding='utf-8-sig')
        run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(script)], 30)
        fixture=json.loads(speech_meta.read_text(encoding='utf-8-sig'))
        output=folder/'whisper.json'
        import gpu_guard
        with runtime.gpu_lease(timeout=30):
            gpu = gpu_guard.check(0, 5000, ROOT)
            memory = runtime.system_memory()
            # Model3.09GB plus runtime/workspace margin, refreshed under the lease.
            if memory.get('available', 0) < 4*1024**3:
                raise RuntimeError('Whisper test needs at least4GiB available RAM')
            if memory.get('commit_available', 0) < int(4.5*1024**3):
                raise RuntimeError('Whisper test needs at least4.5GiB commit headroom')
            start=time.monotonic()
            job=run([str(expected),str(ROOT/'lab/whisper_job.py'),str(speech),str(output),fixture['language'],str(model),'words'], 600)
        data=json.loads(output.read_text(encoding='utf-8'))
        words=[w for s in data['segments'] for w in s.get('words', [])]
        text=' '.join(s['text'] for s in data['segments'])
        if data['language']!=fixture['language'] or len(text.split())<3 or len(words)<3:
            raise RuntimeError('Whisper produced no valid synthetic transcript')
        if not all(0<=w['s']<=w['e']<=data['duration']+.1 for w in words):
            raise RuntimeError('Whisper word times are invalid')
        expected_words=Counter(re.findall(r'[^\W_]+',fixture['text'].casefold(),re.UNICODE))
        recognized_words=Counter(re.findall(r'[^\W_]+',text.casefold(),re.UNICODE))
        overlap=sum((expected_words & recognized_words).values())
        recall=overlap/sum(expected_words.values())
        if recall < .7:
            raise RuntimeError(f'Whisper did not recognize the known synthetic phrase: word recall{recall:.3f}')
        report['tests']['whisper']={'passed':True,'fixture':fixture,'wordRecall':recall,'gpuAdmission':gpu,'memoryBefore':memory,'elapsed_s':round(time.monotonic()-start,2),'result':data,'stderrTail':job.stderr[-2000:]}
    report['passed']=True
except Exception as exc:
    report['passed']=False
    report['error']=str(exc)
    raise
finally:
    name=('dsp-' if args.dsp else '')+('whisper-' if args.whisper else '')+'report.json'
    (folder/name).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'passed':report.get('passed'), 'tests':list(report['tests']), 'report':str(folder/name)}, ensure_ascii=False))
