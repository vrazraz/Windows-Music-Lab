"""Synthetic Windows Artist checks; no ML imports, weights or inference."""
import base64
from contextlib import ExitStack, nullcontext
import io
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "lab"))
import art_job
import artist
import artist_job
import artist_loras
import artist_sdxl
import artist_upscale


class ArtistWindowsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="Artist Unicode ")
        self.kit = Path(self.temp.name) / "Музыка 🎨"
        self.kit.mkdir()
        self.stack = ExitStack()
        self.stack.enter_context(patch.object(art_job, "KIT", self.kit))
        for key, path in (("LINK", "SDXL-Artwork-Model"), ("OURS", "CyberRealistic-XL-v10"),
                          ("NUMBERS", "SDXL-Artwork-Model.json")):
            self.stack.enter_context(patch.object(art_job, key, self.kit / "artwork" / path))
        self.stack.enter_context(patch.object(artist_upscale, "UPSCALERS", self.kit / "artwork/upscalers"))
        self.old_h = dict(artist.H)
        artist.H.clear()
        artist.setup(kit=self.kit, py=Path(sys.executable), jobs={}, lock=threading.RLock(),
                     painter=lambda value: value or "sdxl", wait_card=lambda *a: None,
                     turn=lambda *a: nullcontext(), free_gpu=lambda *a: (0, None), say=lambda *a: None)

    def tearDown(self):
        artist.H.clear()
        artist.H.update(self.old_h)
        self.stack.close()
        self.temp.cleanup()

    def component(self, name, shards=None):
        d = self.kit / "artwork" / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "config.json").write_text("{}", encoding="utf-8")
        if shards:
            (d / "model.safetensors.index.json").write_text(json.dumps({"weight_map": shards}), encoding="utf-8")
        else:
            (d / "model.fp16.safetensors").write_bytes(b"fixture, never loaded")
        return d

    def adapter(self):
        d = self.kit / "artwork/loras/sdxl/Набор"
        d.mkdir(parents=True)
        p = d / "Цвета.safetensors"
        header = json.dumps({"__metadata__": {"modelspec.trigger_phrase": "warm colours"}}).encode()
        p.write_bytes(struct.pack("<Q", len(header)) + header)
        return p, "sdxl/Набор/Цвета.safetensors"

    def test_missing_artist_python_fails_before_queue_or_files(self):
        artist.H["py"] = self.kit / ".venv-art/Scripts/python.exe"
        with self.assertRaisesRegex(RuntimeError, "Artist environment"):
            artist.draw({"prompt": "synthetic", "shapes": ["1:1"]})
        self.assertEqual(artist.H["jobs"], {})
        self.assertFalse((self.kit / "artist").exists())

    def test_sdxl_local_selector_uses_unicode_folder_without_symlink(self):
        d = self.component("Модель SDXL")
        art_job.NUMBERS.write_text(json.dumps({"model": d.name}), encoding="utf-8")
        self.assertEqual(art_job.sdxl_path(), d.resolve())

    def test_sdxl_selector_rejects_windows_absolute_and_traversal(self):
        art_job.NUMBERS.parent.mkdir(parents=True)
        for name in ("C:/secret/model", "\\\\server\\share", "../outside", "/absolute"):
            art_job.NUMBERS.write_text(json.dumps({"model": name}), encoding="utf-8")
            with self.subTest(name=name), self.assertRaises(RuntimeError):
                art_job.sdxl_path()

    def test_missing_or_malformed_sdxl_selector_is_explicit(self):
        art_job.NUMBERS.parent.mkdir(parents=True)
        art_job.NUMBERS.write_text('{"model":"absent"}', encoding="utf-8")
        self.assertFalse(artist.sdxl_ready())
        art_job.NUMBERS.write_text('{', encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "Invalid artwork"):
            art_job.sdxl_path()

    def test_complete_model_is_required_not_only_index(self):
        d = self.component("weights", {"a": "part-1.safetensors", "b": "part-2.safetensors"})
        (d / "part-1.safetensors").write_bytes(b"one")
        self.assertFalse(artist._model_weights_ready(d))
        (d / "part-2.safetensors").write_bytes(b"")
        self.assertFalse(artist._model_weights_ready(d))
        (d / "part-2.safetensors").write_bytes(b"two")
        self.assertTrue(artist._model_weights_ready(d))

    def test_index_cannot_escape_component(self):
        d = self.component("weights", {"a": "../outside.safetensors"})
        (d.parent / "outside.safetensors").write_bytes(b"outside")
        self.assertFalse(artist._model_weights_ready(d))

    def test_reference_and_mask_data_preserve_uploaded_fixture_bytes(self):
        data = b"\x89PNG\r\n\x1a\nsynthetic"
        url = "data:image/png;base64," + base64.b64encode(data).decode()
        ref, label, strength = artist._reference({"ref": url, "strength": 0.42})
        self.assertEqual(ref, (".png", data))
        self.assertEqual(strength, 0.42)
        self.assertEqual(artist._mask({"mask": url}), data)
        with self.assertRaises(ValueError):
            artist._reference({"ref": url, "strength": 2})
        with self.assertRaises(ValueError):
            artist._mask({"mask": "data:image/png;base64,cGxhaW4="})

    def test_canvas_places_retain_values_and_reject_invalid_shapes(self):
        self.assertEqual(artist._places({"1:1": {"x": 0.5, "y": -0.2, "s": 1.2}, "bad": {}}),
                         {"1:1": {"x": 0.5, "y": -0.2, "s": 1.2}})
        with self.assertRaises(ValueError):
            artist._places({"1:1": {"x": 9, "y": 0.5, "s": 1}})

    def test_local_lora_metadata_strengths_and_family_are_retained(self):
        p, lid = self.adapter()
        self.assertEqual(artist_loras.path_of(self.kit, lid), p)
        self.assertEqual(artist_loras.known(p)["words"], ["warm colours"])
        chosen = artist_loras.chosen(self.kit, "sdxl", [{"id": lid, "weight": 0.7}, {"id": lid, "weight": 0.9}])
        self.assertEqual(len(chosen), 1)
        self.assertEqual(chosen[0]["weight"], 0.7)
        self.assertEqual(artist_loras.chosen(self.kit, "sdxl", [{"id": lid, "weight": 0}]), [])
        with self.assertRaises(ValueError):
            artist_loras.chosen(self.kit, "qwen21", [{"id": lid}])

    def test_lora_path_rejects_absolute_unc_colon_and_parent(self):
        for lid in ("sdxl/../outside.safetensors", "C:/sdxl/a.safetensors", "\\\\server\\sdxl\\a.safetensors", "sdxl/C:/a.safetensors"):
            with self.subTest(lid=lid), self.assertRaises(ValueError):
                artist_loras.path_of(self.kit, lid)

    def test_civitai_is_disabled_without_network_or_file_side_effect(self):
        _, lid = self.adapter()
        with patch.dict(os.environ, {"WINDOWS_MUSIC_LAB_LOCAL_ONLY": "1"}), patch.object(artist_loras, "_get") as get:
            with self.assertRaisesRegex(ValueError, "disabled"):
                artist_loras.civitai(self.kit, lid, {})
            get.assert_not_called()
        self.assertFalse(list(self.kit.rglob("*.civitai.info")))

    def test_upscaler_path_rejects_windows_absolute_and_parent(self):
        d = artist_upscale.UPSCALERS
        d.mkdir(parents=True)
        (d / "4x-Данные.safetensors").write_bytes(b"fixture")
        self.assertEqual(artist_upscale.model_path("4x-Данные.safetensors"), d / "4x-Данные.safetensors")
        for name in ("../outside.pth", "C:/outside.pth", "\\\\server\\share\\outside.pth", "/outside.pth"):
            with self.subTest(name=name), self.assertRaises(RuntimeError):
                artist_upscale.model_path(name)

    def test_sdxl_sampler_family_gate_is_not_flow_matching(self):
        self.assertEqual(artist.sampling("sdxl", {"steps": 24, "sampler": "dpmpp", "schedule": "karras", "cfg": 5.5})["cfg"], 5.5)
        for values in ({"sampler": "er_sde"}, {"schedule": "beta57"}, {"sampler": "euler", "schedule": "karras"}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                artist.sampling("sdxl", values)

    def test_sdxl_worker_dispatches_without_loading_other_painters(self):
        run = self.kit / "run"
        run.mkdir()
        (run / "ask.json").write_text('{"prompt":"synthetic","seed":1}', encoding="utf-8")
        with patch.dict(os.environ, {"ART_PAINTER": "sdxl"}), patch.object(sys, "argv", ["artist_job.py", str(run)]), \
             patch.object(artist_job, "configure_runtime") as configure, patch.object(artist_sdxl, "main", return_value="routed") as main:
            self.assertEqual(artist_job.main(), "routed")
            configure.assert_called_once_with(art_job.KIT, artist=True)
            main.assert_called_once()

    def synthetic_work(self, code, quiet=None):
        here = self.kit / "worker"
        here.mkdir()
        (here / "artist_job.py").write_text(code, encoding="utf-8")
        rid = "20261012-120000-abcd"
        d = self.kit / "artist" / rid
        d.mkdir(parents=True)
        run = {"id": rid, "painter": "upscale", "of": 1, "pictures": [], "status": "queued"}
        job = {"status": "queued"}
        artist.H["jobs"]["artist:" + rid] = job
        with patch.object(artist, "HERE", here), patch.object(artist, "QUIET_LOAD", quiet if quiet is not None else 600):
            artist.work(d, run, job)
        self.assertEqual(artist.H["jobs"], {})
        return artist.read(d)

    def test_real_stdlib_child_unicode_protocol_and_cleanup(self):
        result = self.synthetic_work('import json,sys\nprint("Диагностика 🎨",file=sys.stderr,flush=True)\nprint(json.dumps({"n":1,"kept":True,"caption":"Тест 🎨"}),flush=True)\nprint(json.dumps({"done":True,"took":0.1}),flush=True)\n')
        self.assertEqual(result["status"], "done")
        self.assertEqual(result["pictures"][0]["caption"], "Тест 🎨")

    def test_failed_stdlib_child_records_error_and_cleans_queue(self):
        result = self.synthetic_work('import sys\nprint("Синтетическая ошибка",file=sys.stderr,flush=True)\nsys.exit(7)\n')
        self.assertEqual(result["status"], "failed")
        self.assertIn("Синтетическая ошибка", result["error"])

    def test_quiet_stdlib_child_is_stopped_instead_of_hanging(self):
        started = time.monotonic()
        result = self.synthetic_work('import time\ntime.sleep(20)\n', quiet=0.2)
        self.assertLess(time.monotonic() - started, 8)
        self.assertEqual(result["status"], "failed")
        self.assertIn("said nothing", result["error"])

    def sdxl_fixture(self, *, reference=False, masked=False, lora=False, resolution=1024, validation=False):
        run = self.kit / "SDXL worker protocol"
        run.mkdir()
        image = MagicMock(name="synthetic image")
        image.convert.return_value = image
        image.getextrema.return_value = (0, 255)
        image.copy.return_value = image
        image.size = (1024, 1024)
        image.save.side_effect = lambda path, *a, **kw: Path(path).write_bytes(b"synthetic image protocol fixture")
        image_module = types.ModuleType("PIL.Image")
        image_module.open = MagicMock(return_value=image)
        image_module.new = MagicMock(return_value=image)
        image_module.LANCZOS = 1
        pil = types.ModuleType("PIL")
        pil.Image = image_module
        torch = MagicMock()
        torch.cuda.max_memory_reserved.return_value = 1024
        torch.cuda.is_initialized.return_value = False
        diffusers = types.ModuleType("diffusers")
        calls = []
        class Pipe:
            def __init__(self):
                self.vae = MagicMock()
                self.load_lora_weights = MagicMock()
                self.set_adapters = MagicMock()
                self.enable_model_cpu_offload = MagicMock()
                self.enable_sequential_cpu_offload = MagicMock()
                self.to = MagicMock()
            def __call__(self, **kwargs):
                calls.append(kwargs)
                kwargs["callback_on_step_end"](self, 0, None, {"latents": "not computed"})
                return types.SimpleNamespace(images=[image])
            @classmethod
            def from_pipe(cls, pipe):
                out = cls()
                out.vae = pipe.vae
                out.load_lora_weights = pipe.load_lora_weights
                out.set_adapters = pipe.set_adapters
                return out
        class Img2Img(Pipe):
            pass
        class Inpaint(Pipe):
            pass
        diffusers.StableDiffusionXLImg2ImgPipeline = Img2Img
        diffusers.StableDiffusionXLInpaintPipeline = Inpaint
        base = Pipe()
        ask = {"prompt": "synthetic only", "seed": 40, "count": 2, "shapes": ["1:1", "16:9"], "preview": False, "resolution": resolution}
        if validation:
            ask.update(count=1,shapes=["1:1"],sampling={"steps":12},validation_profile=artist_sdxl.VALIDATION_PROFILE)
        if reference:
            ask["ref"] = "ref.png"
        if masked:
            ask["mask"] = "mask.png"
        if lora:
            _, lid = self.adapter()
            ask["loras"] = [{"id": lid, "weight": 0.4}]
        with patch.dict(sys.modules, {"torch": torch, "PIL": pil, "PIL.Image": image_module, "diffusers": diffusers}), \
             patch.object(art_job, "FILTER", self.kit / "no filter"), \
             patch.object(art_job, "painter", return_value=(base, "synthetic SDXL", (20, 5.5, "dpmpp"))), \
             patch.object(artist_sdxl, "system_memory", return_value={"available": 16 * 2 ** 30, "commit_available": 24 * 2 ** 30}), \
             patch.object(artist_sdxl, "schedule"), \
             patch.object(artist_sdxl, "validate_model_storage", return_value={"all_tensors_fp16":True,"fixture":True}), \
             patch.object(artist_sdxl, "reference", return_value=(image, image if masked else None, image if masked else None, 0.6)) as geometry, \
             patch.object(artist_job, "composite", return_value=image) as composite, \
             patch("sys.stdout", new_callable=io.StringIO) as stdout, patch("sys.stderr", new_callable=io.StringIO):
            artist_sdxl.main(run, ask)
        rows = [json.loads(line) for line in stdout.getvalue().splitlines()]
        return run, rows, calls, base, geometry, composite

    def test_sdxl_text_worker_uses_cpu_offload_seeds_shapes_and_json_outputs(self):
        run, rows, calls, base, _, _ = self.sdxl_fixture()
        self.assertEqual(len(calls), 4)
        self.assertEqual([(c["width"], c["height"]) for c in calls], [(1024, 1024), (1344, 768)] * 2)
        self.assertEqual([r["seed"] for r in rows if "n" in r], [40, 40, 41, 41])
        self.assertEqual(len(list(run.glob("*.png"))), 4)
        self.assertEqual(rows[-1]["painter"], "sdxl")
        self.assertTrue(rows[-1]["done"])
        base.vae.enable_tiling.assert_called_once()
        base.enable_model_cpu_offload.assert_called_once_with(gpu_id=0)
        self.assertNotIn("image", calls[0])

    def test_sdxl_img2img_worker_passes_local_reference_strength(self):
        _, rows, calls, _, geometry, composite = self.sdxl_fixture(reference=True)
        self.assertEqual(geometry.call_count, 4)
        self.assertIn("image", calls[0])
        self.assertEqual(calls[0]["strength"], 0.6)
        self.assertNotIn("mask_image", calls[0])
        composite.assert_not_called()
        self.assertTrue(rows[-1]["done"])

    def test_sdxl_inpaint_worker_passes_mask_and_keeps_composite(self):
        _, rows, calls, _, geometry, composite = self.sdxl_fixture(reference=True, masked=True)
        self.assertEqual(geometry.call_count, 4)
        self.assertIn("mask_image", calls[0])
        self.assertEqual(composite.call_count, 4)
        self.assertTrue(all(r["masked"] for r in rows if "n" in r))

    def test_sdxl_lora_worker_loads_only_local_safetensors_with_strength(self):
        _, _, _, base, _, _ = self.sdxl_fixture(lora=True)
        args, kwargs = base.load_lora_weights.call_args
        self.assertEqual(Path(args[0]).name, "Набор")
        self.assertEqual(kwargs["weight_name"], "Цвета.safetensors")
        self.assertTrue(kwargs["local_files_only"])
        self.assertTrue(kwargs["use_safetensors"])
        base.set_adapters.assert_called_once_with(["a0"], adapter_weights=[0.4])

    def test_idle_engine_handoff_occurs_inside_gpu_lease_before_child(self):
        events, active = [], {"held": False}
        class Lease:
            def __enter__(self):
                active["held"] = True
                events.append("lease")
            def __exit__(self, *args):
                active["held"] = False
                events.append("release")
        def handoff(gpu, need, why):
            self.assertTrue(active["held"])
            self.assertEqual(gpu, 0)
            events.append("handoff")
        original_popen = artist.subprocess.Popen
        def spawn(*args, **kwargs):
            self.assertTrue(active["held"])
            self.assertEqual(events[-1], "handoff")
            events.append("spawn")
            return original_popen(*args, **kwargs)
        artist.H["gpu_handoff"] = handoff
        with patch.object(artist, "gpu_lease", return_value=Lease()), patch.object(artist.subprocess, "Popen", side_effect=spawn):
            result = self.synthetic_work('import json\nprint(json.dumps({"done":True,"took":0}),flush=True)\n')
        self.assertEqual(result["status"], "done")
        self.assertEqual(events, ["lease", "handoff", "spawn", "release"])

    def test_sdxl_resolution_dimensions_and_invalid_values(self):
        self.assertEqual(artist_sdxl.dimensions({}, "1:1"), (1024, 1024))
        self.assertEqual(artist_sdxl.dimensions({"resolution":512}, "1:1"), (512, 512))
        self.assertEqual(artist_sdxl.dimensions({"resolution":512}, "16:9"), (672, 384))
        self.assertEqual(artist_sdxl.dimensions({"resolution":512}, "9:16"), (384, 672))
        for value in (0, 256, 768, 2048, True, None, 512.0, "512x512"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                artist_sdxl.resolution_of({"resolution":value})

    def test_memory_preflight_requires_commit_and_ram_independently(self):
        self.assertEqual(artist_sdxl.preflight_memory({"available":9*2**30,"commit_available":int(11.5*2**30)})["available"],9*2**30)
        for snapshot in ({"available":32*2**30,"commit_available":8*2**30},
                         {"available":8*2**30,"commit_available":32*2**30},
                         {"available":32*2**30}):
            with self.subTest(snapshot=snapshot), self.assertRaises(RuntimeError):
                artist_sdxl.preflight_memory(snapshot)

    def test_memory_failure_happens_before_torch_or_pipeline_import(self):
        original_import = __import__
        imported = []
        def observe(name, *args, **kwargs):
            imported.append(name)
            return original_import(name, *args, **kwargs)
        with patch.object(artist_sdxl, "system_memory", return_value={"available":32*2**30,"commit_available":8*2**30}), \
             patch("builtins.__import__", side_effect=observe), patch.object(art_job, "painter") as painter:
            with self.assertRaisesRegex(RuntimeError,r"11\.5 GiB commit"):
                artist_sdxl.main(self.kit,{"resolution":512,"validation_profile":artist_sdxl.VALIDATION_PROFILE,"count":1,"shapes":["1:1"],"sampling":{"steps":12}})
            painter.assert_not_called()
        self.assertNotIn("torch",imported)
        self.assertNotIn("diffusers",imported)

    def test_sdxl512_worker_reports_and_uses512_geometry(self):
        _, rows, calls, _, _, _ = self.sdxl_fixture(resolution=512)
        self.assertEqual([(c["width"],c["height"]) for c in calls],[(512,512),(672,384)]*2)
        self.assertEqual(rows[-1]["resolution"],512)
        self.assertEqual([(r["w"],r["h"]) for r in rows if "n" in r],[(512,512),(672,384)]*2)

    def test_sdxl512_refs_masks_fit_and_place_use_same_target_dimensions(self):
        image = MagicMock()
        pil = types.ModuleType("PIL")
        pil.Image = types.SimpleNamespace(BILINEAR=2)
        pil.ImageFilter = MagicMock()
        ask = {"resolution":512,"strength":0.4,"mask_opts":{"edge":0,"soft":False}}
        with patch.dict(sys.modules,{"PIL":pil}), patch.object(artist_job,"cover",return_value=image) as cover:
            artist_sdxl.reference(ask,"16:9",image,image)
            self.assertEqual(cover.call_args_list[0].args[1:],(672,384))
            self.assertEqual(cover.call_args_list[1].args[1:3],(672,384))
        with patch.dict(sys.modules,{"PIL":pil}), patch.object(artist_job,"fitted",return_value=(image,image)) as fitted:
            artist_sdxl.reference({**ask,"fit":True},"1:1",image,image)
            self.assertEqual(fitted.call_args.args[2:],(512,512))
        place={"x":0.5,"y":0.5,"s":0.8}
        with patch.dict(sys.modules,{"PIL":pil}), patch.object(artist_job,"placed",return_value=(image,image,False)) as placed:
            artist_sdxl.reference({**ask,"place":{"9:16":place}},"9:16",image,image)
            self.assertEqual(placed.call_args.args[2:],(384,672,place))

    def test_sdxl_defaults_match_local_selector_numbers(self):
        self.assertEqual(artist_sdxl.defaults((20,5.0,"Euler")),{"steps":20,"cfg":5.0,"sampler":"euler","schedule":"simple"})

    def test_sdxl_api_preserves_resolution_and_rejects_invalid_before_creation(self):
        with patch.object(artist,"sdxl_ready",return_value=True), patch.object(artist.threading,"Thread"):
            with self.assertRaises(ValueError):
                artist.draw({"prompt":"synthetic","painter":"sdxl","shapes":["1:1"],"resolution":2048})
            self.assertFalse((self.kit/"artist").exists())
            run=artist.draw({"prompt":"synthetic","painter":"sdxl","shapes":["1:1"],"resolution":512})
            self.assertEqual(run["resolution"],512)
            self.assertEqual(json.loads((self.kit/"artist"/run["id"]/"ask.json").read_text(encoding="utf-8"))["resolution"],512)

    def test_validation_profile_is_limited_to_single512_text_frame(self):
        valid={"resolution":512,"validation_profile":artist_sdxl.VALIDATION_PROFILE,"count":1,"shapes":["1:1"],"sampling":{"steps":12}}
        self.assertTrue(artist_sdxl.validate_profile(valid))
        self.assertFalse(artist_sdxl.validate_profile({"resolution":1024}))
        for change in ({"count":2},{"resolution":1024},{"shapes":["16:9"]},{"loras":[{}]},{"ref":"ref.png"},{"sampling":{"steps":8}}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                artist_sdxl.validate_profile({**valid,**change})

    def test_validation_metrics_are_serialized_and_cleanup_stage_recorded(self):
        _,rows,calls,base,_,_=self.sdxl_fixture(resolution=512,validation=True)
        base.enable_sequential_cpu_offload.assert_called_once_with(gpu_id=0)
        base.enable_model_cpu_offload.assert_not_called()
        base.to.assert_not_called()
        self.assertEqual(rows[-1]["offload_mode"],"sequential")
        self.assertEqual(len(calls),1)
        stages=[row["resources"]["stage"] for row in rows if "resources" in row]
        self.assertEqual(stages,["before_import","after_import","after_load","before_inference","step","after_delete"])
        for row in rows:
            if "resources" in row:
                self.assertEqual(row["resources"]["offload_mode"],"sequential")
                self.assertEqual(row["resources"]["weight_dtype"],"float16")
                self.assertIn("COW",row["resources"]["weights_storage"])
                self.assertGreater(row["resources"]["private_bytes"],0)
                self.assertGreaterEqual(row["resources"]["peak_private_bytes_sampled"],row["resources"]["private_bytes"])
        self.assertTrue(rows[-1]["done"])

    def test_resource_protocol_does_not_add_fake_pictures(self):
        result=self.synthetic_work('import json\nprint(json.dumps({"resources":{"stage":"before_import","private_bytes":123}}),flush=True)\nprint(json.dumps({"done":True,"took":0}),flush=True)\n')
        self.assertEqual(result["pictures"],[])
        self.assertEqual(result["resources"][0]["private_bytes"],123)

    def test_after_import_guard_checks_remaining_model_load_budget(self):
        self.assertEqual(artist_sdxl.preflight_memory({"available":8*2**30,"commit_available":int(9.5*2**30)},stage="after_import")["commit_available"],int(9.5*2**30))
        with self.assertRaises(RuntimeError):
            artist_sdxl.preflight_memory({"available":8*2**30-1,"commit_available":int(9.5*2**30)},stage="after_import")

    def test_sdxl_loader_explicitly_keeps_local_fp16_low_cpu_mmap(self):
        base=self.kit/"artwork"/"approved folder"; (base/"unet").mkdir(parents=True)
        (base/"model_index.json").write_text('{"_class_name":"StableDiffusionXLPipeline"}',encoding="utf-8")
        (base/"unet/diffusion_pytorch_model.fp16.safetensors").write_bytes(b"synthetic header only")
        torch=types.ModuleType("torch");torch.float16="float16-marker"
        diffusers=types.ModuleType("diffusers");loader=MagicMock();scheduler=MagicMock()
        diffusers.StableDiffusionXLPipeline=loader;diffusers.DPMSolverMultistepScheduler=scheduler
        pipe=loader.from_pretrained.return_value
        with patch.dict(sys.modules,{"torch":torch,"diffusers":diffusers}), \
             patch.dict(os.environ,{"ART_PAINTER":"sdxl"}),patch.object(art_job,"sdxl_path",return_value=base):
            result=art_job.painter()
        self.assertIs(result[0],pipe)
        loader.from_pretrained.assert_called_once_with(base,torch_dtype="float16-marker",use_safetensors=True,
            variant="fp16",local_files_only=True,low_cpu_mem_usage=True,disable_mmap=False)
        pipe.to.assert_not_called()

    def test_live_memory_guard_failure_cleans_model_without_saving_frame(self):
        metrics=MagicMock()
        def guard(snapshot=None,stage="before_import"):
            if stage=="step":raise RuntimeError("synthetic commit pressure")
            return {"available":16*2**30,"commit_available":24*2**30}
        with patch.object(artist_sdxl,"preflight_memory",side_effect=guard), \
             patch.object(artist_sdxl,"ResourceMetrics",return_value=metrics):
            with self.assertRaisesRegex(RuntimeError,"synthetic commit pressure"):
                self.sdxl_fixture(resolution=512,validation=True)
        metrics.close.assert_called_once()
        self.assertEqual(metrics.emit.call_args.args[0],"after_delete")
        self.assertFalse(list(self.kit.rglob("*.png")))

    def test_sequential_policy_budget_counts_windows_mapping_commit(self):
        policy=artist_sdxl.validation_policy()
        self.assertFalse(policy["measured_inference_bound"])
        self.assertFalse(policy["loras"])
        self.assertEqual(policy["production_offload_mode"],"component")
        for stage,ram,commit in [("before_import",9,11.5),("after_import",8,9.5),("before_inference",1,2),("step",1,2)]:
            snapshot={"available":int(ram*2**30),"commit_available":int(commit*2**30)}
            self.assertEqual(artist_sdxl.preflight_memory(snapshot,stage),snapshot)
            for key in snapshot:
                with self.subTest(stage=stage,key=key),self.assertRaises(RuntimeError):
                    artist_sdxl.preflight_memory({**snapshot,key:snapshot[key]-1},stage)
        self.assertIn("still consume commit",policy["reason"])

    def test_measured_import_allowance_corrects_future_admission_only(self):
        self.assertEqual(artist_sdxl.MIN_COMMIT_BYTES,int(11.5*2**30))
        after_ram,after_commit=artist_sdxl.PHASE_GUARDS["after_import"]
        self.assertEqual(after_commit,int(9.5*2**30))
        self.assertEqual(artist_sdxl.MIN_COMMIT_BYTES-after_commit,2*2**30)
        self.assertEqual(artist_sdxl.PHASE_GUARDS["step"],(2**30,2*2**30))
        with self.assertRaisesRegex(RuntimeError,r"11\.5 GiB commit"):
            artist_sdxl.preflight_memory({"available":18*2**30,"commit_available":12012298240})
        with self.assertRaisesRegex(RuntimeError,"9.5 GiB commit"):
            artist_sdxl.preflight_memory({"available":17812267008,"commit_available":9904226304},"after_import")

    def test_validation_headers_require_fp16_without_loading_tensors(self):
        base=self.kit/"local model";sizes={}
        for name in artist_sdxl.VALIDATION_WEIGHTS:
            p=base/name;p.parent.mkdir(parents=True,exist_ok=True)
            header=json.dumps({"weight":{"dtype":"F16","shape":[2],"data_offsets":[0,4]}}).encode()
            p.write_bytes(struct.pack("<Q",len(header))+header+b"\0"*4)
            sizes[name]=p.stat().st_size
        with patch.object(artist_sdxl,"VALIDATION_WEIGHTS",sizes):
            value=artist_sdxl.validate_model_storage(base)
            self.assertTrue(value["all_tensors_fp16"])
            self.assertEqual(value["tensor_bytes"],16)
            self.assertEqual(value["tensor_count"],4)
            p=base/next(iter(sizes))
            p.write_bytes(p.read_bytes().replace(b"F16",b"F32"))
            with self.assertRaisesRegex(RuntimeError,"unchanged fp16"):
                artist_sdxl.validate_model_storage(base)
            p.write_bytes(b"partial")
            with self.assertRaisesRegex(RuntimeError,"missing/partial"):
                artist_sdxl.validate_model_storage(base)

    def harness_module(self):
        import importlib.util
        spec=importlib.util.spec_from_file_location("one_frame_harness",ROOT/"windows/Test-Artist-OneFrame.py")
        harness=importlib.util.module_from_spec(spec);spec.loader.exec_module(harness)
        return harness

    def test_plan_reports_existing_claim_without_submission(self):
        harness=self.harness_module();claim=self.kit/"synthetic claim.json"
        with patch.object(harness,"CLAIM",claim):
            self.assertFalse(harness.plan()["existing_claim_blocks_execution"])
            claim.write_text('{"status":"failed_or_uncertain"}',encoding="utf-8")
            review=harness.plan()
            self.assertTrue(review["existing_claim_blocks_execution"])
            self.assertFalse(review["submission_performed"])
            self.assertEqual(review["commit_headroom_min_bytes"],int(11.5*2**30))

    def standalone_fixture(self, worker_exit=0, timed_out=False, mutate=None, gpu_failure=False):
        harness=self.harness_module()
        memory={"available":16*2**30,"commit_available":24*2**30,
                "commit_scope":"machine","commit_source":"GetPerformanceInfo(machine-wide)"}
        stages=["before_import","after_import","after_load","before_inference"]+["step"]*12+["after_delete"]
        resources=[];step=0
        for stage in stages:
            row={"stage":stage,"system":dict(memory),"offload_mode":"sequential","validation_profile":artist_sdxl.VALIDATION_PROFILE,"weight_dtype":"float16"}
            if stage=="step":step+=1;row["step"]=step
            resources.append(row)
        picture={"n":1,"shape":"1:1","seed":20261012,"w":512,"h":512,"kept":True,"file":"01-1x1-s20261012.png"}
        final={"done":True,"painter":"sdxl","resolution":512,"steps":12,"offload_mode":"sequential","validation_profile":artist_sdxl.VALIDATION_PROFILE,"took":1.2,"peak_gb":2.0}
        rows=[{"resources":row} for row in resources]+[picture,final]
        if mutate:mutate(rows)
        stdout="\n".join(json.dumps(row) for row in rows)+"\n"
        interpreter=self.kit/".venv-art/Scripts/python.exe";interpreter.parent.mkdir(parents=True);interpreter.write_bytes(b"inert fixture")
        worker=self.kit/"lab/artist_job.py";worker.parent.mkdir();worker.write_text("# synthetic, never executed",encoding="utf-8")
        cache=self.kit/"one-frame-cache";claim=cache/"claim.json";events=[];held={"lease":False,"ports":False}
        class Lease:
            def __enter__(inner):events.append("lease");held["lease"]=True;return inner
            def __exit__(inner,*args):held["lease"]=False;events.append("release")
        class Ports:
            def __enter__(inner):held["ports"]=True;return {"ports":[41868,41871,41872]}
            def __exit__(inner,*args):held["ports"]=False
        class Child:
            returncode=None
            def wait(inner,timeout):
                if timed_out:raise harness.subprocess.TimeoutExpired("synthetic child",timeout)
                inner.returncode=worker_exit;return worker_exit
            def poll(inner):return inner.returncode
        child=Child()
        def launch(args,**kw):
            self.assertTrue(held["lease"]);self.assertTrue(held["ports"]);self.assertTrue(claim.exists())
            self.assertEqual(args[:2],[str(interpreter),str(worker)])
            self.assertEqual(kw["env"]["ART_PAINTER"],"sdxl")
            self.assertEqual(kw["env"]["HF_HUB_OFFLINE"],"1")
            self.assertEqual(kw["env"]["RUACH_GPU_MUTEX"],"Local\\WindowsMusicLab-GPU0")
            folder=Path(args[2]);ask=json.loads((folder/"ask.json").read_text(encoding="utf-8"))
            self.assertEqual(ask,harness.REQUEST)
            if not worker_exit and not timed_out:
                (folder/picture["file"]).write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\x0dIHDR"+struct.pack(">II",512,512))
            kw["stdout"].write(stdout);kw["stdout"].flush();kw["stderr"].write("synthetic Unicode log: тест\n");kw["stderr"].flush()
            events.append("spawn");return child
        def gpu(*args,**kw):
            self.assertTrue(held["lease"])
            self.assertEqual(kw["need_mb"],8000)
            if gpu_failure:raise ValueError("synthetic heavy GPU process")
            return {"index":0,"free_mb":10598,"room_mb":10086,"policy":"aggregate","ok":True}
        def kill(value):
            self.assertIs(value,child);value.returncode=-15;events.append("terminate")
        stack=ExitStack()
        for target,name,value in [(harness,"ROOT",self.kit),(harness,"CACHE",cache),(harness,"CLAIM",claim)]:stack.enter_context(patch.object(target,name,value))
        stack.enter_context(patch.dict(os.environ,{}))
        stack.enter_context(patch.object(harness.runtime,"configure_runtime"))
        stack.enter_context(patch.object(harness.runtime,"venv_python",return_value=interpreter))
        stack.enter_context(patch.object(harness,"standalone_memory",return_value=memory))
        stack.enter_context(patch.object(harness,"stopped_workers",return_value={"own_workers":[]}))
        stack.enter_context(patch.object(harness,"verify_model",return_value={"sha256_verified":True,"files":20}))
        stack.enter_context(patch.object(harness,"idle_ports",return_value=Ports()))
        lease=stack.enter_context(patch.object(harness.runtime,"gpu_lease",side_effect=lambda *a,**kw:Lease()))
        stack.enter_context(patch.object(harness.gpu_guard,"check",side_effect=gpu))
        spawn=stack.enter_context(patch.object(harness.subprocess,"Popen",side_effect=launch))
        terminate=stack.enter_context(patch.object(harness.runtime,"terminate_process",side_effect=kill))
        stack.enter_context(patch.object(harness.runtime,"system_memory",return_value=memory))
        stack.enter_context(patch.object(harness,"endpoint",side_effect=AssertionError("standalone must not call API")))
        return harness,stack,claim,events,lease,spawn,terminate

    def test_standalone_same_claim_parent_lease_exact_one_result(self):
        harness,stack,claim,events,lease,spawn,terminate=self.standalone_fixture()
        with stack:
            result=harness.standalone_once()
            self.assertEqual(result["frames"],1)
            self.assertEqual(result["mode"],"standalone-production-worker")
            self.assertEqual(events,["lease","spawn","release"])
            lease.assert_called_once();spawn.assert_called_once();terminate.assert_not_called()
            for action in (harness.standalone_once,harness.run_once):
                with self.assertRaisesRegex(RuntimeError,"claim already exists"):action()
            self.assertEqual(spawn.call_count,1)
        saved=json.loads(claim.read_text(encoding="utf-8"))
        self.assertEqual(saved["status"],"done")
        self.assertEqual(len(saved["resources"]),17)
        self.assertIn("тест",Path(saved["logs"]["stderr"]).read_text(encoding="utf-8"))

    def test_standalone_gpu_admission_failure_has_no_claim_or_spawn(self):
        harness,stack,claim,events,lease,spawn,_=self.standalone_fixture(gpu_failure=True)
        with stack:
            with self.assertRaisesRegex(ValueError,"heavy GPU process"):harness.standalone_once()
            spawn.assert_not_called()
        self.assertFalse(claim.exists());self.assertEqual(events,["lease","release"])

    def test_standalone_timeout_stops_only_owned_child_and_latches_claim(self):
        harness,stack,claim,events,lease,spawn,terminate=self.standalone_fixture(timed_out=True)
        with stack:
            with self.assertRaises(harness.subprocess.TimeoutExpired):harness.standalone_once(timeout=1)
            terminate.assert_called_once()
            with self.assertRaisesRegex(RuntimeError,"claim already exists"):harness.standalone_once()
            spawn.assert_called_once()
        saved=json.loads(claim.read_text(encoding="utf-8"))
        self.assertEqual(saved["status"],"failed_or_uncertain")
        self.assertEqual(saved["returncode"],-15)
        self.assertEqual(events,["lease","spawn","terminate","release"])

    def test_standalone_child_failure_preserves_resource_logs_without_retry(self):
        harness,stack,claim,events,lease,spawn,_=self.standalone_fixture(worker_exit=1)
        with stack:
            with self.assertRaisesRegex(RuntimeError,"exited with code1".replace("code1","code 1")):harness.standalone_once()
        saved=json.loads(claim.read_text(encoding="utf-8"))
        self.assertEqual(saved["status"],"failed_or_uncertain")
        self.assertEqual(len(saved["resources"]),17)
        self.assertTrue(Path(saved["logs"]["stdout"]).is_file())

    def test_standalone_rejects_wrong_completion_profile(self):
        def mutate(rows):rows[-1]["offload_mode"]="component"
        harness,stack,claim,_,_,_,_=self.standalone_fixture(mutate=mutate)
        with stack:
            with self.assertRaisesRegex(RuntimeError,"completion profile differs"):harness.standalone_once()
        self.assertEqual(json.loads(claim.read_text(encoding="utf-8"))["status"],"failed_or_uncertain")

    def test_standalone_rejects_reported_phase_commit_below_reviewed_guard(self):
        def mutate(rows):rows[1]["resources"]["system"]["commit_available"]=int(9.5*2**30)-1
        harness,stack,claim,_,_,_,_=self.standalone_fixture(mutate=mutate)
        with stack:
            with self.assertRaisesRegex(RuntimeError,"9.5 GiB commit"):harness.standalone_once()
        self.assertEqual(json.loads(claim.read_text(encoding="utf-8"))["status"],"failed_or_uncertain")

    def test_standalone_listener_mtmd_inventory_is_blocked(self):
        harness=self.harness_module()
        row={"ProcessId":999999,"Name":"llama-mtmd-cli.exe",
             "ExecutablePath":str((self.kit/"windows/build/llama-mtmd-cli.exe").resolve()),
             "CommandLine":"synthetic owned Listener"}
        result=types.SimpleNamespace(returncode=0,stdout=json.dumps([row]))
        with patch.object(harness,"ROOT",self.kit),patch.object(harness.runtime,"run_process",return_value=result) as query:
            with self.assertRaisesRegex(RuntimeError,"llama-mtmd-cli.exe"):harness.stopped_workers()
        self.assertIn("Name='llama-mtmd-cli.exe'",query.call_args.args[0][-1])

    def test_standalone_ports_and_process_checks_fail_closed(self):
        harness=self.harness_module()
        handles=[MagicMock(),MagicMock()];handles[1].bind.side_effect=OSError("already occupied")
        with patch.object(harness.socket,"socket",side_effect=handles):
            with self.assertRaisesRegex(RuntimeError,"free loopback port"):
                with harness.idle_ports([41868]):pass
        for handle in handles:handle.close.assert_called_once()
        with patch.object(harness,"ROOT",self.kit):
            with self.assertRaisesRegex(RuntimeError,"stopped own"):
                harness.stopped_workers([{"ProcessId":999999,"Name":"python.exe","ExecutablePath":str(self.kit/".venv/python.exe"),"CommandLine":"worker"}])
            self.assertTrue(harness.stopped_workers([{"ProcessId":999999,"Name":"python.exe","ExecutablePath":"C:/unrelated/python.exe","CommandLine":"unrelated"}])["inventory_verified"])
            with self.assertRaisesRegex(RuntimeError,"cannot identify"):
                harness.stopped_workers([{"ProcessId":999999,"Name":"python.exe"}])
        with patch.object(artist_sdxl,"preflight_memory",return_value={"commit_scope":"process_bound"}):
            with self.assertRaisesRegex(RuntimeError,"machine-wide"):harness.standalone_memory()

    def test_one_frame_harness_plan_and_durable_claim_no_repeat_submission(self):
        import importlib.util
        spec=importlib.util.spec_from_file_location("one_frame_harness",ROOT/"windows/Test-Artist-OneFrame.py")
        harness=importlib.util.module_from_spec(spec);spec.loader.exec_module(harness)
        with patch.object(harness,"endpoint",side_effect=AssertionError("plan must not access API")), \
             patch.object(harness,"verify_model",side_effect=AssertionError("plan must not read weights")):
            review=harness.plan()
        self.assertEqual(review["offload_mode"],"sequential")
        self.assertFalse(review["submission_performed"])
        self.assertEqual(review["request"]["validation_profile"],artist_sdxl.VALIDATION_PROFILE)
        self.assertEqual(review["request"]["count"],1)
        self.assertEqual(harness.plan()["request"]["resolution"],512)
        rid="20261012-120000-abcd";name="01-1x1-s20261012.png"
        image=self.kit/"artist"/rid/name;image.parent.mkdir(parents=True)
        image.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\x0dIHDR"+struct.pack(">II",512,512))
        posts=[]
        def endpoint(port,path,body=None):
            if body is not None:posts.append((path,body))
            if path=="/artist/draw":return {"id":rid}
            if path=="/artist/runs":return {"runs":[{"id":rid,"status":"done","pictures":[{"kept":True,"file":name}]}]}
            return {}
        cache=self.kit/"cache";claim=cache/"claim.json"
        with patch.object(harness,"ROOT",self.kit),patch.object(harness,"CACHE",cache),patch.object(harness,"CLAIM",claim), \
             patch.object(harness.runtime,"configure_runtime"),patch.object(harness,"verify_model",return_value={"fixture":True}), \
             patch.object(harness,"server_preflight",return_value={"fixture":True}),patch.object(harness,"endpoint",side_effect=endpoint), \
             patch.object(artist_sdxl,"preflight_memory",return_value={"available":16*2**30,"commit_available":24*2**30}):
            result=harness.run_once()
            self.assertEqual(result["frames"],1)
            self.assertEqual(len(posts),1)
            self.assertEqual(posts[0][0],"/artist/draw")
            with self.assertRaisesRegex(RuntimeError,"claim already exists"):
                harness.run_once()
            self.assertEqual(len(posts),1)
        self.assertEqual(json.loads(claim.read_text(encoding="utf-8"))["status"],"done")

if __name__ == "__main__":
    unittest.main(verbosity=2)