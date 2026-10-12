"""No-network tests for the budgeted, pinned Listener data installer."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import sys
import unittest
from unittest import mock

SPEC = importlib.util.spec_from_file_location('listener_download', Path(__file__).with_name('listener_download.py'))
download = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = download
SPEC.loader.exec_module(download)


class Response(io.BytesIO):
    def __init__(self, data, start, total, status=206):
        super().__init__(data)
        self.status = status
        self.headers = {'Content-Range': f'bytes {start}-{start + len(data) - 1}/{total}', 'Content-Length': str(len(data))}
        self.read1 = mock.Mock(wraps=super().read1)


class ListenerInstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = b'synthetic approved data'
        self.asset = ('Qwen/test', 'a' * 40, 'fixture.gguf', 'checkpoints/fixture.gguf', len(self.data), hashlib.sha256(self.data).hexdigest())
        self.patch = mock.patch.multiple(download, ROOT=self.root, ASSETS=(self.asset,), MIN_FREE=0)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.ledger_path = self.root / 'ledger.json'
        self.ledger = download.load_ledger(self.ledger_path)

    def test_redirect_body_counted_without_network_and_closed(self):
        response = io.BytesIO(b'tiny redirect body')
        handler = download.HttpsOnly(self.ledger, self.ledger_path)
        handler.parent = mock.Mock()
        request = download.urllib.request.Request('https://example.invalid/pinned')
        request.timeout = 10
        handler.http_error_302(request, response, 302, 'Found', {'location': 'https://other.invalid/pinned', 'Content-Length': '18'})
        self.assertTrue(response.closed)
        self.assertEqual(self.ledger['received_redirect_body_bytes'], 18)
        self.assertEqual(self.ledger['redirect_charged_upper_bound'], 18)
        self.assertEqual(self.ledger['redirect_response_count'], 1)
        handler.parent.open.assert_called_once()

    def test_redirect_oversized_body_is_bounded_and_budget_retained(self):
        response = io.BytesIO(b'x' * (80 * 2**10))
        handler = download.HttpsOnly(self.ledger, self.ledger_path)
        with self.assertRaisesRegex(RuntimeError, 'length/bound mismatch'):
            handler.drain_redirect(response, {})
        self.assertEqual(response.tell(), 65537)
        self.assertEqual(self.ledger['redirect_charged_upper_bound'], 65537)
        self.assertEqual(self.ledger['received_redirect_body_bytes'], 65537)

    def test_redirect_cap_before_body_read(self):
        self.ledger['charged_payload_upper_bound'] = download.CAP - 2
        response = mock.Mock()
        handler = download.HttpsOnly(self.ledger, self.ledger_path)
        with self.assertRaisesRegex(RuntimeError, 'cap reached'):
            handler.drain_redirect(response, {'Content-Length': '3'})
        response.read.assert_not_called()

    def test_complete_range_full_hash_and_atomic_finalization(self):
        response = Response(self.data, 0, len(self.data))
        opener = mock.Mock()
        opener.open.return_value = response
        download.receive(self.asset, opener, self.ledger, self.ledger_path, 0, 0)
        self.assertEqual((self.root / self.asset[3]).read_bytes(), self.data)
        self.assertFalse((self.root / (self.asset[3] + '.part')).exists())
        saved = json.loads(self.ledger_path.read_text(encoding='utf-8'))
        self.assertEqual(saved['charged_payload_upper_bound'], len(self.data))
        self.assertEqual(saved['received_payload_bytes'], len(self.data))
        self.assertTrue(saved['files'][self.asset[3]]['verified'])

    def test_partial_resume_only_requests_remaining_bytes(self):
        part = self.root / (self.asset[3] + '.part')
        part.parent.mkdir(parents=True)
        part.write_bytes(self.data[:3])
        self.ledger['charged_payload_upper_bound'] = 3
        self.ledger['received_payload_bytes'] = 3
        opener = mock.Mock()
        opener.open.return_value = Response(self.data[3:], 3, len(self.data))
        download.receive(self.asset, opener, self.ledger, self.ledger_path, 0, 0)
        request = opener.open.call_args.args[0]
        self.assertEqual(request.get_header('Range'), f'bytes=3-{len(self.data) - 1}')
        self.assertEqual(self.ledger['charged_payload_upper_bound'], len(self.data))
        self.assertEqual((self.root / self.asset[3]).read_bytes(), self.data)

    def test_cap_stops_before_request(self):
        opener = mock.Mock()
        self.ledger['charged_payload_upper_bound'] = download.CAP - len(self.data) + 1
        with self.assertRaisesRegex(RuntimeError, 'network cap'):
            download.receive(self.asset, opener, self.ledger, self.ledger_path, 0, 0)
        opener.open.assert_not_called()

    def test_server_ignoring_range_stops_without_reading_payload(self):
        opener = mock.Mock()
        response = Response(self.data, 0, len(self.data), status=200)
        opener.open.return_value = response
        with mock.patch.object(download, 'RANGE', 4):
            with self.assertRaisesRegex(RuntimeError, 'did not honor'):
                download.receive(self.asset, opener, self.ledger, self.ledger_path, 0, 0)
        response.read1.assert_not_called()
        self.assertEqual(self.ledger['charged_payload_upper_bound'], 4)
        self.assertEqual(self.ledger['received_payload_bytes'], 0)

    def test_bad_existing_file_kept_without_http(self):
        path = self.root / self.asset[3]
        path.parent.mkdir(parents=True)
        path.write_bytes(b'user existing fixture')
        opener = mock.Mock()
        with self.assertRaisesRegex(RuntimeError, 'preserved'):
            download.receive(self.asset, opener, self.ledger, self.ledger_path, 0, 0)
        self.assertEqual(path.read_bytes(), b'user existing fixture')
        opener.open.assert_not_called()

    def test_failed_disk_reserve_before_request(self):
        opener = mock.Mock()
        with mock.patch.object(download.shutil, 'disk_usage', return_value=mock.Mock(free=100)):
            with self.assertRaisesRegex(RuntimeError, 'paused'):
                download.receive(self.asset, opener, self.ledger, self.ledger_path, 200, 0)
        opener.open.assert_not_called()

    def test_parallel_ranges_exact_bytes_and_bounded_staging(self):
        opener = mock.Mock()
        def respond(request, **kwargs):
            start, end = map(int, request.get_header('Range').removeprefix('bytes=').split('-'))
            return Response(self.data[start:end + 1], start, len(self.data))
        opener.open.side_effect = respond
        with mock.patch.object(download, 'RANGE', 4):
            download.listener_parallel.receive(download, self.asset, opener, self.ledger, self.ledger_path, 0, 0, workers=3)
        self.assertEqual((self.root / self.asset[3]).read_bytes(), self.data)
        self.assertEqual(self.ledger['charged_payload_upper_bound'], len(self.data))
        self.assertEqual(self.ledger['received_payload_bytes'], len(self.data))
        self.assertEqual(opener.open.call_count, 6)
        self.assertFalse(list((self.root / 'windows/cache/listener/segments').rglob('*.chunk')))

    def test_parallel_cap_stops_without_http(self):
        opener = mock.Mock()
        self.ledger['charged_payload_upper_bound'] = download.CAP
        with self.assertRaisesRegex(RuntimeError, 'network cap'):
            download.listener_parallel.receive(download, self.asset, opener, self.ledger, self.ledger_path, 0, 0, workers=3)
        opener.open.assert_not_called()

    def test_path_cannot_escape_project(self):
        with self.assertRaises(ValueError):
            download.destination('../outside')


if __name__ == '__main__':
    unittest.main(verbosity=2)
