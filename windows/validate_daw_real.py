"""Real local DAW structural validation; synthetic files, no models/DAW/network.

Run with the verified .venv/Scripts/python.exe. Existing legacy DSP evidence under
windows/cache/real-daw remains unchanged. Every new run owns a unique ignored folder.
"""
import datetime
import hashlib
import io
import json
import math
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import shlex
import shutil
import struct
import sys
import uuid
import wave
from xml.etree import ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
if Path(sys.executable).resolve() != (ROOT / '.venv/Scripts/python.exe').resolve():
    raise SystemExit('Use the verified isolated core venv')
sys.path.insert(0, str(ROOT / 'lab'))
import platform_runtime as runtime
os.environ['WINDOWS_MUSIC_LAB_LOCAL_ONLY'] = os.environ['RUACH_OFFLINE'] = '1'
runtime.configure_runtime(ROOT)
import abc_tools
import dawproject
import library_io
import midi_score
import rpp
import soundfile as sf

PPQ = 480
ABC = ('X:1\nT:\nM:3/4\nL:1/4\nQ:1/4=80\n'
       'V: Vocal clef=treble name="Vocal Melody" snm="Vocal"\n'
       'V: Ins clef=treble name="Ins Melody" snm="Inst."\nK:D\n'
       'V: Vocal\nDEF|GAB|\nV: Ins\nD,3|A,3|')
NOTES = {'Vocal': [(0, 62, 1), (1, 64, 1), (2, 66, 1), (3, 67, 1), (4, 69, 1), (5, 71, 1)],
         'Ins': [(0, 50, 3), (3, 57, 3)]}
LYRICS = '[Verse]\nСинтетическая строка один\nТихая строка два\n[Chorus]\nСветлая строка три\nПоследняя строка четыре'
ROWS = [{'text': text, 'start': start, 'end': end} for text, start, end in
        [('Синтетическая строка один', .25, .9), ('Тихая строка два', 1.2, 2),
         ('Светлая строка три', 2.5, 3.3), ('Последняя строка четыре', 3.7, 4.7)]]
TITLE = 'Тест & <ноты> "Свет"'
SEEDS = ('18446744073709551614', '9223372036854775807')


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def disk_guard():
    available = shutil.disk_usage(ROOT).free
    if available < 50 * 1024 ** 3 + 64 * 1024 ** 2:
        raise RuntimeError('Preserve global 50 GiB disk reserve plus this small fixture margin')
    return available


def vlq(value):
    result = [value & 127]
    while value >> 7:
        value >>= 7
        result.insert(0, (value & 127) | 128)
    return bytes(result)


def midi_fixture():
    tracks = []
    for ch, (voice, notes) in enumerate(NOTES.items()):
        body = b'\0\xff\x03' + vlq(len(voice)) + voice.encode()
        if ch == 0:
            body += b'\0\xff\x51\x03\x0b\x71\xb0\0\xff\x58\x04\x03\x02\x18\x08\0\xff\x59\x02\x02\0'
        events = []
        for start, pitch, duration in notes:
            events.extend([(start * PPQ, bytes([0x90 | ch, pitch, 96 - 16 * ch])),
                           ((start + duration) * PPQ, bytes([0x80 | ch, pitch, 0]))])
        events.sort(key=lambda event: (event[0], event[1][0] >> 4))
        last = 0
        for tick, event in events:
            body += vlq(tick - last) + event
            last = tick
        body += b'\0\xff\x2f\0'
        tracks.append(b'MTrk' + struct.pack('>I', len(body)) + body)
    return b'MThd' + struct.pack('>IHHH', 6, 1, 2, PPQ) + b''.join(tracks)


def pcm_fixture(path, channels=2, rate=48000, width=2):
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = 5 * rate
    data = bytearray()
    scale = 1 << (width * 8 - 15)
    for i in range(frames):
        value = ((i % 128) - 64) * 128 * scale
        for channel in range(channels):
            data.extend((value if channel == 0 else -value).to_bytes(width, 'little', signed=True))
    with wave.open(str(path), 'wb') as handle:
        handle.setparams((channels, width, rate, 0, 'NONE', 'not compressed'))
        handle.writeframes(data)


def ffmpeg(args):
    return runtime.run_process(['ffmpeg', '-v', 'error', '-y', *args], root=ROOT,
                               check=True, capture_output=True, timeout=30)


def zip_safety(archive):
    names = archive.namelist()
    assert archive.testzip() is None
    assert len(names) == len({name.casefold() for name in names})
    for name in names:
        win, posix = PureWindowsPath(name), PurePosixPath(name)
        assert not win.drive and not win.root and not posix.is_absolute()
        assert '\\' not in name and '..' not in posix.parts
        assert all(library_io.valid_component(part) for part in posix.parts)
        mode = archive.getinfo(name).external_attr >> 16
        assert mode & 0o170000 in (0, 0o100000), (name, mode)
    return names


def wav_check(raw, original):
    data, rate = sf.read(io.BytesIO(raw), dtype='int32', always_2d=True)
    info = sf.info(io.BytesIO(raw))
    assert (info.channels, info.subtype, rate, info.frames) == (2, 'PCM_24', 48000, 240000), info
    assert int(abs(data).max()) > 0
    before, original_rate = sf.read(original, dtype='float64', always_2d=True)
    original_info = sf.info(original)
    assert math.isclose(original_info.duration, 5, abs_tol=.03)
    mono = original_info.channels == 1
    if mono:assert (data[:, 0] == data[:, 1]).all(), 'Mono was not duplicated identically'
    before_rms = float((before * before).mean()) ** .5
    normalized = data.astype('float64') / 2 ** 31
    after_rms = float((normalized * normalized).mean()) ** .5
    assert math.isclose(before_rms, after_rms, rel_tol=.15, abs_tol=.001), (before_rms, after_rms)
    exact = original_rate == 48000 and original_info.subtype in ('PCM_16', 'PCM_24')
    if exact:
        expected, _ = sf.read(original, dtype='int32', always_2d=True)
        if mono:expected = expected.repeat(2, axis=1)
        assert (data == expected).all(), 'Lossless source samples changed or stem mapping was wrong'
    return {'channels': 2, 'sampleRate': rate, 'subtype': info.subtype,
            'frames': info.frames, 'seconds': info.duration, 'peakInt32': int(abs(data).max()),
            'original': str(original), 'originalSampleRate': original_rate, 'originalSubtype': original_info.subtype,
            'monoDuplicated': mono, 'bitExactLosslessSource': exact,
            'originalRms': before_rms, 'exportRms': after_rms}


def rpp_tree(text):
    roots, stack = [], []
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith('<'):
            node = {'kind': line.split()[0][1:], 'lines': [], 'children': []}
            (stack[-1]['children'] if stack else roots).append(node)
            stack.append(node)
        elif line == '>':
            assert stack, 'Unexpected RPP closing block'
            stack.pop()
        else:
            assert stack, 'RPP line outside a block'
            stack[-1]['lines'].append(line)
    assert not stack and len(roots) == 1 and roots[0]['kind'] == 'REAPER_PROJECT'
    return roots[0]


def lines_named(node, name):
    return [shlex.split(line) for line in node['lines'] if line.startswith(name + ' ')]


def children(node, kind):
    return [child for child in node['children'] if child['kind'] == kind]


def check_reaper(archive, expected_sources, expected_bpm, expected_meter, with_score, timed):
    expected_audio = len(expected_sources)
    names = zip_safety(archive)
    project_name = next(name for name in names if name.endswith('.RPP'))
    text = archive.read(project_name).decode('utf8')
    assert '\x00' not in text and str(ROOT) not in text
    project = rpp_tree(text)
    tempo = lines_named(project, 'TEMPO')[0]
    assert float(tempo[1]) == expected_bpm and tuple(map(int, tempo[2:4])) == expected_meter
    pt = lines_named(children(project, 'TEMPOENVEX')[0], 'PT')[0]
    assert float(pt[2]) == expected_bpm and int(pt[4]) == (expected_meter[1] << 16) | expected_meter[0]
    notes_text = '\n'.join(children(project, 'NOTES')[0]['lines'])
    assert TITLE in notes_text and SEEDS[0] in notes_text and SEEDS[1] in notes_text
    tracks = children(project, 'TRACK')
    audio, score, lyrics = [], [], []
    for track in tracks:
        label = lines_named(track, 'NAME')[0][1]
        items = children(track, 'ITEM')
        sources = [source for item in items for source in children(item, 'SOURCE')]
        if sources and any(line.startswith('FILE ') for line in sources[0]['lines']):
            reference = lines_named(sources[0], 'FILE')[0][1]
            assert '\\' not in reference and not PureWindowsPath(reference).drive
            member = str(PurePosixPath(project_name).parent / reference)
            assert member in names
            assert label == expected_sources[len(audio)][0]
            info = wav_check(archive.read(member), expected_sources[len(audio)][2])
            assert float(lines_named(items[0], 'POSITION')[0][1]) == 0
            assert math.isclose(float(lines_named(items[0], 'LENGTH')[0][1]), 5)
            mute = int(lines_named(track, 'MUTESOLO')[0][1])
            assert mute == (1 if label == 'Mix' and expected_audio > 1 else 0)
            audio.append({'label': label, 'file': member, 'muted': bool(mute), **info})
        elif label == 'Lyrics':
            assert timed
            assert len(items) == len(ROWS)
            for item, row in zip(items, ROWS):
                assert float(lines_named(item, 'POSITION')[0][1]) == row['start']
                assert math.isclose(float(lines_named(item, 'LENGTH')[0][1]), row['end'] - row['start'])
                assert children(item, 'NOTES')[0]['lines'] == ['|' + row['text']]
            lyrics = ROWS
        else:
            assert with_score and sources
            voice = 'Vocal' if 'Vocal' in label else 'Ins'
            tick, on, actual = 0, {}, []
            for line in lines_named(sources[0], 'E'):
                tick += int(line[1])
                event = bytes(int(x, 16) for x in line[2:])
                kind, channel, pitch, velocity = event[0] >> 4, event[0] & 15, event[1], event[2]
                if kind == 9 and velocity:
                    on[channel, pitch] = tick
                elif kind in (8, 9):
                    start = on.pop((channel, pitch))
                    actual.append((start / 960, pitch, (tick - start) / 960))
            assert not on and sorted(actual) == NOTES[voice]
            assert math.isclose(float(lines_named(items[0], 'LENGTH')[0][1]), 6 * 60 / expected_bpm)
            score.append({'voice': voice, 'notes': actual})
    assert len(audio) == expected_audio and len(score) == (2 if with_score else 0)
    markers = lines_named(project, 'MARKER')
    if timed:
        assert len(markers) == 4
        assert [(float(m[2]), m[3]) for m in markers] == [(.25, 'Verse'), (2.5, ''), (2.5, 'Chorus'), (5., '')]
    else:
        assert not markers and not lyrics
    return {'audio': audio, 'score': score, 'timedLyrics': len(lyrics), 'regions': len(markers) // 2,
            'bpm': expected_bpm, 'meter': list(expected_meter), 'relativeReferencesVerified': True}


def check_dawproject(archive, expected_sources, expected_bpm, expected_meter, with_score, timed):
    expected_audio = len(expected_sources)
    names = zip_safety(archive)
    project = ET.fromstring(archive.read('project.xml'))
    metadata = ET.fromstring(archive.read('metadata.xml'))
    assert metadata.findtext('Title') == TITLE
    assert LYRICS in metadata.findtext('Comment')
    transport = project.find('Transport')
    assert float(transport.find('Tempo').get('value')) == expected_bpm
    signature = transport.find('TimeSignature')
    assert (int(signature.get('numerator')), int(signature.get('denominator'))) == expected_meter
    structure = project.find('Structure')
    tracks = {track.get('id'): track for track in structure.findall('Track')}
    assert len(tracks) == len(set(tracks))
    master = next(track for track in tracks.values() if track.find('Channel').get('role') == 'master')
    destination = master.find('Channel').get('id')
    for track in tracks.values():
        if track is not master:assert track.find('Channel').get('destination') == destination
    audio, score = [], []
    for lane in project.findall('Arrangement/Lanes/Lanes'):
        track = tracks[lane.get('track')]
        if track is master:continue
        clip = lane.find('Clips/Clip')
        assert float(clip.get('time')) == 0
        if track.get('contentType') == 'audio':
            source = clip.find('Clips/Clip/Warps/Audio')
            reference = source.find('File').get('path')
            assert reference in names and reference.startswith('audio/') and '\\' not in reference
            assert track.get('name') == expected_sources[len(audio)][0]
            info = wav_check(archive.read(reference), expected_sources[len(audio)][2])
            assert int(source.get('sampleRate')) == 48000 and int(source.get('channels')) == 2
            assert float(source.get('duration')) == 5
            assert math.isclose(float(clip.get('duration')), 5 * expected_bpm / 60, abs_tol=1e-6)
            warps = clip.findall('Clips/Clip/Warps/Warp')
            assert len(warps) == 2 and float(warps[0].get('time')) == 0
            assert float(warps[1].get('contentTime')) == 5
            assert math.isclose(float(warps[1].get('time')), 5 * expected_bpm / 60, abs_tol=1e-6)
            mute = track.find('Channel/Mute').get('value')
            assert mute == ('true' if track.get('name') == 'Mix' and expected_audio > 1 else 'false')
            audio.append({'label': track.get('name'), 'file': reference, 'muted': mute == 'true', **info})
        else:
            assert with_score and track.get('contentType') == 'notes'
            voice = 'Vocal' if 'Vocal' in track.get('name') else 'Ins'
            notes = clip.findall('Notes/Note')
            actual = [(float(n.get('time')), int(n.get('key')), float(n.get('duration'))) for n in notes]
            assert actual == NOTES[voice]
            for note in notes:
                assert int(note.get('channel')) == (0 if voice == 'Vocal' else 1)
                assert math.isclose(float(note.get('vel')), (96 if voice == 'Vocal' else 80) / 127, abs_tol=1e-6)
            score.append({'voice': voice, 'notes': actual})
    assert len(audio) == expected_audio and len(score) == (2 if with_score else 0)
    markers = project.findall('Arrangement/Markers/Marker')
    assert len(markers) == (2 if timed else 0)
    if timed:
        for marker, expected in zip(markers, [('Verse', .25), ('Chorus', 2.5)]):
            assert marker.get('name') == expected[0]
            assert math.isclose(float(marker.get('time')) * 60 / expected_bpm, expected[1], abs_tol=1e-6)
    return {'audio': audio, 'score': score, 'sectionMarkers': len(markers),
            'bpm': expected_bpm, 'meter': list(expected_meter), 'relativeReferencesVerified': True}


def main():
    disk_guard()
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    cache = ROOT / 'windows/cache/daw-structural' / (stamp + '-' + uuid.uuid4().hex[:8])
    outputs, timing = cache / 'outputs', cache / 'timing'
    outputs.mkdir(parents=True)
    timing.mkdir()
    report = {'schemaVersion': 2, 'syntheticOnly': True, 'externalInference': False,
              'mlModelsLoaded': False, 'dawLaunched': False, 'browserLaunched': False,
              'fixtureRoot': str(cache), 'sourceSha256': {n: sha(ROOT / n) for n in
                  ('windows/validate_daw_real.py', 'lab/rpp.py', 'lab/dawproject.py', 'lab/daw_audio.py', 'lab/library_io.py')},
              'pythonVersion': sys.version.splitlines()[0], 'soundfileVersion': sf.__version__, 'tests': {}, 'limits': ['Structural checks, not DAW import/playback',
              'No complete DAWproject XSD validation', 'Known authored lyric timings, not Whisper inference']}
    try:
        proof = library_io.read_json(ROOT / 'windows/cache/validation-runtime/ready.json')
        exe = ROOT / proof['ffmpeg']['pathRelative']
        assert exe.resolve().is_relative_to(ROOT) and sha(exe) == proof['ffmpeg']['sha256']
        assert Path(shutil.which('ffmpeg')).resolve() == exe.resolve()
        version = runtime.run_process([str(exe), '-version'], root=ROOT, capture_output=True, text=True, check=True, timeout=10).stdout.splitlines()[0]
        assert '9.0.2' in version
        report['ffmpeg'] = {'actual': True, 'path': str(exe), 'sha256': sha(exe), 'version': version}
        reference = cache / 'reference.wav'
        pcm_fixture(reference)
        score = abc_tools.parse(ABC)
        for voice in NOTES:
            assert [[float(t), p, float(n)] for t, p, n in score.voices[voice].notes] == [list(x) for x in NOTES[voice]]
        midi = midi_fixture()
        (cache / 'authored.mid').write_bytes(midi)
        (cache / 'authored.abc').write_bytes(ABC.encode('utf8'))
        parsed = midi_score.read_midi(midi)
        assert parsed['tempo'] == 80 and parsed['meter'] == (3, 4) and parsed['key'] == (2, False)
        cases = [('pcm-mix', 'wav', False, True, True, 80, (3, 4)),
                 ('flac-stems', 'flac', True, True, True, 80, (3, 4)),
                 ('mp3-stems', 'mp3', True, True, True, 80, (3, 4)),
                 ('style-tempo', 'wav', False, False, True, 97, (4, 4)),
                 ('stale-default', 'wav', False, False, False, 120, (4, 4))]
        for name, fmt, stems, with_score, timed, bpm, meter in cases:
            disk_guard()
            take = outputs / name
            take.mkdir()
            mix = take / ('audio.' + fmt)
            if fmt == 'wav':shutil.copyfile(reference, mix)
            else:ffmpeg(['-i', str(reference), '-c:a', 'flac' if fmt == 'flac' else 'libmp3lame', str(mix)])
            request = {'style': 'synthetic fixture, 170 bpm & <test>' if with_score else ('synthetic, 97 bpm' if bpm == 97 else 'synthetic'),
                       'abc': ABC if with_score else '', 'lyrics': LYRICS, 'lm_seed': SEEDS[0], 'seed': SEEDS[1]}
            library_io.write_json(take / 'meta.json', {'title': TITLE, 'seconds': 5, 'created': 1})
            library_io.write_json(take / 'request.json', request)
            if stems:
                older = take / 'derived/stems-older'
                newer = take / 'derived/stems-newer'
                older.mkdir(parents=True)
                newer.mkdir()
                pcm_fixture(older / 'obsolete.wav')
                library_io.write_json(older / 'manifest.json', {'mode': 'vocals', 'created': '2026-01-01',
                    'files': [{'name': 'obsolete', 'path': 'derived/stems-older/obsolete.wav'}]})
                pcm_fixture(newer / 'vocals.wav', channels=1, width=3)
                # Real float32 mono44.1kHz input exercises FFmpeg resampling/upmix.
                sf.write(newer / 'instrumental.wav', [((i % 128) - 64) / 256 for i in range(220500)], 44100, subtype='FLOAT')
                library_io.write_json(newer / 'manifest.json', {'mode': 'vocals', 'created': '2026-10-12',
                    'files': [{'name': 'vocals', 'path': 'derived/stems-newer/vocals.wav'},
                              {'name': 'instrumental', 'path': 'derived/stems-newer/instrumental.wav'}]})
            timing_file = timing / (name + '.timing.json')
            library_io.write_json(timing_file, {'rows': ROWS})
            if not timed:
                old = mix.stat().st_mtime - 60
                os.utime(timing_file, (old, old))
            entries = {}
            for export_name, module, check in [('reaper', rpp, check_reaper), ('dawproject', dawproject, check_dawproject)]:
                archive_path, info = module.build(ROOT, outputs, name, midi=midi if with_score else None, cache=timing)
                with zipfile.ZipFile(archive_path) as archive:
                    checks = check(archive, library_io.sources_of(take), bpm, meter, with_score, timed)
                    assert all('Obsolete' not in item['label'] for item in checks['audio'])
                entries[export_name] = {'passed': True, 'path': str(archive_path), 'sha256': sha(archive_path), 'info': info, **checks}
            report['tests'][name] = entries
        # A real undecodable source makes approved FFmpeg fail; preserve prior archives.
        take = outputs / 'flac-stems'
        bad = take / 'derived/stems-newer/instrumental.wav'
        good = bad.read_bytes()
        bad.write_bytes(b'not a decodable synthetic audio file')
        preservation = {}
        for label, module in [('reaper', rpp), ('dawproject', dawproject)]:
            previous = report['tests']['flac-stems'][label]
            path = Path(previous['path'])
            try:
                module.build(ROOT, outputs, take.name, midi=midi, cache=timing)
            except Exception as error:
                assert isinstance(error, __import__('subprocess').CalledProcessError), type(error)
                assert error.returncode != 0
                assert sha(path) == previous['sha256']
                assert sorted(item.name for item in path.parent.iterdir()) == [path.name]
                preservation[label] = {'passed': True, 'realConversionFailure': True, 'errorType': type(error).__name__, 'exitCode': error.returncode, 'failingTool': Path(error.cmd[0]).stem, 'previousArchiveUnchanged': True, 'temporaryFilesCleaned': True}
            else:raise AssertionError('Undecodable synthetic source unexpectedly exported')
        bad.write_bytes(good)
        report['tests']['failure-preservation'] = preservation
        report['passed'] = True
        report['finalDiskFreeBytes'] = disk_guard()
    except Exception as error:
        report.update(passed=False, error=repr(error))
        raise
    finally:
        library_io.write_json(cache / 'report.json', report)
        print(json.dumps({'passed': report.get('passed'), 'report': str(cache / 'report.json')}, ensure_ascii=True))


if __name__ == '__main__':
    main()
