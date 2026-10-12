"""Native critical-floor cleanup proof with an owned stdlib child, no CUDA/vendor code."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import listener_resources as resources


class ResourceTests(unittest.TestCase):
    def test_critical_floor_stops_only_owned_child_and_preserves_objects(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / 'windows/build/listener-cuda'
            output.mkdir(parents=True)
            object_file = output / 'completed.obj'
            object_file.write_bytes(b'synthetic completed object')
            healthy = {'physical_available': 12 * 2**30, 'commit_headroom': 6 * 2**30}
            critical = {'physical_available': 12 * 2**30, 'commit_headroom': 1 * 2**30}
            real_popen = subprocess.Popen
            children = []
            def child(command, **kwargs):
                if str(command[0]).lower().endswith('taskkill.exe'):
                    self.assertEqual(command[1:], ['/PID', str(children[0].pid), '/T', '/F'])
                    return real_popen(command, **kwargs)
                self.assertEqual(command[-4:], ['--target', 'llama-mtmd-cli', '--parallel', '1'])
                owned = real_popen([sys.executable, '-c', 'import time; time.sleep(30)'], **kwargs)
                children.append(owned)
                return owned
            try:
                with mock.patch.object(resources, 'ROOT', root), mock.patch.object(resources, 'memory', side_effect=[healthy, critical, healthy]), \
                     mock.patch.object(resources.subprocess, 'Popen', side_effect=child):
                    with self.assertRaisesRegex(RuntimeError, 'critical floor'):
                        resources.build(Path(sys.executable), output)
                self.assertEqual(len(children), 1)
                self.assertIsNotNone(children[0].poll())
                self.assertEqual(object_file.read_bytes(), b'synthetic completed object')
                report = json.loads((root / 'windows/cache/listener/build-memory-owned.json').read_text(encoding='utf-8'))
                self.assertEqual(report['status'], 'critical-floor-stop')
                self.assertEqual(report['pid'], children[0].pid)
            finally:
                for owned in children:
                    if owned.poll() is None:
                        owned.kill()
                    owned.wait(timeout=5)


if __name__ == '__main__':
    unittest.main(verbosity=2)
