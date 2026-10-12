"""HERESY 1102: the DAW bridge (Viktor, 02.10.2026). Two ways out of the studio, and only two: the mixed
track as it is, or the whole take handed to the user's own DAW, where whatever happens next happens outside
the studio. Nothing comes back in: the studio does not import a DAW's project.

REAPER first, Waveform second; others by pull request. This part finds which of them the studio's own machine
has. A DAW on another computer (the browser on a laptop, the studio on a server) cannot be seen from here: the
page lets the user name it.

    GET /daw     the DAWs known to the bridge, which are on this machine, where, which version"""
import os, platform, re, shutil
from pathlib import Path

KNOWN = [
    {"id": "reaper", "name": "REAPER", "by": "Cockos", "state": "first",
     "paths": ["/opt/REAPER/reaper", "~/opt/REAPER/reaper", "/usr/local/bin/reaper"], "which": ["reaper"],
     "licence": "60 days of evaluation with every function, then a licence: $60 for personal use or a small business",
     "install": "reaper.fm/download.php → the Linux x86_64 tarball → unpack it and run ./install-reaper.sh (it goes to /opt/REAPER)"},
    {"id": "waveform", "name": "Waveform", "by": "Tracktion", "state": "second",
     "paths": ["/usr/bin/Waveform15", "/usr/bin/Waveform14", "/opt/Waveform15/Waveform15", "/opt/Waveform14/Waveform14"],
     "which": ["Waveform15", "Waveform14"],                 # HERESY 1139: 14 at least (it opens DAWproject); 13 is not supported
     "licence": "Waveform Free 14 or newer: free, no track or export limits; it opens the studio's DAWproject (File > Import Other > Import a DAWproject file). Waveform 13 is not supported",
     "install": "tracktion.com/products/waveform-free → the .deb of Waveform 14 for Linux → sudo apt install ./waveform14_*.deb"},
    {"id": "bitwig", "name": "Bitwig Studio", "by": "Bitwig", "state": "DAWproject",
     "paths": ["/opt/bitwig-studio/bitwig-studio", "/var/lib/flatpak/exports/bin/com.bitwig.BitwigStudio",
               "~/.local/share/flatpak/exports/bin/com.bitwig.BitwigStudio"], "which": ["bitwig-studio"],   # HERESY 1148: the Flatpak too
     "licence": "30 days without limits after signing up, then Essentials $99, Producer $199 or Studio $399 (bitwig.com, 03.10.2026); opens the studio's DAWproject: the mix, the stems, the score as notes, the sections as markers",
     "install": "bitwig.com/download: the Ubuntu .deb (sudo apt install ./bitwig-studio-*.deb) or the Flatpak"},
]


def _windows_paths(d):
    """Discover conventional native installations without launching a DAW."""
    roots = [Path(p) for p in dict.fromkeys(os.environ.get(key, "")
             for key in ("ProgramW6432", "ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA")) if p]
    candidates = []
    patterns = {
        "reaper": ("REAPER*/reaper.exe", "Programs/REAPER*/reaper.exe"),
        "waveform": ("Tracktion/Waveform*/Waveform*.exe", "Waveform*/Waveform*.exe",
                     "Programs/Tracktion/Waveform*/Waveform*.exe"),
        "bitwig": ("Bitwig Studio*/Bitwig Studio.exe", "Bitwig Studio/*/Bitwig Studio.exe",
                   "Programs/Bitwig Studio*/Bitwig Studio.exe"),
    }
    for root in roots:
        for pattern in patterns.get(d["id"], ()):
            if root.is_dir():
                candidates.extend(sorted(root.glob(pattern), reverse=True))
    if d["id"] == "reaper" and os.environ.get("APPDATA"):
        candidates.append(Path(os.environ["APPDATA"]) / "REAPER" / "reaper.exe")
    return candidates


def _found(d):
    paths = _windows_paths(d) if os.name == "nt" else d["paths"]
    for p in paths:
        p = os.path.expanduser(p)
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    for w in d["which"]:
        p = shutil.which(w)
        if p:
            return p
    return ""


def _version(d, path):
    """Read from the install itself, not by starting the program (a DAW may open a window)."""
    try:
        if d["id"] == "reaper":
            first = (Path(os.path.realpath(path)).parent / "whatsnew.txt").read_text(errors="replace").splitlines()[0]
            m = re.match(r"v?(\d+\.\d+\S*)", first.strip())
            return m.group(1) if m else ""
        if d["id"] == "waveform":                      # the .deb's version, else the number in the program's name
            if os.name == "nt":
                for folder in Path(path).parents:
                    m = re.fullmatch(r"Waveform\s*(\d{1,2})", folder.name, re.I)
                    if m:
                        return m.group(1)
                return ""                              # Waveform64.exe is an architecture, not version 64
            m = re.search(r"(\d+)$", os.path.basename(path))
            status = Path("/var/lib/dpkg/status")
            if status.is_file() and m:
                block = re.search(r"Package: waveform" + m.group(1) + r"\n(?:.+\n)*?Version: (\S+)", status.read_text(errors="replace"))
                if block:
                    return block.group(1)
            return m.group(1) if m else ""
        if d["id"] == "bitwig" and os.name == "nt":
            m = re.search(r"Bitwig Studio[ /\\-]+(\d+(?:\.\d+)+)", str(path), re.I)
            return m.group(1) if m else ""
    except (OSError, IndexError):
        return ""
    return ""


def detect():
    out = []
    windows_install = {
        "reaper": "https://www.reaper.fm/download.php — native Windows installer or your existing portable install",
        "waveform": "https://www.tracktion.com/products/waveform-free — native Windows release, version 14 or newer for DAWproject",
        "bitwig": "https://www.bitwig.com/download/ — native Windows installer",
    }
    for d in KNOWN:
        path = _found(d)
        item = {k: d[k] for k in ("id", "name", "by", "state", "licence", "install")}
        if os.name == "nt":
            item["install"] = windows_install[d["id"]]
        item.update(here=bool(path), path=path, version=_version(d, path) if path else "")
        if d["id"] == "waveform" and item["version"].isdigit() and int(item["version"]) < 14:
            item.update(here=False, state="unsupported", reason="Waveform 14 or newer is required for DAWproject")
        out.append(item)
    return {"daws": out, "host": platform.node()}
