"""Portable, local file primitives for notebooks, collections and DAW exports.

No external dependencies. Resolve paths before opening anything, including on
POSIX when handling a backup or manifest originally made on Windows.
"""
import json
import os
import re
import uuid
from pathlib import Path, PureWindowsPath

_RESERVED = re.compile(r"^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", re.I)
_INVALID = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def valid_component(value):
    return (isinstance(value, str) and bool(value) and not value.startswith(".")
            and not _INVALID.search(value) and value == value.rstrip(" .")
            and not _RESERVED.match(value))


def local_child(root, name):
    if not valid_component(name):
        raise ValueError("invalid local file name")
    root = Path(root).resolve()
    path = (root / name).resolve()
    if not path.is_relative_to(root) or path == root:
        raise ValueError("path leaves its local folder")
    return path


def manifest_file(root, value):
    """A local relative file; reject absolute, drive, traversal and link escapes."""
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ValueError("invalid manifest path")
    win = PureWindowsPath(value)
    value = value.replace("\\", "/")
    parts = value.split("/")
    if win.drive or win.root or value.startswith("/") or any(p in ("", ".", "..") for p in parts):
        raise ValueError("manifest path must be relative without traversal")
    if any(_INVALID.search(p) or _RESERVED.match(p) or p != p.rstrip(" .") for p in parts):
        raise ValueError("invalid manifest file name")
    root = Path(root).resolve()
    path = root.joinpath(*parts).resolve()
    if not path.is_relative_to(root) or path == root:
        raise ValueError("manifest path leaves the take")
    return path


def read_json(path):
    with Path(path).open(encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path, value):
    """Replace only after closing the new file: Windows cannot replace open files."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".part")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=1, allow_nan=False)
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def filename(value, limit=80):
    value = _INVALID.sub("_", str(value or "")).strip(" ._")[:limit].rstrip(" .")
    if not value:
        value = "take"
    if _RESERVED.match(value):
        value = "_" + value
    return value


def sources_of(take):
    """Mix plus the newest stem set for each mode; never trust a manifest's paths."""
    take = Path(take)
    mix = next((manifest_file(take, name) for name in ("audio.wav", "audio.flac", "audio.mp3")
                if manifest_file(take, name).is_file()), None)
    if mix is None:
        raise FileNotFoundError("take has no audio (audio.wav, .flac or .mp3)")
    sources = [("Mix", "mix", mix)]
    newest = {}
    for manifest in sorted(take.glob("derived/stems-*/manifest.json")):
        manifest = manifest_file(take, manifest.relative_to(take).as_posix())
        value = read_json(manifest)
        mode = str(value.get("mode") or "vocals")
        if mode not in newest or str(value.get("created") or "") >= str(newest[mode].get("created") or ""):
            newest[mode] = value
    for mode in sorted(newest):
        value = newest[mode]
        for item in value.get("files", []):
            path = manifest_file(take, item["path"])
            if path.is_file():
                kind = str(item.get("name") or path.stem)
                label = kind.capitalize() + ("" if mode == "vocals" else f" ({mode})")
                sources.append((label, kind, path))
    return sources