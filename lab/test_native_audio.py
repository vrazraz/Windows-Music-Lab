"""Synthetic Windows portability tests; no ML dependency/model downloads."""
import argparse
import importlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import time
import types
import unittest
from unittest import mock
import wave

LAB = Path(__file__).resolve().parent
ROOT = LAB.parent
sys.path.insert(0, str(LAB))
import gtsinger
import listener
import platform_runtime
import starter
import training
from trainer.control import stop_requested


class NativeAudioTests(unittest.TestCase):
    def setUp(self):
        cache = ROOT / 'lab/cache/test-audio'
        cache.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=cache)
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        # Synthetic children never contend with the user's real Creator/Listener lease.
        isolated = mock.patch.dict(os.environ, {'RUACH_GPU_MUTEX': 'Local\\WindowsMusicLab-Fixture_' + self.folder.name})
        isolated.start()
        self.addCleanup(isolated.stop)

    def test_windows_venv_paths(self):
        with mock.patch.object(platform_runtime, 'WINDOWS', True):
            self.assertEqual(platform_runtime.venv_python(self.folder), self.folder / '.venv/Scripts/python.exe')
            self.assertEqual(training.paths(self.folder)['aitk_py'], self.folder / 'vendor/AI_Toolkit/.venv/Scripts/python.exe')

    def test_mtmd_ninja_and_visual_studio_layouts(self):
        with mock.patch.object(listener, 'WINDOWS', True):
            self.assertEqual(listener.mtmd_cli(self.folder).name, 'llama-mtmd-cli.exe')
            exe = self.folder / 'vendor/llama.cpp/build/bin/Release/llama-mtmd-cli.exe'
            exe.parent.mkdir(parents=True)
            exe.write_bytes(b'fixture; never executed')
            self.assertEqual(listener.mtmd_cli(self.folder), exe)
            published = self.folder / 'windows/build/listener-cuda/bin/llama-mtmd-cli.exe'
            published.parent.mkdir(parents=True)
            published.write_bytes(b'fixture; never executed')
            self.assertEqual(listener.mtmd_cli(self.folder), published)
            with mock.patch.object(listener, 'KIT', self.folder):
                self.assertEqual(listener.local_cli(published), published.resolve())
                with self.assertRaises(ValueError):
                    listener.local_cli(self.folder / 'windows/other.exe')

    def test_listener_memory_admission_accepts_exact_machine_thresholds(self):
        measured = {'commit_scope': 'machine', 'commit_available': 11 * 2**30, 'available': 10 * 2**30}
        args = argparse.Namespace(model='local.gguf')
        with mock.patch.object(listener, 'WINDOWS', True), mock.patch.object(listener, 'system_memory', return_value=measured):
            self.assertEqual(listener.listener_memory_admission(args), measured)

    def test_listener_memory_admission_rejects_low_or_nonmachine_counters(self):
        for measured in ({'commit_scope': 'machine', 'commit_available': 11 * 2**30 - 1, 'available': 20 * 2**30},
                         {'commit_scope': 'machine', 'commit_available': 20 * 2**30, 'available': 10 * 2**30 - 1},
                         {'commit_scope': 'process_bound', 'commit_available': 20 * 2**30, 'available': 20 * 2**30}):
            with self.subTest(measured=measured), mock.patch.object(listener, 'WINDOWS', True), mock.patch.object(listener, 'system_memory', return_value=measured):
                with self.assertRaises(RuntimeError):
                    listener.listener_memory_admission(argparse.Namespace(model='local.gguf'))

    def test_listener_main_blocks_before_inference_when_commit_is_low(self):
        # All other admissions are mocked; the real memory gate must prevent model code.
        with mock.patch.object(sys, 'argv', ['listener.py', 'owned-set', '--model', 'local.gguf']), \
                mock.patch.object(listener, 'WINDOWS', True), mock.patch.object(listener, 'configure_runtime'), \
                mock.patch.object(listener, 'dataset'), mock.patch.object(listener, 'selected_stems'), \
                mock.patch.object(listener, 'gguf_paths', return_value=(Path('fixture.exe'), Path('local.gguf'), Path('mmproj.gguf'))), \
                mock.patch.object(listener, 'gpu_lease'), mock.patch.object(listener, 'release_engine_for_gpu_job'), \
                mock.patch.object(listener, 'system_memory', return_value={'commit_scope': 'machine', 'commit_available': 10 * 2**30, 'available': 20 * 2**30}), \
                mock.patch.object(listener, '_inference') as inference:
            with self.assertRaisesRegex(RuntimeError, 'No model started'):
                listener.main()
            inference.assert_not_called()

    def test_listener_dataset_cannot_escape(self):
        folder = self.folder / 'datasets/prepared/Русский набор'
        folder.mkdir(parents=True)
        self.assertEqual(listener.dataset(self.folder, 'Русский набор'), folder.resolve())
        for name in ('../../../escape', str(self.folder), '..'):
            with self.assertRaises(ValueError):
                listener.dataset(self.folder, name)

    def test_listener_track_selection_rejects_empty_missing_and_escape(self):
        _, _, _, _, data = self.listener_fixture()
        manifest = data / 'dataset.json'
        args = argparse.Namespace(only='001')
        with mock.patch.object(listener, 'KIT', self.folder):
            manifest.write_text(json.dumps({'tracks': [{'stem': '001'}]}), encoding='utf-8')
            self.assertEqual(listener.selected_stems(args, data), ['001'])
            args.only = 'missing'
            with self.assertRaisesRegex(ValueError, 'no local dataset tracks'):
                listener.selected_stems(args, data)
            args.only = ''
            manifest.write_text(json.dumps({'tracks': [{'stem': '../../../outside'}]}), encoding='utf-8')
            with self.assertRaises(ValueError):
                listener.selected_stems(args, data)
            manifest.write_text(json.dumps({'tracks': []}), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'no local dataset tracks'):
                listener.selected_stems(args, data)

    def test_styles_atomic_utf8(self):
        path = self.folder / 'styles.json'
        listener.write_styles(path, {'tags': {'песня': 'женский вокал'}})
        self.assertEqual(json.loads(path.read_text(encoding='utf-8'))['tags']['песня'], 'женский вокал')
        self.assertFalse(path.with_suffix('.json.part').exists())

    def test_cooperative_stop_file(self):
        with mock.patch.dict(os.environ, {'RUACH_TRAIN_STOP_FILE': str(self.folder / 'custom.stop')}):
            self.assertFalse(stop_requested(self.folder))
            (self.folder / 'custom.stop').write_text('stop', encoding='utf-8')
            self.assertTrue(stop_requested(self.folder))

    def test_starter_download_blocked_before_process(self):
        with mock.patch.dict(os.environ, {'WINDOWS_MUSIC_LAB_LOCAL_ONLY': '1'}), mock.patch.object(starter.subprocess, 'run') as run:
            with self.assertRaisesRegex(ValueError, 'local-only'):
                starter.fetch(self.folder, 'GTSinger-RU-sample')
            run.assert_not_called()

    def test_diamond_listing_offline_without_http(self):
        import diamond
        with mock.patch.dict(os.environ, {'WINDOWS_MUSIC_LAB_LOCAL_ONLY': '1'}), mock.patch.object(diamond, '_get') as get:
            manifest, error = diamond._manifest(self.folder, diamond.SOURCES[0])
            self.assertIsNone(manifest)
            self.assertIn('local-only', error)
            self.assertIsNone(diamond._token())
            get.assert_not_called()

    def listener_fixture(self):
        model = self.folder / 'checkpoints/model.gguf'
        projector = self.folder / 'checkpoints/mmproj-Q8_0.gguf'
        cli = self.folder / 'vendor/llama.cpp/build/bin/llama-mtmd-cli.exe'
        audio = self.folder / 'lab/cache/tmp/excerpt.wav'
        data = self.folder / 'datasets/prepared/synthetic'
        data.mkdir(parents=True)
        for path in (model, projector, cli, audio, data / '001.wav'):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'fixture; never executed or decoded')
        return model, projector, cli, audio, data

    def test_listener_worker_failure_cleans_only_its_native_child(self):
        _, _, _, _, data = self.listener_fixture()
        (data / 'dataset.json').write_text(json.dumps({'tracks': [{'stem': '001'}]}), encoding='utf-8')
        child = mock.MagicMock()
        child.stdout.__iter__.side_effect = OSError('synthetic stdout failure')
        child.poll.return_value = None
        choice = {'present': True, 'fits': True, 'runtime_ready': True,
                  'path': 'model.gguf', 'mmproj': 'mmproj-Q8_0.gguf', 'needs_mb': 8200, 'what': 'fixture'}
        class ImmediateThread:
            def __init__(self, target, daemon):
                self.target = target
            def start(self):
                self.target()
        with mock.patch.object(training, 'LISTEN', {}), mock.patch.object(training, 'listeners', return_value=[choice]), \
             mock.patch.object(training.subprocess, 'Popen', return_value=child), \
             mock.patch.object(training, 'terminate_process') as terminate, \
             mock.patch.object(training.threading, 'Thread', ImmediateThread):
            job = training.listen(self.folder, {'dataset': 'synthetic'}, lambda need: (0, 10000))
        self.assertEqual(job['status'], 'failed')
        self.assertIn('synthetic stdout failure', job['error'])
        terminate.assert_called_once_with(child)
        child.stdout.close.assert_called_once()

    def test_listener_failed_track_returns_failure_not_success(self):
        model, projector, cli, _, data = self.listener_fixture()
        args = argparse.Namespace(model=str(model), mmproj=str(projector), gpu='0', seconds=1)
        failed = subprocess.CompletedProcess([], 1, '', 'synthetic error')
        def cut(command, **kwargs):
            Path(command[-1]).write_bytes(b'synthetic excerpt')
        with mock.patch.object(listener, 'KIT', self.folder), mock.patch.object(listener, 'mtmd_cli', return_value=cli), \
             mock.patch.object(listener, 'length', return_value=2), mock.patch.object(listener.subprocess, 'run', side_effect=cut), \
             mock.patch.object(listener, 'run_cli', return_value=failed):
            self.assertEqual(listener.gguf(args, data, ['001']), 1)
        self.assertFalse((data / 'styles.json').exists())

    def test_listener_rejects_successful_cpu_fallback_without_publishing_tags(self):
        model, projector, cli, _, data = self.listener_fixture()
        args = argparse.Namespace(model=str(model), mmproj=str(projector), gpu='0', seconds=1)
        cpu = subprocess.CompletedProcess([], 0, 'ambient, instrumental\n', 'CPU model buffer; offloaded 0/29 layers to GPU')
        def cut(command, **kwargs):
            Path(command[-1]).write_bytes(b'synthetic excerpt')
        with mock.patch.object(listener, 'KIT', self.folder), mock.patch.object(listener, 'mtmd_cli', return_value=cli), \
             mock.patch.object(listener, 'length', return_value=2), mock.patch.object(listener.subprocess, 'run', side_effect=cut), \
             mock.patch.object(listener, 'run_cli', return_value=cpu):
            self.assertEqual(listener.gguf(args, data, ['001']), 1)
        self.assertFalse((data / 'styles.json').exists())
        self.assertTrue(listener.cuda_offload('CUDA0 model buffer; offloaded 29/29 layers to GPU; CLIP using CUDA0 backend; has audio encoder'))
        self.assertFalse(listener.cuda_offload('CUDA0 model buffer; offloaded 29/29 layers to GPU; CLIP using CPU backend; has audio encoder'))
        self.assertFalse(listener.cuda_offload('CUDA0 model buffer; offloaded 2/29 layers to GPU'))
        self.assertFalse(listener.cuda_offload('offloaded 29/29 layers to GPU'))

    def test_listener_command_uses_only_local_absolute_files_and_pinned_flags(self):
        model, projector, cli, audio, _ = self.listener_fixture()
        with mock.patch.object(listener, 'KIT', self.folder):
            command = listener.gguf_command(cli, model, projector, audio)
        self.assertEqual(command[1:3], ['--offline', '--jinja'])
        for flag, path in (('-m', model), ('--mmproj', projector), ('--audio', audio)):
            self.assertEqual(command[command.index(flag) + 1], str(path.resolve()))
        self.assertEqual(command[command.index('-p') + 1], listener.PROMPT)
        self.assertEqual(command[command.index('--batch-size') + 1], '256')
        self.assertEqual(command[command.index('--ubatch-size') + 1], '128')
        self.assertEqual(command[command.index('--threads') + 1], '4')
        self.assertEqual(command[command.index('--verbosity') + 1], '4')
        self.assertIn('--perf', command)
        for unsupported in ('--hf', '-hf', '--model-url', '--mmproj-url', '--mmproj-ntoken', '--simple-io'):
            self.assertNotIn(unsupported, command)
        self.assertFalse(any('://' in value for value in command))

    def test_listener_rejects_nonlocal_or_outside_model_projector_audio(self):
        model, projector, cli, audio, _ = self.listener_fixture()
        outside = self.folder / 'outside.gguf'
        outside.write_bytes(b'fixture')
        with mock.patch.object(listener, 'KIT', self.folder):
            for value in ('https://example.invalid/model.gguf', r'\\server\share\model.gguf', outside):
                with self.assertRaises(ValueError):
                    listener.gguf_command(cli, value, projector, audio)
            with self.assertRaises(ValueError):
                listener.gguf_command(cli, model, outside, audio)
            with self.assertRaises(ValueError):
                listener.gguf_command(cli, model, projector, model)
            with self.assertRaises(FileNotFoundError):
                listener.gguf_command(cli, model, projector, audio.parent / 'missing.wav')

    def test_listener_child_environment_removes_remote_and_secret_overrides(self):
        inherited = {'LLAMA_ARG_HF_REPO': 'example/remote', 'LLAMA_ARG_MODEL_URL': 'https://example.invalid',
                     'LLAMA_ARG_OFFLINE': '0', 'MTMD_TEST_RESPONSE_MARKER': 'fake',
                     'GGML_RPC_SERVER': 'example:5000', 'HF_TOKEN': 'synthetic-secret',
                     'HF_ENDPOINT': 'https://example.invalid', 'OPENAI_API_KEY': 'synthetic-secret',
                     'https_proxy': 'https://example.invalid', 'CUDA_VISIBLE_DEVICES': '7'}
        with mock.patch.object(listener, 'KIT', self.folder), mock.patch.object(listener, 'job_environment', return_value=inherited):
            env = listener.cli_environment(0)
        self.assertEqual(env['LLAMA_ARG_OFFLINE'], '1')
        self.assertEqual(env['CUDA_VISIBLE_DEVICES'], '0')
        self.assertEqual(env['HF_HUB_OFFLINE'], '1')
        for key in inherited.keys() - {'LLAMA_ARG_OFFLINE', 'CUDA_VISIBLE_DEVICES', 'HF_HUB_OFFLINE',
                                      'HF_HUB_DISABLE_TELEMETRY', 'TRANSFORMERS_OFFLINE',
                                      'WINDOWS_MUSIC_LAB_LOCAL_ONLY', 'NO_PROXY'}:
            self.assertNotIn(key, env)
        self.assertNotIn('synthetic-secret', env.values())

    def test_listener_native_child_one_turn_closed_stdin_and_logs(self):
        process = mock.Mock(returncode=0)
        process.communicate.return_value = ('ambient, instrumental\n', 'audio encoder diagnostic\n')
        process.poll.return_value = 0
        command = ['fixture.exe', '--offline', '--audio', 'fixture.wav', '-p', listener.PROMPT]
        logs = self.folder / 'logs'
        with mock.patch.object(listener, 'KIT', self.folder), mock.patch.object(listener.subprocess, 'Popen', return_value=process) as popen, \
             mock.patch.object(listener, 'terminate_process') as stop:
            result = listener.run_cli(command, {'CUDA_VISIBLE_DEVICES': '0'}, logs)
        self.assertEqual(result.stdout.strip(), 'ambient, instrumental')
        self.assertEqual(popen.call_args.args[0], command)
        self.assertEqual(popen.call_args.kwargs['stdin'], subprocess.DEVNULL)
        self.assertEqual(popen.call_args.kwargs['cwd'], str(self.folder))
        self.assertNotIn('shell', popen.call_args.kwargs)
        self.assertIn('creationflags' if os.name == 'nt' else 'start_new_session', popen.call_args.kwargs)
        stop.assert_not_called()
        self.assertIn('audio encoder', (logs / 'stderr.log').read_text(encoding='utf-8'))
        self.assertEqual(json.loads((logs / 'command.json').read_text(encoding='utf-8'))['stdin'], 'DEVNULL')

    def test_listener_timeout_cleans_only_owned_native_child(self):
        process = mock.Mock(returncode=-1)
        process.communicate.side_effect = [subprocess.TimeoutExpired(['fixture.exe'], .01), ('', 'stopped')]
        process.poll.return_value = -1
        logs = self.folder / 'timeout-logs'
        with mock.patch.object(listener, 'KIT', self.folder), mock.patch.object(listener.subprocess, 'Popen', return_value=process), \
             mock.patch.object(listener, 'terminate_process') as stop:
            with self.assertRaises(subprocess.TimeoutExpired):
                listener.run_cli(['fixture.exe'], {'CUDA_VISIBLE_DEVICES': '0'}, logs, timeout=.01)
        stop.assert_called_once_with(process)
        self.assertEqual(json.loads((logs / 'command.json').read_text(encoding='utf-8'))['failure'], 'TimeoutExpired')

    def test_gtsinger_join_unicode_synthetic_pcm(self):
        src = self.folder / 'исходные'
        phrase = src / 'Альто/normal/Песня/Control_Group/0001.json'
        phrase.parent.mkdir(parents=True)
        phrase.write_text(json.dumps([{'word': 'Привет', 'start_time': 0, 'end_time': 0.1}], ensure_ascii=False), encoding='utf-8')
        with wave.open(str(phrase.with_suffix('.wav')), 'wb') as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(8000)
            output.writeframes(b'\x01\x00' * 800)
        out = self.folder / 'готовое'
        out.mkdir()
        gtsinger.join(src, out, 'russian', False)
        self.assertEqual(len(list(out.glob('*.wav'))), 1)
        self.assertIn('Привет', next(path for path in out.glob('*.txt') if not path.name.endswith('.style.txt')).read_text(encoding='utf-8'))
        with wave.open(str(next(out.glob('*.wav')))) as generated:
            self.assertEqual(generated.getnframes(), 800)

    def test_whisper_missing_local_model_before_import(self):
        result = subprocess.run([sys.executable, str(LAB / 'whisper_job.py'), 'not-read.wav', str(self.folder / 'out.json'), 'ru', str(self.folder / 'missing')], capture_output=True, text=True, encoding='utf-8')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('local Whisper model folder is missing', result.stderr)
        self.assertNotIn('ModuleNotFoundError', result.stderr)

    def test_stems_missing_weights_before_import(self):
        with mock.patch.dict(os.environ, {'LAB_ROFORMER_DIR': str(self.folder / 'missing')}):
            result = subprocess.run([sys.executable, str(LAB / 'stems_job.py'), 'not-read.wav', str(self.folder / 'output'), 'vocals'], capture_output=True, text=True, encoding='utf-8')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('local separation weights/config are missing', result.stderr)
        self.assertNotIn('ModuleNotFoundError', result.stderr)

    def test_whisper_word_json_utf8_and_local_only_model(self):
        class FakeArray:
            def mean(self, axis): return self
            def numpy(self): return self
            def astype(self, dtype): return self
        sf = types.SimpleNamespace(read=lambda *args, **kwargs: (FakeArray(), 16000))
        torch = types.SimpleNamespace(from_numpy=lambda array: array)
        word = types.SimpleNamespace(word=' привет', start=0, end=.2, probability=.99)
        segment = types.SimpleNamespace(start=0, end=.2, text='Привет', words=[word])
        model = mock.Mock()
        model.transcribe.return_value = ([segment], types.SimpleNamespace(language='ru', duration=.2))
        whisper = types.SimpleNamespace(WhisperModel=mock.Mock(return_value=model))
        weights = self.folder / 'модель'
        weights.mkdir()
        out = self.folder / 'слова.json'
        modules = {'faster_whisper': whisper, 'numpy': types.SimpleNamespace(float32='f32'),
                   'soundfile': sf, 'torch': torch, 'torchaudio': types.SimpleNamespace()}
        with mock.patch.dict(sys.modules, modules), mock.patch.object(platform_runtime, 'configure_runtime'), \
             mock.patch.object(sys, 'argv', ['whisper_job.py', 'fixture.wav', str(out), 'ru', str(weights), 'words']):
            runpy.run_path(str(LAB / 'whisper_job.py'), run_name='__main__')
        self.assertEqual(json.loads(out.read_text(encoding='utf-8'))['segments'][0]['words'][0]['w'], 'привет')
        self.assertTrue(whisper.WhisperModel.call_args.kwargs['local_files_only'])

    def launch_supervisor(self, child_source, grace=3):
        child = self.folder / 'fixture_child.py'
        child.write_text(child_source, encoding='utf-8')
        launch = {'command': [sys.executable, str(child)], 'cwd': str(self.folder), 'env': {}, 'grace_seconds': grace}
        (self.folder / 'native-launch.json').write_text(json.dumps(launch), encoding='utf-8')
        process = subprocess.Popen([sys.executable, str(LAB / 'training_supervisor.py'), str(self.folder)],
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8',
                                   env=dict(os.environ), **platform_runtime.process_options())
        def cleanup():
            if process.poll() is None:
                platform_runtime.terminate_process(process)
            if process.stdout:
                process.stdout.close()
        self.addCleanup(cleanup)
        return process

    def wait_state(self, status, timeout=8):
        until = time.monotonic() + timeout
        state = {}
        while time.monotonic() < until:
            try:
                state = json.loads((self.folder / 'native-process.json').read_text(encoding='utf-8'))
                if state['status'] == status:
                    return state
            except (OSError, ValueError):
                pass
            time.sleep(.05)
        self.fail('supervisor state did not become ' + status + '; last state=' + json.dumps(state))

    def test_supervisor_failure_persisted(self):
        process = self.launch_supervisor('raise RuntimeError("synthetic child failure")\n')
        output, _ = process.communicate(timeout=8)
        self.assertNotEqual(process.returncode, 0)
        self.assertEqual(self.wait_state('failed')['returncode'], 1)
        self.assertIn('synthetic child failure', output)

    def test_supervisor_cooperative_stop_keeps_checkpoint(self):
        source = 'import os,time\nfrom pathlib import Path\nwhile not Path(os.environ["RUACH_TRAIN_STOP_FILE"]).is_file(): time.sleep(.02)\nPath("saved-checkpoint.fixture").write_text("saved",encoding="utf-8")\n'
        process = self.launch_supervisor(source)
        self.wait_state('running')
        (self.folder / 'stop.requested').write_text('stop', encoding='utf-8')
        process.communicate(timeout=8)
        state = self.wait_state('stopped')
        self.assertFalse(state['forced'])
        self.assertEqual(state['returncode'], 0)
        self.assertTrue((self.folder / 'saved-checkpoint.fixture').is_file())

    def test_supervisor_forced_stop_only_owned_child(self):
        process = self.launch_supervisor('import time\ntime.sleep(30)\n', grace=.15)
        self.wait_state('running')
        (self.folder / 'stop.requested').write_text('stop', encoding='utf-8')
        process.communicate(timeout=10)
        self.assertTrue(self.wait_state('stopped')['forced'])
        self.assertTrue(platform_runtime.pid_alive(os.getpid()))  # test process is untouched

    def test_native_train_launch_does_not_use_systemd(self):
        prepared = self.folder / 'datasets/prepared/synthetic'
        prepared.mkdir(parents=True)
        (prepared / 'dataset.json').write_text(json.dumps({'tracks': [{'stem': '001'}]}), encoding='utf-8')
        python = platform_runtime.venv_python(self.folder)
        python.parent.mkdir(parents=True)
        python.write_bytes(b'fixture; never executed')
        checkpoint = training.paths(self.folder)['models'] / 'checkpoints' / training.OWN_CKPT['bf16']
        checkpoint.parent.mkdir(parents=True)
        checkpoint.write_bytes(b'fixture; never loaded')
        worker = mock.Mock(pid=12345)
        worker.poll.return_value = None
        picker = mock.Mock(return_value=(0, 24000))
        with mock.patch.object(training, 'WINDOWS', True), mock.patch.dict(training.RUNS, {}, clear=True), \
             mock.patch.dict(training._NATIVE_WORKERS, {}, clear=True), mock.patch.object(training.subprocess, 'Popen', return_value=worker) as popen, \
             mock.patch.object(training.threading, 'Thread') as thread:
            result = training.train(self.folder, {'dataset': 'synthetic', 'name': 'windows-test', 'engine': 'ruach', 'quant': 'bf16', 'steps': 1}, picker)
            self.assertEqual(result['status'], 'running')
            self.assertEqual(popen.call_args.args[0][0], str(python))
            self.assertEqual(Path(popen.call_args.args[0][1]).name, 'training_supervisor.py')
            self.assertNotIn('shell', popen.call_args.kwargs)
            self.assertIn('creationflags', popen.call_args.kwargs)
            picker.assert_called_once_with(20000, 'train')
            launch = json.loads((self.folder / 'training/windows-test/native-launch.json').read_text(encoding='utf-8'))
            self.assertEqual(Path(launch['command'][1]).name, 'train.py')
            self.assertNotIn('systemd-run', launch['command'])
            thread.return_value.start.assert_called_once()

    def test_native_stop_writes_cooperative_request_without_pid_kill(self):
        folder = self.folder / 'training/fixture'
        folder.mkdir(parents=True)
        (folder / 'run.json').write_text(json.dumps({'status': 'running'}), encoding='utf-8')
        with mock.patch.object(training, 'WINDOWS', True), mock.patch.object(training, '_unit_state', return_value='active'), \
             mock.patch.object(training, '_systemctl') as systemctl:
            self.assertEqual(training.stop(self.folder, 'fixture')['status'], 'stopping')
            self.assertTrue((folder / 'stop.requested').is_file())
            self.assertTrue(json.loads((folder / 'run.json').read_text(encoding='utf-8'))['stopping'])
            systemctl.assert_not_called()

    def test_upscale_missing_local_snapshot_before_import(self):
        with mock.patch.dict(os.environ, {'LAB_UNIVERSR_DIR': str(self.folder / 'missing')}):
            result = subprocess.run([sys.executable, str(LAB / 'upscale_job.py'), 'not-read.wav', str(self.folder / 'output'), 'subtle', '1'], capture_output=True, text=True, encoding='utf-8')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('local UniverSR weights/config are missing', result.stderr)
        self.assertNotIn('ModuleNotFoundError', result.stderr)

    def test_local_separator_resolves_without_model_registry(self):
        from separation_local import DEMUCS, DEMUCS_WEIGHTS, ROFORMER, ROFORMER_CONFIG, local_separator_class
        class FakeBase:
            model_file_dir = str(self.folder)
            def list_supported_model_files(self):
                raise AssertionError("registry access must not happen")
        separator = local_separator_class(FakeBase)()
        for name in (ROFORMER, ROFORMER_CONFIG, DEMUCS, *DEMUCS_WEIGHTS):
            (self.folder / name).write_bytes(b'fixture; never loaded')
        self.assertEqual(separator.download_model_files(ROFORMER)[1], 'MDXC')
        self.assertEqual(separator.download_model_files(DEMUCS)[1], 'Demucs')
        self.assertFalse(separator.model_is_uvr_vip)
        with self.assertRaisesRegex(FileNotFoundError, 'automatic separation downloads are disabled'):
            separator.download_file_if_not_exists('https://example.invalid/no-network', str(self.folder / 'missing'))
        with self.assertRaisesRegex(ValueError, 'unsupported local'):
            separator.download_model_files('unknown-model')

    def test_local_separator_rejects_partial_model_bundle(self):
        from separation_local import DEMUCS, DEMUCS_WEIGHTS, local_separator_class
        class FakeBase:
            model_file_dir = str(self.folder)
        separator = local_separator_class(FakeBase)()
        (self.folder / DEMUCS).write_bytes(b'config fixture')
        for name in DEMUCS_WEIGHTS[:-1]:
            (self.folder / name).write_bytes(b'weight fixture')
        with self.assertRaisesRegex(FileNotFoundError, DEMUCS_WEIGHTS[-1]):
            separator.download_model_files(DEMUCS)

    def test_listener_conservative_vram_profiles(self):
        args = argparse.Namespace(model='Qwen2.5-Omni-7B-Q4_K_M.gguf', mmproj='Qwen2.5-Omni-7B.mmproj-Q8_0.gguf')
        self.assertEqual(listener.listener_need(args), 8200)
        args.mmproj = 'mmproj-f16.gguf'
        self.assertEqual(listener.listener_need(args), 9000)
        args.model = 'Qwen2.5-Omni-7B'
        self.assertEqual(listener.listener_need(args), 23000)

    @unittest.skipUnless(os.name == 'nt', 'native Windows named mutex')
    def test_supervisor_queued_gpu_cancel_never_launches_child(self):
        name = 'Local\\WindowsMusicLab-AudioTest_' + str(os.getpid())
        with mock.patch.dict(os.environ, {'RUACH_GPU_MUTEX': name}):
            with platform_runtime.gpu_lease(0):
                process = self.launch_supervisor('from pathlib import Path\nPath("should-not-launch.fixture").write_text("bad")\n')
                self.wait_state('starting')
                (self.folder / 'stop.requested').write_text('stop', encoding='utf-8')
                process.communicate(timeout=8)
                state = self.wait_state('stopped')
                self.assertIn('waiting for the GPU', state.get('error', ''))
                self.assertFalse((self.folder / 'should-not-launch.fixture').exists())

    def test_portable_run_names_reject_windows_devices_and_trailing_dots(self):
        for name in ('CON', 'NUL.txt', 'COM1', 'LPT9.adapter', 'normal.', 'normal\n', '../escape'):
            self.assertFalse(training.valid_name(name), name)
        self.assertTrue(training.valid_name('synthetic-lora_v1'))

    def test_unpublish_cannot_escape_lora_folder(self):
        private = self.folder / 'private'
        private.mkdir()
        target = private / 'keep.safetensors'
        target.write_bytes(b'private fixture')
        with self.assertRaises(FileNotFoundError):
            training.unpublish(self.folder, '../private', target.name)
        self.assertTrue(target.is_file())

    def test_windows_trainer_readiness_explains_hardware_gate(self):
        with mock.patch.object(training, 'WINDOWS', True):
            readiness = training.native_readiness([{'name': 'RTX 3060', 'total_mb': 12288, 'free_mb': 12000}])
            self.assertFalse(readiness['supported'])
            self.assertEqual(readiness['minimum_free_vram_mb'], 20000)
            self.assertIn('RTX 3060', readiness['reason'])
            self.assertFalse(readiness['auto_download'])
            self.assertNotIn('.sh', readiness['docs'])

    def test_windows_unit_status_uses_persisted_supervisor(self):
        run = self.folder / 'training/fixture'
        run.mkdir(parents=True)
        (run / 'native-process.json').write_text(json.dumps({'status': 'running', 'supervisor_pid': os.getpid()}), encoding='utf-8')
        with mock.patch.object(training, 'WINDOWS', True), mock.patch.object(training, '_systemctl') as systemctl:
            self.assertEqual(training._unit_state('fixture', self.folder), 'active')
            (run / 'native-process.json').write_text(json.dumps({'status': 'done', 'returncode': 0}), encoding='utf-8')
            self.assertEqual(training._unit_state('fixture', self.folder), 'gone')
            systemctl.assert_not_called()


if __name__ == '__main__':
    unittest.main(verbosity=2)
