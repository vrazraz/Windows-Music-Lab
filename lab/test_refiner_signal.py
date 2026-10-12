"""Real CPU-worker regression checks for the short/empty Inspector paths; no models."""
import json
import math
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
import wave

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'lab'))
from platform_runtime import job_environment, run_process


class InspectSmallSignalTests(unittest.TestCase):
    def setUp(self):
        folder = ROOT / 'lab/cache/test-refiner'
        folder.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=folder)
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)

    def inspect(self, frames, tone=False):
        src = self.folder / 'own.wav'
        out = self.folder / 'inspect.json'
        with wave.open(str(src), 'wb') as audio:
            audio.setparams((2, 2, 48000, 0, 'NONE', 'not compressed'))
            for index in range(frames):
                value = round(3000 * math.sin(2 * math.pi * 997 * index / 48000)) if tone else 0
                audio.writeframesraw(struct.pack('<hh', value, value))
        env = job_environment(ROOT)
        env['CUDA_VISIBLE_DEVICES'] = ''
        child = run_process([sys.executable, str(ROOT / 'lab/inspect_job.py'), str(src), str(out)],
                            cwd=ROOT, env=env, stdin=subprocess.DEVNULL, capture_output=True,
                            text=True, encoding='utf-8', timeout=60)
        return child, out

    def test_100ms_tone_keeps_true_duration_and_marks_unresolved_framebuzz(self):
        child, out = self.inspect(4800, tone=True)
        self.assertEqual(child.returncode, 0, child.stderr)
        data = json.loads(out.read_text(encoding='utf-8'))
        self.assertEqual((data['seconds'], data['rate'], data['channels']), (.1, 48000, 2))
        self.assertIsNone(data['framebuzz']['mean_db'])
        self.assertEqual(data['framebuzz']['windows'], [])
        self.assertEqual(data['framebuzz']['unresolved_windows'][0]['by_hz'], [None] * 6)
        self.assertTrue(any('zero-padded' in note for note in data['analysis_notes']))

    def test_20ms_silence_produces_strict_json_with_null_true_peak(self):
        child, out = self.inspect(960)
        self.assertEqual(child.returncode, 0, child.stderr)
        def invalid(value):
            self.fail('Nonstandard JSON constant: ' + value)
        data = json.loads(out.read_text(encoding='utf-8'), parse_constant=invalid)
        self.assertEqual(data['tones'], [])
        self.assertEqual(data['clicks'], [])
        self.assertIsNone(data['loudness']['true_peak'])
        self.assertIsNone(data['framebuzz']['mean_db'])

    def test_24bit_antiphase_rounding_is_not_an_audible_click(self):
        src = self.folder / 'antiphase.wav'
        out = self.folder / 'inspect.json'
        with wave.open(str(src), 'wb') as audio:
            audio.setparams((2, 3, 48000, 0, 'NONE', 'not compressed'))
            frames = bytearray()
            for index in range(24000):
                value = .2 * math.sin(2 * math.pi * 997 * index / 48000)
                # Independent24bit channel quantization makes a half-LSB mono residue.
                left, right = math.floor(value * 2**23), math.floor(-value * 2**23)
                frames.extend(left.to_bytes(3, 'little', signed=True))
                frames.extend(right.to_bytes(3, 'little', signed=True))
            audio.writeframes(frames)
        env = job_environment(ROOT)
        env['CUDA_VISIBLE_DEVICES'] = ''
        child = run_process([sys.executable, str(ROOT / 'lab/inspect_job.py'), str(src), str(out)],
                            cwd=ROOT, env=env, stdin=subprocess.DEVNULL, capture_output=True,
                            text=True, encoding='utf-8', timeout=60)
        self.assertEqual(child.returncode, 0, child.stderr)
        data = json.loads(out.read_text(encoding='utf-8'))
        self.assertEqual(data['clicks'], [])

    def test_empty_audio_fails_before_publication(self):
        child, out = self.inspect(0)
        self.assertNotEqual(child.returncode, 0)
        self.assertIn('nonempty finite audio', child.stderr)
        self.assertFalse(out.exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
