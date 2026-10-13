"""Synthetic native runtime checks; never access the installed project's work.
Run with: py -3.10 lab/test_platform_runtime.py
"""
import http.client
import ctypes
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import platform_runtime as runtime
import gpu_guard
import places

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / 'lab/cache/runtime-tests'
FIXTURES.mkdir(parents=True, exist_ok=True)
assert FIXTURES.resolve().is_relative_to(ROOT.resolve())


class RuntimeTests(unittest.TestCase):
    def test_filename_unicode_and_windows_traversal_aliases(self):
        self.assertEqual(runtime.safe_component('Песня-1'), 'Песня-1')
        for value in ('..', r'..\outside', 'C:outside', r'C:\outside', 'audio.wav:stream', 'CON', 'LPT1.txt', 'trailing.', 'name '):
            with self.assertRaises(ValueError):
                runtime.safe_component(value)

    def test_interpreter_platform_paths(self):
        expected = 'Scripts/python.exe' if runtime.WINDOWS else 'bin/python'
        self.assertEqual(runtime.venv_python(ROOT), ROOT / '.venv' / expected)
        self.assertEqual(runtime.venv_python(ROOT, artist=True), ROOT / '.venv-art' / expected)

    def test_child_env_offline_unicode_and_caches(self):
        env = runtime.job_environment(ROOT, {'PATH': '', 'https_proxy': 'https://example.invalid', 'HF_HOME': 'outside'})
        self.assertEqual(env['HF_HOME'], str(ROOT / 'lab/cache/huggingface'))
        self.assertEqual(env['PYTHONIOENCODING'], 'utf-8')
        self.assertEqual(env['HF_HUB_OFFLINE'], '1')
        self.assertEqual(env['DIFFUSERS_GGUF_CUDA_KERNELS'], '0')
        self.assertNotIn('https_proxy', env)
        self.assertNotEqual(os.environ.get('HF_HOME'), 'outside')

    def test_windows_os_memory_and_liveness(self):
        self.assertTrue(runtime.pid_alive(os.getpid()))
        self.assertFalse(runtime.pid_alive(-1))
        memory = runtime.system_memory()
        self.assertGreater(memory['total'], memory['available'])
        self.assertGreater(memory['available'], 0)

    def test_windows_machine_memory_converts_psapi_pages_and_preserves_scope(self):
        info = runtime._WindowsPerformanceInformation()
        info.PageSize=4096; info.PhysicalTotal=8_000_000; info.PhysicalAvailable=3_000_000
        info.CommitLimit=12_000_000; info.CommitTotal=9_000_000
        with mock.patch.object(runtime,'_windows_performance_info',return_value=info), mock.patch.object(runtime,'_windows_memory_status') as fallback:
            result=runtime.system_memory()
        self.assertEqual(result['total'],8_000_000*4096)
        self.assertEqual(result['available'],3_000_000*4096)
        self.assertEqual(result['commit_limit'],12_000_000*4096)
        self.assertEqual(result['commit_used'],9_000_000*4096)
        self.assertEqual(result['commit_available'],3_000_000*4096)
        self.assertEqual(result['commit_scope'],'machine')
        self.assertEqual(result['commit_source'],'GetPerformanceInfo(machine-wide)')
        fallback.assert_not_called()
        self.assertEqual(ctypes.sizeof(runtime._WindowsPerformanceInformation),104 if ctypes.sizeof(ctypes.c_void_p)==8 else 56)

    def test_windows_memory_failure_uses_only_labeled_process_commit_bound(self):
        value=runtime._WindowsMemoryStatus()
        value.total=32*2**30; value.available=10*2**30
        value.commit_limit=30*2**30; value.commit_available=2*2**30; value.virtual_available=1000*2**30
        with mock.patch.object(runtime,'_windows_performance_info',side_effect=OSError('fixture API failure')), mock.patch.object(runtime,'_windows_memory_status',return_value=value):
            result=runtime.system_memory()
        self.assertEqual(result['commit_available'],2*2**30)
        self.assertNotEqual(result['commit_available'],result['available'])
        self.assertNotEqual(result['commit_available'],value.virtual_available)
        self.assertIsNone(result['commit_used'])
        self.assertEqual(result['commit_scope'],'process_bound')
        self.assertEqual(result['commit_source'],'GlobalMemoryStatusEx(process conservative bound)')
        self.assertIn('fixture API failure',result['commit_error'])

    def test_windows_both_memory_apis_fail_closed(self):
        with mock.patch.object(runtime,'_windows_performance_info',side_effect=OSError('PSAPI unavailable')), mock.patch.object(runtime,'_windows_memory_status',side_effect=OSError('Global memory unavailable')):
            with self.assertRaisesRegex(OSError,'Global memory unavailable'):
                runtime.system_memory()

    def test_windows_psapi_false_return_raises_native_error(self):
        getter=mock.Mock(return_value=0)
        api=mock.Mock(GetPerformanceInfo=getter)
        with mock.patch.object(ctypes,'WinDLL',return_value=api), mock.patch.object(ctypes,'get_last_error',return_value=5):
            with self.assertRaises(OSError) as caught:
                runtime._windows_performance_info()
        self.assertEqual(caught.exception.errno,5)
        self.assertEqual(getter.argtypes,[ctypes.POINTER(runtime._WindowsPerformanceInformation),ctypes.c_uint32])
        self.assertEqual(getter.restype,ctypes.c_int)

    def test_actual_windows_machine_commit_matches_independent_psapi_read(self):
        result=runtime.system_memory()
        independent=runtime._WindowsPerformanceInformation()
        independent.cb=ctypes.sizeof(independent)
        getter=ctypes.WinDLL('psapi.dll',use_last_error=True,winmode=0x800).GetPerformanceInfo
        getter.argtypes=[ctypes.POINTER(runtime._WindowsPerformanceInformation),ctypes.c_uint32]; getter.restype=ctypes.c_int
        self.assertTrue(getter(ctypes.byref(independent),ctypes.sizeof(independent)))
        self.assertEqual(result['commit_scope'],'machine')
        self.assertEqual(result['commit_source'],'GetPerformanceInfo(machine-wide)')
        self.assertEqual(result['commit_available'],result['commit_limit']-result['commit_used'])
        self.assertEqual(result['commit_limit'],independent.CommitLimit*independent.PageSize)
        # Another process can allocate between these adjacent calls; allow128MiB drift.
        self.assertLess(abs(result['commit_used']-independent.CommitTotal*independent.PageSize),128*2**20)
        self.assertLess(abs(result['available']-independent.PhysicalAvailable*independent.PageSize),128*2**20)

    def test_loopback_hosts_and_ipv6_mapped(self):
        for host in ('localhost', '127.0.0.1', '::1', '::ffff:127.0.0.1'):
            self.assertTrue(runtime.is_loopback(host))
        for host in ('0.0.0.0', 'example.invalid', '192.168.0.2'):
            with self.assertRaises(ValueError):
                runtime.loopback_host(host)

    def test_browser_boundary_rejects_dns_rebinding_and_cloud_origins(self):
        headers = {'Host': '127.0.0.1:41871', 'Origin': 'http://localhost:41868'}
        self.assertTrue(runtime.local_request_allowed(headers, '127.0.0.1', {41868, 41871}))
        for change in ({'Host': 'evil.invalid:41871'}, {'Origin': 'https://evil.invalid'}, {'Origin': 'null'},
                       {'Host': 'localhost:99'}, {'Origin': 'http://localhost:99'}):
            self.assertFalse(runtime.local_request_allowed(dict(headers, **change), '127.0.0.1', {41868, 41871}))
        self.assertFalse(runtime.local_request_allowed(headers, '192.168.0.2', {41868, 41871}))

    def test_offline_alias_cannot_be_overridden_by_secondary_flag(self):
        with mock.patch.dict(os.environ, {'RUACH_OFFLINE': '1', 'WINDOWS_MUSIC_LAB_LOCAL_ONLY': '0'}):
            self.assertTrue(runtime.local_only())
            with self.assertRaises(ValueError):
                runtime.require_network('cloud upload')

    def test_audit_guard_blocks_connection_and_dns_before_outbound_io(self):
        code = "import platform_runtime as r, socket; r.install_local_network_guard();\nfor op in (lambda:socket.getaddrinfo('example.invalid',443),lambda:socket.socket().connect(('192.0.2.1',443))):\n try: op()\n except PermissionError: print('blocked')\n else: raise AssertionError('outbound was not blocked')"
        result = runtime.run_process([sys.executable, '-c', code], root=ROOT, cwd=ROOT / 'lab',
                                     capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip().splitlines(), ['blocked', 'blocked'])

    def test_atomic_json_failure_preserves_previous_document(self):
        with tempfile.TemporaryDirectory(dir=FIXTURES) as td:
            path = Path(td) / 'документ.json'
            runtime.write_json(path, {'title':'Песня'}, ensure_ascii=False)
            self.assertEqual(runtime.read_json(path), {'title':'Песня'})
            with self.assertRaises(TypeError):
                runtime.write_json(path, {'unsupported':object()})
            self.assertEqual(runtime.read_json(path), {'title':'Песня'})
            self.assertEqual(list(Path(td).iterdir()), [path])

    def test_native_unicode_subprocess(self):
        result = runtime.run_process([sys.executable, '-c', "print('Песня — Unicode')"], root=ROOT,
                                     capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), 'Песня — Unicode')

    def _tree_command(self, marker):
        child = "import time; time.sleep(60)"
        code = "import subprocess,sys,time,pathlib; p=subprocess.Popen([sys.executable,'-c',%r]); pathlib.Path(%r).write_text(str(p.pid)); time.sleep(60)" % (child, str(marker))
        return [sys.executable, '-c', code]

    def _wait_marker(self, marker):
        end = time.monotonic() + 10
        while not marker.exists() and time.monotonic() < end:
            time.sleep(.05)
        self.assertTrue(marker.exists())
        return int(marker.read_text())

    def test_owned_process_tree_stop(self):
        with tempfile.TemporaryDirectory(dir=FIXTURES) as td:
            marker = Path(td) / 'child.pid'
            process = subprocess.Popen(self._tree_command(marker), **runtime.process_options())
            try:
                child = self._wait_marker(marker)
                self.assertTrue(runtime.pid_alive(child))
                runtime.terminate_process(process)
                self.assertIsNotNone(process.poll())
                self.assertFalse(runtime.pid_alive(child))
                self.assertTrue(runtime.pid_alive(os.getpid()))
            finally:
                runtime.terminate_process(process)

    def test_timeout_cleans_owned_child_tree(self):
        with tempfile.TemporaryDirectory(dir=FIXTURES) as td:
            marker = Path(td) / 'child.pid'
            with self.assertRaises(subprocess.TimeoutExpired):
                runtime.run_process(self._tree_command(marker), root=ROOT, capture_output=True, text=True, timeout=2)
            child = self._wait_marker(marker)
            self.assertFalse(runtime.pid_alive(child))

    def test_junction_roundtrip_does_not_remove_unicode_target(self):
        with tempfile.TemporaryDirectory(dir=FIXTURES) as td:
            base = Path(td); target = base / 'Музыка'; target.mkdir()
            (target / 'песня.txt').write_bytes(b'keep')
            link = base / 'Songs'
            runtime.create_directory_link(target, link)
            self.assertTrue(runtime.is_directory_link(link))
            self.assertEqual((link / 'песня.txt').read_bytes(), b'keep')
            runtime.remove_directory_link(link)
            self.assertEqual((target / 'песня.txt').read_bytes(), b'keep')
            with self.assertRaises(ValueError):
                runtime.remove_directory_link(target)

    def test_junction_replace_and_collision_preserves_previous_location(self):
        with tempfile.TemporaryDirectory(dir=FIXTURES) as td:
            base = Path(td); a = base / 'a'; b = base / 'b'; a.mkdir(); b.mkdir()
            (a / 'file').write_bytes(b'a'); (b / 'file').write_bytes(b'b')
            link = base / 'link'; runtime.create_directory_link(a, link)
            runtime.replace_directory_link(b, link)
            self.assertEqual((link / 'file').read_bytes(), b'b')
            (base / 'link.link-part').mkdir()
            with self.assertRaises(FileExistsError):
                runtime.replace_directory_link(a, link)
            self.assertEqual((link / 'file').read_bytes(), b'b')
            runtime.remove_directory_link(link)
            self.assertEqual((a / 'file').read_bytes(), b'a')

    def test_gpu_guard_wddm_unknown_foreign_memory_is_not_zero(self):
        answers = [subprocess.CompletedProcess([], 0, '0, GPU-x, 12288, 11000\n', ''),
                   subprocess.CompletedProcess([], 0, '456, GPU-x, [N/A]\n', '')]
        with mock.patch.dict(os.environ, {'RUACH_WDDM_MEMORY_POLICY':'strict'}), mock.patch.object(runtime, 'run_process', side_effect=answers), mock.patch.object(runtime, 'process_details', return_value={456: {'exe': 'C:/foreign.exe', 'cmd': 'foreign', 'name': 'foreign.exe'}}):
            card = gpu_guard.snapshot(ROOT)[0]
        self.assertFalse(card['ok'])
        self.assertIsNone(card['foreign'][0][2])
        self.assertIn('WDDM', card['why'])
        self.assertFalse(gpu_guard.empty_fits(card, 1000))

    def test_gpu_guard_explicit_aggregate_policy_keeps_unknown_and_reserve(self):
        answers = [subprocess.CompletedProcess([], 0, '0, GPU-x, 12288, 11000\n', ''),
                   subprocess.CompletedProcess([], 0, '456, GPU-x, [N/A]\n', '')]
        info = {456:{'exe':'C:/foreign.exe','cmd':'foreign','name':'foreign.exe'}}
        with mock.patch.dict(os.environ, {'RUACH_WDDM_MEMORY_POLICY':'aggregate'}), mock.patch.object(runtime, 'run_process', side_effect=answers), mock.patch.object(runtime, 'process_details', return_value=info):
            card = gpu_guard.snapshot(ROOT)[0]
        self.assertTrue(card['ok'])
        self.assertEqual(card['accounting'], 'aggregate_only')
        self.assertEqual(card['reserve_mb'], 512)
        self.assertEqual(card['room_mb'], 10488)
        self.assertIsNone(card['foreign'][0][2])
        self.assertIn('unavailable', card['warning'])

    def test_named_gpu_mutex_serializes_two_real_processes(self):
        with tempfile.TemporaryDirectory(dir=FIXTURES) as td:
            base = Path(td); first = base / 'first.json'; second = base / 'second.json'
            mutex = 'Local\\WindowsMusicLab-Test-' + str(os.getpid()) + '-' + str(time.time_ns())
            env = runtime.job_environment(ROOT, dict(os.environ, RUACH_GPU_MUTEX=mutex))
            code = "import platform_runtime as r,time,sys; from pathlib import Path;\nwith r.gpu_lease():\n r.write_json(sys.argv[1],{'start':time.monotonic()}); time.sleep(float(sys.argv[2])); r.write_json(sys.argv[1],{'end':time.monotonic()})"
            a = subprocess.Popen([sys.executable, '-c', code, str(first), '.7'], cwd=ROOT/'lab', env=env, **runtime.process_options())
            b = None
            try:
                end = time.monotonic()+5
                while not first.exists() and time.monotonic()<end: time.sleep(.02)
                self.assertTrue(first.exists())
                b = subprocess.Popen([sys.executable, '-c', code, str(second), '0'], cwd=ROOT/'lab', env=env, **runtime.process_options())
                self.assertEqual(a.wait(timeout=10), 0); self.assertEqual(b.wait(timeout=10), 0)
                # Second writes only after acquiring. Its final end follows the first release.
                self.assertGreaterEqual(runtime.read_json(second)['end'], runtime.read_json(first)['end'])
            finally:
                runtime.terminate_process(a)
                if b is not None: runtime.terminate_process(b)

    def test_gpu_mutex_abandoned_owner_and_cancelled_wait(self):
        with tempfile.TemporaryDirectory(dir=FIXTURES) as td:
            base = Path(td); owner = base/'owner.json'; waiting=base/'waiting.json'; result=base/'result.json'
            mutex = 'Local\\WindowsMusicLab-Test-' + str(os.getpid()) + '-' + str(time.time_ns())
            env = runtime.job_environment(ROOT, dict(os.environ, RUACH_GPU_MUTEX=mutex))
            a_code="import platform_runtime as r,sys,time;\nwith r.gpu_lease():\n r.write_json(sys.argv[1],{'owned':True}); time.sleep(60)"
            b_code="import platform_runtime as r,sys;\nwith r.gpu_lease(waiting=lambda _:r.write_json(sys.argv[1],{'waiting':True})) as lease:\n r.write_json(sys.argv[2],{'abandoned':lease.abandoned})"
            a = subprocess.Popen([sys.executable,'-c',a_code,str(owner)], cwd=ROOT/'lab',env=env,**runtime.process_options()); b=None
            try:
                end=time.monotonic()+5
                while not owner.exists() and time.monotonic()<end:time.sleep(.02)
                self.assertTrue(owner.exists())
                b=subprocess.Popen([sys.executable,'-c',b_code,str(waiting),str(result)],cwd=ROOT/'lab',env=env,**runtime.process_options())
                end=time.monotonic()+5
                while not waiting.exists() and time.monotonic()<end:time.sleep(.02)
                self.assertTrue(waiting.exists())
                runtime.terminate_process(a)
                self.assertEqual(b.wait(timeout=10),0)
                self.assertTrue(runtime.read_json(result)['abandoned'])
            finally:
                runtime.terminate_process(a)
                if b is not None:runtime.terminate_process(b)
            with mock.patch.dict(os.environ,{'RUACH_GPU_MUTEX':mutex}):
                with self.assertRaises(runtime.GPUWaitCancelled):
                    with runtime.gpu_lease(job={'cancel':True}):self.fail('cancelled lease acquired')

    def test_gpu_guard_process_query_failure_is_reported(self):
        answers = [subprocess.CompletedProcess([], 0, '0, GPU-x, 12288, 11000\n', ''),
                   subprocess.CompletedProcess([], 1, '', 'not supported')]
        with mock.patch.object(runtime, 'run_process', side_effect=answers):
            with self.assertRaisesRegex(RuntimeError, 'process accounting'):
                gpu_guard.snapshot(ROOT)

    def test_gpu_guard_owned_process_and_memory_limit(self):
        with tempfile.TemporaryDirectory(dir=FIXTURES) as td:
            root = Path(td); (root / 'user').mkdir()
            (root / 'user/gpus.json').write_text('{"limits":{"0":8192}}')
            answers = [subprocess.CompletedProcess([], 0, '0, GPU-x, 12288, 7000\n', ''),
                       subprocess.CompletedProcess([], 0, '456, GPU-x, [N/A]\n', '')]
            info = {456: {'exe': str(root / '.venv/Scripts/python.exe'), 'cmd': '', 'name': 'python.exe'}}
            with mock.patch.object(runtime, 'run_process', side_effect=answers), mock.patch.object(runtime, 'process_details', return_value=info):
                card = gpu_guard.snapshot(root)[0]
            self.assertTrue(card['ok'])
            self.assertEqual(card['foreign'], [])
            self.assertEqual(card['room_mb'], 2904)


class PlacesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=FIXTURES)
        self.base = Path(self.temp.name)
        self.kit = self.base / 'studio'
        for d in ('outputs/take-1', 'trash', 'artist', 'writer', 'user'):
            (self.kit / d).mkdir(parents=True)
        self.settings = self.kit / 'user/settings.json'
        self.settings.write_text('{"keys":{"theme":"keep"}}')
        (self.kit / 'outputs/take-1/песня.wav').write_bytes(b'synthetic audio fixture')
        places.JOB.clear(); places.SIZES.clear()
        self.busy = False
        places.setup(self.kit, lambda: self.busy, threading.Lock(), self.settings, studio_port='9', say=lambda _: None)

    def tearDown(self):
        self.temp.cleanup()

    def _wait(self):
        end = time.monotonic() + 10
        while time.monotonic() < end:
            with places.LOCK:
                result = dict(places.JOB)
            if result.get('phase') in ('done', 'failed'):
                return result
            time.sleep(.05)
        self.fail('folder move did not finish')

    def test_native_paths_and_remote_share_refusal(self):
        self.assertEqual(places.norm(str(self.base)), str(self.base))
        for path in ('relative', 'D:relative', r'\\remote\music'):
            with self.assertRaises(ValueError):
                places.norm(path)
        self.assertFalse(places._wsl())

    def test_move_out_and_home_preserves_files_and_page_settings(self):
        destination = self.base / 'storage'; destination.mkdir()
        places.move({'name': 'outputs', 'to': str(destination)})
        job = self._wait(); self.assertEqual(job['phase'], 'done', job)
        self.assertTrue(runtime.is_directory_link(self.kit / 'outputs'))
        self.assertEqual((self.kit / 'outputs/take-1/песня.wav').read_bytes(), b'synthetic audio fixture')
        self.assertEqual(json.loads(self.settings.read_text())['keys'], {'theme': 'keep'})
        places.move({'name': 'outputs', 'to': ''})
        job = self._wait(); self.assertEqual(job['phase'], 'done', job)
        self.assertFalse(runtime.is_directory_link(self.kit / 'outputs'))
        self.assertEqual((self.kit / 'outputs/take-1/песня.wav').read_bytes(), b'synthetic audio fixture')
        self.assertEqual(json.loads(self.settings.read_text())['paths']['outputs']['at'], '')

    def test_copy_remaps_internal_junction_to_new_tree(self):
        source = self.kit / 'outputs'
        runtime.create_directory_link(source / 'take-1', source / 'alias')
        copied = self.base / 'copied'
        places.JOB.update(done=0, files=0)
        places._copy_tree(str(source), str(copied))
        self.assertEqual(places._walk(str(source)), places._walk(str(copied)))
        self.assertEqual((copied / 'alias/песня.wav').read_bytes(), b'synthetic audio fixture')
        os.rename(source, self.kit / 'outputs-old')
        self.assertEqual((copied / 'alias/песня.wav').read_bytes(), b'synthetic audio fixture')
        self.assertEqual((copied / 'alias').resolve(), (copied / 'take-1').resolve())

    def test_relink_record_native_junction_without_system_settings(self):
        destination = self.base / 'external'; destination.mkdir()
        (destination / 'picture.txt').write_bytes(b'keep')
        places._write_record('artist', {'at': str(destination)})
        places.relink({'name': 'artist'})
        self.assertTrue(runtime.is_directory_link(self.kit / 'artist'))
        self.assertEqual((self.kit / 'artist/picture.txt').read_bytes(), b'keep')

    def test_path_containment_busy_scope_and_existing_destination(self):
        self.assertFalse(places.plan('outputs', str(self.kit / 'outputs'))['ok'])
        self.assertFalse(places.plan('outputs', str(self.kit / 'user'))['ok'])
        self.assertFalse(places.plan('outputs', str(self.base / 'missing'))['ok'])
        self.busy = True
        with self.assertRaisesRegex(ValueError, 'working'):
            places.move({'name': 'outputs', 'to': str(self.base)})
        self.busy = False
        with self.assertRaisesRegex(ValueError, 'test page'):
            places.move({'name': 'outputs', 'to': str(self.base)}, scope='test')
        (self.base / 'outputs').mkdir(); (self.base / 'outputs/file').write_bytes(b'occupied')
        self.assertFalse(places.plan('outputs', str(self.base))['ok'])


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import lab
        cls.lab = lab
        cls.server = lab.LocalHTTPServer(('127.0.0.1', 0), lab.Handler)
        cls.worker = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.worker.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.worker.join(timeout=5)

    def _get(self, headers=None, path='/health', method='GET', body=None):
        c = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        try:
            c.request(method, path, body=body, headers=headers or {})
            response = c.getresponse()
            return response.status, dict(response.headers), response.read()
        finally:
            c.close()

    def test_take_paths_cannot_traverse_on_windows(self):
        for name in (r'..\source\outputs', r'C:\Users', 'C:relative', 'audio.wav:stream'):
            with self.assertRaises(ValueError):
                self.lab.take_dir(name)

    def test_server_constructor_rejects_wildcard_before_socket_bind(self):
        with self.assertRaises(ValueError):
            self.lab.LocalHTTPServer(('0.0.0.0', 0), self.lab.Handler)

    def test_actual_ipv6_loopback_health(self):
        if not socket.has_ipv6:
            self.skipTest('IPv6 not enabled in this OS')
        server = self.lab.LocalHTTPServer(('::1', 0), self.lab.Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True); worker.start()
        connection = http.client.HTTPConnection('::1', server.server_port, timeout=5)
        try:
            connection.request('GET', '/health')
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertTrue(json.loads(response.read())['ok'])
        finally:
            connection.close(); server.shutdown(); server.server_close(); worker.join(timeout=5)

    def test_actual_local_health_without_heavy_dependencies(self):
        status, headers, body = self._get()
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)['local_only'])
        self.assertNotIn('Access-Control-Allow-Origin', headers)
        self.assertEqual(headers.get('X-Content-Type-Options'), 'nosniff')

    def test_actual_cross_origin_and_dns_rebinding_refused(self):
        for headers in ({'Origin':'https://evil.invalid'}, {'Host':'evil.invalid:1'}, {'Referer':'https://evil.invalid/'}):
            self.assertEqual(self._get(headers)[0], 403)

    def test_allowed_studio_origin_options(self):
        headers = {'Origin': 'http://localhost:41867'}
        status, out, _ = self._get(headers, method='OPTIONS')
        self.assertEqual(status, 204)
        self.assertEqual(out['Access-Control-Allow-Origin'], headers['Origin'])

    def test_fetch_and_oversized_api_body_block_before_read_or_download(self):
        self.assertEqual(self._get(path='/weights/fetch', method='POST', body=b'{}')[0], 400)
        self.assertEqual(self._get({'Content-Length':str(70*1024*1024)}, path='/api/v1/songs', method='POST')[0], 413)

    def test_windows_unsupervised_restart_does_not_call_systemctl(self):
        with mock.patch.object(self.lab, 'native_run') as run, mock.patch('urllib.request.urlopen') as urlopen:
            urlopen.return_value.read.return_value = b'{"busy": false}'
            with mock.patch.dict(os.environ, {'RUACH_FULL_SUPERVISED': '0'}):
                with self.assertRaisesRegex(ValueError, 'launcher'):
                    self.lab.studio_restart()
            run.assert_not_called()

    def test_windows_supervised_restart_is_scoped_marker_only(self):
        with tempfile.TemporaryDirectory(dir=FIXTURES) as td:
            state = Path(td)
            with mock.patch('urllib.request.urlopen') as urlopen, mock.patch.dict(os.environ,
                    {'RUACH_FULL_SUPERVISED':'1','RUACH_FULL_STATE_DIR':str(state),'RUACH_FULL_INSTANCE':'fixture'}):
                urlopen.return_value.read.return_value = b'{"busy": false}'
                result = self.lab.studio_restart()
            self.assertEqual(result['status'], 'restarting')
            self.assertEqual(json.loads((state / 'restart.requested').read_text())['instance'], 'fixture')


if __name__ == '__main__':
    unittest.main(verbosity=2)
