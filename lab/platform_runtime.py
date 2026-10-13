"""Native process, filesystem and local-network boundary for Windows Music Lab.

Only standard-library/Windows OS APIs are used. Linux callers retain their process
sessions and symlinks; Windows jobs use a process group and native directory junctions.
"""
from __future__ import annotations

import ctypes
import ipaddress
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import struct
import subprocess
import sys
import threading
import time
import urllib.parse

WINDOWS = os.name == "nt"
_PROCESS_CACHE = {}
_PROCESS_LOCK = threading.Lock()
_NETWORK_GUARD = False


def local_only():
    """Windows is offline by default; no cloud/upload API is enabled by the port."""
    return os.environ.get("RUACH_OFFLINE") == "1" or os.environ.get("WINDOWS_MUSIC_LAB_LOCAL_ONLY", "1" if WINDOWS else "0") != "0"


def require_network(operation="external download"):
    if local_only():
        raise ValueError(f"{operation} is disabled in local-only mode; install approved files locally first")


def is_loopback(host):
    host = str(host or "").strip("[]").lower()
    if host == "localhost":
        return True
    try:
        address = ipaddress.ip_address(host)
        if getattr(address, "ipv4_mapped", None):
            address = address.ipv4_mapped
        return address.is_loopback
    except ValueError:
        return False


def loopback_host(host):
    if not is_loopback(host):
        raise ValueError("LAB_HOST must be a loopback address (127.0.0.1 or ::1)")
    return host


def local_request_allowed(headers, peer, ports):
    """Reject DNS rebinding and cross-site calls, including legacy GET mutations."""
    if not is_loopback(peer):
        return False
    raw_host = headers.get("Host", "")
    try:
        parsed = urllib.parse.urlsplit("http://" + raw_host)
        if not is_loopback(parsed.hostname) or parsed.port not in ports:
            return False
        origin = headers.get("Origin", "")
        if origin:
            parsed = urllib.parse.urlsplit(origin)
            if parsed.scheme not in ("http", "https") or not is_loopback(parsed.hostname) or parsed.port not in ports:
                return False
        referer = headers.get("Referer", "")
        if referer and not origin:
            parsed = urllib.parse.urlsplit(referer)
            if not is_loopback(parsed.hostname) or parsed.port not in ports:
                return False
        return headers.get("Sec-Fetch-Site", "") != "cross-site" or bool(origin)
    except ValueError:
        return False


def install_local_network_guard():
    """A process-local audit guard; never edits firewall/network/system settings.

    Prevent Python network connections and DNS lookups outside loopback. Child
    inference processes receive Hugging Face offline flags separately. Download
    subprocess routes also call require_network before starting a command.
    """
    global _NETWORK_GUARD
    if not local_only() or _NETWORK_GUARD:
        return

    def audit(event, args):
        if event == "socket.getaddrinfo":
            host = args[0]
            if host is not None and not is_loopback(host):
                raise PermissionError("external DNS is disabled in local-only mode")
        elif event in ("socket.connect", "socket.sendto"):
            address = args[1] if event == "socket.connect" else args[-1]
            if isinstance(address, tuple) and not is_loopback(address[0]):
                raise PermissionError("external connections are disabled in local-only mode")
    sys.addaudithook(audit)
    _NETWORK_GUARD = True


def venv_python(root, artist=False):
    base = Path(root) / (".venv-art" if artist else ".venv")
    return base / ("Scripts/python.exe" if WINDOWS else "bin/python")


def site_packages(root, artist=False):
    base = Path(root) / (".venv-art" if artist else ".venv")
    if WINDOWS:
        return base / "Lib/site-packages"
    paths = sorted((base / "lib").glob("python*/site-packages"))
    return paths[-1] if paths else base / f"lib/python{sys.version_info.major}.{sys.version_info.minor}/site-packages"


def job_environment(root, env=None, artist=False):
    """Return a child-only environment; keep caches/temp inside the project."""
    root = Path(root).resolve()
    out = dict(os.environ if env is None else env)
    cache = root / "lab/cache"
    for key, suffix in (("HF_HOME", "huggingface"), ("TORCH_HOME", "torch"),
                        ("XDG_CACHE_HOME", "xdg"), ("CUDA_CACHE_PATH", "cuda")):
        out[key] = str(cache / suffix)
    for key in ("RUACH_GPU_MUTEX", "RUACH_WDDM_MEMORY_POLICY", "RUACH_FULL_GPU"):
        if key in os.environ:
            out.setdefault(key, os.environ[key])
    out["PYTHONIOENCODING"] = "utf-8"
    out["PYTHONUTF8"] = "1"
    out["WINDOWS_MUSIC_LAB_LOCAL_ONLY"] = "1" if local_only() else "0"
    if local_only():
        for key in tuple(out):
            if key.lower() in ("http_proxy", "https_proxy", "all_proxy"):
                out.pop(key)
        out["NO_PROXY"] = "localhost,127.0.0.1,::1"
        out.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", DIFFUSERS_OFFLINE="1",
                   HF_HUB_DISABLE_TELEMETRY="1", DO_NOT_TRACK="1", WANDB_MODE="offline",
                   DIFFUSERS_GGUF_CUDA_KERNELS="0")
    if WINDOWS:
        tmp = cache / "tmp"
        tmp.mkdir(parents=True, exist_ok=True)
        out.update(TEMP=str(tmp), TMP=str(tmp))
        packages = site_packages(root, artist=artist)
        candidates = [packages / "torch/lib"]
        candidates.extend(sorted((packages / "nvidia").glob("*/bin")))
        candidates.extend(sorted((packages / "nvidia").glob("*/lib")))
        candidates += [root / "toolchain/cuda-12.8.1/bin", root.parent / "toolchain/cuda-12.8.1/bin",
                       root / "toolchain/ffmpeg/bin"]
        out["PATH"] = os.pathsep.join(str(p) for p in candidates if p.is_dir()) + os.pathsep + out.get("PATH", "")
    return out


_DLL_HANDLES = []


def configure_runtime(root, artist=False):
    """Apply the same environment to a dedicated lab process, never the machine."""
    os.environ.update(job_environment(root, artist=artist))
    if WINDOWS and hasattr(os, "add_dll_directory"):
        for p in os.environ["PATH"].split(os.pathsep):
            if p and Path(p).is_dir():
                try:
                    _DLL_HANDLES.append(os.add_dll_directory(p))
                except OSError:
                    pass
    install_local_network_guard()


def process_options():
    if WINDOWS:
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW}
    return {"start_new_session": True}


def subprocess_flags():
    return process_options()


def terminate_process(process, timeout=5):
    """Stop a Popen that this caller owns; never accepts an arbitrary numeric PID.

    POSIX sessions must have been launched using process_options; otherwise only
    that child is stopped. Windows taskkill /T is scoped to the still-live child.
    """
    if process.poll() is not None:
        return process.returncode
    if WINDOWS:
        subprocess.run([str(Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32/taskkill.exe"),
                        "/PID", str(process.pid), "/T", "/F"], capture_output=True, timeout=timeout,
                       creationflags=subprocess.CREATE_NO_WINDOW)
    else:
        try:
            pgid = os.getpgid(process.pid)
            if pgid == process.pid:
                os.killpg(pgid, signal.SIGTERM)
            else:
                process.terminate()
        except ProcessLookupError:
            pass
    try:
        return process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        if not WINDOWS:
            try:
                if os.getpgid(process.pid) == process.pid:
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
            except ProcessLookupError:
                pass
        else:
            process.kill()
        return process.wait(timeout=timeout)


def pid_alive(pid):
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if not WINDOWS:
        try:
            os.kill(pid, 0)
            return True
        except PermissionError:
            return True
        except ProcessLookupError:
            return False
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.restype = ctypes.c_void_p
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        return ctypes.get_last_error() == 5     # protected process: alive, not ours to inspect
    code = ctypes.c_ulong()
    try:
        return bool(kernel.GetExitCodeProcess(ctypes.c_void_p(handle), ctypes.byref(code))) and code.value == 259
    finally:
        kernel.CloseHandle(ctypes.c_void_p(handle))


def process_details(pids):
    """Best-effort PID metadata, batched CIM on Windows; never presume unreadable is ours."""
    pids = sorted({int(p) for p in pids if str(p).isdigit() and int(p) > 0})
    if not pids:
        return {}
    if not WINDOWS:
        out = {}
        for pid in pids:
            try:
                cmd = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", "replace")
                out[pid] = {"exe": os.path.realpath(f"/proc/{pid}/exe"), "cmd": cmd}
            except OSError:
                pass
        return out
    key = tuple(pids)
    with _PROCESS_LOCK:
        old = _PROCESS_CACHE.get(key)
        if old and time.monotonic() - old[0] < 2:
            return old[1]
    query = " OR ".join("ProcessId=" + str(pid) for pid in pids)
    script = "[Console]::OutputEncoding=[Text.UTF8Encoding]::new(); Get-CimInstance Win32_Process -Filter '" + query + "' | Select-Object ProcessId,ExecutablePath,CommandLine,Name | ConvertTo-Json -Compress"
    try:
        done = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                              capture_output=True, encoding="utf-8", errors="replace", timeout=10,
                              creationflags=subprocess.CREATE_NO_WINDOW)
        data = json.loads(done.stdout) if done.returncode == 0 and done.stdout.strip() else []
        if isinstance(data, dict):
            data = [data]
        out = {int(r["ProcessId"]): {"exe": r.get("ExecutablePath") or "", "cmd": r.get("CommandLine") or "", "name": r.get("Name") or "?"} for r in data}
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        out = {}
    with _PROCESS_LOCK:
        _PROCESS_CACHE.clear()
        _PROCESS_CACHE[key] = (time.monotonic(), out)
    return out


def process_in_root(info, root):
    root = os.path.normcase(str(Path(root).resolve())).rstrip("/\\")
    exe = os.path.normcase(info.get("exe", ""))
    cmd = os.path.normcase(info.get("cmd", ""))
    return exe.startswith(root + os.sep) or root + os.sep in cmd or (root + "/" in cmd if WINDOWS else False)


def nvidia_smi():
    found = shutil.which("nvidia-smi")
    if found:
        return found
    if WINDOWS:
        for path in (Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32/nvidia-smi.exe",
                     Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "NVIDIA Corporation/NVSMI/nvidia-smi.exe"):
            if path.is_file():
                return str(path)
    return "nvidia-smi"


class _WindowsPerformanceInformation(ctypes.Structure):
    # psapi.h PERFORMANCE_INFORMATION: SIZE_T is pointer-width, DWORD is 32 bits.
    _fields_ = [("cb", ctypes.c_uint32)] + [(name, ctypes.c_size_t) for name in
        ("CommitTotal", "CommitLimit", "CommitPeak", "PhysicalTotal", "PhysicalAvailable",
         "SystemCache", "KernelTotal", "KernelPaged", "KernelNonpaged", "PageSize")] + [
        ("HandleCount", ctypes.c_uint32), ("ProcessCount", ctypes.c_uint32), ("ThreadCount", ctypes.c_uint32)]


class _WindowsMemoryStatus(ctypes.Structure):
    _fields_ = [("length", ctypes.c_uint32), ("load", ctypes.c_uint32)] + [(name, ctypes.c_uint64) for name in
        ("total", "available", "commit_limit", "commit_available", "virtual_total", "virtual_available", "extended")]


def _windows_performance_info():
    value = _WindowsPerformanceInformation()
    value.cb = ctypes.sizeof(value)
    # Resolve only from System32; no current-directory DLL search or subprocess.
    api = ctypes.WinDLL("psapi.dll", use_last_error=True, winmode=0x800)
    getter = api.GetPerformanceInfo
    getter.argtypes = [ctypes.POINTER(_WindowsPerformanceInformation), ctypes.c_uint32]
    getter.restype = ctypes.c_int
    if not getter(ctypes.byref(value), ctypes.sizeof(value)):
        raise OSError(ctypes.get_last_error(), "GetPerformanceInfo failed")
    if not value.PageSize or not value.PhysicalTotal or not value.CommitLimit:
        raise OSError("GetPerformanceInfo returned invalid memory counters")
    return value


def _windows_memory_status():
    value = _WindowsMemoryStatus()
    value.length = ctypes.sizeof(value)
    api = ctypes.WinDLL("kernel32.dll", use_last_error=True, winmode=0x800)
    getter = api.GlobalMemoryStatusEx
    getter.argtypes = [ctypes.POINTER(_WindowsMemoryStatus)]
    getter.restype = ctypes.c_int
    if not getter(ctypes.byref(value)):
        raise OSError(ctypes.get_last_error(), "GlobalMemoryStatusEx failed")
    return value


def system_memory():
    """Fast RAM and commit snapshot; all capacities in bytes.

    PSAPI CommitTotal/CommitLimit are machine-wide page counters. Never use free
    virtual address space or available physical RAM as a commit substitute. If
    PSAPI is unavailable, ullAvailPageFile is a conservative process commit bound
    (<= machine headroom), labelled explicitly; failure of both APIs raises.
    Microsoft definitions: https://learn.microsoft.com/en-us/windows/win32/api/psapi/ns-psapi-performance_information
    Fallback semantics: https://learn.microsoft.com/en-us/windows/win32/api/sysinfoapi/ns-sysinfoapi-memorystatusex
    """
    if WINDOWS:
        try:
            value = _windows_performance_info()
            page = value.PageSize
            limit, used = value.CommitLimit * page, value.CommitTotal * page
            return {"total": value.PhysicalTotal * page, "available": value.PhysicalAvailable * page,
                    "ram_source": "GetPerformanceInfo.PhysicalAvailable", "commit_limit": limit, "commit_used": used,
                    "commit_available": max(0, limit - used), "commit_source": "GetPerformanceInfo(machine-wide)",
                    "commit_scope": "machine", "page_size": page}
        except (OSError, AttributeError) as error:
            value = _windows_memory_status()   # failure here propagates: admission fails closed
            return {"total": value.total, "available": value.available, "ram_source": "GlobalMemoryStatusEx.ullAvailPhys",
                    "commit_limit": value.commit_limit, "commit_used": None,
                    "commit_available": max(0, min(value.commit_available, value.commit_limit)),
                    "commit_source": "GlobalMemoryStatusEx(process conservative bound)", "commit_scope": "process_bound",
                    "commit_error": str(error)}
    values = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        name, text = line.split(":", 1)
        values[name] = int(text.strip().split()[0]) * 1024
    return {"total": values["MemTotal"], "available": values.get("MemAvailable", values.get("MemFree", 0))}


def is_directory_link(path):
    if os.path.islink(path):
        return True
    try:
        return getattr(os.lstat(path), "st_reparse_tag", 0) == 0xA0000003
    except OSError:
        return False


def create_directory_link(target, link):
    """Junction on native Windows: no Developer Mode/elevation requirement."""
    if not WINDOWS:
        os.symlink(target, link, target_is_directory=True)
        return
    target, link = str(Path(target).resolve()), str(Path(link).absolute())
    if target.startswith("\\\\"):
        raise ValueError("directory relocation supports local drives; network shares are disabled")
    if os.path.lexists(link):
        raise FileExistsError(link)
    substitute = ("\\??\\" + target).encode("utf-16-le")
    printed = target.encode("utf-16-le")
    names = substitute + b"\0\0" + printed + b"\0\0"
    mount = struct.pack("<HHHH", 0, len(substitute), len(substitute) + 2, len(printed)) + names
    data = struct.pack("<IHH", 0xA0000003, len(mount), 0) + mount
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p]
    kernel.CreateFileW.restype = ctypes.c_void_p
    kernel.DeviceIoControl.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p, ctypes.c_void_p]
    os.mkdir(link)
    handle = kernel.CreateFileW(link, 0x40000000, 0, None, 3, 0x02200000, None)
    try:
        if handle in (None, ctypes.c_void_p(-1).value):
            raise ctypes.WinError(ctypes.get_last_error())
        count = ctypes.c_ulong()
        buffer = ctypes.create_string_buffer(data)
        if not kernel.DeviceIoControl(handle, 0x000900A4, buffer, len(data), None, 0, ctypes.byref(count), None):
            raise ctypes.WinError(ctypes.get_last_error())
    except Exception:
        if handle not in (None, ctypes.c_void_p(-1).value):
            kernel.CloseHandle(ctypes.c_void_p(handle))
            handle = None
        os.rmdir(link)             # our newly-created empty link directory only
        raise
    finally:
        if handle not in (None, ctypes.c_void_p(-1).value):
            kernel.CloseHandle(ctypes.c_void_p(handle))


def remove_directory_link(link):
    if not is_directory_link(link):
        raise ValueError("refusing to remove a directory that is not a link")
    if WINDOWS and getattr(os.lstat(link), "st_reparse_tag", 0) == 0xA0000003:
        os.rmdir(link)             # Windows removes a junction, never its contents
    else:
        os.unlink(link)


def replace_directory_link(target, link):
    if not WINDOWS:
        temp = Path(str(link) + ".link-part")
        create_directory_link(target, temp)
        os.replace(temp, link)
        return
    temp, backup = Path(str(link) + ".link-part"), Path(str(link) + ".link-old")
    if os.path.lexists(temp) or os.path.lexists(backup):
        raise FileExistsError("an earlier link transaction needs inspection")
    create_directory_link(target, temp)
    try:
        os.rename(link, backup)
        try:
            os.rename(temp, link)
        except Exception:
            os.rename(backup, link)
            raise
        remove_directory_link(backup)
    finally:
        if os.path.lexists(temp):
            remove_directory_link(temp)


def run_process(*args, input=None, capture_output=False, timeout=None, check=False, root=None, **kwargs):
    """subprocess.run equivalent with native UTF-8, env and owned-tree timeout cleanup."""
    if input is not None:
        if kwargs.get("stdin") is not None:
            raise ValueError("stdin and input cannot both be supplied")
        kwargs["stdin"] = subprocess.PIPE
    if capture_output:
        if kwargs.get("stdout") is not None or kwargs.get("stderr") is not None:
            raise ValueError("capture_output conflicts with stdout/stderr")
        kwargs.update(stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    for key, value in process_options().items():
        kwargs.setdefault(key, value)
    if root is not None:
        kwargs["env"] = job_environment(root, kwargs.get("env"))
    if kwargs.get("text") or kwargs.get("universal_newlines"):
        kwargs.setdefault("encoding", "utf-8")
        kwargs.setdefault("errors", "replace")
    with subprocess.Popen(*args, **kwargs) as process:
        try:
            stdout, stderr = process.communicate(input, timeout=timeout)
        except subprocess.TimeoutExpired as error:
            terminate_process(process)
            stdout, stderr = process.communicate()
            error.output, error.stderr = stdout, stderr
            raise
        except BaseException:
            terminate_process(process)
            raise
        result = subprocess.CompletedProcess(process.args, process.returncode, stdout, stderr)
        if check:
            result.check_returncode()
        return result


def read_json(path):
    with open(path, encoding="utf-8") as source:
        return json.load(source)


def write_json(path, value, **options):
    """Whole JSON transaction with closed handles before Windows replacement."""
    import tempfile
    path = Path(path)
    temp = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                prefix="." + path.name + "-", suffix=".part", dir=path.parent, delete=False) as output:
            temp = Path(output.name)
            json.dump(value, output, **options)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temp, path)
    finally:
        if temp is not None and temp.exists():
            temp.unlink()            # this transaction's own generated file only


def safe_component(value):
    """One filename on both native platforms; reject drive/ADS/traversal aliases."""
    import re
    value = str(value)
    if not value or value in (".", "..") or value[-1:] in (".", " ") or re.search(r'[<>:"/\\|?*\x00-\x1f]', value):
        raise ValueError("a single valid filename is required")
    if re.match(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", value, flags=re.IGNORECASE):
        raise ValueError("Windows device names are not valid filenames")
    return value


class GPUWaitCancelled(RuntimeError):
    """A queued GPU job was stopped before it acquired the hardware lease."""


class gpu_lease:
    """Cross-process GPU serialization, shared by the C++ Creator and lab workers.

    The launcher opts in through RUACH_GPU_MUTEX. Only the process/thread owning
    the actual child lifetime holds a lease: never acquire again in that child.
    Windows automatically abandons a mutex on owner death; the next job accepts
    WAIT_ABANDONED, records it and continues. No system settings are changed.
    """
    def __init__(self, gpu=0, job=None, waiting=None, cancelled=None, timeout=None):
        import re
        self.handle = None
        self.acquired = False
        self.abandoned = False
        self.job = job
        self.waiting = waiting
        self.cancelled = cancelled
        self.timeout = timeout
        self.thread = None
        configured = os.environ.get("RUACH_GPU_MUTEX", "")
        self.name = ""
        if WINDOWS and configured:
            gpu = int(gpu)
            if gpu < 0:
                raise ValueError("GPU index must be non-negative")
            self.name = f"Local\\WindowsMusicLab-GPU{gpu}" if configured == "1" else configured
            if re.fullmatch(r"Local\\WindowsMusicLab-GPU\d+", self.name):
                self.name = re.sub(r"GPU\d+$", "GPU" + str(gpu), self.name)
            if not re.fullmatch(r"Local\\WindowsMusicLab-[A-Za-z0-9_-]{1,96}", self.name):
                raise ValueError("RUACH_GPU_MUTEX must be a local Windows Music Lab mutex name")

    def _cancelled(self):
        return (self.cancelled is not None and self.cancelled()) or (self.job is not None and (self.job.get("cancel") or self.job.get("stop")))

    def __enter__(self):
        if self._cancelled():
            raise GPUWaitCancelled("GPU job stopped while queued")
        if not self.name:
            return self
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
        kernel.CreateMutexW.restype = ctypes.c_void_p
        kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        kernel.WaitForSingleObject.restype = ctypes.c_ulong
        kernel.ReleaseMutex.argtypes = [ctypes.c_void_p]
        self.kernel = kernel
        self.handle = kernel.CreateMutexW(None, False, self.name)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        self.thread = threading.get_ident()
        started, said = time.monotonic(), False
        try:
            while True:
                if self._cancelled():
                    raise GPUWaitCancelled("GPU job stopped while queued")
                status = kernel.WaitForSingleObject(self.handle, 250)
                if status in (0, 0x80):         # WAIT_OBJECT_0 or WAIT_ABANDONED
                    self.acquired, self.abandoned = True, status == 0x80
                    if self.job is not None:
                        self.job.update(status="running", gpu_mutex=self.name)
                        self.job.pop("waiting", None)
                        if self.abandoned:
                            self.job["gpu_mutex_abandoned"] = True
                    return self
                if status != 0x102:             # WAIT_TIMEOUT
                    raise ctypes.WinError(ctypes.get_last_error())
                if self.timeout is not None and time.monotonic() - started >= self.timeout:
                    raise TimeoutError("timed out waiting for the GPU lease")
                if self.job is not None:
                    self.job.update(status="queued", waiting="waiting for another local GPU job to finish")
                if not said and self.waiting is not None:
                    self.waiting("waiting for another local GPU job to finish")
                    said = True
        except BaseException:
            kernel.CloseHandle(ctypes.c_void_p(self.handle))
            self.handle = None
            raise

    def __exit__(self, *exc):
        if self.handle is not None:
            if threading.get_ident() != self.thread:
                raise RuntimeError("the GPU lease must be released by its owning thread")
            try:
                if self.acquired and not self.kernel.ReleaseMutex(self.handle):
                    raise ctypes.WinError(ctypes.get_last_error())
            finally:
                self.kernel.CloseHandle(ctypes.c_void_p(self.handle))
                self.handle = None
                self.acquired = False
        return False


def release_engine_for_gpu_job(port=None):
    """Release only the local idle engine's cached models under a held GPU lease.

    The full engine reports waiting_gpu separately from actual busy execution and
    services unload controls during its lease wait. Never uploads audio or keys.
    """
    import urllib.request
    port = int(port or os.environ.get("YUE2CPP_PORT", "41867"))
    url = f"http://127.0.0.1:{port}"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        for look in (0, 1):
            if look:
                time.sleep(3)
            with opener.open(url + "/hardware", timeout=5) as response:
                hardware = json.load(response)
            if hardware.get("busy") or int(hardware.get("loaded_bytes") or 0) < 256 * 2**20:
                return 0
        req = urllib.request.Request(url + "/unload", data=b"{}", method="POST", headers={"Content-Type":"application/json"})
        with opener.open(req, timeout=15) as response:
            result = json.load(response)
        freed = int(result.get("freed_mb") or 0) if result.get("applied") else 0
        if freed:
            time.sleep(1.5)
        return freed
    except (OSError, ValueError):
        return 0


def copy_directory_link(source, destination, source_tree, destination_tree):
    """Preserve POSIX link text; remap internal native junctions into a tree copy."""
    if not WINDOWS:
        os.symlink(os.readlink(source), destination, target_is_directory=True)
        return
    target = Path(os.path.realpath(source))
    try:
        target = Path(destination_tree) / target.relative_to(Path(source_tree).resolve())
    except ValueError:
        pass                            # an external local target stays external
    create_directory_link(target, destination)
