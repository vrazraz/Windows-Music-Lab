"""Native Windows training owner: durable status and scoped cooperative stop.

No shell, service installation or external network calls. The launched child is
owned by this supervisor even when the web UI restarts. A stop file lets the own
trainer checkpoint at its next safe step boundary; only this owned child can be
terminated when the grace period expires.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import time

from atomic_audio import replace_file
from platform_runtime import (GPUWaitCancelled, configure_runtime, gpu_lease, job_environment,
                              process_options, release_engine_for_gpu_job, terminate_process)


def write_state(path, value):
    part = path.with_suffix(".json.part")
    with part.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=1)
    replace_file(part, path)


def supervise(directory):
    directory = Path(directory).resolve()
    kit = Path(__file__).resolve().parent.parent
    configure_runtime(kit)
    launch = json.loads((directory / "native-launch.json").read_text(encoding="utf-8"))
    command = launch["command"]
    if not isinstance(command, list) or not command or not all(isinstance(part, str) for part in command):
        raise ValueError("native-launch.json must contain an argument list")
    state_path = directory / "native-process.json"
    state = {"supervisor_pid": os.getpid(), "status": "starting", "started": time.time()}
    write_state(state_path, state)
    stop = directory / "stop.requested"
    grace = max(0.1, float(launch.get("grace_seconds", 60)))
    process = None
    requested = None
    forced = False
    lease = gpu_lease(int(launch.get("env", {}).get("CUDA_VISIBLE_DEVICES", "0")), cancelled=stop.is_file)
    try:
        lease.__enter__()
        needed = int(launch.get("need_mb", 0))
        if needed:
            release_engine_for_gpu_job()
            import gpu_guard
            gpu_guard.check(int(launch["env"]["CUDA_VISIBLE_DEVICES"]), needed, kit)
        environment = job_environment(kit)
        environment.update(launch.get("env", {}))
        environment["RUACH_TRAIN_STOP_FILE"] = str(stop)
        process = subprocess.Popen(command, cwd=launch["cwd"], env=environment,
                                   stdin=subprocess.DEVNULL, **process_options())
        state.update(status="running", child_pid=process.pid)
        write_state(state_path, state)
        while process.poll() is None:
            if stop.is_file():
                requested = requested or time.monotonic()
                if time.monotonic() - requested >= grace:
                    forced = True
                    print("stop grace period expired; terminating the owned training process; the last completed checkpoint is retained", flush=True)
                    terminate_process(process, timeout=5)
                    break
            time.sleep(0.1)
        returncode = process.wait()
        if stop.is_file() and requested is None:
            requested = time.monotonic()
        state.update(status="stopped" if requested is not None else ("done" if returncode == 0 else "failed"),
                     returncode=returncode, forced=forced, ended=time.time())
        write_state(state_path, state)
        return 0 if requested is not None else returncode
    except GPUWaitCancelled:
        state.update(status="stopped", returncode=0, forced=False, ended=time.time(), error="stopped while waiting for the GPU")
        write_state(state_path, state)
        return 0
    except BaseException as error:
        if process is not None and process.poll() is None:
            terminate_process(process, timeout=5)
        state.update(status="failed", error=str(error), ended=time.time())
        write_state(state_path, state)
        raise
    finally:
        lease.__exit__(None, None, None)


if __name__ == "__main__":
    sys.exit(supervise(sys.argv[1]))
