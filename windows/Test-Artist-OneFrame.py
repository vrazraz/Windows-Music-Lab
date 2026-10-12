"""Exactly one approved SDXL512 frame via the production Artist API or worker.

Default --plan performs no GPU/API/model access. --run must only be invoked after
installation/download completion and the explicit execution go-ahead. A durable
claim prevents an uncertain HTTP result or rerun from generating another frame.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import socket
import subprocess
import sys
import time
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lab"))
import artist_sdxl
import platform_runtime as runtime
import gpu_guard

CACHE = ROOT / "windows/cache/artist-one-frame"
CLAIM = CACHE / "claim.json"
STUDIO_PORTS = (41868, 41871, 41872)
REQUEST = {"prompt": "A small neutral blue cube on a plain wooden table, studio lighting, clean background, no people, no text",
           "painter": "sdxl", "resolution": 512, "validation_profile": artist_sdxl.VALIDATION_PROFILE, "shapes": ["1:1"], "count": 1,
           "seed": 20261012, "preview": False,
           "sampling": {"steps": 12, "sampler": "dpmpp", "schedule": "simple", "cfg": 5.0}}


def plan():
    return {"request": dict(REQUEST), "frames": 1, "resolution": [512, 512], "offline": True,
            "available_ram_min_bytes": artist_sdxl.MIN_RAM_BYTES,
            "commit_headroom_min_bytes": artist_sdxl.MIN_COMMIT_BYTES,
            "gpu_requested_mb": 8000, "gpu_mutex_required": True,
            "claim_policy": "one durable claim; no automatic submission retry",
            "guard_reason": artist_sdxl.MEMORY_REASON, "memory_policy": artist_sdxl.validation_policy(),
            "offload_mode": "sequential", "submission_performed": False, "execution": "plan only; no submission", "existing_claim_blocks_execution": CLAIM.exists(),
            "standalone": {"command": "--run-standalone", "worker": "lab/artist_job.py", "interpreter": ".venv-art/Scripts/python.exe",
                           "ports_must_be_free": list(STUDIO_PORTS), "own_workers_must_be_stopped": True,
                           "gpu_policy": "aggregate WDDM, known-heavy check, 8000 MiB requested, shared parent-only lease",
                           "memory_guard_unchanged": True, "claim": "same claim.json for API and standalone"}}


def sha(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 ** 2), b""):
            result.update(block)
    return result.hexdigest()


def verify_model():
    manifest = json.loads((ROOT / "windows/full-art-models.json").read_text(encoding="utf-8"))["models"]
    selected = next(item for item in manifest if item["id"] == "sdxl-base-fp16")
    if selected["revision"] != "462165984030d82259a11f4367a4eed129e94a7b":
        raise RuntimeError("The approved SDXL revision changed")
    base = (ROOT / selected["directory"]).resolve()
    if not base.is_relative_to(ROOT.resolve()) or artist_sdxl.art_job.sdxl_path() != base:
        raise RuntimeError("Artist must select the approved SDXL folder in this worktree")
    for item in selected["files"]:
        file = (base / item["path"]).resolve()
        if not file.is_relative_to(base) or not file.is_file() or file.stat().st_size != item["size"] or sha(file) != item["sha256"]:
            raise RuntimeError("Approved model file is missing/partial/corrupt: " + item["path"])
    return {"revision": selected["revision"], "files": len(selected["files"]), "sha256_verified": True, "storage": artist_sdxl.validate_model_storage(base)}


def endpoint(port, path, body=None):
    url = f"http://127.0.0.1:{port}{path}"
    if not 1024 <= port <= 65535 or not path.startswith("/"):
        raise ValueError("Only the configured loopback API is allowed")
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="GET" if body is None else "POST")
    with urllib.request.urlopen(request, timeout=20) as response:
        if response.url != url:
            raise RuntimeError("The local endpoint redirected; stopped")
        return json.load(response)


def server_preflight(lab_port, engine_port, gpu):
    health = endpoint(lab_port, "/health")
    if not health.get("ok") or not health.get("local_only") or health.get("busy") or health.get("jobs"):
        raise RuntimeError("The local-only lab must be healthy and idle with no running/queued jobs")
    painters = endpoint(lab_port, "/artist/painters")
    execution = painters.get("execution") or {}
    expected_mutex = f"Local\\WindowsMusicLab-GPU{gpu}"
    if execution.get("gpu_mutex") != expected_mutex or not execution.get("gpu_handoff") or not execution.get("local_only"):
        raise RuntimeError("Production Artist must confirm local-only mode, the shared named GPU mutex and idle engine handoff")
    if not any(p.get("key") == "sdxl" and p.get("ready") for p in painters.get("painters", [])):
        raise RuntimeError("The approved local SDXL model is not ready")
    hardware = endpoint(engine_port, "/hardware")
    if hardware.get("busy") or hardware.get("waiting_gpu") or int(hardware.get("queued_jobs") or 0):
        raise RuntimeError("The engine must be idle with an empty queue")
    return {"local_only": True, "gpu_mutex": expected_mutex, "gpu_handoff": True}


def write_claim(value):
    runtime.write_json(CLAIM, value, ensure_ascii=False, indent=2)


def run_once(lab_port=41871, engine_port=41868, gpu=0, timeout=900):
    if CLAIM.exists():
        raise RuntimeError("An Artist one-frame claim already exists; no repeat submission is allowed. Inspect its outcome first")
    runtime.configure_runtime(ROOT)
    memory = artist_sdxl.preflight_memory()
    model = verify_model()
    server = server_preflight(lab_port, engine_port, gpu)
    # Model verification/HTTP reads can take time: recheck immediately before POST.
    memory = artist_sdxl.preflight_memory()
    CACHE.mkdir(parents=True, exist_ok=True)
    claim = {"status": "submitting", "started_unix": time.time(), "request": REQUEST,
             "memory_before": memory, "model": model, "server": server}
    with CLAIM.open("x", encoding="utf-8") as stream:
        json.dump(claim, stream, ensure_ascii=False, indent=2)
    try:
        queued = endpoint(lab_port, "/artist/draw", REQUEST)
        rid = queued.get("id")
        if not re.fullmatch(r"\d{8}-\d{6}-[0-9a-f]{4}", str(rid or "")):
            raise RuntimeError("Artist returned no verified run id; outcome uncertain, do not retry")
        claim.update(status="queued", run=rid)
        write_claim(claim)
        until = time.monotonic() + timeout
        while time.monotonic() < until:
            runs = endpoint(lab_port, "/artist/runs").get("runs", [])
            current = next((r for r in runs if r.get("id") == rid), None)
            if current is None:
                raise RuntimeError("The submitted Artist run disappeared; outcome uncertain, do not retry")
            if current.get("status") in ("failed", "stopped"):
                raise RuntimeError("Artist one-frame run failed: " + str(current.get("error") or current["status"]))
            if current.get("status") == "done":
                pictures = current.get("pictures") or []
                if len(pictures) != 1 or not pictures[0].get("kept"):
                    raise RuntimeError("Artist did not keep exactly one image")
                filename = str(pictures[0].get("file") or "")
                if not re.fullmatch(r"01-1x1-s20261012\.png", filename):
                    raise RuntimeError("Unexpected image filename")
                image = (ROOT / "artist" / rid / filename).resolve()
                if not image.is_relative_to((ROOT / "artist").resolve()) or not image.is_file():
                    raise RuntimeError("The generated image is not a local Artist file")
                with image.open("rb") as stream:
                    header = stream.read(24)
                if header[:8] != b"\x89PNG\r\n\x1a\n" or struct.unpack(">II", header[16:24]) != (512, 512):
                    raise RuntimeError("The generated PNG is not 512×512")
                result = {"status": "done", "frames": 1, "run": rid, "image": str(image), "sha256": sha(image),
                          "resolution": [512, 512], "steps": 12, "offload_mode": "sequential",
                          "validation_profile": artist_sdxl.VALIDATION_PROFILE, "memory_after": runtime.system_memory(),
                          "peak_gpu_gb": current.get("peak_gb"), "resources": current.get("resources", []), "runtime": current.get("took"),
                          "visual_inspection": "pending", "variants_lora_upscale": "not tested"}
                claim.update(result)
                write_claim(claim)
                return result
            time.sleep(1)
        endpoint(lab_port, "/artist/stop", {"id": rid})
        raise RuntimeError("The one-frame run exceeded its time budget; Stop was requested, no retry")
    except BaseException as error:
        if claim.get("run"):
            try:
                endpoint(lab_port, "/artist/stop", {"id": claim["run"]})
                claim["stop_requested"] = True
            except Exception as stop_error:
                claim["stop_error"] = str(stop_error)
        claim.update(status="failed_or_uncertain", error=str(error))
        write_claim(claim)
        raise



@contextmanager
def idle_ports(ports=STUDIO_PORTS):
    """Require and reserve all Studio/Writer loopback ports without listening.

    Exclusive Windows binds stay open through the one child lifetime. They also
    prevent an accidental Studio restart taking these ports during validation.
    """
    handles = []
    try:
        for port in ports:
            for family, address in ((socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")):
                handle = socket.socket(family, socket.SOCK_STREAM)
                handles.append(handle)
                if os.name == "nt":
                    handle.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                if family == socket.AF_INET6:
                    handle.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
                try:
                    handle.bind((address, int(port)))
                except OSError as error:
                    raise RuntimeError(f"Standalone requires free loopback port {port}; existing service was left untouched") from error
        yield {"ports": list(ports), "exclusive_reserved_without_listener": True}
    finally:
        for handle in handles:
            handle.close()


def process_inventory():
    """Read-only, bounded CIM query; return no command lines in persisted reports."""
    names = ("python.exe", "pythonw.exe", "py.exe", "yue-server.exe", "yue-train.exe", "llama-server.exe", "llama-cli.exe", "llama-mtmd-cli.exe", "whisper.exe")
    filter_text = " OR ".join("Name='" + name + "'" for name in names)
    script = ("$ErrorActionPreference='Stop'; [Console]::OutputEncoding=[Text.UTF8Encoding]::new(); "
              "$items=@(Get-CimInstance Win32_Process -Filter \"" + filter_text + "\" | "
              "Select-Object ProcessId,Name,ExecutablePath,CommandLine); ConvertTo-Json -InputObject $items -Compress")
    result = runtime.run_process(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                                 capture_output=True, text=True, timeout=20)
    if result.returncode != 0 or not result.stdout.strip():
        raise RuntimeError("Standalone cannot verify stopped workers; CIM inventory failed")
    items = json.loads(result.stdout)
    if not isinstance(items, list):
        raise RuntimeError("Standalone process inventory format is invalid")
    return items


def stopped_workers(snapshot=None):
    rows = process_inventory() if snapshot is None else snapshot
    blocked = []
    roots = (ROOT, ROOT.parent / "source")
    for row in rows:
        pid = int(row["ProcessId"])
        if pid in (os.getpid(), os.getppid()):
            continue
        info = {"exe": row.get("ExecutablePath") or "", "cmd": row.get("CommandLine") or ""}
        if not info["exe"] and not info["cmd"]:
            raise RuntimeError("Standalone cannot identify worker PID " + str(pid))
        if info["exe"]:
            info["exe"] = str(Path(info["exe"]).resolve())
        if any(runtime.process_in_root(info, root) for root in roots):
            blocked.append({"pid": pid, "name": str(row.get("Name") or "?")})
    if blocked:
        raise RuntimeError("Standalone requires stopped own Studio/Writer/ML workers: " + json.dumps(blocked))
    return {"own_workers": [], "inventory_verified": True}


def standalone_memory():
    memory = artist_sdxl.preflight_memory()
    if memory.get("commit_scope") != "machine" or memory.get("commit_source") != "GetPerformanceInfo(machine-wide)":
        raise RuntimeError("Standalone requires verified machine-wide GetPerformanceInfo commit accounting")
    return memory


def protocol(stdout):
    rows = []
    for line in stdout.splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return {"pictures": [row for row in rows if "n" in row],
            "resources": [row["resources"] for row in rows if isinstance(row.get("resources"), dict)],
            "done": [row for row in rows if row.get("done")]}


def verify_standalone_result(folder, stdout):
    data = protocol(stdout)
    pictures, resources, done = data["pictures"], data["resources"], data["done"]
    if len(done) != 1 or len(pictures) != 1:
        raise RuntimeError("Production worker must report exactly one done and one image")
    final, picture = done[0], pictures[0]
    expected = {"painter": "sdxl", "resolution": 512, "steps": 12,
                "offload_mode": "sequential", "validation_profile": artist_sdxl.VALIDATION_PROFILE}
    if any(final.get(key) != value for key, value in expected.items()):
        raise RuntimeError("Production worker completion profile differs from the approved one-frame request")
    if any(picture.get(key) != value for key, value in {"n": 1, "shape": "1:1", "seed": 20261012, "w": 512, "h": 512, "kept": True}.items()):
        raise RuntimeError("Production worker image seed/count/geometry differs from the approved request")
    required = ["before_import", "after_import", "after_load", "before_inference"] + ["step"] * 12 + ["after_delete"]
    if [row.get("stage") for row in resources] != required:
        raise RuntimeError("Production worker did not report all resource stages and exactly12 denoising steps")
    for row in resources:
        if row.get("offload_mode") != "sequential" or row.get("validation_profile") != artist_sdxl.VALIDATION_PROFILE or row.get("weight_dtype") != "float16":
            raise RuntimeError("Production worker resource profile changed")
        system = row.get("system") or {}
        if system.get("commit_scope") != "machine" or system.get("commit_source") != "GetPerformanceInfo(machine-wide)":
            raise RuntimeError("Production worker did not use machine-wide Windows commit telemetry")
        if row["stage"] in artist_sdxl.PHASE_GUARDS:
            artist_sdxl.preflight_memory(system, row["stage"])
    if [row.get("step") for row in resources if row.get("stage") == "step"] != list(range(1, 13)):
        raise RuntimeError("Production worker step sequence is incomplete")
    name = "01-1x1-s20261012.png"
    image = folder / name
    if picture.get("file") != name or list(folder.glob("*.png")) != [image] or not image.is_file():
        raise RuntimeError("Production worker did not keep precisely the approved single PNG")
    with image.open("rb") as stream:
        header = stream.read(24)
    if header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR" or struct.unpack(">II", header[16:24]) != (512, 512):
        raise RuntimeError("Production worker PNG bounds are not512x512")
    return {"status": "done", "frames": 1, "image": str(image), "sha256": sha(image), "pictures": pictures,
            "resolution": [512, 512], "steps": 12, "seed": 20261012, "offload_mode": "sequential",
            "validation_profile": artist_sdxl.VALIDATION_PROFILE, "resources": resources,
            "peak_gpu_gb": final.get("peak_gb"), "runtime": final.get("took"),
            "visual_inspection": "pending", "variants_lora_upscale": "not tested"}


def standalone_once(gpu=0, timeout=900):
    """Only the explicit --run-standalone action may create the durable claim."""
    if CLAIM.exists():
        raise RuntimeError("An Artist one-frame claim already exists; no repeat submission is allowed. Inspect its outcome first")
    if os.name != "nt" or gpu != 0:
        raise RuntimeError("Reviewed standalone validation requires native Windows GPU0")
    os.environ.update(WINDOWS_MUSIC_LAB_LOCAL_ONLY="1", RUACH_OFFLINE="1", RUACH_GPU_MUTEX="Local\\WindowsMusicLab-GPU0",
                      RUACH_WDDM_MEMORY_POLICY="aggregate", RUACH_FULL_GPU="0")
    runtime.configure_runtime(ROOT)
    interpreter = runtime.venv_python(ROOT, artist=True)
    worker = ROOT / "lab/artist_job.py"
    if not interpreter.is_file() or not worker.is_file():
        raise RuntimeError("Production Artist interpreter/worker is missing")
    artist_sdxl.validate_profile(REQUEST)
    standalone_memory()
    stopped_workers()
    model = verify_model()
    home = (ROOT / "artist").resolve()
    if home.parent != ROOT.resolve():
        raise RuntimeError("Standalone Artist output directory must remain inside this project")
    with idle_ports() as ports, runtime.gpu_lease(gpu, timeout=30) as lease:
        workers = stopped_workers()
        card = gpu_guard.check(gpu, need_mb=8000, root=ROOT)
        # Refresh after SHA/CIM/nvidia-smi, under the same lease as the child.
        memory = standalone_memory()
        if CLAIM.exists():
            raise RuntimeError("An Artist one-frame claim already exists; no repeat submission is allowed")
        CACHE.mkdir(parents=True, exist_ok=True)
        rid = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
        folder = home / rid
        claim = {"status": "starting", "mode": "standalone-production-worker", "started_unix": time.time(), "request": REQUEST,
                 "memory_before": memory, "model": model, "ports": ports, "workers": workers, "gpu_admission": card,
                 "gpu_mutex": "Local\\WindowsMusicLab-GPU0", "run": rid}
        with CLAIM.open("x", encoding="utf-8") as stream:
            json.dump(claim, stream, ensure_ascii=False, indent=2)
        record = {"id": rid, "prompt": REQUEST["prompt"], "painter": "sdxl", "resolution": 512, "shapes": ["1:1"],
                  "seed": 20261012, "count": 1, "created": time.time(), "status": "running", "of": 1,
                  "pictures": [], "validation_profile": artist_sdxl.VALIDATION_PROFILE, "validation_mode": "standalone"}
        process = None
        try:
            folder.mkdir(parents=True, exist_ok=False)
            runtime.write_json(folder / "ask.json", REQUEST, ensure_ascii=False, indent=2)
            runtime.write_json(folder / "run.json", record, ensure_ascii=False, indent=2)
            env = runtime.job_environment(ROOT, dict(os.environ, CUDA_VISIBLE_DEVICES=str(gpu), CUDA_DEVICE_ORDER="PCI_BUS_ID", ART_PAINTER="sdxl"), artist=True)
            logs = {"stdout": str(folder / "stdout.log"), "stderr": str(folder / "stderr.log")}
            claim.update(status="running", logs=logs)
            write_claim(claim)
            with (folder / "stdout.log").open("w", encoding="utf-8") as out, (folder / "stderr.log").open("w", encoding="utf-8") as err:
                process = subprocess.Popen([str(interpreter), str(worker), str(folder)], cwd=str(ROOT), env=env,
                                           stdout=out, stderr=err, text=True, encoding="utf-8", errors="replace", **runtime.process_options())
                try:
                    code = process.wait(timeout=timeout)
                except BaseException:
                    runtime.terminate_process(process)
                    raise
            stdout = (folder / "stdout.log").read_text(encoding="utf-8", errors="replace")
            if code != 0:
                raise RuntimeError("Production Artist worker exited with code " + str(code) + "; see its local stdout/stderr logs")
            result = verify_standalone_result(folder, stdout)
            result.update(run=rid, mode="standalone-production-worker", logs=logs, gpu_admission=card, memory_after=runtime.system_memory())
            record.update(status="done", pictures=result["pictures"], resources=result["resources"], took=result["runtime"], peak_gb=result["peak_gpu_gb"])
            runtime.write_json(folder / "run.json", record, ensure_ascii=False, indent=2)
            claim.update(result)
            write_claim(claim)
            return result
        except BaseException as error:
            if process is not None and process.poll() is None:
                runtime.terminate_process(process)
            saved = protocol((folder / "stdout.log").read_text(encoding="utf-8", errors="replace")) if (folder / "stdout.log").is_file() else {"resources": [], "pictures": []}
            claim.update(status="failed_or_uncertain", error=str(error), resources=saved["resources"], pictures=saved["pictures"],
                         child_started=process is not None, returncode=process.returncode if process is not None else None)
            record.update(status="failed", error=str(error), resources=saved["resources"], pictures=saved["pictures"])
            if folder.is_dir():
                runtime.write_json(folder / "run.json", record, ensure_ascii=False, indent=2)
            write_claim(claim)
            raise

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--run-standalone", action="store_true", help="run the same approved production worker without servers, only after explicit start permission")
    actions.add_argument("--run", action="store_true", help="submit exactly one frame only after explicit start permission")
    actions.add_argument("--plan", action="store_true", help="print the reviewed request without API/GPU/model access")
    parser.add_argument("--lab-port", type=int, default=41871)
    parser.add_argument("--engine-port", type=int, default=41868)
    parser.add_argument("--gpu", type=int, default=0, choices=[0])
    arguments = parser.parse_args()
    result = standalone_once(arguments.gpu) if arguments.run_standalone else run_once(arguments.lab_port, arguments.engine_port, arguments.gpu) if arguments.run else plan()
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()