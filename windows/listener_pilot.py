"""Own Windows SAPI fixture and measured Listener pilot; no user audio or cloud speech."""
import argparse
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import time
import uuid
import wave
from listener_resources import memory

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'lab'))
from platform_runtime import job_environment, process_options, terminate_process

SPEECH = '''$ErrorActionPreference='Stop'
$file=[Environment]::GetEnvironmentVariable('WINDOWS_MUSIC_LAB_PILOT_WAV','Process')
$speaker=New-Object -ComObject SAPI.SpVoice
$stream=New-Object -ComObject SAPI.SpFileStream
try {
 if($speaker.GetVoices().Count -lt 1){throw 'No installed local SAPI voice'}
 $stream.Format.Type=18
 $stream.Open($file,3,$false)
 $speaker.AudioOutputStream=$stream
 $speaker.Rate=0
 $speaker.Speak('This is a local synthetic test. The voice was created on this computer. There is no music accompaniment.')|Out-Null
}finally {
 $speaker.AudioOutputStream=$null
 $stream.Close()
 [Runtime.InteropServices.Marshal]::FinalReleaseComObject($stream)|Out-Null
 [Runtime.InteropServices.Marshal]::FinalReleaseComObject($speaker)|Out-Null
}'''


def metrics(pid=0):
    script = '''$m=Get-CimInstance Win32_PerfFormattedData_PerfOS_Memory
$ids=@([int]$env:WINDOWS_MUSIC_LAB_METRIC_PID)
if($ids[0] -le 0){$ids=@()}
$all=@(Get-CimInstance Win32_Process)
$changed=$true
while($changed){$changed=$false;foreach($p in $all){if($ids -contains [int]$p.ParentProcessId -and $ids -notcontains [int]$p.ProcessId){$ids+=([int]$p.ProcessId);$changed=$true}}}
$children=@();foreach($id in $ids){if($id -le 0){continue};$p=Get-Process -Id $id -ErrorAction SilentlyContinue;if($p){$children+=@{pid=$id;name=$p.ProcessName;working_set=$p.WorkingSet64;peak_working_set=$p.PeakWorkingSet64;private_bytes=$p.PrivateMemorySize64;peak_commit=$p.PeakPagedMemorySize64}}}
@{physical_available=[long]$m.AvailableBytes;commit_headroom=([long]$m.CommitLimit-[long]$m.CommittedBytes);children=$children}|ConvertTo-Json -Depth 6 -Compress'''
    env = dict(os.environ, WINDOWS_MUSIC_LAB_METRIC_PID=str(pid))
    result = subprocess.run(['powershell.exe', '-NoProfile', '-Command', script],
                            capture_output=True, text=True, encoding='utf-8', env=env, timeout=30, **process_options())
    if result.returncode:
        raise RuntimeError('Windows memory metrics failed: ' + result.stderr[-400:])
    value = json.loads(result.stdout)
    value.update(memory())  # Override CIM with exact machine-wide native commit counters.
    gpu = subprocess.run(['nvidia-smi', '--query-gpu=index,memory.used,memory.free', '--format=csv,noheader,nounits'],
                         capture_output=True, text=True, encoding='utf-8', timeout=20, **process_options())
    if gpu.returncode:
        raise RuntimeError('GPU metrics failed: ' + gpu.stderr[-400:])
    value['gpus'] = [{'index': int(parts[0]), 'used_mib': int(parts[1]), 'free_mib': int(parts[2])}
                     for line in gpu.stdout.splitlines() if (parts := [s.strip() for s in line.split(',')]) and len(parts) == 3]
    value['time'] = time.time()
    return value


def fixture():
    name = 'windows-listener-pilot-' + time.strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:6]
    folder = ROOT / 'datasets/prepared' / name
    folder.mkdir(parents=True, exist_ok=False)
    wav = folder / '001.wav'
    env = job_environment(ROOT)
    env['WINDOWS_MUSIC_LAB_PILOT_WAV'] = str(wav)
    result = subprocess.run(['powershell.exe', '-NoProfile', '-Command', SPEECH], capture_output=True,
                            text=True, encoding='utf-8', errors='replace', env=env, timeout=60, **process_options())
    if result.returncode:
        raise RuntimeError('Local SAPI fixture failed: ' + result.stderr[-1000:])
    with wave.open(str(wav)) as audio:
        if (audio.getnchannels(), audio.getsampwidth(), audio.getframerate()) != (1, 2, 16000):
            raise RuntimeError('SAPI did not create the expected 16kHz mono PCM WAV')
        seconds = audio.getnframes() / audio.getframerate()
    (folder / 'dataset.json').write_text(json.dumps({
        'fixture': 'WindowsMusicLab local SAPI v1', 'tracks': [{'stem': '001', 'file': '001.wav', 'seconds': seconds}],
        'seconds': seconds}, indent=1), encoding='utf-8')
    return name, folder, seconds


def existing_fixture(name):
    base = (ROOT / "datasets/prepared").resolve()
    folder = (base / name).resolve()
    if base not in folder.parents or not folder.name.startswith("windows-listener-pilot-"):
        raise ValueError("Only an existing owned Listener SAPI fixture is allowed")
    data = json.loads((folder / "dataset.json").read_text(encoding="utf-8"))
    if data.get("fixture") != "WindowsMusicLab local SAPI v1" or data.get("tracks", [{}])[0].get("stem") != "001":
        raise ValueError("Dataset is not the previously created own SAPI fixture")
    audio = (folder / "001.wav").resolve()
    if folder not in audio.parents or (folder / "styles.json").exists():
        raise ValueError("Fixture audio must be contained and its previous results preserved")
    with wave.open(str(audio)) as wav:
        if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) != (1, 2, 16000):
            raise ValueError("Fixture format changed")
        seconds = wav.getnframes() / wav.getframerate()
    return folder.name, folder, seconds


def performance_counters(diagnostic):
    """Parse native recorded counters, retaining the distinction between tokens and runs."""
    counters = {}
    patterns = {
        "prompt_eval": r"prompt eval time\s*=\s*([\d.]+)\s+ms\s*/\s*(\d+)\s+tokens\s*\(\s*[\d.]+\s+ms per token,\s*([\d.]+)\s+tokens per second\)",
        "generation_eval": r"(?<!prompt )eval time\s*=\s*([\d.]+)\s+ms\s*/\s*(\d+)\s+runs\s*\(\s*[\d.]+\s+ms per token,\s*([\d.]+)\s+tokens per second\)"}
    for key, pattern in patterns.items():
        counter = re.search(pattern, diagnostic)
        if counter:
            counters[key] = {"milliseconds": float(counter.group(1)),
                             "tokens" if key == "prompt_eval" else "runs": int(counter.group(2)),
                             "tokens_per_second": float(counter.group(3))}
    return counters


def speech_fixture_assessment(tags):
    """Only the coarse speech/no-music classification of our known SAPI fixture."""
    heard = {" ".join(tag.lower().split()) for tag in tags.split(",") if tag.strip()}
    allowed = {"speech", "spoken word", "spoken voice", "no music", "no instruments"}
    return {"scope": "owned 10-second SAPI speech-only excerpt: coarse speech versus music classification",
            "passed": bool(heard & {"speech", "spoken word", "spoken voice"}) and
                      "no music" in heard and heard <= allowed,
            "general_music_tagging_verified": False,
            "long_audio_verified": False}


def decoded_evidence(wrapper_log):
    """Record exact native performance counters; do not infer tokens from tag text."""
    match = re.search(r"^listener logs: (.+)$", Path(wrapper_log).read_text(encoding="utf-8"), re.M)
    if not match:
        return {"native_log_found": False}
    base = (ROOT / "lab/cache/listener").resolve()
    run = Path(match.group(1).strip()).resolve()
    if base not in run.parents:
        raise ValueError("Pilot native logs escaped the owned cache")
    directory = run / "0001"
    diagnostic = (directory / "stderr.log").read_text(encoding="utf-8")
    output = (directory / "stdout.log").read_text(encoding="utf-8")
    record = json.loads((directory / "command.json").read_text(encoding="utf-8"))
    value = {"native_log_found": True, "native_log": str(directory), "native_command": record,
             "decoded_stdout": output, "counters": {}}
    value["counters"] = performance_counters(diagnostic)
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--dataset', default='', help='reuse the specified own SAPI fixture, preserving previous results')
    parser.add_argument('--pending-core-bytes', type=int, default=0)
    args = parser.parse_args()
    name, folder, seconds = existing_fixture(args.dataset) if args.dataset else fixture()
    print(json.dumps({'dataset': name, 'path': str(folder), 'source': 'local OS SAPI, no user files', 'seconds': seconds}), flush=True)
    if args.prepare_only:
        return 0
    import listener_download
    for _, _, _, relative, size, expected in listener_download.ASSETS:
        path = listener_download.destination(relative)
        if not path.is_file() or path.stat().st_size != size or listener_download.sha256(path) != expected:
            raise RuntimeError('Pilot weights/notices are not fully SHA256 verified: ' + relative)
    listener_download.disk_gate(0, args.pending_core_bytes, 0)
    before = metrics()
    # Short pilot observed8.17GiB native peak commit. Admission11GiB commit/10GiB RAM
    # leaves a conservative reserve, not a hard limit or proof for120s. Checked again in the
    # production Listener under the GPU lease, before model imports/loading.
    if before['physical_available'] < 10 * 2**30 or before['commit_headroom'] < 11 * 2**30:
        raise RuntimeError('Insufficient physical/commit headroom for the first measured Listener pilot: ' + json.dumps(before))
    if not any(gpu['index'] == 0 and gpu['free_mib'] >= 8200 for gpu in before['gpus']):
        raise RuntimeError('Need the approved estimated 8200MiB free on physical GPU0 for the pilot')
    cache = ROOT / 'windows/cache/listener/pilot' / name / ('attempt-' + time.strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:6])
    cache.mkdir(parents=True, exist_ok=False)
    command = [str(ROOT / '.venv/Scripts/python.exe'), str(ROOT / 'lab/listener.py'), name, '--gpu', '0',
               '--seconds', '10', '--only', '001', '--model', str(ROOT / listener_download.ASSETS[0][3]),
               '--mmproj', str(ROOT / listener_download.ASSETS[1][3])]
    report = {'dataset': name, 'argv': command, 'before': before, 'samples': [], 'verified': False}
    report['gpu_admission_policy'] = {'mode': 'aggregate', 'source': 'existing Start-Full.ps1 launch contract',
                                      'free_mib_required': 8200, 'known_heavy_foreign_process_veto': True}
    start = time.monotonic()
    child_env = job_environment(ROOT)
    child_env.update(RUACH_GPU_MUTEX="Local\\WindowsMusicLab-GPU0", YUE2CPP_PORT="41868",
                     RUACH_WDDM_MEMORY_POLICY="aggregate")
    with (cache / 'wrapper.log').open('w', encoding='utf-8') as log:
        process = subprocess.Popen(command, cwd=str(ROOT), env=child_env, stdin=subprocess.DEVNULL,
                                   stdout=log, stderr=subprocess.STDOUT, **process_options())
        try:
            while process.poll() is None:
                report['samples'].append(metrics(process.pid))
                (cache / 'metrics.json').write_text(json.dumps(report, indent=1), encoding='utf-8')
                if time.monotonic() - start > 650:
                    raise TimeoutError('Listener pilot exceeded 650s; only its owned tree will be stopped')
                time.sleep(1)
            report['returncode'] = process.wait()
        finally:
            if process.poll() is None:
                terminate_process(process)
            report.update(seconds=round(time.monotonic() - start, 3), after=metrics())
            (cache / 'metrics.json').write_text(json.dumps(report, indent=1), encoding='utf-8')
    report['native_decode'] = decoded_evidence(cache / 'wrapper.log')
    (cache / 'metrics.json').write_text(json.dumps(report, indent=1), encoding='utf-8')
    style_path = folder / 'styles.json'
    if report['returncode'] != 0 or not style_path.is_file():
        raise RuntimeError(f'Listener actual pilot failed; see {cache / "wrapper.log"}')
    tags = json.loads(style_path.read_text(encoding='utf-8')).get('tags', {}).get('001', '')
    if not tags.strip():
        raise RuntimeError('Listener did not produce a real nonempty answer')
    assessment = speech_fixture_assessment(tags)
    report.update(verified=True, execution_verified=True, quality_verified=assessment['passed'],
                  quality_assessment=assessment, tags=tags,
                  verification_scope='actual native execution/CUDA/audio decode plus the stated coarse SAPI fixture assessment only')
    (cache / 'metrics.json').write_text(json.dumps(report, indent=1), encoding='utf-8')
    print(json.dumps({'actual_decoded_tags': tags, 'report': str(cache / 'metrics.json'), 'seconds': report['seconds']}), flush=True)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, RuntimeError, TimeoutError) as error:
        print('Listener pilot stopped: ' + str(error), file=sys.stderr, flush=True)
        sys.exit(1)
