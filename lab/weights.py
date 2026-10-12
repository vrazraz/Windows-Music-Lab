"""HERESY 1289 (Viktor 10.10.2026: «И нужно в Engine добавить докачку моделей и LoRA»): the Engine's Models card over
heresy/fetch-heresy.sh, the one list of what the studio needs beside itself: its pins, its sizes checked file by file, a
download cut short going on from where it stopped, a second try after half a minute. The lab runs it and keeps its words.

    GET  /weights               the last whole run's verdicts, part by part (the install's own run too: fetch-heresy.sh keeps
                                them in tmp/fetch-heresy.list), the extras here or not, a run under way and its words
    POST /weights/check         fetch-heresy.sh --check: what is here and what is missing; nothing is downloaded
    POST /weights/fetch {…}     one run at a time, on the user's word (the page has said the size): {"part": "missing"}
                                everything the install brings that is not here, {"part": "loras"} one part of it, or one
                                extra: {"backbone": "BF16"}, {"listener": "Q8_0"}, {"artwork": "q4"}, {"trainer": "int8"}

A test page (?scope=…) checks but fetches nothing: the lab refuses. New LoRAs reach the engine at once; new backbones,
decoders and sliders at its next start (it reads them when it starts), which the card says."""
import json
import collections
import shutil
import platform_runtime as runtime
import os
import re
import subprocess
import threading
import time
from pathlib import Path

# what the install brings, part by part (fetch-heresy.sh --only NAME): what a fetch of the whole part takes, measured on the
# Forge 10.10.2026 (HERESY 1290: the extras come converted, from goldhub/Ruach_Studio_Models_v2: nothing is made here any more)
PARTS = {"extras": "1.3 GB", "whisper": "3.1 GB", "stems": "1.0 GB", "upscale": "0.2 GB", "loras": "2.3 GB"}   # HERESY 1292: du -sb, decimal

OMNI = "checkpoints/Qwen2.5-Omni-7B-GGUF/"
PROJ = OMNI + "mradermacher/Qwen2.5-Omni-7B.mmproj-Q8_0.gguf"
MUSE = "artwork/Krea-2-Muse/museByStableYogi_v35{}Extended.gguf"
# HERESY 1297: the prompt writer by its shards' index (_here checks every shard it names), not by its config.json, which comes
# first: a fetch cut short left the config and one shard on Viktor's laptop, and the card said «here»
KREA = ["artwork/Krea-2-Turbo/text_encoder/model.safetensors", "artwork/Krea-2-Turbo/vae/diffusion_pytorch_model.safetensors",
        "artwork/nsfw-filter/model.safetensors", "artwork/Qwen3-4B-Instruct-2507/model.safetensors.index.json"]
# HERESY 1323 (Viktor 10.10.2026: «Забирай 2512 тоже в Студию»; «как альтернативу для менее мощных карт бери смело … Q6_K + Lightning…
# Для 16 ГБ — Q4_K_M»; on Qwen-Image-2.1: «мы предупреждаем пользователя по этому поводу»): the Qwen painters, as artist.py's
# qwen_ready() wants them; the sizes from the pinned file lists (Qwen/Qwen-Image-2512 25468b9: its parts 16.8 GB, the GGUF 13.2 and
# 16.8, Lightning 0.85; Qwen/Qwen-Image-2.1 d26bb61: 33.1)
Q2512 = "artwork/Qwen-Image-2512/"
Q2512_PARTS = [Q2512 + "model_index.json", Q2512 + "transformer/config.json", Q2512 + "text_encoder/model.safetensors.index.json",
               Q2512 + "vae/diffusion_pytorch_model.safetensors", Q2512 + "lightning/Qwen-Image-2512-Lightning-8steps-V1.0-bf16.safetensors"]
QWEN21 = ["artwork/Qwen-Image-2.1/model_index.json", "artwork/Qwen-Image-2.1/transformer/diffusion_pytorch_model.safetensors.index.json",
          "artwork/Qwen-Image-2.1/text_encoder/model.safetensors.index.json", "artwork/Qwen-Image-2.1/vae/diffusion_pytorch_model.safetensors"]
# the extras, each only when asked for, with fetch-heresy.sh's own sizes and notes; a variant is here when all its files are
EXTRAS = [
    {"name": "backbone", "label": "Backbone", "restart": True,
     "what": "M-A-P's YuE2 as GGUF (Serveurperso/YuE2-GGUF): Compute chooses between those here",
     "variants": [
         {"id": "BF16", "size": "7.2 GB", "note": "the whole model; on a card older than Ampere (an RTX 20xx, a Quadro RTX) it runs without its tensor cores, slower than Q8_0",
          "files": ["models/YuE2-3B-BF16.gguf"]},
         {"id": "Q8_0", "size": "3.8 GB", "files": ["models/YuE2-3B-Q8_0.gguf"]},
         {"id": "Q6_K", "size": "2.9 GB", "files": ["models/YuE2-3B-Q6_K.gguf"]},
         {"id": "Q5_K_M", "size": "2.6 GB", "files": ["models/YuE2-3B-Q5_K_M.gguf"]}]},
    {"name": "listener", "label": "Style listener",
     "what": "Qwen2.5-Omni-7B: hears the songs of a training set and writes each one's style tags; the GGUF ones run through llama.cpp (vendor/llama.cpp, built by you)",
     "variants": [
         {"id": "Q8_0", "size": "9.6 GB", "note": "10.3 GB of VRAM when it listens", "files": [OMNI + "Qwen2.5-Omni-7B-Q8_0.gguf", PROJ]},
         {"id": "Q5_K_M", "size": "6.9 GB", "note": "8.0 GB of VRAM when it listens", "files": [OMNI + "unsloth/Qwen2.5-Omni-7B-Q5_K_M.gguf", PROJ]},
         {"id": "Q4_K_M", "size": "6.2 GB", "note": "7.3 GB of VRAM when it listens", "files": [OMNI + "Qwen2.5-Omni-7B-Q4_K_M.gguf", PROJ]},
         {"id": "bf16", "size": "22 GB", "note": "18.3 GB of VRAM when it listens: a 24 GB card",
          "files": ["checkpoints/Qwen2.5-Omni-7B/model.safetensors.index.json"]}]},
    None,   # the artwork's, by the biggest card here (below)
    {"name": "qwen", "label": "Qwen painters",
     "what": "the Artist's Qwen-Image painters: 2512 with Lightning's 8 steps (Apache-2.0: its parts from Qwen, the transformer as GGUF) and 2.1 (Qwen's research licence)",
     "variants": [
         {"id": "2512-q4", "label": "Qwen-Image 2512 Q4", "size": "31 GB",
          "note": "for a card of 16 GB (below 20 GB its text encoder reads the prompt on the processor: 17 GB of RAM); half a minute a picture on a 3090; less when some of it is here",
          "files": Q2512_PARTS + [Q2512 + "gguf/qwen-image-2512-Q4_K_M.gguf"]},
         {"id": "2512-q6", "label": "Qwen-Image 2512 Q6", "size": "34.5 GB", "note": "for a card of 24 GB; less when some of it is here",
          "files": Q2512_PARTS + [Q2512 + "gguf/qwen-image-2512-Q6_K.gguf"]},
         {"id": "2.1", "label": "Qwen-Image 2.1", "size": "33.1 GB",
          "note": "under Qwen's research licence: research and evaluation only, not for commercial use (a cover for a song that is sold is commercial use); a card of 24 GB, about two minutes a picture",
          "files": QWEN21}]},
    # HERESY 1303: MERT-v2-FullSong comes with the base (m-a-p's own repository, 2.5 GB): the set's latent cache needs it
    {"name": "trainer", "label": "LoRA trainer's base",
     "what": "Comfy-Org/YuE2 for the Trainer, with Mothersuperior's tokenizer head and m-a-p's MERT-v2-FullSong (the set's latent cache hears with it)",
     "variants": [
         {"id": "bf16", "size": "10.3 GB", "note": "trains on unquantized weights; MERT-v2-FullSong's 2.5 GB among them, less when it is here",
          "files": ["checkpoints/comfy/checkpoints/yue2_3b_bf16.safetensors", "checkpoints/MERT-v2-FullSong/model.safetensors"]},
         {"id": "int8", "size": "6.5 GB", "note": "for a smaller card; MERT-v2-FullSong's 2.5 GB among them, less when it is here",
          "files": ["checkpoints/comfy/checkpoints/yue2_3b_int8_convrot.safetensors", "checkpoints/MERT-v2-FullSong/model.safetensors"]}]},
]
ARTWORK_BIG = {"name": "artwork", "label": "Artwork",
               "what": "the Artist's painter: Krea 2 Muse by Stable Yogi with Krea 2's text encoder and VAE, the content filter its licence asks for, and the prompt writer (Qwen3-4B)",
               "variants": [
                   {"id": "q4", "label": "Krea 2 Muse Q4", "size": "26 GB", "note": "less when some of it is here", "files": [MUSE.format("Q4")] + KREA},
                   {"id": "q8", "label": "Krea 2 Muse Q4 and Q8", "size": "41 GB", "note": "less when some of it is here",
                    "files": [MUSE.format("Q4"), MUSE.format("Q8")] + KREA}]}
ARTWORK_SMALL = {"name": "artwork", "label": "Artwork",
                 "what": "the Artist's painter (no card here has the 16 GB Krea 2 wants): SDXL CyberRealistic, and the prompt writer (Qwen3-4B)",
                 "variants": [
                     {"id": "sdxl", "label": "SDXL CyberRealistic", "size": "15 GB", "note": "a 16 GB card when it draws",
                      "files": ["artwork/CyberRealistic-XL-v10/model_index.json", "artwork/CyberRealistic-XL-v10/unet/diffusion_pytorch_model.safetensors",
                                "artwork/Qwen3-4B-Instruct-2507/model.safetensors.index.json"]}]}

LINE = re.compile(r"^(here|differs|missing|fetched|unknown|failed)\s+(.*)$")
SUM = re.compile(r"^here (\d+) · unknown (\d+) · differs (\d+) · fetched (\d+) · missing (\d+) · failed (\d+)$")
JOB = {}
LOCK = threading.Lock()
_BIG = []


def _local_management():
    return runtime.WINDOWS or runtime.local_only()


def _reject_fetch():
    if _local_management():
        raise ValueError("model downloads are disabled in Windows/local-only mode; use reviewed pinned manifests and separately approved operator installation commands")


def _biggest_card_mb():
    """The biggest card's memory, as fetch-heresy.sh --artwork judges it (0 without nvidia-smi); asked once."""
    if _local_management():
        return 0                           # local status never starts a hardware subprocess
    if not _BIG:
        try:
            out = subprocess.run(["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
                                 capture_output=True, text=True, timeout=20).stdout
            _BIG.append(max([int(x) for x in out.split() if x.strip().isdigit()] or [0]))
        except (OSError, subprocess.SubprocessError):
            _BIG.append(0)
    return _BIG[0]


def _here(kit, files):
    for rel in files:
        f = kit / rel
        try:
            if not f.is_file() or f.stat().st_size == 0:
                return False
            if rel.endswith(".safetensors.index.json"):          # every shard its index names
                shards = set(json.loads(f.read_text(encoding="utf-8")).get("weight_map", {}).values())
                if not shards or any(not (f.parent / s).is_file() or (f.parent / s).stat().st_size == 0 for s in shards):
                    return False
        except (OSError, ValueError, TypeError, AttributeError):
            return False
    return True


def _extras(kit):
    out = []
    for e in EXTRAS:
        if e is None and _local_management():
            e = dict(ARTWORK_SMALL, variants=ARTWORK_SMALL["variants"] + ARTWORK_BIG["variants"])
        e = e or (ARTWORK_BIG if _biggest_card_mb() >= 16000 else ARTWORK_SMALL)
        out.append(dict({k: v for k, v in e.items() if k != "variants"},
                        variants=[dict({k: v for k, v in x.items() if k != "files"}, here=_here(kit, x["files"])) for x in e["variants"]]))
    return out


def _strip(kit, text):
    for root in {str(kit), os.path.realpath(kit)}:
        text = text.replace(root + "/", "")
    return text


def _last_run(kit):
    """The last whole run's verdicts (tmp/fetch-heresy.list): parts, each with its rows; None before the first."""
    f = kit / "tmp" / "fetch-heresy.list"
    try:
        lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    parts, counts, mode, at, cur = [], None, "", int(f.stat().st_mtime), None
    for line in lines:
        cols = line.split("\t")
        if len(cols) < 3:
            continue
        st, what, words = cols[0], _strip(kit, cols[1]), _strip(kit, cols[2])
        if st == "##":
            cur = {"part": what, "label": words, "size": PARTS.get(what, ""), "rows": []}
            parts.append(cur)
        elif st == "#sum":
            n = what.split()
            if len(n) == 6:
                counts = dict(zip(("here", "unknown", "differs", "fetched", "missing", "failed"), map(int, n)))
            m = words.split()
            mode, at = (m[0] if m else ""), (int(m[1]) if len(m) > 1 and m[1].isdigit() else at)
        elif cur is not None:
            cur["rows"].append({"state": st, "text": (what + " " + words).strip()})
    return {"parts": parts, "counts": counts, "mode": mode, "at": at}


def _free(kit):
    try:
        return shutil.disk_usage(kit).free
    except OSError:
        return None


def _job_view(kit):
    with LOCK:
        if not JOB:
            return None
        j = {k: v for k, v in JOB.items() if k not in ("lines", "free0")}
        j["lines"] = JOB["lines"][-200:]
        if JOB["status"] == "running" and JOB.get("free0") is not None:
            now = _free(kit)
            j["written"] = max(0, JOB["free0"] - now) if now is not None else None   # the disk's free room it took so far
    return j


def listing(kit):
    kit = Path(kit)
    if _local_management():
        return _local_listing(kit)
    script = kit / "heresy" / "fetch-heresy.sh"
    return {"script": script.is_file(), "last": _last_run(kit), "extras": _extras(kit), "parts": PARTS,
            "job": _job_view(kit), "now": int(time.time())}


def running():
    with LOCK:
        return bool(JOB) and JOB.get("status") == "running"


NAMES = {"extras": "the extra decoders and the sliders", "whisper": "Whisper", "stems": "the stems' models", "upscale": "UniverSR",
         "loras": "the LoRAs"}


def _args(body):
    """fetch-heresy.sh's arguments and the run's name for a POST /weights/fetch body; ValueError for anything else."""
    part = str(body.get("part", "") or "")
    if part == "missing":
        return [], "what is missing"
    if part in PARTS:
        return ["--only", part], NAMES[part]
    for e in EXTRAS:
        name = e["name"] if e else "artwork"
        v = body.get(name)
        if v is None:
            continue
        v = str(v)
        ids = [x["id"] for x in (e or ARTWORK_BIG)["variants"]] + ([] if e else ["sdxl"])
        if v not in ids:
            raise ValueError(f"{name} takes {', '.join(ids)}")
        x = (e or ARTWORK_BIG)["variants"] + ([] if e else ARTWORK_SMALL["variants"])
        label = (e or ARTWORK_BIG)["label"]
        what = "the " + label[0].lower() + label[1:] + " " + next((y.get("label") or y["id"] for y in x if y["id"] == v), v)
        if name == "artwork":
            return ["--only", "none", "--artwork-q8" if v == "q8" else "--artwork", "--yes"], what
        return ["--only", "none", "--" + name, v, "--yes"], what
    raise ValueError("say what to fetch: a part (missing, " + ", ".join(PARTS) + ") or an extra (backbone, listener, artwork, qwen, trainer)")


def _bytes(size):
    """HERESY 1302: «7.2 GB», «56 MB» → bytes, decimal as the sizes are measured (du -sb); None where it says no number."""
    m = re.match(r"^\s*(\d+(?:\.\d+)?)\s*(GB|MB)\b", str(size or ""))
    return int(float(m.group(1)) * (1e9 if m.group(2) == "GB" else 1e6)) if m else None


def _which(body):
    """HERESY 1302: what a fetch was asked for, for the page to draw its progress at that row ({"part": …} or {"extra": …,
    "variant": …}), and the bytes the card says it brings (None for «what is missing»: its size is not one number)."""
    part = str(body.get("part", "") or "")
    if part:
        return {"part": part}, _bytes(PARTS.get(part))
    for e in EXTRAS:
        name = e["name"] if e else "artwork"
        if body.get(name) is None:
            continue
        v = str(body[name])
        x = (e or ARTWORK_BIG)["variants"] + ([] if e else ARTWORK_SMALL["variants"])
        return {"extra": name, "variant": v}, _bytes(next((y["size"] for y in x if y["id"] == v), ""))
    return {}, None


def _start(kit, args, what, kind, then_check, which=None, expect=None):
    _reject_fetch()
    with LOCK:
        if JOB.get("status") == "running":
            raise ValueError(f"a run is under way ({JOB.get('what')}): one at a time")
        JOB.clear()
        JOB.update(kind=kind, what=what, args=args, status="running", started=time.time(), ended=None, rc=None, lines=[],
                   counts=None, restart=False, free0=_free(kit) if kind == "fetch" else None,
                   which=which or {}, expect=expect)   # HERESY 1302
    threading.Thread(target=_run, args=(kit, args, then_check), daemon=True).start()
    return listing(kit)


def check(kit):
    if _local_management():
        return _local_listing(Path(kit))
    if not (kit / "heresy" / "fetch-heresy.sh").is_file():
        raise FileNotFoundError("no heresy/fetch-heresy.sh in this tree")
    return _start(kit, ["--check"], "what is here", "check", False)


def fetch(kit, body, scope=""):
    _reject_fetch()
    if scope:
        raise ValueError("a test page fetches nothing: open the studio without ?scope= to fetch")
    if not (kit / "heresy" / "fetch-heresy.sh").is_file():
        raise FileNotFoundError("no heresy/fetch-heresy.sh in this tree")
    body = body if isinstance(body, dict) else {}
    args, what = _args(body)
    which, expect = _which(body)                    # HERESY 1302: the page's progress at the row pressed
    # a part fetched alone leaves the whole list as it was: a check after it says where everything stands
    return _start(kit, args, what, "fetch", bool(args and args[0] == "--only" and args[1] != "none"), which, expect)


def _say(kit, args):
    """One run of fetch-heresy.sh into JOB["lines"]; its exit status (0: nothing failed)."""
    _reject_fetch()
    env = dict(os.environ, NO_COLOR="1", HF_HUB_DISABLE_TELEMETRY="1")
    p = subprocess.Popen(["bash", str(kit / "heresy" / "fetch-heresy.sh")] + args, cwd=str(kit), env=env, stdin=subprocess.DEVNULL,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace")
    for line in p.stdout:
        line = _strip(kit, line.rstrip("\n"))
        with LOCK:
            JOB["lines"].append(line)
            del JOB["lines"][:-1000]
            m = SUM.match(line)
            if m:
                JOB["counts"] = dict(zip(("here", "unknown", "differs", "fetched", "missing", "failed"), map(int, m.groups())))
            # a backbone, a decoder or the sliders: the engine reads those when it starts (LoRAs it reads each time)
            if JOB["kind"] == "fetch" and re.match(r"^fetched\s+(models/|legacy, blend and sliders)", line):
                JOB["restart"] = True
    return p.wait()


def _run(kit, args, then_check):
    _reject_fetch()
    try:
        rc = _say(kit, args)
        with LOCK:
            JOB["rc"] = rc
        if then_check:
            with LOCK:
                JOB["lines"].append("")
                JOB["lines"].append("— the check, after it —")
                JOB["checking"] = True
                counts = JOB["counts"]
            _say(kit, ["--check"])
            with LOCK:
                JOB["checking"] = False
                JOB["after"] = JOB["counts"]
                JOB["counts"] = counts
        with LOCK:
            JOB["status"] = "done" if rc == 0 else "failed"
    except (OSError, subprocess.SubprocessError) as e:
        with LOCK:
            JOB["lines"].append(f"failed: {e}")
            JOB["status"] = "failed"
    finally:
        with LOCK:
            JOB["ended"] = time.time()


def _manifest_path(root, relative):
    relative = str(relative)
    parts = relative.replace("\\", "/").split("/")
    if not parts:
        raise ValueError("empty model path")
    for part in parts:
        runtime.safe_component(part)
    path = (Path(root) / Path(*parts)).resolve()
    path.relative_to(Path(root).resolve())
    return path


def _local_listing(kit):
    """File-only inventory. Presence/size is reported; SHA validation is not invented."""
    groups = collections.OrderedDict()
    counts = {k:0 for k in ("here", "unknown", "differs", "fetched", "missing", "failed")}
    metadata_errors = []
    sources = []

    def add(part, relative, row, base=kit):
        group = groups.setdefault(part, {"part":part,"label":part,"size":"","rows":[]})
        try:
            path = _manifest_path(base, relative)
            expected = int(row.get("size") or 0)
            actual = path.stat().st_size if path.is_file() else None
            state = "missing" if actual is None else "unknown" if expected <= 0 else "here" if actual == expected else "differs"
            verdict = {"state":state, "text":str(relative), "bytes":actual, "expected_bytes":expected,
                       "expected_sha256":str(row.get("sha256") or ""),
                       "verification":"size_only" if actual is not None else "not_checked",
                       "repository":row.get("repo") or row.get("repository"), "revision":row.get("revision"), "license":row.get("license")}
        except (OSError, ValueError, TypeError):
            state, verdict = "unknown", {"state":"unknown", "text":"invalid or unreadable manifest entry", "verification":"not_checked"}
        counts[state] += 1
        group["rows"].append(verdict)

    for filename in ("downloads.json", "full-audio-models.json", "full-art-models.json"):
        path = kit / "windows" / filename
        if not path.is_file():
            continue
        try:
            document = runtime.read_json(path)
            sources.append("windows/" + filename)
            for model in document.get("models", []):
                if filename == "downloads.json":
                    base = Path(os.environ.get("RUACH_MODELS_DIR") or kit / "models").resolve()
                    add("backbone", model["filename"], model, base=base)
                elif "files" in model:
                    for file in model["files"]:
                        record = dict(model, **file)
                        add("artwork:" + str(model.get("id", "local")), model["directory"] + "/" + file["path"], record)
                else:
                    add(str(model.get("profile") or "models"), model["destination"], model)
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            metadata_errors.append("windows/" + filename + " is unreadable or invalid")
    for group in groups.values():
        group["size"] = f"{sum(r.get('expected_bytes',0) for r in group['rows']) / 1e9:.3f} GB"
    last = {"parts":list(groups.values()), "counts":counts, "mode":"local-presence-and-size", "at":int(time.time()),
            "verification":"size_only; SHA256 must be checked by approved installation tooling"}
    return {"script":False, "mode":"local", "download_enabled":False, "check_performed":True,
            "notice":"Local file presence/size only. No remote lookup, download or SHA256 validation was performed.",
            "instructions":"Review windows/downloads.json, windows/full-audio-models.json and windows/full-art-models.json; approve additional models before running operator installation commands.",
            "manifest_sources":sources, "metadata_errors":metadata_errors, "last":last, "extras":_extras(kit), "parts":PARTS,
            "job":None, "free_bytes":_free(kit), "now":int(time.time())}
