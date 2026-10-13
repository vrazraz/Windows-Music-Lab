"""HERESY 1068: the listener (Viktor, 02.10.2026). Qwen2.5-Omni hears a track and writes what is heard
as one line of style tags, so a training set gets a style of its own for every song instead of the SUNO
prompt (SUNO follows its prompt loosely: the prompt is not a description of its track).

Only Omni's thinker is loaded (the talker speaks; we need text). The lyrics are not asked for: the sets
carry the exact texts already. Runs as its own process on a GPU of its own and leaves nothing behind:

    .venv/bin/python lab/listener.py fosforida-v2 --gpu 2 [--model checkpoints/Qwen2.5-Omni-7B] [--seconds 120]

writes datasets/prepared/NAME/styles.json: {stem: tags}, with the model, the excerpt and the VRAM peak
(the figure the trainer's calculator and the listener's gate are built on).

HERESY 1077: a GGUF model goes through llama.cpp (vendor/llama.cpp, llama-mtmd-cli with --mmproj), one call
a track. Measured 02.10.2026 on one 120 s excerpt, peak VRAM: transformers bf16 18.3 GB · Q8_0 + mmproj-f16
11.3 GiB · Q4_K_M + mmproj-f16 8.4 GiB, about 5 s a track; the three hear the same, and all three are drafts
(Fosforida's harp and low strings came out as piano or synthesizer).

    .venv/bin/python lab/listener.py SET --gpu 1 --model checkpoints/Qwen2.5-Omni-7B-GGUF/Qwen2.5-Omni-7B-Q8_0.gguf"""
import argparse, json, os, re, subprocess, sys, time
from pathlib import Path
from atomic_audio import replace_file
from platform_runtime import (WINDOWS, configure_runtime, gpu_lease, job_environment,
                              process_options, release_engine_for_gpu_job, system_memory, terminate_process)

KIT = Path(__file__).resolve().parent.parent
PROMPT = ("Listen to this audio and decide whether music, speech, or both are actually audible. "
          "Describe only what you hear as one line of comma-separated lowercase style tags. "
          "For speech without music, include spoken word and no music; do not invent a musical genre, "
          "beat, harmony, accompaniment, or instruments. If no instruments are audible, say no instruments. "
          "When music is present, name its genre and sub-genre only if they are clear, then mood, vocal type "
          "(male vocal, female vocal, duet, choir, instrumental), audible vocal delivery, instruments that "
          "you can really hear, production, and tempo feel or harmony colour only where supported by the audio. "
          "Spoken delivery is different from singing or belting. Do not infer sounds from this request. "
          "No sentences, artist or song names, or lyrics. Output only the tag line.")


def mtmd_cli(kit=KIT):
    """Support both Ninja and Visual Studio llama.cpp builds, without PATH guessing."""
    suffix = ".exe" if WINDOWS else ""
    bases = [Path(kit) / "windows/build/listener-cuda/bin",
             Path(kit) / "vendor/llama.cpp/build/bin"]
    candidates = [base / name for base in bases for name in
                  ("llama-mtmd-cli" + suffix, "Release/llama-mtmd-cli" + suffix)]
    return next((path for path in candidates if path.is_file()), candidates[0])



def local_path(value, base, label, directory=False):
    """Resolve an existing project-local path; never treat a URL or UNC path as a model."""
    raw = str(value)
    if "://" in raw or raw.startswith(("\\\\", "//")):
        raise ValueError(f"{label} must be a local path inside the project")
    candidate = Path(raw)
    candidate = candidate if candidate.is_absolute() else KIT / candidate
    candidate = candidate.resolve()
    base = Path(base).resolve()
    if base not in candidate.parents:
        raise ValueError(f"{label} must stay inside {base}")
    if directory:
        if not candidate.is_dir():
            raise FileNotFoundError(f"local {label} folder is missing: {candidate}")
    elif not candidate.is_file() or candidate.stat().st_size == 0:
        raise FileNotFoundError(f"local {label} file is missing or empty: {candidate}")
    return candidate


def local_cli(value):
    """Only the published native package or the explicitly approved local build."""
    raw = str(value)
    if "://" in raw or raw.startswith(("\\\\", "//")):
        raise ValueError("llama-mtmd-cli must be a local project build")
    candidate = Path(value)
    candidate = (candidate if candidate.is_absolute() else KIT / candidate).resolve()
    for relative in ("windows/build/listener-cuda", "vendor/llama.cpp/build"):
        base = (KIT / relative).resolve()
        if base in candidate.parents:
            return local_path(candidate, base, "llama-mtmd-cli")
    raise ValueError("llama-mtmd-cli must stay inside its approved build folders")


def gguf_paths(a):
    model = local_path(a.model, KIT / "checkpoints", "listener model")
    if model.suffix.lower() != ".gguf":
        raise ValueError("listener model must be a local .gguf file")
    proj = a.mmproj or next(iter(sorted(model.parent.glob("mmproj-*f16.gguf")) or
                                sorted(model.parent.glob("mmproj-*.gguf"))), None)
    if proj is None:
        raise FileNotFoundError("local audio projector is missing; install approved weights first")
    proj = local_path(proj, KIT / "checkpoints", "audio projector")
    if proj.suffix.lower() != ".gguf":
        raise ValueError("audio projector must be a local .gguf file")
    cli = local_cli(mtmd_cli())
    return cli, model, proj


def cli_environment(gpu):
    """Ignore external llama presets/URLs/cloud/token overrides in this one owned child."""
    env = dict(job_environment(KIT))
    for key in tuple(env):
        upper = key.upper()
        if (upper.startswith(("LLAMA_", "MTMD_", "GGML_RPC_")) or
                upper in {"HF_TOKEN", "HUGGING_FACE_HUB_TOKEN", "HUGGINGFACE_HUB_TOKEN",
                          "HF_ENDPOINT", "OPENAI_API_KEY", "OPENAI_BASE_URL"} or
                key.lower() in {"http_proxy", "https_proxy", "all_proxy"}):
            env.pop(key)
    env.update(CUDA_VISIBLE_DEVICES=str(gpu), LLAMA_ARG_OFFLINE="1",
               HF_HUB_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1", TRANSFORMERS_OFFLINE="1",
               WINDOWS_MUSIC_LAB_LOCAL_ONLY="1", NO_PROXY="localhost,127.0.0.1,::1")
    return env


def gguf_command(cli, model, proj, audio):
    """Only flags accepted by the pinned v0.6.0 MTMD parser; one-turn audio chat."""
    cli = local_cli(cli)
    model = local_path(model, KIT / "checkpoints", "listener model")
    proj = local_path(proj, KIT / "checkpoints", "audio projector")
    audio = local_path(audio, KIT / "lab/cache/tmp", "audio excerpt")
    return [str(cli), "--offline", "--jinja", "-m", str(model), "--mmproj", str(proj),
            "--audio", str(audio), "-p", PROMPT, "-ngl", "99", "-c", "8192", "-n", "160",
            "--temp", "0", "--batch-size", "256", "--ubatch-size", "128", "--threads", "4",
            "--log-colors", "off", "--verbosity", "4", "--perf"]



def cuda_offload(diagnostic):
    """Require the pinned loader's actual full-layer CUDA evidence, not just an ngl request."""
    match = re.search(r"offloaded\s+(\d+)/(\d+)\s+layers to GPU", diagnostic)
    if not match or "CUDA0" not in diagnostic:
        return False
    actual, total = map(int, match.groups())
    clip_backends = re.findall(r"CLIP using (\S+) backend", diagnostic)
    return (total > 0 and actual == total and bool(clip_backends) and
            all(name == "CUDA0" for name in clip_backends) and "has audio encoder" in diagnostic)


def run_cli(command, env, log_dir, timeout=600):
    """No interactive stdin; cleanup only the native child/process tree this call owns."""
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    begun = time.monotonic()
    process = subprocess.Popen(command, cwd=str(KIT), stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                               encoding="utf-8", errors="replace", env=env, **process_options())
    output, error = "", ""
    failure = None
    try:
        output, error = process.communicate(timeout=timeout)
        return subprocess.CompletedProcess(command, process.returncode, output, error)
    except BaseException as exc:
        failure = type(exc).__name__
        terminate_process(process)
        output, error = process.communicate(timeout=5)
        raise
    finally:
        if process.poll() is None:
            terminate_process(process)
        (log_dir / "stdout.log").write_text(output or "", encoding="utf-8")
        (log_dir / "stderr.log").write_text(error or "", encoding="utf-8")
        (log_dir / "command.json").write_text(json.dumps({
            "argv": command, "cwd": str(KIT), "stdin": "DEVNULL", "returncode": process.returncode,
            "seconds": round(time.monotonic() - begun, 3), "failure": failure,
            "offline": True, "gpu": env["CUDA_VISIBLE_DEVICES"]}, indent=1), encoding="utf-8")


def dataset(kit, name):
    base = (Path(kit) / "datasets/prepared").resolve()
    folder = (base / name).resolve()
    if base not in folder.parents or not folder.is_dir():
        raise ValueError("dataset must be an existing folder inside datasets/prepared")
    return folder



def selected_stems(a, folder):
    with (folder / "dataset.json").open(encoding="utf-8") as stream:
        manifest = json.load(stream)
    chosen = {name.strip() for name in str(getattr(a, "only", "")).split(",") if name.strip()}
    stems = []
    for track in manifest.get("tracks", []):
        stem = track.get("stem")
        if not isinstance(stem, str) or not stem.strip():
            raise ValueError("dataset track must have a nonempty string stem")
        if chosen and stem not in chosen:
            continue
        local_path(folder / (stem + ".wav"), folder, "dataset audio")
        if stem in stems:
            raise ValueError("dataset contains duplicate stems")
        stems.append(stem)
    if not stems:
        raise ValueError("no local dataset tracks match this Listener request")
    return stems


def write_styles(path, value):
    part = path.with_suffix(".json.part")
    with part.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=1)
    replace_file(part, path)


def excerpt(path, start, seconds):
    """The track as 16 kHz mono float32 (what Omni's audio encoder takes), cut from `start`."""
    import numpy as np
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(start), "-t", str(seconds), "-i", str(path),
                          "-ac", "1", "-ar", "16000", "-f", "f32le", "-"], capture_output=True, check=True, timeout=300).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()


def length(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30).stdout.strip()
    return float(out or 0)


def gguf(a, d, stems):
    """The same listening through llama.cpp: a GGUF and its audio projector (mmproj-*.gguf beside it)."""
    import tempfile
    cli, model, proj = gguf_paths(a)
    d = dataset(KIT, str(Path(d).resolve().relative_to((KIT / "datasets/prepared").resolve())))
    out_path = d / "styles.json"
    out = {}
    if out_path.is_file():
        with out_path.open(encoding="utf-8") as saved:
            out = json.load(saved)
    out.setdefault("tags", {})
    env = cli_environment(a.gpu)
    t0 = time.time()
    temporary = KIT / "lab/cache/tmp"
    temporary.mkdir(parents=True, exist_ok=True)
    logs = KIT / "lab/cache/listener"
    logs.mkdir(parents=True, exist_ok=True)
    log_root = Path(tempfile.mkdtemp(prefix="listener-", dir=logs))
    print(f"listener logs: {log_root}", flush=True)
    failures = 0
    with tempfile.TemporaryDirectory(dir=temporary) as tmp:
        for i, stem in enumerate(stems):
            wav = local_path(d / (stem + ".wav"), d, "dataset audio")
            total = length(wav)
            start = max(0.0, min(total * 0.2, total - a.seconds))
            cut = Path(tmp) / "excerpt.wav"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(start), "-t", str(a.seconds), "-i", str(wav), "-ac", "1", "-ar", "16000", str(cut)],
                           check=True, timeout=300, stdin=subprocess.DEVNULL, env=env, **process_options())
            r = run_cli(gguf_command(cli, model, proj, cut), env, log_root / f"{i + 1:04d}")
            lines = [l.strip() for l in r.stdout.splitlines() if l.strip()]
            diagnostic = (r.stderr or "") + "\n" + (r.stdout or "")
            gpu_ready = cuda_offload(diagnostic)
            if r.returncode != 0 or not lines or not gpu_ready:
                reason = (r.stderr or '').strip().splitlines()[-1:]
                if r.returncode == 0 and not gpu_ready:
                    reason = ["native CLI did not confirm full CUDA offload; CPU fallback is not accepted"]
                print(f"{i + 1}/{len(stems)} {stem} FAILED: {reason}", flush=True)
                failures += 1
                continue                                   # said aloud, and no empty tags written as if heard
            out["tags"][stem] = " ".join(lines[-1].split())
            print(f"{i + 1}/{len(stems)} {stem} [{start:.0f}s+{a.seconds:.0f}s] {out['tags'][stem]}", flush=True)
            out.update(model=model.name, mmproj=proj.name, seconds=a.seconds, backend="cuda",
                       gpu=str(a.gpu), full_cuda_offload=True, made=time.strftime("%Y-%m-%d %H:%M"))
            write_styles(out_path, out)
    print(f"done: {len(stems) - failures}/{len(stems)} in {time.time() - t0:.0f} s (llama.cpp, {model.name})", flush=True)
    return 1 if failures else 0


def listener_memory_admission(a):
    """Windows GGUF admission before model import/load, based on the measured short pilot.

    11GiB initial machine commit and10GiB available RAM are short-test minimums.
    This does not validate memory or model quality for the UI's120s excerpt.
    """
    if not WINDOWS or not str(a.model).lower().endswith(".gguf"):
        return None
    memory = system_memory()
    if memory.get("commit_scope") != "machine":
        raise RuntimeError("Listener needs machine-wide Windows commit counters before loading; "
                           "no model started. Source: " + str(memory.get("commit_source")))
    commit = memory.get("commit_available", 0)
    physical = memory.get("available", 0)
    if commit < 11 * 2**30 or physical < 10 * 2**30:
        raise RuntimeError("Listener GGUF requires at least11GiB machine commit headroom and10GiB available RAM "
                           f"before loading (available commit={commit}, RAM={physical}bytes). "
                           "These are measured short-pilot minimums;120s audio is unvalidated. No model started.")
    return memory


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dataset")
    ap.add_argument("--gpu", default="0")
    ap.add_argument("--model", default=str(KIT / "checkpoints" / "Qwen2.5-Omni-7B"))
    ap.add_argument("--seconds", type=float, default=120.0)
    ap.add_argument("--only", default="", help="comma-separated stems, for a quick look")
    ap.add_argument("--mmproj", default="", help="a GGUF model's audio projector (default: mmproj-*.gguf beside it)")
    a = ap.parse_args()
    configure_runtime(KIT)
    if not 0 < a.seconds <= 600:
        ap.error("seconds must be greater than 0 and at most 600")
    try:
        selected_stems(a, dataset(KIT, a.dataset))
        if str(a.model).lower().endswith(".gguf"):
            _, model, proj = gguf_paths(a)
            a.model, a.mmproj = str(model), str(proj)
        else:
            a.model = str(local_path(a.model, KIT / "checkpoints", "listener model", directory=True))
    except (OSError, ValueError) as error:
        ap.error(str(error))
    with gpu_lease(int(a.gpu)):
        release_engine_for_gpu_job()
        admitted = listener_memory_admission(a)
        if admitted is not None:
            print("listener memory admission: " + json.dumps(admitted), flush=True)
        import gpu_guard
        gpu_guard.check(int(a.gpu), listener_need(a), KIT)
        return _inference(a)


def listener_need(a):
    if not str(a.model).lower().endswith(".gguf"):
        return 23000
    projector_q8 = "q8_0" in str(a.mmproj).lower()
    name = Path(a.model).name.lower()
    if "q4_k_m" in name:
        return 8200 if projector_q8 else 9000
    if "q5_k_m" in name:
        return 9000 if projector_q8 else 11000
    return 11500 if projector_q8 else 12000


def _inference(a):
    if str(a.model).lower().endswith(".gguf"):
        d = dataset(KIT, a.dataset)
        return gguf(a, d, selected_stems(a, d))
    os.environ["CUDA_VISIBLE_DEVICES"] = str(a.gpu)
    import torch
    from transformers import Qwen2_5OmniProcessor, Qwen2_5OmniThinkerForConditionalGeneration

    d = dataset(KIT, a.dataset)
    stems = selected_stems(a, d)
    t0 = time.time()
    proc = Qwen2_5OmniProcessor.from_pretrained(a.model, local_files_only=True)
    model = Qwen2_5OmniThinkerForConditionalGeneration.from_pretrained(a.model, torch_dtype=torch.bfloat16, local_files_only=True).to("cuda:0")   # no accelerate needed
    model.eval()
    loaded = time.time() - t0
    out_path = d / "styles.json"
    out = {}
    if out_path.is_file():
        with out_path.open(encoding="utf-8") as saved:
            out = json.load(saved)
    out.setdefault("tags", {})
    for i, stem in enumerate(stems):
        wav = local_path(d / (stem + ".wav"), d, "dataset audio")
        total = length(wav)
        start = max(0.0, min(total * 0.2, total - a.seconds))       # past the intro, into the body of the song
        audio = excerpt(wav, start, a.seconds)
        conv = [{"role": "system", "content": [{"type": "text", "text": "You are a music producer who names what is heard, precisely."}]},
                {"role": "user", "content": [{"type": "audio", "audio": "track"}, {"type": "text", "text": PROMPT}]}]
        text = proc.apply_chat_template(conv, add_generation_prompt=True, tokenize=False)
        inputs = proc(text=text, audio=[audio], sampling_rate=16000, return_tensors="pt", padding=True).to("cuda:0")
        inputs = {k: (v.to(torch.bfloat16) if v.dtype == torch.float32 else v) for k, v in inputs.items()}
        with torch.no_grad():
            ids = model.generate(**inputs, max_new_tokens=160, do_sample=False)
        tags = proc.batch_decode(ids[:, inputs["input_ids"].shape[1]:], skip_special_tokens=True)[0].strip().splitlines()
        tags = " ".join(tags[0].split()) if tags else ""
        out["tags"][stem] = tags
        print(f"{i + 1}/{len(stems)} {stem} [{start:.0f}s+{a.seconds:.0f}s] {tags}", flush=True)
        out.update(model=Path(a.model).name, seconds=a.seconds, loaded_in=round(loaded, 1),
                   vram_peak_mb=round(torch.cuda.max_memory_allocated() / 2 ** 20), made=time.strftime("%Y-%m-%d %H:%M"))
        write_styles(out_path, out)
    print(f"done: {len(stems)} in {time.time() - t0:.0f} s · VRAM peak {out.get('vram_peak_mb')} MB (torch)", flush=True)


if __name__ == "__main__":
    sys.exit(main())
