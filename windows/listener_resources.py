"""Machine-wide memory admission and owned one-job offline CUDA build monitoring."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'lab'))
from atomic_audio import replace_file
from platform_runtime import process_options, system_memory, terminate_process


def memory():
    data = system_memory()
    if data.get('commit_scope') != 'machine':
        raise RuntimeError('Listener requires machine-wide GetPerformanceInfo commit counters')
    return {'physical_available': int(data['available']), 'commit_headroom': int(data['commit_available']),
            'commit_limit': int(data['commit_limit']), 'commit_used': int(data['commit_used']),
            'commit_source': data['commit_source'], 'commit_scope': data['commit_scope']}


def check_build():
    value = memory()
    if value['physical_available'] < 6 * 2**30 or value['commit_headroom'] < 4 * 2**30:
        raise RuntimeError('One-job build admission needs6GiB RAM /4GiB commit: ' + json.dumps(value))
    return value


def build(cmake, directory):
    directory = Path(directory).resolve()
    if directory != (ROOT / 'windows/build/listener-cuda').resolve():
        raise ValueError('Fresh Listener build must use the canonical project-local output folder')
    cache = ROOT / 'windows/cache/listener'
    cache.mkdir(parents=True, exist_ok=True)
    command = [str(cmake), '--build', str(directory), '--target', 'llama-mtmd-cli', '--parallel', '1']
    result = {'command': command, 'before': check_build(), 'samples': [], 'status': 'building'}
    destination = cache / 'build-memory-owned.json'
    with (cache / 'build.log').open('w', encoding='utf-8') as log:
        process = subprocess.Popen(command, cwd=str(ROOT), stdin=subprocess.DEVNULL, stdout=log,
                                   stderr=subprocess.STDOUT, **process_options())
        result['pid'] = process.pid
        try:
            while process.poll() is None:
                value = memory()
                result['samples'].append(value)
                temporary = destination.with_suffix('.json.part')
                temporary.write_text(json.dumps(result, indent=1), encoding='utf-8')
                replace_file(temporary, destination)
                if value['commit_headroom'] < 2 * 2**30 or value['physical_available'] < 4 * 2**30:
                    result['status'] = 'critical-floor-stop'
                    raise RuntimeError('Build critical floor2GiB commit /4GiB RAM reached; keeping objects')
                time.sleep(5)
            result['returncode'] = process.wait()
            result['status'] = 'done' if result['returncode'] == 0 else 'failed'
        finally:
            if process.poll() is None:
                terminate_process(process)
            result['returncode'] = process.wait(timeout=5)
            result['after'] = memory()
            temporary = destination.with_suffix('.json.part')
            temporary.write_text(json.dumps(result, indent=1), encoding='utf-8')
            replace_file(temporary, destination)
    print(json.dumps({'returncode': result['returncode'], 'status': result['status'], 'report': str(destination)}), flush=True)
    return result['returncode']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path)
    parser.add_argument('--cmake', type=Path)
    args = parser.parse_args()
    if args.build:
        if not args.cmake or not args.cmake.is_file():
            parser.error('--cmake must name the existing approved native compiler driver')
        return build(args.cmake, args.build)
    print(json.dumps(check_build()), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
