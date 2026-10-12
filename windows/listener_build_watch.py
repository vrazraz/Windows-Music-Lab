"""Live native memory guard for the one coordinated, already running Listener build."""
import argparse
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'lab'))
from atomic_audio import replace_file
from platform_runtime import process_options, system_memory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid', required=True, type=int)
    parser.add_argument('--parent', required=True, type=int)
    args = parser.parse_args()
    script = f"Get-CimInstance Win32_Process -Filter 'ProcessId={args.pid}' | Select-Object ProcessId,ParentProcessId,CommandLine | ConvertTo-Json -Compress"
    snapshot = subprocess.run(['powershell.exe', '-NoProfile', '-Command', script], capture_output=True,
                              text=True, encoding='utf-8', check=True, **process_options())
    data = json.loads(snapshot.stdout)
    command = data['CommandLine']
    allowed = [str(ROOT / 'vendor/llama.cpp/build'), str(ROOT / 'windows/build/listener-cuda')]
    if (data['ParentProcessId'] != args.parent or '--target llama-mtmd-cli --parallel 1' not in command or
            not any('--build ' + folder in command for folder in allowed)):
        raise RuntimeError('Refusing to watch/stop a build outside the exact authorized identity')
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x1000 | 0x100000, False, args.pid)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    cache = ROOT / 'windows/cache/listener/build-memory.json'
    result = {'pid': args.pid, 'parent': args.parent, 'command': command, 'samples': 0,
              'commit_floor': 2 * 2**30, 'physical_floor': 4 * 2**30,
              'minimum_commit_headroom': None, 'minimum_physical_available': None, 'status': 'watching'}
    try:
        while kernel.WaitForSingleObject(handle, 0) == 258:
            memory = system_memory()
            if memory.get('commit_scope') != 'machine':
                raise RuntimeError('Guard requires machine-wide GetPerformanceInfo commit')
            commit, physical = int(memory['commit_available']), int(memory['available'])
            result['samples'] += 1
            for name, value in [('commit_headroom', commit), ('physical_available', physical)]:
                key = 'minimum_' + name
                result[key] = value if result[key] is None else min(value, result[key])
            result.update(last_commit_headroom=commit, last_physical_available=physical,
                          commit_source=memory['commit_source'], time=time.time())
            if commit < result['commit_floor'] or physical < result['physical_floor']:
                if kernel.WaitForSingleObject(handle, 0) == 258:
                    stopped = subprocess.run(['taskkill.exe', '/PID', str(args.pid), '/T', '/F'],
                                             capture_output=True, text=True, **process_options())
                    result.update(status='critical-floor-stop', taskkill_returncode=stopped.returncode)
                break
            temporary = cache.with_suffix('.json.part')
            temporary.write_text(json.dumps(result, indent=1), encoding='utf-8')
            replace_file(temporary, cache)
            time.sleep(5)
        if result['status'] == 'watching':
            result['status'] = 'owned-build-ended'
    finally:
        kernel.CloseHandle(handle)
        temporary = cache.with_suffix('.json.part')
        temporary.write_text(json.dumps(result, indent=1), encoding='utf-8')
        replace_file(temporary, cache)
    print(json.dumps(result), flush=True)
    return 1 if result['status'] == 'critical-floor-stop' else 0


if __name__ == '__main__':
    sys.exit(main())
