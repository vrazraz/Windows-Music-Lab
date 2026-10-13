# Windows Music Lab — native Windows Studio

Independent Windows port of [Ruach Studio](https://github.com/igrbible/Ruach_Studio) by **Viktor Zhuromskyy**, based on `a69739725e81b74921c6e2a24da8e83659f45a3a` (2.0.0-rc5). This **`full-windows-port` branch** adds the native full Studio shell; `main` retains the earlier minimal build. No WSL is required. [Русская установка и запуск](windows/README_RU.md).

## Run a prepared installation

From this checkout, double-click **`Start-Full.cmd`**, keep its console open, then open **http://localhost:41868**. Studio and Lab listen only on `127.0.0.1:41868` / `:41871`; an installed and verified CPU Writer starts at `http://127.0.0.1:41872/v1`. An occupied port is not replaced. Stop from another PowerShell window in the checkout:

```powershell
powershell.exe -NoProfile -File .\windows\Stop-Full.ps1
```

Ctrl+C in the launcher console also stops its owned services. For Studio without loading Writer, use `Start-Full.cmd -WithoutWriter`. No generation is started by the launcher.

**A source clone is not a prepared installation.** Binaries, environments, models and readiness receipts are local, excluded from Git. `Start-Full.cmd` validates them and refuses missing required artifacts; it does not automatically install Python packages or download optional models. The earlier **`Start.cmd`** remains available at **http://localhost:41867** and downloads only its two missing pinned base models on first start. It is a different, minimal UI.

## Current scope and evidence

| Module | Implemented and checked | Practical limit |
|---|---|---|
| Creator | Native Studio UI/API, ABC/MIDI editing and roundtrip, previews, GPU ownership/cancel/unload. The baseline native text/style → audio pipeline was tested. | Covers/remixes/sliders/LoRA and advanced full-Studio music generation were not revalidated in this branch. |
| Writer | Local CPU Qwen3-4B, verified automatic startup/stop, short structured Russian response; notebook autosave/version/import/export/trash and handoff. | Requires separate installation and local ready marker; literary quality, long Muse/Idea and streaming are unverified. Some UI workflows used an explicitly marked mock. |
| Refiner | Synthetic DSP/spectrum/debuzz, Whisper transcription, short-clip Inspect and basic Remaster. | Neural stems/karaoke and UniverSR are not installed or validated; broader DSP stress cases remain unverified. |
| Librarian | Unicode collections, workspaces, favorites/notes/pins, archive, trash/restore and contained filesystem operations. | Cloud publishing is disabled in local mode. |
| Artist | Gallery/upload/metadata/compare and reference/mask/outpaint orchestration; Krea/Qwen code retained. | **SDXL is removed**, its pending test cancelled. No compatible installed painter currently exists; drawing is disabled with a reason. Image upscale still needs a separate approved install/pilot. |
| Listener | Native CUDA build and one short synthetic speech/no-music pilot. | Music tagging quality and long audio are unverified; separate local models/build required. |
| Trainer | Windows job supervision, dataset preparation controls, stop/cancel/checkpoint scaffolding. | Real training was not run; BF16 gate is 20,000 MiB, above the tested 12 GB GPU. |
| DAW export | Synthetic REAPER/DAWproject archives, audio conversion, ABC MIDI and timed lyrics; mono gain corrected. | Destination DAW import/XSD compatibility was not tested in the DAW applications. |

Windows 11 / RTX 3060 12 GB was the reference machine. Six Studio tabs and local HTTP were exercised; SDXL removal passed 22 backend, 70 frontend, 39 runtime, 13 management + 8 management-UI checks, 54 bundled scripts and 5 HTTP checks. These are bounded local checks, not proof that every inherited Linux feature runs. Details: [Windows status](windows/FULL_WINDOWS_STATUS_RU.md), [independent UI/DSP/DAW checks](windows/UI_INDEPENDENT_RU.md), [SDXL removal](windows/SDXL_REMOVAL_RU.md). Reports/screenshots referenced under `windows/cache/` and `windows/state/` exist only on the test installation and are **not** shipped in a clone.

## Prepare a fresh checkout

Requirements: Windows 11 x64; working NVIDIA Windows driver; Git and `curl.exe`; **Python 3.10 x64 with `py.exe`**; Visual Studio 2022 Desktop C++ tools/Windows SDK/CMake/Ninja. Node 22+ and Chrome are needed for browser QA, not ordinary server startup. Tested with MSVC 19.44, CMake 3.31.6 and project-local CUDA 12.8.1 (`sm86`). Other hardware is unverified.

Run the following **explicit setup commands** after reviewing their sources, licences and download sizes. They install/download/build; they are not performed automatically by `Start-Full.cmd`. Use one compile job and sufficient free RAM/commit. Retain at least **50 GiB free disk after all planned writes** for the full profile; 15–20 GB is only the earlier minimal profile's footprint.

```powershell
git clone --branch full-windows-port https://github.com/vrazraz/Windows-Music-Lab.git
cd Windows-Music-Lab
powershell.exe -NoProfile -File .\windows\Prepare-Toolkit.ps1
powershell.exe -NoProfile -File .\windows\Build.ps1 -Jobs 1
powershell.exe -NoProfile -File .\windows\Build-FullEngine.ps1 -RunTests
powershell.exe -NoProfile -File .\windows\Install-ValidationRuntime.ps1 -Phase All
powershell.exe -NoProfile -File .\windows\Download-Models.ps1
.\Start-Full.cmd -WithoutWriter
```

`Install-ValidationRuntime` resolves/audits pinned publisher metadata, receives hash-locked Windows wheels, installs binary-only into `.venv` / `.venv-art`, prepares local FFmpeg 9.0.2 and validates imports before writing its local readiness receipt. It does not run model inference. Stop on checksum/metadata/ABI/resource errors; do not create readiness JSON manually. Base files already in a valid sibling `source/models` may be reused by the full launcher; otherwise use this checkout's `models/`.

| Download group | Source / transfer size | When obtained |
|---|---|---|
| Native base backbone + VAE | [Serveurperso/YuE2-GGUF pinned conversion](https://huggingface.co/Serveurperso/YuE2-GGUF/tree/64b030e3deb6e8150d2b7c0db641ef5a17eca8a3), **4,340,729,408 B** | Explicit `Download-Models.ps1`, or automatically by the **minimal** `Start.cmd`; [manifest](windows/downloads.json). |
| Portable CUDA toolkit | NVIDIA, **690,522,782 B** compressed archives | Explicit `Prepare-Toolkit.ps1`; compatible local/sibling toolkit may be reused. No driver installation. |
| Full Python runtime + FFmpeg | Official PyTorch/PyPI Windows wheels and Gyan FFmpeg build | Explicit `Install-ValidationRuntime`; prior audited wheel transfer was about **9.82 GB**, plus **114,768,076 B** FFmpeg archive, installation/unpack space. Recheck its plan, cache and exact locks. |
| Whisper | [Systran faster-whisper-large-v3](https://huggingface.co/Systran/faster-whisper-large-v3), **3,090,835,702 B / 5 files** | Only for transcription: inspect `Download-ValidationModels.ps1 -PlanOnly`, then explicitly run it. It no longer downloads SDXL or every entry in the larger audio catalogue. |
| CPU Writer | Official llama.cpp source + Qwen3-4B-Q4_K_M, **2,497,280,256 B** model | Separate [Writer setup/validation](windows/WRITER.md); `Install-Writer.ps1 -Stage All` builds/downloads, `Test-Writer.ps1` sends a short real test before ready registration. |
| Listener | Six pinned local GGUF/notice files, **6,231,576,570 B** | Separate [Listener review/install/pilot](windows/LISTENER_AI_APPROVAL.md); not a full-launch dependency or automatic download. |

Downloads use pinned filenames/size/full SHA, resume `.part` and validate before use. No weights are stored in this repository. Preserve failed/unknown files for inspection; no cleanup of another project is required. Toolkit/environment/build caches, settings, notebooks and generated audio remain local. No account keys, paid service, global PATH/CUDA/driver, firewall, locale or network configuration changes are required. Generation runs locally after setup.

## Optional modules stay pending

**Image-upscale is not installed:** the independently reviewed next candidate is Spandrel 0.4.2 + einops 0.8.2 in ART and official RealESRGAN_x4plus (67,427,438 B total payload). Wheel-body audit, install/imports and a real bounded synthetic pilot still require a separate decision; do not install the whole optional catalogue to enable it.

**Stems remain held:** original RoFormer checkpoint licence terms were not established, and runtime/weights/pilots are absent. UniverSR has a reviewed selected source path but no built local wheel or runtime pilot; its unchanged 11,000 MiB gate failed the recorded memory snapshot. SheetSage's fixed 300 s native peak is unknown. Standard Krea/Qwen exceed the tested card's gates and require absent weights; streamed variants are unvalidated. Real Trainer BF16 requires a 24 GB class card. An adapter catalogue does not require downloading external voices. [Optional audit/proposal](windows/OPTIONAL_RUNTIME_APPROVAL_RU.md) records candidates and remaining gates, **not installation readiness or approval**.

SDXL selectors/worker/fallback/import gate/autoload/download plan and pending inference test were removed. Previously downloaded SDXL files, shared dependencies and user data were retained on the reference installation; they are not distributed. Older upstream docs/patch archives retain historical mentions.

## Licences and attribution

- Code: **AGPL-3.0-or-later**, [LICENSE](LICENSE); embedded GGML/engine and other third-party sources retain their included notices.
- YuE2 original weights by MAP / m-a-p, GGUF conversion by Serveurperso: **CC BY-NC 4.0**. Model licences apply separately from code; this is not blanket commercial clearance.
- Original attributed Ruach Studio branding/assets: **CC BY-NC-ND 4.0**, [LICENSE-ASSETS.md](LICENSE-ASSETS.md); the Windows UI uses this fork's text identity. No affiliation/endorsement is implied.
- CUDA comes separately under [NVIDIA's terms](https://docs.nvidia.com/cuda/eula/index.html); FFmpeg build GPL-3, Writer/Listener weights Apache-2.0 and llama.cpp MIT have their own notices. Optional packages/weights have separately recorded terms.

This branch publishes source, tests and attributed upstream source assets. It excludes trained weights, environments, portable SDKs, compiled binaries, local credentials/settings, generated work, browser profiles, logs and QA outputs. [Upstream README](UPSTREAM_README.md) and Linux/WSL instructions remain historical material; use the native commands above for this branch.
