"""Synthetic stdlib tests: no real user library, network, models or DAW launches.

PCM WAV conversion, archives, XML, MIDI, JSON and filesystem operations are real.
FFmpeg fallback for compressed formats is mocked. Run: python -m unittest discover -s lab -p test_windows_library.py -v
"""
import copy
import json
import shutil
import struct
import subprocess
import tempfile
import time
import unittest
import wave
import zipfile
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

import abc_tools
import collection
import daw_audio
import dawbridge
import dawproject
import library_io
import midi_io
import midi_score
import platform_runtime
import rpp
import writer


def vlq(value):
    out = [value & 127]
    while value >> 7:
        value >>= 7
        out.insert(0, (value & 127) | 128)
    return bytes(out)


def track(events, name=""):
    payload = b""
    if name:
        body = name.encode("utf-8")
        payload += b"\0\xff\x03" + vlq(len(body)) + body
    last = 0
    for at, body in events:
        payload += vlq(at - last) + body
        last = at
    payload += b"\0\xff\x2f\0"
    return b"MTrk" + len(payload).to_bytes(4, "big") + payload


def midi():
    vocal = track([(0, b"\xff\x51\x03\x07\xa1\x20"),
                   (0, b"\xff\x58\x04\x04\x02\x18\x08"),
                   (0, b"\x90\x3c\x64"), (480, b"\x80\x3c\0"),
                   (480, b"\x90\x40\x64"), (960, b"\x80\x40\0")], "Vocal голос")
    ins = track([(0, b"\x91\x30\x64"), (1920, b"\x81\x30\0")], "Ins")
    return b"MThd" + struct.pack(">IHHH", 6, 1, 2, 480) + vocal + ins


class Files(unittest.TestCase):
    def setUp(self):
        cache = Path(__file__).resolve().parent.parent / "windows" / "cache" / "tests"
        cache.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="библиотека-", dir=cache)
        self.root = Path(self.temporary.name)
        self.kit = self.root / "проект с пробелами"
        self.outputs = self.kit / "outputs"
        self.config = self.kit / "user"
        self.outputs.mkdir(parents=True)
        self.config.mkdir()
        self.take = self.outputs / "песня-01"
        self.take.mkdir()
        library_io.write_json(self.take / "meta.json", {"title": "Лес и свет", "favorite": True, "created": 1, "seconds": 1})
        library_io.write_json(self.take / "request.json", {"style": "folk, 90 bpm", "lyrics": "[Verse]\nСвет\n[Chorus]\nЛес", "seed": 4})
        with wave.open(str(self.take / "audio.wav"), "wb") as handle:
            handle.setparams((2, 3, 48000, 0, "NONE", "not compressed"))
            handle.writeframes(b"\x01\x02\x03" * 96000)

    def tearDown(self):
        self.temporary.cleanup()

    def stem(self, path="derived/stems-test/vocals.wav", name="vocals"):
        folder = self.take / "derived" / "stems-test"
        folder.mkdir(parents=True, exist_ok=True)
        if not path.startswith(("../", "C:", "/")) and "\\" not in path:
            target = self.take / path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(self.take / "audio.wav", target)
        library_io.write_json(folder / "manifest.json", {"created": "2026", "mode": "vocals",
                                                        "files": [{"path": path, "name": name}]})

    @staticmethod
    def ffmpeg(args, **kwargs):
        if args[0] == "ffprobe":
            return subprocess.CompletedProcess(args, 0, stdout="1.000\n", stderr="")
        if args[0] == "ffmpeg":
            shutil.copyfile(args[args.index("-i") + 1], args[-1])
            return subprocess.CompletedProcess(args, 0)
        raise AssertionError("unexpected external command")

    def export_done(self, **kwargs):
        job = collection.export_start(self.kit, self.outputs, [self.take.name], **kwargs)
        until = time.monotonic() + 3
        while collection.export_status(job["id"])["status"] == "running" and time.monotonic() < until:
            time.sleep(.01)
        return collection.export_status(job["id"])

    def test_json_unicode_atomic_failure_keeps_existing_and_cleans_part(self):
        path = self.config / "настройки.json"
        library_io.write_json(path, {"имя": "свет"})
        old = path.read_bytes()
        with patch.object(library_io.os, "replace", side_effect=OSError("locked")):
            with self.assertRaises(OSError):
                library_io.write_json(path, {"имя": "ветер"})
        self.assertEqual(path.read_bytes(), old)
        self.assertFalse(list(self.config.glob("*.part")))
        library_io.write_json(path, {"имя": "ветер"})
        self.assertEqual(library_io.read_json(path)["имя"], "ветер")

    def test_writer_save_snapshot_restore_trash_backup_conflict(self):
        doc = writer.post(self.kit, {"op": "put", "title": "Песня", "lyrics": "Первый", "notes": "**Заметка**", "params": {"seed": "9"}})
        did = doc["id"]
        doc = writer.post(self.kit, {"op": "put", "id": did, "lyrics": "Второй"})
        self.assertEqual(doc["versions"][0]["lyrics"], "Первый")
        writer.post(self.kit, {"op": "snapshot", "id": did, "label": "Контроль"})
        doc = writer.post(self.kit, {"op": "restore", "id": did, "version": 0})
        self.assertEqual(doc["lyrics"], "Первый")
        writer.post(self.kit, {"op": "link", "id": did, "takes": ["песня-01", "..\\secret", "C:\\secret"]})
        self.assertEqual(writer.get(self.kit, did)["takes"], ["песня-01"])
        backup = writer.post(self.kit, {"op": "export"})
        writer.post(self.kit, {"op": "put", "id": did, "lyrics": "Местная"})
        result = writer.post(self.kit, {"op": "import", "backup": backup})
        self.assertEqual(result["imported"]["copies"], 1)
        self.assertEqual(writer.get(self.kit, did)["lyrics"], "Местная")
        writer.post(self.kit, {"op": "delete", "id": did})
        self.assertEqual(len(writer.listing(self.kit)["docs"]), 1)
        self.assertTrue((self.kit / "writer" / ".trash" / f"{did}.json").is_file())
        exported = writer.post(self.kit, {"op": "export"})
        elsewhere = self.root / "другая папка"
        result = writer.post(elsewhere, {"op": "import", "backup": exported})
        self.assertEqual(result["imported"]["trashed"], 1)
        self.assertEqual(result["imported"]["added"], 1)
        self.assertEqual(writer.post(elsewhere, {"op": "import", "backup": exported})["imported"]["same"], 2)

    def test_writer_autosave_quiet_versions_and_scope(self):
        doc = writer.post(self.kit, {"op": "put", "title": "Черновик"})
        for lyric in ("а", "аб", "абв"):
            doc = writer.post(self.kit, {"op": "put", "id": doc["id"], "lyrics": lyric, "autosave": True})
        self.assertEqual(doc["versions"], [])
        writer.post(self.kit, {"op": "put", "title": "Test"}, scope="../../CHECK")
        self.assertEqual(len(writer.listing(self.kit)["docs"]), 1)
        self.assertEqual(len(writer.listing(self.kit, "check")["docs"]), 1)

    def test_writer_invalid_id_and_backup(self):
        for bad in ("..\\secret", "C:/secret", [], None):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                writer.get(self.kit, bad)
        backup = {"kind": writer.BACKUP_KIND, "docs": [{"id": "a" * 12, "created": "invalid"}, {"id": "../bad"}]}
        self.assertEqual(writer.post(self.kit, {"op": "import", "backup": backup})["imported"]["skipped"], 2)

    def test_collection_metadata_workspace_lock_freeze_and_pins(self):
        n = self.take.name
        for data in ({"op": "ws-create", "workspace": "Проект / Куплет"},
                     {"op": "ws-add", "workspace": "Проект / Куплет", "names": [n]},
                     {"op": "rate", "value": 1, "names": [n]},
                     {"op": "note", "text": "Моя заметка", "names": [n]},
                     {"op": "pin", "place": "Проект", "on": True, "names": [n]}):
            collection.collection_post(self.config, self.outputs, data)
        row = collection.catalog(self.outputs, self.config)["takes"][0]
        self.assertTrue(row["favorite"])
        self.assertEqual(row["rating"], 1)
        self.assertEqual(row["note"], "Моя заметка")
        collection.collection_post(self.config, self.outputs, {"op": "freeze", "workspace": "Проект", "on": True})
        with self.assertRaises(ValueError):
            collection.collection_post(self.config, self.outputs, {"op": "note", "text": "новая", "names": [n]})
        self.assertEqual(collection.trash_move(self.kit, self.outputs, [n], self.config)["locked"], [n])
        collection.collection_post(self.config, self.outputs, {"op": "freeze", "workspace": "Проект", "on": False})
        collection.collection_post(self.config, self.outputs, {"op": "lock", "workspace": "Проект / Куплет", "what": "tracks", "on": True})
        self.assertEqual(collection.trash_move(self.kit, self.outputs, [n], self.config)["locked"], [n])

    def test_trash_roundtrip_unicode_and_traversal(self):
        for bad in ("..\\secret", "C:\\secret", "/secret", "..", "nul"):
            self.assertEqual(collection.trash_move(self.kit, self.outputs, [bad])["moved"], [])
        self.assertTrue(self.take.exists())
        self.assertEqual(collection.trash_move(self.kit, self.outputs, [self.take.name])["moved"], [self.take.name])
        item = collection.trash_list(self.kit)["items"][0]
        bad = dict(item, day="..\\outside")
        self.assertEqual(collection.trash_restore(self.kit, self.outputs, [bad])["restored"], [])
        self.assertEqual(collection.trash_restore(self.kit, self.outputs, [item])["restored"], [self.take.name])
        self.assertTrue((self.take / "audio.wav").exists())

    def test_paths_drive_unc_traversal_and_reserved_names(self):
        for bad in ("../secret", "..\\secret", "/secret", "C:/secret", "C:secret", "\\\\server\\file",
                    "derived//file", "audio/../../secret", "CON", "name. "):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                library_io.manifest_file(self.take, bad)
        path = library_io.manifest_file(self.take, "derived\\стем.wav")
        self.assertEqual(path, self.take / "derived" / "стем.wav")
        used = set()
        a = collection._fname("CON", used, ".wav")
        b = collection._fname("con", used, ".wav")
        self.assertNotEqual(a.casefold(), b.casefold())
        self.assertTrue(library_io.valid_component(a))
        for title in ("..", "NUL", "песня:*?<>", "aux.txt"):
            self.assertTrue(library_io.valid_component(library_io.filename(title)))

    def test_junction_escape_is_rejected(self):
        outside = self.root / "вне библиотеки"
        outside.mkdir()
        link = self.take / "derived"
        platform_runtime.create_directory_link(outside, link)
        try:
            with self.assertRaises(ValueError):
                library_io.manifest_file(self.take, "derived/private.wav")
        finally:
            platform_runtime.remove_directory_link(link)

    def test_library_zip_real_wav_and_unsafe_manifest_failure(self):
        job = self.export_done(fmt="wav", derived=False)
        self.assertEqual(job["status"], "done")
        path = collection.export_path(self.kit, job["id"])
        with zipfile.ZipFile(path) as z:
            self.assertEqual(z.namelist(), ["Лес и свет.wav"])
            self.assertEqual(z.read(z.namelist()[0]), (self.take / "audio.wav").read_bytes())
        self.stem("../private.wav")
        job = self.export_done(fmt="wav", derived=True)
        self.assertEqual(job["status"], "failed")
        self.assertFalse(list((self.kit / "tmp" / "exports").glob("*.part")))

    def test_reaper_zip_audio_score_lyrics_paths_and_cleanup(self):
        self.stem()
        cache = self.kit / "tmp" / "timing"
        cache.mkdir(parents=True)
        library_io.write_json(cache / f"{self.take.name}.timing.json", {"rows": [{"text": "Свет", "start": 0, "end": .5},
                                                                               {"text": "Лес", "start": .5, "end": 1}]})
        with patch.object(daw_audio, "run_process") as run:
            path, info = rpp.build(self.kit, self.outputs, self.take.name, midi=midi(), cache=cache)
            run.assert_not_called()
        self.assertEqual(len(info["tracks"]), 5)
        with zipfile.ZipFile(path) as z:
            self.assertTrue(all("\\" not in p and not p.startswith("/") and ".." not in p.split("/") for p in z.namelist()))
            name = next(n for n in z.namelist() if n.endswith(".RPP"))
            text = z.read(name).decode("utf-8")
            self.assertIn("HASDATA 1 960 QN", text)
            self.assertIn('FILE "audio/00-mix.wav"', text)
            self.assertIn('MARKER 1 0.000 "Verse"', text)
            self.assertNotIn(str(self.kit), text)
            self.assertIn("Windows Music Lab", text)
            self.assertEqual(sum(l.strip() == ">" for l in text.splitlines()), sum(l.lstrip().startswith("<") for l in text.splitlines()))
        self.assertEqual(list(path.parent.iterdir()), [path])

    def test_dawproject_zip_xml_audio_notes_and_failure_keeps_previous(self):
        self.stem(name="vo/cals:*?")
        library_io.write_json(self.take / "meta.json", {"title": "Лес & <свет>\x00", "created": 1})
        with patch.object(daw_audio, "run_process") as run:
            path, info = dawproject.build(self.kit, self.outputs, self.take.name, midi=midi())
            run.assert_not_called()
        old = path.read_bytes()
        with zipfile.ZipFile(path) as z:
            project = ET.fromstring(z.read("project.xml"))
            metadata = ET.fromstring(z.read("metadata.xml"))
            self.assertEqual(project.find("Application").attrib["name"], "Windows Music Lab")
            self.assertEqual(metadata.findtext("Title"), "Лес & <свет>")
            self.assertTrue(project.findall(".//Note"))
            for node in project.findall(".//File"):
                self.assertIn(node.attrib["path"], z.namelist())
                self.assertNotIn("\\", node.attrib["path"])
        with patch.object(dawproject, "to_wav", side_effect=subprocess.CalledProcessError(1, "ffmpeg")):
            with self.assertRaises(subprocess.CalledProcessError):
                dawproject.build(self.kit, self.outputs, self.take.name)
        self.assertEqual(path.read_bytes(), old)
        self.assertEqual(list(path.parent.iterdir()), [path])

    def test_exports_reject_bad_name_manifest_before_external_command(self):
        self.stem("C:\\private.wav")
        with patch.object(rpp.subprocess, "run") as run:
            for exporter in (rpp, dawproject):
                with self.assertRaises(ValueError):
                    exporter.build(self.kit, self.outputs, self.take.name)
                with self.assertRaises(ValueError):
                    exporter.build(self.kit, self.outputs, "..\\private")
            run.assert_not_called()

    def test_real_engine_pcm16_to_daw_pcm24_stereo(self):
        source = self.kit / "синтетический звук.wav"
        raw = struct.pack("<hhhhhh", -32768, 32767, -1, 0, 1, 16384)
        with wave.open(str(source), "wb") as w:
            w.setparams((2, 2, 48000, 0, "NONE", "not compressed"))
            w.writeframes(raw)
        target = source.with_name("экспорт.wav")
        with patch.object(daw_audio, "run_process") as run:
            daw_audio.to_wav(source, target)
            run.assert_not_called()
        with wave.open(str(target), "rb") as w:
            self.assertEqual((w.getnchannels(), w.getsampwidth(), w.getframerate()), (2, 3, 48000))
            converted = w.readframes(w.getnframes())
        self.assertEqual([int.from_bytes(converted[i:i+3], "little", signed=True) for i in range(0,len(converted),3)],
                         [-32768*256, 32767*256, -256, 0, 256, 16384*256])

    def test_real_pcm32_mono_to_daw_stereo(self):
        source = self.kit / "моно.wav"
        with wave.open(str(source), "wb") as w:
            w.setparams((1, 4, 48000, 0, "NONE", "not compressed"))
            w.writeframes(struct.pack("<iii", -2147483648, 0, 2147483647))
        target = source.with_name("стерео.wav")
        with patch.object(daw_audio, "run_process") as run:
            daw_audio.to_wav(source, target)
            run.assert_not_called()
        with wave.open(str(target), "rb") as w:
            converted = w.readframes(w.getnframes())
            self.assertEqual(w.getnframes(), 3)
        values = [int.from_bytes(converted[i:i+3], "little", signed=True) for i in range(0,len(converted),3)]
        self.assertEqual(values, [-8388608, -8388608, 0, 0, 8388607, 8388607])

    def test_ffmpeg_fallback_for_compressed_audio_is_explicit(self):
        source = self.kit / "тест.mp3"
        source.write_bytes(b"synthetic unsupported audio")
        target = source.with_suffix(".wav")
        with patch.object(daw_audio, "run_process", side_effect=self.ffmpeg) as run:
            daw_audio.to_wav(source, target, root=self.kit)
        args = run.call_args.args[0]
        self.assertEqual(args[0], "ffmpeg")
        self.assertIn("-ac", args)
        self.assertEqual(run.call_args.kwargs["root"], self.kit)
        self.assertEqual(target.read_bytes(), source.read_bytes())

    def test_native_daw_discovery_and_no_program_launch(self):
        programs = self.root / "Program Files"
        exe = programs / "REAPER (x64)" / "reaper.exe"
        exe.parent.mkdir(parents=True)
        exe.write_bytes(b"not executed")
        (exe.parent / "whatsnew.txt").write_text("v7.81 - test\n", encoding="utf-8")
        with patch.dict(dawbridge.os.environ, {"ProgramW6432": str(programs)}, clear=True):
            candidates = dawbridge._windows_paths(dawbridge.KNOWN[0])
            self.assertIn(exe, candidates)
            result = dawbridge.detect()
        reaper = result["daws"][0]
        self.assertTrue(reaper["here"])
        self.assertEqual(reaper["version"], "7.81")
        self.assertIn("Windows", reaper["install"])
        self.assertIsInstance(result["host"], str)
        self.assertEqual(dawbridge._version(dawbridge.KNOWN[1], str(programs / "Waveform Free" / "Waveform64.exe")), "")
        self.assertEqual(dawbridge._version(dawbridge.KNOWN[1], str(programs / "Waveform14" / "Waveform64.exe")), "14")


class Score(unittest.TestCase):
    def test_midi_to_abc_roundtrip_and_rpp_events(self):
        data = midi()
        result = midi_score.from_midi(data)
        score = abc_tools.parse(result["abc"])
        self.assertEqual(result["notes"], {"Vocal": 2, "Ins": 1})
        self.assertEqual(result["bpm"], 120)
        self.assertEqual(len(score.voices["Vocal"].notes), 2)
        division, voices = rpp.midi_tracks(data)
        self.assertEqual(division, 480)
        self.assertEqual(len(voices), 2)
        lines, end = rpp._midi_chunk(division, voices[0])
        self.assertEqual(end, 1920)
        self.assertTrue(any("90 3c 64" in s for s in lines))

    def test_abc_chord_removal_preserves_notes(self):
        result = midi_score.from_midi(midi())
        abc = result["abc"].replace("V: Vocal\n", 'V: Vocal\n"Am"', 1)
        before = abc_tools.parse(abc)
        after = abc_tools.parse(abc_tools.strip_chords(abc))
        self.assertTrue(abc_tools.compare(before, after)["match"])
        self.assertEqual(after.voices["Vocal"].chords, [])

    def test_midi_channels_and_overlapping_same_pitch_are_separate(self):
        events = [(0, b"\x90\x3c\x64"), (120, b"\x91\x3c\x64"),
                  (240, b"\x80\x3c\0"), (480, b"\x81\x3c\0")]
        data = b"MThd" + struct.pack(">IHHH", 6, 0, 1, 480) + track(events)
        self.assertEqual(midi_score.read_midi(data)["tracks"][0]["notes"], [[0, 60, 240], [120, 60, 360]])

    def test_malformed_midi_and_bad_grid_fail_closed(self):
        good = midi()
        bads = [b"", good[:13], good[:-1], good[:12] + b"\0\0" + good[14:],
                good[:8] + struct.pack(">HHH", 2, 2, 480) + good[14:],
                good + b"junk", good.replace(b"MTrk", b"BAD!", 1)]
        header = b"MThd" + struct.pack(">IHHH", 6, 0, 1, 480)
        for payload in (b"\0\x3c\x64", b"\x81\x81\x81\x81\0", b"\0\x90\xff\0"):
            bads.append(header + b"MTrk" + len(payload).to_bytes(4, "big") + payload)
        for data in bads:
            with self.subTest(length=len(data)), self.assertRaises(ValueError):
                midi_io.tracks(data)
            with self.assertRaises(abc_tools.AbcError):
                midi_score.from_midi(data)
        for unit in (0, 3, 17, 2048):
            with self.subTest(unit=unit), self.assertRaises(abc_tools.AbcError):
                midi_score.from_midi(good, unit=unit)

    def test_tempo_meter_validation(self):
        self.assertEqual(dawproject.tempo_meter({"abc": "Q:1/8=160\nM:3/4"}), (80, 3, 4))
        for abc in ("Q:1/0=160", "M:4/0", "M:4/3"):
            with self.assertRaises(ValueError):
                dawproject.tempo_meter({"abc": abc})


if __name__ == "__main__":
    unittest.main()