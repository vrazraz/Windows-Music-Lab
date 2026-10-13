"""Authorized CPU-only synthetic Inspect/basic Remaster validation. Default: plan only."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true')
    args = parser.parse_args()
    if not args.run:
        print(json.dumps({'plan': True, 'scope': 'own synthetic CPU Inspect and basic FFmpeg Remaster only',
                          'models': False, 'network': False, 'newDependencies': False}))
        return 0
    expected = ROOT / '.venv/Scripts/python.exe'
    require(Path(sys.executable).resolve() == expected.resolve(), 'Use the verified project core venv')
    ready = json.loads((ROOT / 'windows/cache/validation-runtime/ready.json').read_text(encoding='utf-8-sig'))
    require(ready.get('completed') and ready['profiles']['core']['importChecksPassed'], 'Installed core runtime is not verified')
    sys.path.insert(0, str(ROOT / 'lab'))
    import platform_runtime as runtime
    os.environ.update(WINDOWS_MUSIC_LAB_LOCAL_ONLY='1', RUACH_OFFLINE='1', CUDA_VISIBLE_DEVICES='')
    runtime.configure_runtime(ROOT)
    import numpy as np
    import soundfile as sf
    folder = ROOT / 'windows/cache/refiner-independent' / (time.strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:6])
    folder.mkdir(parents=True, exist_ok=False)
    report = {'startedUtc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
              'syntheticOnly': True, 'gpuInference': False, 'externalInference': False,
              'newDependencies': False, 'python': str(expected), 'commands': [], 'tests': {}, 'passed': False}

    def run(label, argv, timeout=120):
        begun = time.monotonic()
        child = runtime.run_process(argv, cwd=ROOT, env=runtime.job_environment(ROOT),
                                    stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                    encoding='utf-8', errors='replace', timeout=timeout)
        (folder / (label + '.stdout.log')).write_text(child.stdout or '', encoding='utf-8')
        (folder / (label + '.stderr.log')).write_text(child.stderr or '', encoding='utf-8')
        report['commands'].append({'label': label, 'argv': list(map(str, argv)),
                                   'returncode': child.returncode, 'seconds': round(time.monotonic() - begun, 3)})
        require(child.returncode == 0, label + ' failed: ' + (child.stderr or '')[-1200:])
        return child

    def probe(label, audio):
        child = run(label, ['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(audio)])
        return json.loads(child.stdout)

    def loudness(label, audio):
        child = run(label, ['ffmpeg', '-hide_banner', '-nostats', '-i', str(audio), '-af',
                            'loudnorm=I=-18:TP=-1:LRA=11:print_format=json', '-f', 'null', '-'])
        return json.loads(child.stderr[child.stderr.rindex('{'):child.stderr.rindex('}') + 1])

    def inspect(label, audio):
        output = folder / (label + '.json')
        run(label, [str(expected), str(ROOT / 'lab/inspect_job.py'), str(audio), str(output)])
        return json.loads(output.read_text(encoding='utf-8'))

    try:
        rate = 48000
        t = np.arange(rate * 8) / rate
        # Known synthetic artifacts: continuous tones, DC, one click, exact clipping plateau,
        # one100ms dropout, and one1s reversed-polarity stereo region. No user audio.
        mono = .16 * np.sin(2 * np.pi * 997 * t) + .06 * np.sin(2 * np.pi * 60 * t)
        mono += .04 * (1 + .25 * np.cos(2 * np.pi * 25 * t)) * np.sin(2 * np.pi * 6101 * t)
        x = np.stack([mono + .02, mono + .02], axis=1)
        x[rate] = .85
        x[rate * 2:rate * 2 + 12] = 1.0
        x[rate * 3:rate * 3 + rate // 10] = 0.0
        x[rate * 5:rate * 6, 1] *= -1
        artifact = folder / 'synthetic-artifacts.wav'
        sf.write(artifact, x, rate, subtype='PCM_24')
        result = inspect('inspect-artifacts', artifact)
        require((result['rate'], result['channels'], result['seconds']) == (rate, 2, 8.0), 'Inspect format/timing differs')
        require(any(abs(q['hz'] - 997) < 12 and q['share'] >= .35 for q in result['tones']), 'Inspect missed known997Hz tone')
        require(any(abs(q['at'] - 1.0) < .02 for q in result['clicks']), 'Inspect missed injected click')
        require(not any(5.05 < q['at'] < 5.95 for q in result['clicks']), 'Inspect reported quantization residue as clicks in the known antiphase null')
        require(any(abs(q['at'] - 2.0) < .02 and q['samples'] == 12 for q in result['clipping']['first']), 'Inspect missed clipping plateau')
        require(any(abs(q['at'] - 3.0) < .02 and 90 <= q['ms'] <= 110 for q in result['dropouts']), 'Inspect missed100ms dropout')
        require(any(abs(q['at'] - 5.0) < .02 and q['correlation'] < -.95 for q in result['stereo']['negative']), 'Inspect missed reversed stereo region')
        require(all(math.isfinite(v) for v in result['dc']) and abs(result['dc'][0] - float(x[:, 0].mean())) < 1e-5, 'Inspect DC measurement differs')
        require(all(math.isfinite(result['loudness'][key]) for key in ('lufs', 'lra', 'true_peak')), 'Inspect loudness incomplete')
        report['tests']['inspect_artifacts'] = {'passed': True, 'expected': {'toneHz': 997, 'clickAt': 1,
            'clippingAt': 2, 'clippingSamples': 12, 'dropoutAt': 3, 'dropoutMs': 100, 'negativeStereoAt': 5}, 'result': result}

        # A valid sub-STFT-length clip exercises the actual small-file path, not a mocked import.
        short = folder / 'synthetic-short.wav'
        sf.write(short, x[:rate // 10], rate, subtype='PCM_24')
        short_result = inspect('inspect-short', short)
        require((short_result['seconds'], short_result['rate'], short_result['channels']) == (.1, rate, 2), 'Short Inspect format differs')
        report['tests']['inspect_short'] = {'passed': True, 'result': short_result}

        take = folder / 'synthetic-take'
        take.mkdir()
        t = np.arange(rate * 6) / rate
        y = .20 * np.sin(2 * np.pi * 440 * t) + .045 * np.sin(2 * np.pi * 1234 * t)
        raw = folder / 'synthetic-remaster-source.wav'
        sf.write(raw, np.stack([y + .025, .8 * y + .025], axis=1), rate, subtype='PCM_24')
        source = take / 'audio.wav'
        run('synthetic-metadata', ['ffmpeg', '-v', 'error', '-y', '-i', str(raw), '-c:a', 'pcm_s24le',
                                  '-metadata', 'title=own synthetic title', '-metadata', 'comment=own synthetic comment', str(source)])
        original_probe = probe('source-probe', source)
        require(original_probe['format'].get('tags', {}).get('title') == 'own synthetic title', 'Synthetic metadata fixture not injected')
        config = {'cleanup': True, 'fade': .3, 'trim_start': 1.0, 'trim_end': 5.0,
                  'deess': False, 'hz432': False, 'loudnorm': True, 'lufs': -18, 'tp': -1,
                  'formats': ['wav', 'flac']}
        settings = folder / 'remaster-settings.json'
        settings.write_text(json.dumps(config), encoding='utf-8')
        out = folder / 'basic-remaster'
        child = run('remaster', [str(expected), str(ROOT / 'lab/remaster_job.py'), str(take), str(out), str(settings)], 180)
        value = json.loads(child.stdout.strip().splitlines()[-1])
        require({row['format'] for row in value['files']} == {'wav', 'flac'}, 'Remaster did not report both requested files')
        verified = {}
        for fmt in config['formats']:
            audio = out / ('remaster_FINAL.' + fmt)
            z, sr = sf.read(audio, dtype='float64', always_2d=True)
            require(sr == rate and z.shape == (rate * 4, 2), 'Remaster trim/duration/channels differs: ' + fmt)
            require(np.isfinite(z).all(), 'Remaster nonfinite output: ' + fmt)
            measured = loudness('remaster-' + fmt + '-loudness', audio)
            require(abs(float(measured['input_i']) + 18) <= .35, 'Remaster LUFS differs: ' + fmt)
            require(float(measured['input_tp']) <= -.7, 'Remaster true peak exceeded tolerance: ' + fmt)
            mid_rms = float(np.sqrt(np.mean(z[rate:rate * 2]**2)))
            begin_rms = float(np.sqrt(np.mean(z[:rate // 100]**2)))
            end_rms = float(np.sqrt(np.mean(z[-rate // 100:]**2)))
            require(begin_rms < .1 * mid_rms and end_rms < .1 * mid_rms, 'Remaster fade not effective: ' + fmt)
            require(np.max(np.abs(z.mean(axis=0))) < .002, 'Remaster cleanup did not remove injected DC: ' + fmt)
            metadata = probe('remaster-' + fmt + '-probe', audio)
            require(not ({'title', 'comment'} & set(metadata['format'].get('tags', {}))), 'Source title/comment survived remaster: ' + fmt)
            require(sf.info(audio).subtype == 'PCM_24', 'Remaster expected24bit PCM: ' + fmt)
            verified[fmt] = {'sha256': hashlib.sha256(audio.read_bytes()).hexdigest(), 'frames': len(z), 'channels': 2,
                             'sampleRate': sr, 'subtype': sf.info(audio).subtype, 'loudness': measured,
                             'first10msRms': begin_rms, 'last10msRms': end_rms, 'middleRms': mid_rms,
                             'dc': z.mean(axis=0).tolist(), 'metadataTags': metadata['format'].get('tags', {})}
        require(abs(value['lufs_out'] + 18) <= .4, 'Worker LUFS summary differs')
        require((out / 'debunker.log').is_file(), 'Remaster log missing')
        report['tests']['basic_remaster'] = {'passed': True, 'settings': config, 'worker': value, 'files': verified}
        report['limits'] = ['own short synthetic CPU fixtures only', 'no stems/separation/Calf/UniverSR/models',
                            'deess and432Hz disabled', 'no subjective music quality or browser workflow validation']
        report['passed'] = True
    except Exception as error:
        report['error'] = type(error).__name__ + ': ' + str(error)
        raise
    finally:
        report['finishedUtc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        (folder / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'passed': report['passed'], 'tests': list(report['tests']), 'report': str(folder / 'report.json')}), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
