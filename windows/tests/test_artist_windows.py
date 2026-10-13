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
import artist_upscale


class ArtistWindowsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="Artist Unicode ")
        self.kit = Path(self.temp.name) / "Музыка 🎨"
        self.kit.mkdir()
        self.stack = ExitStack()
        self.stack.enter_context(patch.object(art_job, "KIT", self.kit))
        self.stack.enter_context(patch.object(artist_upscale, "UPSCALERS", self.kit / "artwork/upscalers"))
        self.old_h = dict(artist.H)
        artist.H.clear()
        artist.setup(kit=self.kit, py=Path(sys.executable), jobs={}, lock=threading.RLock(),
                     painter=lambda value: value or "krea2-q4", wait_card=lambda *a: None,
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
        d = self.kit / "artwork/loras/krea2/Набор"
        d.mkdir(parents=True)
        p = d / "Цвета.safetensors"
        header = json.dumps({"__metadata__": {"modelspec.trigger_phrase": "warm colours"}}).encode()
        p.write_bytes(struct.pack("<Q", len(header)) + header)
        return p, "krea2/Набор/Цвета.safetensors"

    def test_missing_artist_python_fails_before_queue_or_files(self):
        artist.H["py"] = self.kit / ".venv-art/Scripts/python.exe"
        with self.assertRaisesRegex(RuntimeError, "Artist environment"):
            artist.draw({"prompt": "synthetic", "shapes": ["1:1"]})
        self.assertEqual(artist.H["jobs"], {})
        self.assertFalse((self.kit / "artist").exists())


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
        chosen = artist_loras.chosen(self.kit, "krea2-q4", [{"id": lid, "weight": 0.7}, {"id": lid, "weight": 0.9}])
        self.assertEqual(len(chosen), 1)
        self.assertEqual(chosen[0]["weight"], 0.7)
        self.assertEqual(artist_loras.chosen(self.kit, "krea2-q4", [{"id": lid, "weight": 0}]), [])
        with self.assertRaises(ValueError):
            artist_loras.chosen(self.kit, "qwen21", [{"id": lid}])

    def test_lora_path_rejects_absolute_unc_colon_and_parent(self):
        for lid in ("krea2/../outside.safetensors", "C:/krea2/a.safetensors", "\\\\server\\krea2\\a.safetensors", "krea2/C:/a.safetensors"):
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


    def test_resource_protocol_does_not_add_fake_pictures(self):
        result=self.synthetic_work('import json\nprint(json.dumps({"resources":{"stage":"before_import","private_bytes":123}}),flush=True)\nprint(json.dumps({"done":True,"took":0}),flush=True)\n')
        self.assertEqual(result["pictures"],[])
        self.assertEqual(result["resources"][0]["private_bytes"],123)

    def test_removed_sdxl_request_fails_before_environment_queue_or_files(self):
        artist.H["py"] = self.kit / "missing-python.exe"
        with patch.object(artist, "_worker_python") as py, patch.object(artist.threading, "Thread") as thread:
            for name in ("sdxl", " SDXL "):
                with self.subTest(name=name), self.assertRaisesRegex(ValueError, "SDXL has been removed"):
                    artist.draw({"painter": name, "prompt": "synthetic", "shapes": ["1:1"]})
            py.assert_not_called()
            thread.assert_not_called()
        self.assertFalse((self.kit / "artist").exists())
        self.assertEqual(artist.H["jobs"], {})

    def test_removed_profile_and_unavailable_selection_have_no_side_effect(self):
        for extra in ({"painter": "__unavailable__"}, {"resolution": 512}, {"validation_profile": "retired"}):
            with self.subTest(extra=extra), patch.object(artist, "_worker_python") as py, self.assertRaises(ValueError):
                artist.draw({"prompt": "synthetic", "shapes": ["1:1"], **extra})
            py.assert_not_called()
        self.assertFalse((self.kit / "artist").exists())

    def test_worker_rejects_removed_sdxl_before_runtime_or_model_import(self):
        with patch.dict(os.environ, {"ART_PAINTER": " SDXL "}), patch.object(sys, "argv", ["artist_job.py"]), patch.object(artist_job, "configure_runtime") as configure:
            with self.assertRaisesRegex(ValueError, "SDXL has been removed"):
                artist_job.main()
            configure.assert_not_called()
        self.assertNotIn("artist_sdxl", sys.modules)

    def test_take_artwork_rejects_sdxl_before_prompter_or_model(self):
        with patch.dict(os.environ, {"ART_PAINTER": "sdxl"}), patch.object(art_job, "configure_runtime") as configure, patch.object(art_job, "write_prompt") as prompt:
            with self.assertRaisesRegex(ValueError, "SDXL has been removed"):
                art_job.main()
            configure.assert_not_called()
            prompt.assert_not_called()
        self.assertNotIn("sdxl", art_job.PAINTERS)
        self.assertIsNone(artist_loras.family_of("sdxl"))
        self.assertFalse((ROOT / "lab/artist_sdxl.py").exists())

    def test_painter_metadata_preserves_krea_qwen_without_sdxl(self):
        rows = artist.painters()["painters"]
        self.assertEqual({p["key"] for p in rows}, {"krea2-q4", "krea2-q8", *artist.QWEN})
        self.assertTrue(all(not p["ready"] and not p["viable"] for p in rows))
        self.assertTrue(all(p["unavailable_reason"] for p in rows))
        self.assertNotIn("sdxl", artist.NEED)

    def test_installed_painter_metadata_respects_existing_gpu_refusal(self):
        artist.H["refusal"] = lambda key, need, why: "GPU budget does not fit"
        with patch.object(artist, "_model_weights_ready", return_value=True), patch.object(Path, "is_file", return_value=True), patch.object(artist, "qwen_ready", return_value=False):
            rows = artist.painters()["painters"]
        krea = [p for p in rows if p["family"] == "krea2"]
        self.assertTrue(all(p["ready"] and not p["viable"] for p in krea))
        self.assertTrue(all(p["unavailable_reason"] == "GPU budget does not fit" for p in krea))

    def test_existing_qwen_streaming_admission_is_preserved(self):
        artist.H["refusal"] = lambda key, need, why: "GPU budget" if need[key] > 6000 else ""
        with patch.object(artist, "qwen_ready", side_effect=lambda key: key == "qwen2512-fp8"), patch.object(artist, "qwen_models", return_value=["local.safetensors"]):
            row = next(p for p in artist.painters()["painters"] if p["key"] == "qwen2512-fp8")
        self.assertTrue(row["ready"] and row["viable"] and row["streaming"])
        self.assertEqual(row["effective_need_mb"], 6000)

    def test_retained_artwork_loaders_dispatch_krea_and_qwen(self):
        with patch.dict(os.environ, {"ART_PAINTER": "krea2-q8"}), patch.object(art_job, "Krea") as krea:
            self.assertIs(art_job.painter()[0], krea.return_value)
            krea.assert_called_once_with("krea2-q8")
        with patch.dict(os.environ, {"ART_PAINTER": "qwen21"}), patch.object(art_job, "Qwen") as qwen:
            self.assertIs(art_job.painter()[0], qwen.return_value)
            qwen.assert_called_once()


if __name__ == "__main__":
    unittest.main(verbosity=2)