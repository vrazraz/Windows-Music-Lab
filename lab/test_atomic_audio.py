"""Actual Windows held-reader proof; no model/vendor execution."""
import ctypes
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from atomic_audio import replace_file
from training_supervisor import write_state


@unittest.skipUnless(os.name == 'nt', 'actual Windows file-share-delete semantics')
class AtomicAudioTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.kernel.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_ulong, ctypes.c_ulong,
                                           ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p]
        self.kernel.CreateFileW.restype = ctypes.c_void_p
        self.kernel.CloseHandle.argtypes = [ctypes.c_void_p]

    def hold_reader(self, path):
        # Share READ+WRITE, deliberately omit DELETE exactly as a normal CRT reader does.
        handle = self.kernel.CreateFileW(str(path), 0x80000000, 3, None, 3, 0x80, None)
        if handle in (None, ctypes.c_void_p(-1).value):
            raise ctypes.WinError(ctypes.get_last_error())
        return handle

    def test_supervisor_publish_waits_for_reader_without_partial_state(self):
        path = self.root / 'state.json'
        old = {'status': 'running', 'values': list(range(64))}
        new = {'status': 'done', 'values': list(range(128))}
        write_state(path, old)
        handle = self.hold_reader(path)
        closed = threading.Event()
        observed = []
        def reader():
            try:
                until = time.monotonic() + .1
                while time.monotonic() < until:
                    observed.append(json.loads(path.read_text(encoding='utf-8')))
                    time.sleep(.002)
            finally:
                self.kernel.CloseHandle(handle)
                closed.set()
        thread = threading.Thread(target=reader)
        thread.start()
        begun = time.monotonic()
        try:
            write_state(path, new)
        finally:
            thread.join(timeout=2)
        self.assertTrue(closed.is_set())
        self.assertGreaterEqual(time.monotonic() - begun, .08)
        self.assertTrue(observed)
        self.assertTrue(all(value == old for value in observed))
        self.assertEqual(json.loads(path.read_text(encoding='utf-8')), new)
        self.assertFalse(path.with_suffix('.json.part').exists())

    def test_retry_exhaustion_preserves_old_and_complete_part(self):
        path = self.root / 'styles.json'
        part = path.with_suffix('.json.part')
        path.write_text('{"old":true}', encoding='utf-8')
        part.write_text('{"new":true}', encoding='utf-8')
        handle = self.hold_reader(path)
        begun = time.monotonic()
        try:
            with self.assertRaises(OSError) as raised:
                replace_file(part, path, timeout=.05)
            self.assertIn(raised.exception.winerror, (5, 32, 33))
        finally:
            self.kernel.CloseHandle(handle)
        self.assertLess(time.monotonic() - begun, .5)
        self.assertEqual(json.loads(path.read_text(encoding='utf-8')), {'old': True})
        self.assertEqual(json.loads(part.read_text(encoding='utf-8')), {'new': True})
        replace_file(part, path)
        self.assertEqual(json.loads(path.read_text(encoding='utf-8')), {'new': True})


if __name__ == '__main__':
    unittest.main(verbosity=2)
