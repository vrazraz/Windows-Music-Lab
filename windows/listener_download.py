"""Budgeted public Listener data download. No model imports, binaries or cloud credentials."""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import time
import threading
import urllib.error
import urllib.parse
import urllib.request
import listener_parallel

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lab"))
from atomic_audio import replace_file
CAP = 6_300_000_000
MIN_FREE = 50 * 2**30
RANGE = 16 * 2**20
CHUNK = 2**20
LEDGER_LOCK = threading.RLock()
LANG_PIN = '89b785438c8901d4635e42f50480ba5985a1bbf1'
PROJ_PIN = '658a1c70e91733330bcad348eead24bb4d15d9eb'
BASE_PIN = '4728b48bcd588a84f0353426515f27f5db911d8a'
BASE = 'checkpoints/Qwen2.5-Omni-7B-GGUF/'
ASSETS = (
    ('ggml-org/Qwen2.5-Omni-7B-GGUF', LANG_PIN, 'Qwen2.5-Omni-7B-Q4_K_M.gguf',
     BASE + 'Qwen2.5-Omni-7B-Q4_K_M.gguf', 4_683_072_384,
     '09883dff531dc56923a041c9c99c7c779e26ffde32caa83adeeb7502ec3b50fe'),
    ('mradermacher/Qwen2.5-Omni-7B-GGUF', PROJ_PIN, 'Qwen2.5-Omni-7B.mmproj-Q8_0.gguf',
     BASE + 'mradermacher/Qwen2.5-Omni-7B.mmproj-Q8_0.gguf', 1_548_488_608,
     '858f1ff0dab23c9139a20a3ef44cdeff85fd392c401ffcf436fe647d3496fdea'),
    ('Qwen/Qwen2.5-Omni-7B', BASE_PIN, 'LICENSE', BASE + 'LICENSE.Qwen.Apache-2.0', 11_343,
     '8d5eb5f806d01e8f5ea2c5a52f7d68ebc54b196b1cfbe1cd5dfa4b94e482a9c6'),
    ('ggml-org/Qwen2.5-Omni-7B-GGUF', LANG_PIN, 'README.md', BASE + 'README.ggml-org.md', 471,
     'e7411584ea811a7e153c11b531977f098e90e488503b904fccaa3dc52c7c7c33'),
    ('mradermacher/Qwen2.5-Omni-7B-GGUF', PROJ_PIN, 'README.md', BASE + 'mradermacher/README.mradermacher.md', 3_764,
     'e9e1bda88620153be5f14809a3fd585d4ad91739ce5a5ff60c1d85ff172a3039'),
)


def destination(relative):
    root = ROOT.resolve()
    path = (root / relative).resolve()
    if root not in path.parents:
        raise ValueError('Listener destination escaped its project')
    return path


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(4 * CHUNK), b''):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path, value):
    with LEDGER_LOCK:
        temporary = path.with_suffix(path.suffix + '.tmp')
        with temporary.open('w', encoding='utf-8', newline='\n') as stream:
            json.dump(value, stream, indent=1)
            stream.flush()
            os.fsync(stream.fileno())
        replace_file(temporary, path)


@contextmanager
def download_lock(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as stream:
        stream.seek(0)
        if not stream.read(1):
            stream.write(b'0')
            stream.flush()
        stream.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            if os.name == 'nt':
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def charged_http_bodies(ledger):
    # Historical allowance is explicitly an assumption, not measured redirect traffic.
    return (ledger['charged_payload_upper_bound'] + ledger.get('historical_redirect_allowance_bytes', 0)
            + ledger.get('redirect_charged_upper_bound', 0))


class HttpsOnly(urllib.request.HTTPRedirectHandler):
    max_redirections = 2
    max_repeats = 1
    maximum_body = 64 * 2**10

    def __init__(self, ledger, ledger_path):
        self.ledger, self.ledger_path = ledger, ledger_path

    def redirect_request(self, request, fp, code, msg, headers, newurl):
        if urllib.parse.urlsplit(newurl).scheme != 'https':
            raise ValueError('Listener download redirect is not HTTPS')
        return super().redirect_request(request, fp, code, msg, headers, newurl)

    def drain_redirect(self, response, headers):
        length = headers.get('Content-Length')
        length = int(length) if length and str(length).isdigit() else None
        if length is not None and length > self.maximum_body:
            raise RuntimeError('Redirect body exceeds the64KiB transport bound')
        reserved = self.maximum_body + 1 if length is None else length
        with LEDGER_LOCK:
            if charged_http_bodies(self.ledger) + reserved > CAP:
                raise RuntimeError('Listener6.3GB HTTP-body cap reached before redirect body read')
            self.ledger['redirect_charged_upper_bound'] = self.ledger.get('redirect_charged_upper_bound', 0) + reserved
            self.ledger['redirect_response_count'] = self.ledger.get('redirect_response_count', 0) + 1
            write_json(self.ledger_path, self.ledger)
        data = response.read(self.maximum_body + 1)
        with LEDGER_LOCK:
            self.ledger['received_redirect_body_bytes'] = self.ledger.get('received_redirect_body_bytes', 0) + len(data)
            write_json(self.ledger_path, self.ledger)
        if len(data) > self.maximum_body or (length is not None and len(data) != length):
            raise RuntimeError('Redirect body length/bound mismatch; reserved budget retained')

    def http_error_302(self, request, response, code, message, headers):
        # urllib's default handler drains fp.read() invisibly. Keep its redirect-loop rules,
        # but count/bound that body explicitly before opening the next HTTPS response.
        location = headers.get('location') or headers.get('uri')
        if not location:
            return None
        newurl = urllib.parse.urljoin(request.full_url, location)
        try:
            redirected = self.redirect_request(request, response, code, message, headers, newurl)
            if redirected is None:
                return None
            visited = getattr(request, 'redirect_dict', {})
            if visited.get(newurl, 0) >= self.max_repeats or len(visited) >= self.max_redirections:
                raise RuntimeError('Listener redirect hop/repetition bound reached')
            redirected.redirect_dict = request.redirect_dict = visited
            visited[newurl] = visited.get(newurl, 0) + 1
            self.drain_redirect(response, headers)
        finally:
            response.close()
        return self.parent.open(redirected, timeout=request.timeout)

    http_error_301 = http_error_303 = http_error_307 = http_error_308 = http_error_302


def disk_gate(remaining, pending_core, additional_ai):
    free = shutil.disk_usage(ROOT).free
    reserve = MIN_FREE + pending_core + additional_ai + remaining
    if free < reserve:
        raise RuntimeError(f'Listener paused: free={free:,} B; need={reserve:,} B '
                           '(50 GiB preserved + pending core + future AI + remaining Listener).')
    return free


def remaining_bytes():
    remaining = 0
    for _, _, _, relative, size, _ in ASSETS:
        path = destination(relative)
        if path.exists():
            continue
        part = path.with_suffix(path.suffix + '.part')
        offset = part.stat().st_size if part.is_file() else 0
        if offset > size:
            raise RuntimeError(f'Existing partial file is too large, preserved: {part}')
        remaining += size - offset - listener_parallel.staged_bytes(sys.modules[__name__], relative, offset, size)
    return remaining


def load_ledger(path):
    if path.is_file():
        value = json.loads(path.read_text(encoding='utf-8'))
        if value.get('schema') != 1 or value.get('cap_bytes') != CAP or value.get('scope') != 'listener-q4-pinned-v1':
            raise RuntimeError('Existing Listener ledger scope/cap mismatch; it was preserved')
        if not 0 <= value.get('charged_payload_upper_bound', -1) <= CAP:
            raise RuntimeError('Invalid Listener byte ledger; preserved')
        for key in ('historical_redirect_allowance_bytes', 'redirect_charged_upper_bound', 'received_redirect_body_bytes'):
            if not isinstance(value.get(key, 0), int) or value.get(key, 0) < 0:
                raise RuntimeError('Invalid redirect accounting; preserved')
        if charged_http_bodies(value) > CAP:
            raise RuntimeError('Combined HTTP-body planning budget exceeds cap; preserved')
        return value
    return {'schema': 1, 'scope': 'listener-q4-pinned-v1', 'cap_bytes': CAP,
            'expected_artifact_bytes': sum(asset[4] for asset in ASSETS),
            'charged_payload_upper_bound': 0, 'received_payload_bytes': 0, 'files': {}}


def receive(asset, opener, ledger, ledger_path, pending_core, additional_ai):
    repo, revision, name, relative, size, expected = asset
    path = destination(relative)
    if path.exists():
        if not path.is_file() or path.stat().st_size != size or sha256(path) != expected:
            raise RuntimeError(f'Existing artifact differs from pinned size/hash; preserved: {path}')
        ledger['files'][relative] = {'size': size, 'sha256': expected, 'verified': True}
        write_json(ledger_path, ledger)
        print(f'Verified existing: {relative}', flush=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_suffix(path.suffix + '.part')
    offset = part.stat().st_size if part.is_file() else 0
    if offset > size:
        raise RuntimeError(f'Existing partial file exceeds pinned size; preserved: {part}')
    url = f'https://huggingface.co/{repo}/resolve/{revision}/{urllib.parse.quote(name)}'
    while offset < size:
        disk_gate(remaining_bytes(), pending_core, additional_ai)
        end = min(size, offset + RANGE) - 1
        requested = end - offset + 1
        if charged_http_bodies(ledger) + requested > CAP:
            raise RuntimeError('Listener 6.3 GB network cap reached; no further request made')
        # Reserve the whole response before opening it. Interrupted/failed requests are not refunded.
        # This conservatively covers bytes read by HTTP/TLS buffering but not returned to Python.
        ledger['charged_payload_upper_bound'] += requested
        ledger['last_request'] = {'destination': relative, 'offset': offset, 'end': end}
        write_json(ledger_path, ledger)
        request = urllib.request.Request(url, headers={
            'Range': f'bytes={offset}-{end}', 'Accept-Encoding': 'identity',
            'Cache-Control': 'no-cache', 'User-Agent': 'WindowsMusicLab-ListenerPinnedInstaller/1'})
        with opener.open(request, timeout=45) as response:
            if response.status == 206:
                content_range = response.headers.get('Content-Range', '')
                if content_range != f'bytes {offset}-{end}/{size}':
                    raise RuntimeError(f'Unexpected Content-Range: {content_range}')
            elif response.status == 200 and offset == 0 and requested == size:
                pass
            else:
                raise RuntimeError(f'HTTP {response.status} did not honor the pinned byte range; stopped before reading body')
            length = response.headers.get('Content-Length')
            if length and int(length) != requested:
                raise RuntimeError('Unexpected HTTP payload length; stopped before reading body')
            with part.open('ab') as output:
                left = requested
                while left:
                    data = response.read1(min(CHUNK, left)) if hasattr(response, 'read1') else response.read(min(CHUNK, left))
                    if not data:
                        raise RuntimeError(f'Incomplete HTTP range; partial retained: {relative}')
                    ledger['received_payload_bytes'] += len(data)
                    output.write(data)
                    left -= len(data)
                    offset += len(data)
                os.fsync(output.fileno())
        ledger['files'][relative] = {'size': size, 'sha256': expected, 'partial_bytes': offset, 'verified': False}
        write_json(ledger_path, ledger)
        if offset == size or offset % (256 * CHUNK) < RANGE:
            print(f'{relative}: {offset:,}/{size:,} B; charged {ledger["charged_payload_upper_bound"]:,}/{CAP:,} B', flush=True)
    print(f'Checking full SHA256: {relative}', flush=True)
    if sha256(part) != expected:
        raise RuntimeError(f'Full SHA256 mismatch; partial preserved and never loaded: {part}')
    os.rename(part, path)  # Windows refuses to overwrite a concurrently created final file.
    ledger['files'][relative] = {'size': size, 'sha256': expected, 'verified': True}
    write_json(ledger_path, ledger)
    print(f'SHA256 verified: {relative}', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--download', action='store_true')
    parser.add_argument('--verify', action='store_true')
    parser.add_argument('--pending-core-bytes', type=int, default=0)
    parser.add_argument('--additional-ai-reserve-bytes', type=int, default=3 * 2**30)
    args = parser.parse_args()
    if min(args.pending_core_bytes, args.additional_ai_reserve_bytes) < 0:
        parser.error('reserves must not be negative')
    ledger_path = destination('windows/cache/listener/network-ledger.json')
    ledger = load_ledger(ledger_path)
    print(json.dumps({'free_disk_bytes': shutil.disk_usage(ROOT).free,
                      'remaining_listener_bytes': remaining_bytes(), 'ledger': ledger}, indent=1), flush=True)
    if args.verify:
        for _, _, _, relative, size, expected in ASSETS:
            path = destination(relative)
            if not path.is_file() or path.stat().st_size != size or sha256(path) != expected:
                raise RuntimeError(f'Pinned Listener artifact not verified: {path}')
        print('All five pinned Listener files verified.', flush=True)
    if not args.download:
        return 0
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with download_lock(ledger_path.parent / 'download.lock'):
        ledger = load_ledger(ledger_path)
        disk_gate(remaining_bytes(), args.pending_core_bytes, args.additional_ai_reserve_bytes)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), HttpsOnly(ledger, ledger_path))
        for asset in ASSETS:
            listener_parallel.receive(sys.modules[__name__], asset, opener, ledger, ledger_path, args.pending_core_bytes, args.additional_ai_reserve_bytes)
        ledger['completed'] = time.strftime('%Y-%m-%d %H:%M:%S')
        write_json(ledger_path, ledger)
        print('Listener pinned data download completed; inference is not yet verified.', flush=True)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError) as error:
        print(f'Listener installer stopped: {error}', file=sys.stderr, flush=True)
        sys.exit(1)
