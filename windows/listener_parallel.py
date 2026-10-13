"""Bounded parallel HTTPS ranges for the fixed Listener package; no automatic retries."""
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
import hashlib
import os
from pathlib import Path
import re
import threading
import urllib.parse
import urllib.request


def segment_folder(module, relative):
    digest = hashlib.sha256(relative.encode('utf-8')).hexdigest()[:16]
    return module.destination('windows/cache/listener/segments/' + digest)


def staged_bytes(module, relative, prefix, size):
    folder = segment_folder(module, relative)
    total = 0
    for path in folder.glob('*'):
        match = re.fullmatch(r'(\d+)-(\d+)\.(chunk|partial)', path.name)
        if not match or not path.is_file():
            continue
        start, end = map(int, match.groups()[:2])
        if prefix <= start <= end < size:
            try:
                total += min(path.stat().st_size, end - start + 1)
            except FileNotFoundError:
                pass  # Controller just appended and retired this range; ignoring is conservative.
    return min(total, size - prefix)


def receive(module, asset, opener, ledger, ledger_path, pending_core, additional_ai, workers=6):
    workers = max(1, min(6, workers))
    repo, revision, name, relative, size, expected = asset
    path = module.destination(relative)
    if path.exists():
        return module.receive(asset, opener, ledger, ledger_path, pending_core, additional_ai)
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_suffix(path.suffix + '.part')
    offset = part.stat().st_size if part.is_file() else 0
    if offset > size:
        raise RuntimeError(f'Existing partial too large; preserved: {part}')
    folder = segment_folder(module, relative)
    folder.mkdir(parents=True, exist_ok=True)
    url = f'https://huggingface.co/{repo}/resolve/{revision}/{urllib.parse.quote(name)}'
    lock = module.LEDGER_LOCK
    origin = offset
    count = (size - origin + module.RANGE - 1) // module.RANGE
    completed = {}
    submitted = 0
    copied = 0
    failure = None

    def transfer(index):
        start = origin + index * module.RANGE
        end = min(size, start + module.RANGE) - 1
        chunk = folder / f'{start}-{end}.chunk'
        partial = folder / f'{start}-{end}.partial'
        if chunk.is_file():
            if chunk.stat().st_size != end - start + 1:
                raise RuntimeError(f'Invalid staged size, preserved: {chunk}')
            return index, chunk
        current = partial.stat().st_size if partial.is_file() else 0
        if current > end - start + 1:
            raise RuntimeError(f'Invalid partial range, preserved: {partial}')
        actual_start = start + current
        requested = end - actual_start + 1
        if requested:
            with lock:
                module.disk_gate(module.remaining_bytes(), pending_core, additional_ai)
                if module.charged_http_bodies(ledger) + requested > module.CAP:
                    raise RuntimeError('Listener 6.3 GB network cap reached; no further request made')
                ledger['charged_payload_upper_bound'] += requested
                ledger['last_request'] = {'destination': relative, 'offset': actual_start, 'end': end, 'parallel': workers}
                module.write_json(ledger_path, ledger)
            request = urllib.request.Request(url, headers={
                'Range': f'bytes={actual_start}-{end}', 'Accept-Encoding': 'identity',
                'Cache-Control': 'no-cache', 'User-Agent': 'WindowsMusicLab-ListenerPinnedInstaller/1'})
            received = 0
            try:
                with opener.open(request, timeout=45) as response:
                    if response.status == 206:
                        content_range = response.headers.get('Content-Range', '')
                        if content_range != f'bytes {actual_start}-{end}/{size}':
                            raise RuntimeError(f'Unexpected Content-Range: {content_range}')
                    elif response.status == 200 and actual_start == 0 and requested == size:
                        pass
                    else:
                        raise RuntimeError(f'HTTP {response.status} did not honor range; no body read')
                    length = response.headers.get('Content-Length')
                    if length and int(length) != requested:
                        raise RuntimeError('Unexpected Content-Length; no body read')
                    with partial.open('ab') as output:
                        left = requested
                        while left:
                            data = response.read(min(module.CHUNK, left))
                            if not data:
                                raise RuntimeError('Incomplete HTTP range; partial retained; no automatic retry')
                            output.write(data)
                            left -= len(data)
                            received += len(data)
                        output.flush()
                        os.fsync(output.fileno())
            finally:
                with lock:
                    ledger['received_payload_bytes'] += received
                    module.write_json(ledger_path, ledger)
        os.rename(partial, chunk)
        return index, chunk

    with ThreadPoolExecutor(max_workers=max(1, min(6, workers))) as pool:
        pending = {}
        with part.open('ab') as output:
            while copied < count:
                # At most one six-range window staged/in flight; never stage an entire model.
                while failure is None and submitted < count and submitted < copied + workers:
                    future = pool.submit(transfer, submitted)
                    pending[future] = submitted
                    submitted += 1
                if not pending:
                    break
                done, _ = wait(pending, return_when=FIRST_COMPLETED)
                for future in done:
                    pending.pop(future)
                    try:
                        index, chunk = future.result()
                        completed[index] = chunk
                    except BaseException as error:
                        failure = error
                while copied in completed:
                    chunk = completed.pop(copied)
                    with chunk.open('rb') as source:
                        for data in iter(lambda: source.read(module.CHUNK), b''):
                            output.write(data)
                            offset += len(data)
                    output.flush()
                    os.fsync(output.fileno())
                    chunk.unlink()  # Only our completed, copied range file in the checked project cache.
                    copied += 1
                    with lock:
                        ledger['files'][relative] = {'size': size, 'sha256': expected, 'partial_bytes': offset, 'verified': False}
                        module.write_json(ledger_path, ledger)
                    if offset == size or offset % (256 * module.CHUNK) < module.RANGE:
                        print(f'{relative}: {offset:,}/{size:,} B; charged {ledger["charged_payload_upper_bound"]:,}/{module.CAP:,} B', flush=True)
                if failure is not None and not pending:
                    break
    if failure is not None:
        raise failure
    if offset != size:
        raise RuntimeError('Listener range controller did not complete the pinned file')
    print(f'Checking full SHA256: {relative}', flush=True)
    if module.sha256(part) != expected:
        raise RuntimeError(f'Full SHA256 mismatch; partial preserved and never loaded: {part}')
    os.rename(part, path)
    ledger['files'][relative] = {'size': size, 'sha256': expected, 'verified': True}
    module.write_json(ledger_path, ledger)
    print(f'SHA256 verified: {relative}', flush=True)
