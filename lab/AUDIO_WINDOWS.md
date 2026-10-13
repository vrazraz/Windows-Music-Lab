# Native Windows audio, Listener and Trainer audit

Source: Ruach Studio / YuE2 upstream, with original licenses retained. This document describes the Windows Music Lab fork's code and the evidence actually collected. Models and runtime packages are not included in Git.

## Implemented and tested without new dependencies

`lab/test_native_audio.py` runs with existing Python 3.10 and standard-library mocks/synthetic fixtures:

```powershell
py -3.10 -X utf8 .\lab\test_native_audio.py
```

The suite covers native `.venv\Scripts\python.exe`, llama.cpp `.exe` discovery for Ninja/Visual Studio layouts, Unicode GTSinger PCM joins and JSON, dataset confinement, local model preflight, offline dataset/workspace routes, and native training process launch/status/stop. The supervisor tests launch our own tiny Python fixtures, never model or vendor code. Mocked Whisper checks word timing JSON and `local_files_only=True`; these are protocol tests, not a Whisper inference benchmark.

| Module | Windows code | Real model processing verified here |
| --- | --- | --- |
| Spectrum / Debuzz | Process-local cache/DLL setup; native paths; WAV reader closes before return | Approved installed environment; real Spectrum payload and synthetic Debuzz processing passed in root validation |
| Remaster / Inspect | Native FFmpeg, short-clip STFT and sub-LSB click fixes | Real CPU Inspect8s+100ms; basic Remaster6→4.000s stereo48kPCM24 WAV/FLAC,−18.03LUFS/−14.84dBTP and fade/DC/metadata checks. See windows/REFINER_INDEPENDENT_RU.md; full Debunker/deess/432Hz/stem mix remain unverified |
| Whisper / karaoke / text trimming | Local model only, Unicode JSON, CUDA DLL search | Actual CUDA synthetic Whisper speech/word timings passed; karaoke alignment/LRC/SRT and text trimming not executed |
| Stems | All Roformer/Demucs weights and YAML required locally; process network guard | Validation core does NOT contain audio-separator; separation package/closure and all optional weights are absent/unapproved; inference unverified |
| UniverSR | Required local `config.yaml` + `pytorch_model.bin`; no implicit Hub download | Pending approved pinned code + weights |
| Listener | Native llama-mtmd-cli.exe discovery; local transformers loading; failed tracks return failure | Approved verified source/weights/CUDA build; real 10s SAPI decode passed speech-vs-music classification; general music tagging/120s unverified |
| Trainer / datasets | Real upstream preparation/config/checkpoint logic retained; Windows supervisor replaces systemd; cooperative checkpoint stop | Process lifecycle tested; actual LoRA training blocked by the 20,000 MB free-VRAM gate on RTX 3060 12 GB |

On Windows, the default engine is the studio's own trainer. AI-Toolkit remains optional and unverified; it is not installed, and its default local path is `vendor/AI_Toolkit` (override with `AITK_ROOT`). The supervisor writes `native-process.json`, owns the child process, and survives a web UI restart. Stop creates `stop.requested`: the own trainer checkpoints at a safe step boundary. After 60 seconds the supervisor may terminate its own process tree, retaining completed checkpoints; a forced stop does not promise that the latest in-progress step was saved. Latent-cache files and model checkpoints use `.part` files before replacement. No services/system settings are installed.

## Approved runtime and optional dependencies

Use a project-local virtual environment. Do not replay the Linux freeze: it includes Linux NVIDIA/NCCL/Triton wheels. Initial package audit used PyPI and the official PyTorch CUDA index. Root subsequently installed the approved cp310 CUDA environment, verified imports/pip checks, and installed the portable FFmpeg below. Optional vendor/model execution still needs its own approved scope.

The upstream stack versions have Windows Python 3.10 wheels: torch 2.11.0, torchaudio 2.11.0, torchvision 0.26.0, audio-separator 0.47.0, faster-whisper 1.2.1, CTranslate2 4.8.2, transformers 4.57.6, safetensors 0.8.0. Transitive dependencies must be resolved with Windows wheel availability checked before installation. Upstream NumPy 2.5.3 requires Python >=3.12 and cannot be used with Python 3.10; NumPy 2.2.6 has a Windows cp310 wheel (12,904,620 bytes). Python 3.14 is another possible environment, but all transitive audio-separator dependencies still require wheel verification.

Important: the small PyPI torch Windows wheel is not the requested CUDA build. The official CUDA 12.8 index lists `torch-2.11.0+cu128-cp310-cp310-win_amd64.whl` (SHA256 `7c792fe95ad5edaf622cf9e4f5573f5aecf2bc0654c7e866eda6134088f95d72`); the wheel host returned HTTP 403 to HEAD metadata requests during this audit. Root subsequently fully verified and installed the official CUDA wheel; no CPU substitution was made. The root runtime lock/installer records the installed dependency closure. All wheels/DLLs/caches belong inside the project; no driver changes.

Portable FFmpeg from the official project's linked Windows build provider:

- URL: https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-9.0.2-essentials_build.zip
- Version 9.0.2; 114,768,076 bytes compressed; GPLv3.
- SHA256: `60f467265b1e312373dbcd92200c2618a74850f98d3d078e94296bb3fa2047ba`.
- Put `ffmpeg.exe` and `ffprobe.exe` under `toolchain/ffmpeg/bin`; process-local PATH supports this. Approved portable binary installed and real synthetic codec/export checks passed in root validation.
- Provider license/build notes: https://www.gyan.dev/ffmpeg/builds/

## Weights and execution status

Numbers below are compressed/download bytes from pinned repository file metadata, not promises about VRAM. Additional config/tokenizer/licenses must be preserved. Runtime weights remain outside Git.

| Profile | Source pin / important files | Download bytes | Terms / resource limit |
| --- | --- | ---: | --- |
| Whisper large-v3 CT2 | `Systran/faster-whisper-large-v3` @ `edaa852ec7e145841d8ffdb056a99866b5f0a478`; `model.bin` plus config/tokenizer | 3,087,284,237 + about 3.55 MB | MIT; CUDA inference or CPU int8 supported by the job, root verified CUDA inference on own synthetic speech; CPU int8 not tested |
| Audio super-resolution | `woongzip1/universr-audio` @ `1c3294844285af851b6ffa56cbde4e43cd41fc2b`; `pytorch_model.bin`, `config.yaml` | 229,072,395 + 533 | **Weights CC BY 4.0**, code MIT; upstream reports ~10 GB peak for 20-second chunks; Windows measurement pending |
| Listener Q4_K_M | `ggml-org/Qwen2.5-Omni-7B-GGUF` @ `89b785438c8901d4635e42f50480ba5985a1bbf1`; Q4_K_M GGUF | 4,683,072,384 | Original Apache2.0 LICENSE verified at initial4728b48b and ae9e1690 revisions; both conversion notices preserved; see LISTENER_AI_APPROVAL.md |
| Listener Q8 projector | `mradermacher/Qwen2.5-Omni-7B-GGUF` @ `658a1c70e91733330bcad348eead24bb4d15d9eb`; `Qwen2.5-Omni-7B.mmproj-Q8_0.gguf` | 1,548,488,608 | Q4 + projector total **6,231,560,992**; upstream measured 7,480 MB peak, admission gate 8,200 MB free VRAM; native sm86 CUDA build and short SAPI pilot verified, see LISTENER_AI_APPROVAL.md |
| Trainer bf16 | `Comfy-Org/YuE2` @ `2f76ca75e6ee094169de899cc7fc99d6887e2196`; `checkpoints/yue2_3b_bf16.safetensors` | 7,799,983,228 | CC BY-NC 4.0; own trainer needs 20,000 MB free VRAM |
| Trainer int8 base | Same Comfy pin; `checkpoints/yue2_3b_int8_convrot.safetensors` | 3,960,938,800 | CC BY-NC 4.0; own trainer unpacks int8 to bf16, so this does **not** reduce the supported VRAM gate |
| MERT | `m-a-p/MERT-v2-FullSong` @ `d8ba1c745e733b3908ce6ad16ebeb17ac7600a42`; `model.safetensors`, configs, custom Python | 2,529,812,848 + configs/code | CC BY-NC 4.0; **local custom model Python executes under `trust_remote_code=True`**, so review and execution approval are required |
| Semantic head | `Mothersuperior/yue2-mothersuperior-realaudio-tokenizer-v4` @ `e2e63d859f3af879baf1b4d4e9f22d1eeda6fde5`; `tokenizer_head_joint_v4.pt` | 171,305,291 | CC BY-NC 4.0; own loader uses `weights_only=True` |

UniverSR code pin: https://github.com/woongzip1/UniverSR/tree/d8636623fe0c0704296239c1d3d3c5b911ecb2e0 . Its pinned `from_pretrained` implementation accepts a local snapshot containing config and weights; the Windows job uses that branch.

Roformer plus four Demucs files are about 0.94 GB in upstream installation notes (Roformer ~610 MB + four ~81 MB files). Pinned candidate URLs, full SHA256/size/config and license notes are recorded in windows/full-audio-models.json. These optional weights have not been installed or executed; approving/executing this optional profile is separate. The job requires all assets present, and its Python network guard prevents separator's automatic registry/model downloads. The known-model local resolver bypasses online registry lookup; full inference with the approved architecture/package stack still needs testing.

GTSinger starter samples/sets are optional external downloads and remain disabled in local-only mode. They are CC BY-NC-SA 4.0 and range from about 97–100 MB for a sample to 2.30–6.96 GB for a whole language set. User audio is never sent to a cloud inference service.

RTX 3060 12 GB can potentially fit the upstream Listener Q4 profile or UniverSR when other models are released; fitting a total-memory profile does not prove enough free VRAM on a live desktop. Check `nvidia-smi` and system commit headroom first. Running Creator, Artist and an audio ML job concurrently is not supported by this audit. RAM 32 GB is limited for full-precision training plus caching; the supported training gate is retained rather than claiming an untested low-memory trainer.

Pinned model file manifest and current source/license metadata: `../windows/full-audio-models.json` (27 files, 21,986,084,016 bytes including the blocked Trainer). This is review metadata, not a downloader. Select only approved profiles.

Windows atomic metadata publication retries only native access/sharing/lock errors (5/32/33) for at most1s, then preserves previous complete JSON and the new part. The two real held-reader tests are `py -3.10 -m unittest lab.test_atomic_audio -v`; native37 + atomic2 passed together. This does not make paired model/optimizer checkpoints a transaction.

Listener download/build/pilot stages are in `windows/Install-ListenerPilot.ps1`; current exact artifacts, notices, approved resource budget and offline CLI contract are documented in `windows/LISTENER_AI_APPROVAL.md`. Source and runtime logs are distinct from a verified model-inference result.


Listener final evidence: `../windows/cache/listener/pilot/windows-listener-pilot-20261012-205111-9b08f8/attempt-20261012-230751-c4e836/metrics.json` and `../windows/build/listener-cuda/runtime-proof.json`. Native CLI exit0/5.219s; all29/29 layers and audio encoder/CLIP contexts CUDA0; actual tags `speech, no music`. Scoped quality passed only speech versus music on the own10s SAPI excerpt; previous synth-pop/instruments hallucination and raw logs remain preserved. No real genre/instrument or120s validation. Observed total GPU used8520MiB, native peak commit8,769,142,784B, peak WS4,823,511,040B; Both pilot and production GGUF listener now require >=11GiB initial machine-wide commit headroom and10GiB available RAM before model import/load; these are short-test minimums, no proof for120s, no parallel heavy models. Three production tests cover exact threshold, low/nonmachine counters and no _inference call when admission fails.

Listener bytes: both GGUF plus three notices6,231,576,570B fully SHA verified. Historical final-payload ledger is verified; old urllib302 bodies were not measured. An explicitly assumed48MiB allowance keeps planning below the approved6.3GB but cannot prove historical all-HTTP-body traffic. Future bounded redirect accounting passed12 no-network tests; no quota reset/redownload. Four evidence tests parse the actual padded perf logs, preserve absent counters, accept speech/spoken-word synonyms, and reject known hallucinated tags: `.\.venv\Scripts\python.exe .\windows\test_listener_pilot.py`.
