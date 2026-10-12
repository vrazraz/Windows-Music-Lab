"""Local SDXL Artist worker for native Windows (no cloud or implicit downloads).

Uses the original Artist canvas/mask geometry and output protocol. SDXL's own
image-to-image/inpaint pipelines replace flow-matching sampling for this family.
CPU offload and tiled VAE keep a 12 GB card usable; inference needs validation
with the approved dependencies and model weights before claiming a VRAM bound.
"""
import json
from pathlib import Path
import time
import sys
import ctypes
import gc
import os
import threading

import art_job
import artist_job
import artist_loras
from platform_runtime import system_memory

SHAPES = {"1:1": (1024, 1024), "16:9": (1344, 768), "9:16": (768, 1344)}
SAMPLERS = ("euler", "euler-sde", "dpmpp", "heun")
SCHEDULES = ("simple", "karras")
RESOLUTIONS = (512, 1024)
# This optional single-frame validation policy does not constrain production jobs.
# On Windows, safetensors/Torch private mmap reserves commit for the whole view.
# Sequential hooks preserve the CPU state_dict and avoid whole-model GPU->CPU copies.
VALIDATION_PROFILE = "sdxl512-sequential-win-v1"
MIN_COMMIT_BYTES = int(11.5 * 2 ** 30)
MIN_RAM_BYTES = 9 * 2 ** 30
MEMORY_REASON = ("Windows sequential CPU offload; 6.46 GiB fp16 weights still consume commit "
                 "(Diffusers COW mmap and Transformers Windows pread). Observed about 2 GiB imports/DLL private commit "
                 "in the blocked one-frame attempt; 9.5 GiB post-import load budget plus 2 GiB import allowance, "
                 "including estimated 1 GiB transient allocations/VAE fp32 and 2 GiB reserve; not a measured inference bound")
PHASE_GUARDS = {"before_import": (MIN_RAM_BYTES, MIN_COMMIT_BYTES),
                "after_import": (8 * 2 ** 30, int(9.5 * 2 ** 30)),
                "before_inference": (2 ** 30, 2 * 2 ** 30), "step": (2 ** 30, 2 * 2 ** 30)}
VALIDATION_WEIGHTS = {"text_encoder/model.fp16.safetensors": 246144152,
                      "text_encoder_2/model.fp16.safetensors": 1389382176,
                      "unet/diffusion_pytorch_model.fp16.safetensors": 5135149760,
                      "vae/diffusion_pytorch_model.fp16.safetensors": 167335342}


def validation_policy():
    return {"profile": VALIDATION_PROFILE, "offload_mode": "sequential", "production_offload_mode": "component",
            "available_ram_bytes": MIN_RAM_BYTES, "commit_headroom_bytes": MIN_COMMIT_BYTES,
            "phase_guards": {stage: {"available_ram_bytes": ram, "commit_headroom_bytes": commit}
                             for stage, (ram, commit) in PHASE_GUARDS.items()},
            "weights_storage": "Diffusers private COW mmap; Transformers Windows pread CPU tensors",
            "low_cpu_mem_usage": True, "weight_dtype": "float16", "loras": False,
            "reason": MEMORY_REASON, "measured_inference_bound": False, "policy_revision": 2, "import_allowance_bytes": 2 * 2 ** 30}


def validate_model_storage(base=None):
    """Read only bounded safetensors headers; never import ML or materialize weights.

    The smaller sequential budget is for the approved fp16 folder, not arbitrary
    checkpoints that need dtype conversion or single-file config reconstruction.
    The one-frame harness separately verifies all approved SHA256 checksums.
    """
    import math
    import struct
    base = art_job.sdxl_path() if base is None else Path(base)
    if not base.is_dir():
        raise RuntimeError("Sequential validation requires the approved local SDXL fp16 folder")
    tensors, total, largest = 0, 0, 0
    for name, expected_size in VALIDATION_WEIGHTS.items():
        path = base / name
        if not path.is_file() or path.stat().st_size != expected_size:
            raise RuntimeError("Sequential validation fp16 weight missing/partial: " + name)
        with path.open("rb") as stream:
            raw = stream.read(8)
            if len(raw) != 8:
                raise RuntimeError("Invalid safetensors header: " + name)
            size = struct.unpack("<Q", raw)[0]
            if not 2 <= size <= 16 * 2 ** 20 or 8 + size > expected_size:
                raise RuntimeError("Invalid safetensors header bound: " + name)
            header = json.loads(stream.read(size))
        offsets = []
        for key, entry in header.items():
            if key == "__metadata__":
                continue
            start, end = entry["data_offsets"]
            shape = entry["shape"]
            if (entry["dtype"] != "F16" or any(not isinstance(n, int) or n < 0 for n in shape)
                    or not 0 <= start <= end <= expected_size - 8 - size or end - start != 2 * math.prod(shape)):
                raise RuntimeError("Sequential validation requires unchanged fp16 tensors: " + name)
            offsets.append((start, end))
            tensors += 1; total += end - start; largest = max(largest, end - start)
        cursor = 0
        for start, end in sorted(offsets):
            if start != cursor:
                raise RuntimeError("Invalid safetensors tensor layout: " + name)
            cursor = end
        if not offsets or cursor != expected_size - 8 - size:
            raise RuntimeError("Invalid safetensors data size: " + name)
    return {"all_tensors_fp16": True, "tensor_count": tensors, "tensor_bytes": total,
            "largest_tensor_bytes": largest, "windows_commit_weight_bytes": sum(VALIDATION_WEIGHTS.values())}


def resolution_of(ask):
    value = ask.get("resolution", 1024)
    if isinstance(value, bool) or str(value) not in ("512", "1024"):
        raise ValueError("SDXL resolution must be 512 or 1024")
    return int(value)


def dimensions(ask, shape):
    if shape not in SHAPES:
        raise ValueError("SDXL needs a supported shape")
    divisor = 2 if resolution_of(ask) == 512 else 1
    return tuple(n // divisor for n in SHAPES[shape])


def validate_profile(ask):
    profile = ask.get("validation_profile")
    if not profile:
        return False
    if (profile != VALIDATION_PROFILE or resolution_of(ask) != 512 or int(ask.get("count") or 1) != 1
            or ask.get("shapes") != ["1:1"] or any(ask.get(k) for k in ("ref", "mask", "fit", "place", "loras"))
            or not 12 <= int((ask.get("sampling") or {}).get("steps") or 12) <= 20):
        raise ValueError("The validation profile allows one 512 square with 12–20 steps, no variants, refs or LoRA")
    return True


def preflight_memory(snapshot=None, stage="before_import"):
    """Resource estimate for the explicitly selected low-memory512 validation flow."""
    memory = system_memory() if snapshot is None else snapshot
    ram, commit = memory.get("available"), memory.get("commit_available")
    minimum_ram, minimum_commit = PHASE_GUARDS.get(stage, PHASE_GUARDS["before_import"])
    if ram is None or commit is None:
        raise RuntimeError("SDXL validation cannot verify RAM and commit headroom")
    if ram < minimum_ram or commit < minimum_commit:
        raise RuntimeError(f"SDXL512 low-memory validation requires {minimum_ram / 2 ** 30:g} GiB RAM and {minimum_commit / 2 ** 30:g} GiB commit at {stage}; "
                           f"currently {ram / 2 ** 30:.2f} GiB RAM and {commit / 2 ** 30:.2f} GiB commit. {MEMORY_REASON}")
    return memory


def process_memory():
    """Private bytes and native process commit/working-set peaks (Windows OS APIs)."""
    if os.name != "nt":
        return {}
    class Counters(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong), ("faults", ctypes.c_ulong)] + [(n, ctypes.c_size_t) for n in
                    ("peak_working_set", "working_set", "peak_paged_pool", "paged_pool", "peak_nonpaged_pool", "nonpaged_pool", "pagefile", "peak_pagefile", "private")]
    counters = Counters(); counters.cb = ctypes.sizeof(counters)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    api = ctypes.WinDLL("psapi", use_last_error=True).GetProcessMemoryInfo
    api.argtypes = [ctypes.c_void_p, ctypes.POINTER(Counters), ctypes.c_ulong]
    api.restype = ctypes.c_int
    if not api(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
        raise OSError(ctypes.get_last_error(), "GetProcessMemoryInfo failed")
    return {"private_bytes": counters.private, "working_set_bytes": counters.working_set,
            "peak_working_set_bytes": counters.peak_working_set, "peak_process_commit_bytes": counters.peak_pagefile}


class ResourceMetrics:
    def __init__(self):
        self.policy = validation_policy()
        self.peak_private = 0
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self.sample, daemon=True)
        self.thread.start()

    def sample(self):
        while not self.stop_event.is_set():
            current = process_memory().get("private_bytes", 0)
            with self.lock:
                self.peak_private = max(self.peak_private, current)
            self.stop_event.wait(0.1)

    def emit(self, stage, torch=None, **extra):
        process = process_memory()
        with self.lock:
            self.peak_private = max(self.peak_private, process.get("private_bytes", 0))
            peak = self.peak_private
        row = {"stage": stage, "unix": time.time(), "system": system_memory(), **process,
               "peak_private_bytes_sampled": peak, "sample_interval_s": 0.1,
               "validation_profile": VALIDATION_PROFILE, "offload_mode": "sequential",
               "weights_storage": self.policy["weights_storage"], "weight_dtype": "float16", **extra}
        if torch is not None and torch.cuda.is_initialized():
            row.update(gpu_reserved_bytes=torch.cuda.memory_reserved(), gpu_peak_reserved_bytes=torch.cuda.max_memory_reserved(),
                       gpu_allocated_bytes=torch.cuda.memory_allocated())
        print(json.dumps({"resources": row}), flush=True)
        return row

    def close(self):
        self.stop_event.set()
        self.thread.join(timeout=2)


def defaults(numbers=None):
    if numbers is None:
        try:
            name = art_job.sdxl_path().name
        except RuntimeError:
            name = "SDXL"
        numbers = art_job.painter_numbers(name)
    sampler = {"euler": "euler", "euler_a": "euler-sde", "euler-sde": "euler-sde", "heun": "heun"}.get(str(numbers[2]).lower(), "dpmpp")
    return {"steps": max(10, min(60, int(numbers[0]))), "cfg": max(1.0, min(10.0, float(numbers[1]))), "sampler": sampler, "schedule": "simple"}


def schedule(pipe, sampling):
    from diffusers import (DPMSolverMultistepScheduler, EulerAncestralDiscreteScheduler,
                           EulerDiscreteScheduler, HeunDiscreteScheduler)
    smp = sampling or {}
    sampler, spacing = smp.get("sampler") or "dpmpp", smp.get("schedule") or "simple"
    if sampler not in SAMPLERS or spacing not in SCHEDULES:
        raise ValueError("SDXL sampling: euler, euler-sde, dpmpp or heun; schedule simple or karras")
    if spacing == "karras" and sampler != "dpmpp":
        raise ValueError("SDXL's Karras schedule uses dpmpp")
    kinds = {"euler": EulerDiscreteScheduler, "euler-sde": EulerAncestralDiscreteScheduler,
             "heun": HeunDiscreteScheduler, "dpmpp": DPMSolverMultistepScheduler}
    options = {"use_karras_sigmas": spacing == "karras", "algorithm_type": "dpmsolver++"} if sampler == "dpmpp" else {}
    pipe.scheduler = kinds[sampler].from_config(pipe.scheduler.config, **options)


def reference(ask, shape, ref, mask):
    """Reference geometry and mask pixels, with the original canvas semantics."""
    from PIL import Image, ImageFilter
    w, h = dimensions(ask, shape)
    place = (ask.get("place") or {}).get(shape)
    if place is not None:
        base, pixels, covered = artist_job.placed(ref, mask, w, h, place)
        strength = float(ask.get("strength") or 0.6) if covered else 1.0
    elif ask.get("fit"):
        base, pixels = artist_job.fitted(ref, mask, w, h)
        strength = 1.0
    else:
        base = artist_job.cover(ref, w, h)
        pixels = artist_job.cover(mask.convert("L"), w, h, Image.BILINEAR) if mask else None
        strength = float(ask.get("strength") or 0.6)
    if pixels is None:
        return base, None, None, strength
    grow, edge, soft, grain = artist_job.mask_opts(ask)
    if soft:
        raise ValueError("SDXL's inpaint mask supports feathered edges; differential diffusion is available with Krea/Qwen")
    if grow:
        pixels = artist_job.grow_mask(pixels, grow)
    feather = pixels.filter(ImageFilter.GaussianBlur(edge)) if edge > 0 else pixels
    return base, pixels, feather, strength


def preview(run, n, steps, enabled, metrics=None):
    """Progress and a cheap latent preview, without another VAE decode."""
    def update(pipe, i, timestep, values):
        if metrics:
            metrics.emit("step", torch=sys.modules.get("torch"), step=i + 1, steps=steps)
            preflight_memory(stage="step")
        row = {"live": n, "step": i + 1, "of": steps}
        if not enabled:
            print(f"SDXL step {i + 1}/{steps}", file=sys.stderr, flush=True)
            return values
        if enabled:
            import torch
            from PIL import Image
            factors = torch.tensor([[0.298, 0.207, 0.208], [0.187, 0.286, 0.173],
                                    [-0.158, 0.189, 0.264], [-0.184, -0.271, -0.473]], device=values["latents"].device)
            rgb = (values["latents"][0].float().permute(1, 2, 0) @ factors).add(1).div(2).clamp(0, 1)
            image = Image.fromarray(rgb.mul(255).byte().cpu().numpy())
            (run / "preview").mkdir(exist_ok=True)
            image.save(run / "preview" / f"{n:02d}.jpg", "JPEG", quality=85)
            row["file"] = f"preview/{n:02d}.jpg"
        print(json.dumps(row), flush=True)
        return values
    return update


def main(run, ask):
    resolution = resolution_of(ask)
    validation = validate_profile(ask)
    metrics = ResourceMetrics() if validation else None
    if metrics:
        metrics.emit("before_import", guard_reason=MEMORY_REASON)
        try:
            preflight_memory()
            storage = validate_model_storage()
        except Exception:
            metrics.close()
            raise
    import torch
    from PIL import Image
    from diffusers import StableDiffusionXLImg2ImgPipeline, StableDiffusionXLInpaintPipeline
    started = time.time()
    if metrics:
        metrics.emit("after_import", torch=torch)
        try:
            preflight_memory(stage="after_import")
        except Exception:
            metrics.close()
            raise
    # The shared loader honours a local folder/file selector and never accesses HF.
    try:
        pipe, name, numbers = art_job.painter()
        if metrics:
            metrics.emit("after_load", torch=torch, model_storage=storage)
        sampling = {**defaults(numbers), **(ask.get("sampling") or {})}
        schedule(pipe, sampling)
        loras = ask.get("loras") or []
        if loras:
            names, weights = [], []
            for i, item in enumerate(loras):
                adapter = f"a{i}"
                path = artist_loras.path_of(art_job.KIT, item["id"])
                pipe.load_lora_weights(str(path.parent), weight_name=path.name, adapter_name=adapter,
                                       local_files_only=True, use_safetensors=True)
                names.append(adapter)
                weights.append(float(item.get("weight", artist_loras.WEIGHT)))
            pipe.set_adapters(names, adapter_weights=weights)
            print(json.dumps({"loras": [{"id": x["id"], "weight": weights[i]} for i, x in enumerate(loras)]}), flush=True)
        steps = int(sampling.get("steps") or numbers[0])
        guidance = float(sampling.get("cfg", numbers[1]))
        pipe.vae.enable_tiling()
        ref = Image.open(run / ask["ref"]).convert("RGB") if ask.get("ref") else None
        mask = Image.open(run / ask["mask"]).convert("L") if ask.get("mask") else None
        # One pipeline per request, sharing loaded components; offload moves components
        # between CPU and CUDA instead of keeping the whole model in VRAM.
        if ref is not None:
            masked = mask is not None or bool(ask.get("fit")) or bool(ask.get("place"))
            cls = StableDiffusionXLInpaintPipeline if masked else StableDiffusionXLImg2ImgPipeline
            pipe = cls.from_pipe(pipe)
        if validation:
            # Never .to(cuda) first: keep the original CPU state_dict for leaf hooks.
            # LoRA/refs are rejected above; their memory/hook interaction is unverified.
            pipe.enable_sequential_cpu_offload(gpu_id=0)
        else:
            pipe.enable_model_cpu_offload(gpu_id=0)
        if metrics:
            metrics.emit("before_inference", torch=torch)
            preflight_memory(stage="before_inference")
        (run / "thumbs").mkdir(exist_ok=True)
        seed, count = int(ask["seed"]), max(1, min(4, int(ask.get("count") or 1)))
        shapes = [s for s in ask.get("shapes") or ["1:1"] if s in SHAPES]
        if not shapes:
            raise ValueError("SDXL needs a supported shape")
        classifier, n = None, 0
        for k in range(count):
            for shape in shapes:
                n += 1
                t0 = time.time()
                w, h = dimensions(ask, shape)
                kwargs = {"prompt": str(ask["prompt"]), "negative_prompt": art_job.NEGATIVE,
                          "height": h, "width": w, "num_inference_steps": steps,
                          "guidance_scale": guidance, "generator": torch.Generator("cpu").manual_seed(seed + k),
                          "callback_on_step_end": preview(run, n, steps, bool(ask.get("preview")), metrics=metrics),
                          "callback_on_step_end_tensor_inputs": ["latents"]}
                feather, base = None, None
                if ref is not None:
                    base, pixels, feather, strength = reference(ask, shape, ref, mask)
                    kwargs.update(image=base, strength=strength)
                    if isinstance(pipe, StableDiffusionXLInpaintPipeline):
                        kwargs["mask_image"] = pixels if pixels is not None else Image.new("L", (w, h), 255)
                image = pipe(**kwargs).images[0].convert("RGB")
                if feather is not None:
                    image = artist_job.composite(image, base, feather, artist_job.mask_opts(ask)[3])
                score = None
                if (art_job.FILTER / "config.json").is_file():
                    classifier = classifier or art_job.content_filter()
                    scores = {r["label"].lower(): r["score"] for r in classifier(image)}
                    score = round(scores.get("nsfw", 0.0), 3)
                low, high = image.convert("L").getextrema()
                if high - low < 8:
                    raise RuntimeError("SDXL produced a flat image; it was not kept")
                row = {"n": n, "shape": shape, "seed": seed + k, "w": w, "h": h, "nsfw": score,
                       "took": round(time.time() - t0, 1), "kept": score is None or score < 0.5}
                if ref is not None:
                    row["ref"] = kwargs["strength"]
                if feather is not None:
                    row["masked"] = True
                if row["kept"]:
                    filename = f"{n:02d}-{shape.replace(':', 'x')}-s{seed + k}"
                    image.save(run / (filename + ".png"))
                    small = image.copy()
                    small.thumbnail((512, 512), resample=Image.LANCZOS)
                    small.save(run / "thumbs" / (filename + ".jpg"), "JPEG", quality=85, optimize=True)
                    row.update(file=filename + ".png", thumb="thumbs/" + filename + ".jpg")
                print(json.dumps(row), flush=True)
    finally:
        if metrics:
            pipe = None
            image = None
            classifier = None
            gc.collect()
            if torch.cuda.is_initialized():
                torch.cuda.empty_cache()
            metrics.emit("after_delete", torch=torch)
            metrics.close()
    print(json.dumps({"done": True, "painter": "sdxl", "model": name, "steps": steps, "cfg": guidance, "resolution": resolution,
                      "offload_mode": "sequential" if validation else "component",
                      "validation_profile": VALIDATION_PROFILE if validation else None,
                      "took": round(time.time() - started, 1),
                      "peak_gb": round(torch.cuda.max_memory_reserved() / 2 ** 30, 1)}), flush=True)
