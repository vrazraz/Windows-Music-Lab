"""Approved Writer artifact installer: stdlib, exact byte ledger and pinned source.

Artifact/cache bodies and explicit conservative allowances are charged. Historical
redirect bodies were not observed; provenance labels that uncertainty. Does not
execute model or vendor code. Source ZIP blobs are checked against official Git tree.
"""
import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import time
import uuid
import urllib.request
import urllib.error
import urllib.parse
import zipfile
from pathlib import Path, PurePosixPath, PureWindowsPath

PIN = "8345f333951c661d166b00e6f9362e553768f292"
REV = "bc640142c66e1fdd12af0bd68f40445458f3869b"
WEIGHT_BYTES = 2497280256
WEIGHT_SHA = "7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5"
LICENSE_BYTES = 11544
LICENSE_BLOB = "6f9739bb281a3d2ade8fb5f6dd6dde597a739c80"
CAP = 2800000000
GIB = 1024 ** 3


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".part")
    with temporary.open("w", encoding="utf8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    for attempt in range(25):
        try:
            temporary.replace(path)
            break
        except PermissionError:
            # A closed, atomic transaction can briefly race a Windows status reader.
            if attempt == 24:
                raise
            time.sleep(.02)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def git_blob(path):
    digest = hashlib.sha1()
    digest.update(b"blob " + str(path.stat().st_size).encode("ascii") + b"\0")
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def contained(root, path):
    path = path.resolve()
    if path == root or not path.is_relative_to(root):
        raise ValueError("artifact path leaves its project")
    return path


def memory():
    path = Path(__file__).resolve().parent.parent / "lab/platform_runtime.py"
    spec = importlib.util.spec_from_file_location("writer_platform_runtime", path)
    runtime = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runtime)
    data = runtime.system_memory()
    if data.get("commit_scope") != "machine":
        raise RuntimeError("Writer admission requires machine-wide GetPerformanceInfo counters")
    return {"physical_available": int(data["available"]),
            "commit_headroom": int(data["commit_available"]),
            "commit_limit": int(data["commit_limit"]), "commit_used": int(data["commit_used"]),
            "commit_source": data["commit_source"], "commit_scope": data["commit_scope"]}

def guard(root, pending, expected_growth=0, require_memory=False, memory_gib=(10, 8)):
    free = shutil.disk_usage(root).free
    if free - pending - expected_growth < 50 * GIB:
        raise RuntimeError(f"disk reserve guard: {free} free, {pending} pending, {expected_growth} growth; retain 50 GiB")
    result = {"disk_free": free, "pending_reserved_bytes": pending, "expected_growth_bytes": expected_growth}
    if require_memory:
        result.update(memory())
        if result["physical_available"] < memory_gib[0] * GIB or result["commit_headroom"] < memory_gib[1] * GIB:
            raise RuntimeError(f"memory guard: {result}")
    return result


class NoHeadRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def final_https_url(url, headers=None, timeout=30):
    """Resolve with HEAD only: no automatic redirect response body is drained."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoHeadRedirect())
    for hop in range(6):
        if urllib.parse.urlsplit(url).scheme != "https":
            raise RuntimeError("artifact redirect leaves HTTPS")
        request = urllib.request.Request(url, method="HEAD", headers={"Accept-Encoding": "identity", **(headers or {})})
        try:
            response = opener.open(request, timeout=timeout)
        except urllib.error.HTTPError as error:
            if error.code not in (301, 302, 303, 307, 308):
                raise
            response = error
        with response:
            status = response.status
            if status in (301, 302, 303, 307, 308):
                location = response.headers.get("Location")
                if not location:
                    raise RuntimeError("redirect has no location")
                url = urllib.parse.urljoin(url, location)
                continue
            if status in (200, 206):
                return url, hop
            raise RuntimeError("unexpected artifact HEAD status")
    raise RuntimeError("artifact has too many redirects")


class Ledger:
    def __init__(self, root, pending):
        self.root, self.pending = root, pending
        self.cache = contained(root, root / "windows/cache/writer")
        self.cache.mkdir(parents=True, exist_ok=True)
        self.path = self.cache / "network-ledger.json"
        self.data = json.loads(self.path.read_text(encoding="utf-8-sig")) if self.path.exists() else {
            "cap_bytes": CAP, "total_body_bytes": 0, "transfers": [], "artifacts": {}, "source_pin": PIN}
        if self.data["cap_bytes"] != CAP or self.data["source_pin"] != PIN:
            raise RuntimeError("ledger does not match the approved package")
        self.last_save = 0

    def save(self):
        self.data["updated"] = time.time()
        self.data["counted_actual_body_bytes"] = sum(int(t.get("body_bytes", 0)) for t in self.data["transfers"])
        self.data["conservative_extra_bytes"] = self.data["total_body_bytes"] - self.data["counted_actual_body_bytes"]
        atomic_json(self.path, self.data)
        self.last_save = time.monotonic()

    def get_curl(self, url, destination, expected_size=None, expected_sha=None, max_file_bytes=None, git_sha=None):
        destination = contained(self.root, destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            recorded = self.data["artifacts"].get(destination.relative_to(self.root).as_posix())
            checked_size = expected_size if expected_size is not None else (recorded["size"] if recorded else None)
            checked_sha = expected_sha if expected_sha is not None else (recorded["sha256"] if recorded else None)
            if checked_size is None and checked_sha is None and git_sha is None:
                raise RuntimeError("cached artifact lacks verification provenance")
            self.validate(destination, checked_size, checked_sha, git_sha)
            print(f"REUSE {destination.name}: verified, no download", flush=True)
            return destination
        partial = destination.with_name(destination.name + ".part")
        offset = partial.stat().st_size if partial.exists() else 0
        limit = expected_size or max_file_bytes
        if not limit or offset > limit:
            raise RuntimeError("partial exceeds expected artifact size")
        if expected_size is not None and offset == expected_size:
            self.validate(partial, expected_size, expected_sha, git_sha)
            partial.replace(destination)
            return destination
        guard(self.root, self.pending, limit-offset)
        future = 0
        if expected_size is None and destination.name == "llama-source.zip":
            model = self.root / "models/writer/Qwen3-4B-Q4_K_M.gguf"
            future = (0 if model.exists() else WEIGHT_BYTES) + LICENSE_BYTES
        available = CAP - self.data["total_body_bytes"] - future
        reserve = min(limit-offset, available)
        if reserve <= 0 or (expected_size is not None and reserve < expected_size-offset):
            raise RuntimeError("artifact cannot fit remaining approved network cap")
        entry = {"url": url, "file": destination.relative_to(self.root).as_posix(), "offset": offset,
                 "body_bytes": 0, "reserved_bytes": reserve, "status": "running-curl", "started": time.time()}
        self.data["transfers"].append(entry)
        self.data["total_body_bytes"] += reserve
        self.save()
        stderr_file = self.cache / (destination.name + ".curl.log")
        args = ["curl.exe", "--disable", "--fail", "--show-error", "--progress-bar",
                "--retry", "0", "--connect-timeout", "30", "--speed-time", "60", "--speed-limit", "1",
                "--proto", "=https", "--max-redirs", "0",
                "--noproxy", "*", "--max-filesize", str(reserve),
                "--output", str(partial), "--write-out",
                '{"body_bytes":%{size_download},"http":%{http_code},"exit":%{exitcode}}']
        if offset:
            args += ["--continue-at", str(offset)]
        process = None
        try:
            resolved, hops = final_https_url(url)
            entry["head_redirect_hops"] = hops
            entry["head_body_bytes"] = 0
            args.append(resolved)
            self.save()
            with stderr_file.open("wb") as error_handle:
                process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=error_handle,
                                           creationflags=subprocess.CREATE_NO_WINDOW)
                last = 0
                while process.poll() is None:
                    if time.monotonic()-last >= 5:
                        size = partial.stat().st_size if partial.exists() else offset
                        print(f"CURL {destination.name}: {size}/{limit}; reserved={reserve}", flush=True)
                        guard(self.root, self.pending)
                        last = time.monotonic()
                    time.sleep(.2)
                output, _ = process.communicate(timeout=10)
            metrics = json.loads(output.decode("utf8"))
            actual = int(metrics["body_bytes"])
            if actual < 0 or actual > reserve:
                raise RuntimeError("curl body counter violates transfer reservation")
            self.data["total_body_bytes"] += actual - reserve
            entry.update(body_bytes=actual, reserved_bytes=0, http=int(metrics["http"]), curl_exit=process.returncode)
            self.save()
            if process.returncode:
                raise RuntimeError(f"curl failed code {process.returncode}; partial kept; see {stderr_file.name}")
            if int(metrics["http"]) not in (200, 206):
                raise RuntimeError("GET unexpectedly redirected; no automatic follow; body counted; partial kept")
            self.validate(partial, expected_size, expected_sha, git_sha)
            partial.replace(destination)
            entry["status"] = "verified"
            self.data["artifacts"][destination.relative_to(self.root).as_posix()] = {
                "size": destination.stat().st_size, "sha256": sha256(destination),
                "expected_sha256": expected_sha, "git_blob_sha1": git_sha,
                "counted_body_bytes": actual}
            self.save()
            return destination
        except BaseException as error:
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            entry.update(status="failed-curl", error=str(error), finished=time.time())
            # Missing metrics leaves the full reservation charged: no silent cap reset.
            self.save()
            raise

    def get(self, url, destination, expected_size=None, expected_sha=None, max_file_bytes=None, git_sha=None):
        return self.get_curl(url, destination, expected_size, expected_sha, max_file_bytes, git_sha)

    @staticmethod
    def validate(path, size=None, digest=None, git_sha=None):
        if size is not None and path.stat().st_size != size:
            raise RuntimeError(f"incorrect size: {path.name}")
        if digest is not None and sha256(path) != digest:
            raise RuntimeError(f"incorrect SHA256: {path.name}; kept unchanged")
        if git_sha is not None and git_blob(path) != git_sha:
            raise RuntimeError(f"incorrect Git blob: {path.name}; kept unchanged")


def safe_archive_name(value, prefix):
    if "\\" in value or "\0" in value or PureWindowsPath(value).drive:
        raise ValueError("unsafe ZIP path")
    raw = PurePosixPath(value)
    if raw.is_absolute() or any(p in ("", ".", "..") for p in value.rstrip("/").split("/")):
        raise ValueError("ZIP traversal")
    parts = raw.parts
    if not parts or parts[0] != prefix:
        raise ValueError("unexpected source ZIP root")
    relative = PurePosixPath(*parts[1:]).as_posix() if len(parts) > 1 else ""
    for part in parts:
        if re.search(r'[<>:"|?*\x00-\x1f]', part) or part != part.rstrip(" ."):
            raise ValueError("invalid Windows file name")
        if re.match(r"^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", part, re.I):
            raise ValueError("reserved Windows file name")
    return relative


def source(ledger):
    root = ledger.root
    commit_file = ledger.get(f"https://api.github.com/repos/ggml-org/llama.cpp/git/commits/{PIN}",
                             ledger.cache / "llama-source-commit.json", max_file_bytes=1024 * 1024)
    commit = json.loads(commit_file.read_text(encoding="utf8"))
    if commit.get("sha") != PIN:
        raise RuntimeError("official commit does not match pin")
    tree_file = ledger.get("https://api.github.com/repos/ggml-org/llama.cpp/git/trees/" + commit["tree"]["sha"] + "?recursive=1",
                          ledger.cache / ("llama-source-tree-" + commit["tree"]["sha"] + ".json"), max_file_bytes=4 * 1024 * 1024)
    tree = json.loads(tree_file.read_text(encoding="utf8"))
    if tree.get("sha") != commit["tree"]["sha"] or tree.get("truncated"):
        raise RuntimeError("official tree is truncated or does not match pin")
    blobs = {}
    for entry in tree["tree"]:
        if entry["type"] == "blob":
            if entry["mode"] not in ("100644", "100755"):
                raise RuntimeError(f"source tree contains unsupported mode {entry['mode']}: {entry['path']}")
            blobs[entry["path"]] = entry
        elif entry["type"] != "tree":
            raise RuntimeError("source tree contains a submodule or unsupported entry")
    target = contained(root, root / "vendor/llama.cpp")
    proof = target / "source-pin.json"
    if target.exists():
        if not proof.is_file():
            raise RuntimeError("existing vendor source has no approved provenance; preserved")
        proof_data = json.loads(proof.read_text(encoding="utf8"))
        if proof_data.get("revision") != PIN or proof_data.get("verified_git_tree") != tree["sha"]:
            raise RuntimeError("source provenance does not match pinned tree")
        for name, item in blobs.items():
            file = contained(root, target / name)
            current = target / name
            while current != target.parent:
                status = current.lstat()
                if stat.S_ISLNK(status.st_mode) or getattr(status, "st_file_attributes", 0) & 0x400:
                    raise RuntimeError("source has a symlink or Windows reparse point")
                current = current.parent
            Ledger.validate(file, item["size"], git_sha=item["sha"])
        for directory, folders, names in os.walk(target):
            # The Listener's independently owned generated build is never a source input.
            if Path(directory) == target and "build" in folders:
                folders.remove("build")
            for name in names:
                relative = (Path(directory) / name).relative_to(target).as_posix()
                if relative not in blobs and relative != "source-pin.json":
                    raise RuntimeError("untracked source input is present: " + relative)
        excluded = "; explicit generated build subtree excluded" if (target / "build").exists() else ""
        print("SOURCE REUSE: all pinned Git source blobs verified" + excluded, flush=True)
        return
    archive = ledger.get(f"https://codeload.github.com/ggml-org/llama.cpp/zip/{PIN}",
                         ledger.cache / "llama-source.zip", max_file_bytes=302708200)
    guard(root, ledger.pending, sum(item["size"] for item in blobs.values()))
    work = ledger.cache / ("source-extract-" + uuid.uuid4().hex)
    work.mkdir()
    prefix = "llama.cpp-" + PIN
    seen, case_seen = set(), set()
    try:
        with zipfile.ZipFile(archive) as zipped:
            for info in zipped.infolist():
                relative = safe_archive_name(info.filename, prefix)
                mode = info.external_attr >> 16
                kind = stat.S_IFMT(mode)
                if info.is_dir():
                    if kind not in (0, stat.S_IFDIR):
                        raise RuntimeError("ZIP directory has invalid mode")
                    continue
                if not relative or kind not in (0, stat.S_IFREG):
                    raise RuntimeError("source ZIP contains a symlink/device/non-file")
                if relative.casefold() in case_seen:
                    raise RuntimeError("source ZIP duplicate or case collision")
                case_seen.add(relative.casefold())
                item = blobs.get(relative)
                if item is None or info.file_size != item["size"]:
                    raise RuntimeError(f"archive file differs from pinned tree: {relative}")
                if mode and mode & 0o777 != int(item["mode"], 8) & 0o777:
                    raise RuntimeError(f"archive file mode differs: {relative}")
                path = contained(root, work / relative)
                path.parent.mkdir(parents=True, exist_ok=True)
                with zipped.open(info) as incoming, path.open("xb") as outgoing:
                    shutil.copyfileobj(incoming, outgoing, 1024 * 1024)
                Ledger.validate(path, item["size"], git_sha=item["sha"])
                seen.add(relative)
        if seen != set(blobs):
            raise RuntimeError(f"source archive omits {len(set(blobs)-seen)} pinned Git blobs")
        proof_data = {"revision": PIN, "tag": "v0.6.0", "verified_git_tree": tree["sha"],
                      "verified_blob_count": len(blobs), "source_file_bytes": sum(i["size"] for i in blobs.values()),
                      "archive_sha256": sha256(archive), "publisher_archive_sha256": None,
                      "verification": "every Git blob SHA1, size and mode; contained regular ZIP entries",
                      "verified_at": time.time(), "fabricated_git_head": False}
        atomic_json(work / "source-pin.json", proof_data)
        target.parent.mkdir(parents=True, exist_ok=True)
        work.replace(target)
        ledger.data["source_provenance"] = proof_data
        ledger.save()
        print(json.dumps(proof_data, ensure_ascii=False), flush=True)
    finally:
        if work.exists():
            shutil.rmtree(work)


def models(ledger):
    parent = contained(ledger.root, ledger.root / "models/writer")
    from writer_ranges import receive
    receive(ledger, parent / "Qwen3-4B-Q4_K_M.gguf", WEIGHT_BYTES, WEIGHT_SHA)
    ledger.get(f"https://huggingface.co/Qwen/Qwen3-4B-GGUF/resolve/{REV}/LICENSE",
               parent / "LICENSE-Qwen3.txt", LICENSE_BYTES, git_sha=LICENSE_BLOB)
    atomic_json(ledger.cache / "model-proof.json", {
        "model_revision": REV, "model_bytes": WEIGHT_BYTES, "model_sha256": WEIGHT_SHA,
        "license_bytes": LICENSE_BYTES, "license_git_blob_sha1": LICENSE_BLOB,
        "license_sha256": sha256(parent / "LICENSE-Qwen3.txt"), "verified_at": time.time()})


def main():
    cli = argparse.ArgumentParser()
    cli.add_argument("stage", choices=("preflight", "preflight-files", "preflight-build", "source", "models"))
    cli.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    cli.add_argument("--pending-bytes", type=int, default=0)
    args = cli.parse_args()
    root = args.root.resolve()
    # File transfers/hash validation need little memory; compile and inference differ.
    limits = (6, 4) if args.stage == "preflight-build" else (10, 8)
    print(json.dumps(guard(root, args.pending_bytes,
                          require_memory=args.stage in ("preflight", "preflight-build"),
                          memory_gib=limits)), flush=True)
    if args.stage.startswith("preflight"):
        return
    ledger = Ledger(root, args.pending_bytes)
    if args.stage == "source":
        source(ledger)
    else:
        models(ledger)


if __name__ == "__main__":
    main()
