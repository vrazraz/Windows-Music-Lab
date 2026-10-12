# Windows Music Lab

Independent native Windows port of [Ruach Studio](https://github.com/igrbible/Ruach_Studio) by **Viktor Zhuromskyy**, based on commit `a69739725e81b74921c6e2a24da8e83659f45a3a` (2.0.0-rc5). Windows changes dated **12 October 2026**. The fork's UI is called **Windows Music Lab**; upstream names and logos are retained only as attributed upstream materials, not as this fork's brand. No affiliation or endorsement is implied.

**[Установка и запуск по-русски](windows/README_RU.md).**

This port runs the C++/CUDA text/style-to-music pipeline directly on Windows, without WSL or Python. It supplies a small Russian browser UI, local MP3/WAV library, 64 style tags and a random style button. The UI supports one 5–30 second take at a time. The full Linux studio's Python rooms, training, Artist and Refiner are outside the verified Windows scope. The original source and docs remain available; see [upstream's original README](UPSTREAM_README.md).

## Quick start from source

Requirements: Windows 11 x64, NVIDIA GPU and working Windows driver, Git, `curl.exe`, Visual Studio 2022 C++ Build Tools with the Desktop C++ workload, Windows SDK, CMake and Ninja. Tested on RTX 3060 12 GB (CUDA architecture 86), MSVC 19.44, CMake 3.31.6 and a project-local CUDA 12.8.1 toolkit. Other hardware has not been verified. Use one compile job and keep ample system RAM/commit available; the CUDA build can exhaust memory when other large apps are open.

```powershell
git clone https://github.com/vrazraz/Windows-Music-Lab.git
cd Windows-Music-Lab
powershell -NoProfile -File .\windows\Prepare-Toolkit.ps1
powershell -NoProfile -File .\windows\Build.ps1 -Jobs 1
.\Start.cmd
```

The first start downloads any missing models, verifies **size and SHA256**, then starts the engine. Valid existing files are verified and reused. Open **http://localhost:41867** and keep the console open. Ctrl+C stops the server; the UI's Stop button cancels the current generation. The server binds to `127.0.0.1`; it is not exposed to the network. If the port is occupied, the launcher exits without replacing the existing server.

Models total **4,340,729,408 bytes (4.34 GB / 4.04 GiB)**: Q8_0 backbone 3.81 GB and F32 VAE 0.53 GB. They come from [Serveurperso/YuE2-GGUF](https://huggingface.co/Serveurperso/YuE2-GGUF/tree/64b030e3deb6e8150d2b7c0db641ef5a17eca8a3), pinned at revision `64b030e3deb6e8150d2b7c0db641ef5a17eca8a3`. Toolkit preparation downloads **690,522,782 bytes (0.69 GB)** from NVIDIA. Allow **15–20 GB free disk space**, plus your generated audio. No keys or paid services are required. Network access is needed for downloads; generation is local.

Downloads display curl progress, resume incomplete `.part` files and only rename them after validation. Network, size or checksum failure prevents engine launch. A corrupt existing model is kept untouched: move it aside, then restart to download a clean copy. A bad complete `.part` must also be moved aside before retrying. See [the pinned manifest](windows/downloads.json).

## Configuration and checks

Default CUDA target is `86`; use `Build.ps1 -CudaArchitecture 89` for another appropriate target (not verified here). `-CudaRoot` on Build/Start accepts a compatible existing CUDA toolkit. Otherwise scripts use `toolchain/cuda-12.8.1` inside the checkout; an existing sibling toolkit from the original installation is also recognized. No global PATH, execution policy, locale, firewall or driver changes are made.

Runtime defaults: Q8_0, standard VAE, `--max-batch 1`, `--max-seq 12288`, `--vae-core 512`, FlashAttention enabled (`GGML_CUDA_FA=ON`, `GGML_CUDA_FA_QUANTS=f16-f16`). Change the port with `Start.ps1 -Port 41868`. Models stay in `models/`, audio in `outputs/`, settings in `windows/state/`, caches in `windows/cache/`. These and all build/toolkit artifacts are ignored by Git.

Validated on the reference Windows machine: native CUDA compilation; real **text + style → AR → NAR → VAE → stereo PCM16 WAV**, 48 kHz, 9.999 seconds in 16.36 seconds; browser playback; desktop/mobile style tag interactions. The request supplied no precomputed semantic tokens. Speed and musical quality vary. Download failure/reuse/resume checks use tiny isolated fixtures, never delete production models, and create no music. Run `windows/Test-ModelDownload.ps1` for those offline checks. `Smoke-Test.ps1` intentionally generates one short WAV; `Check-UI.ps1 -Tags` checks the running UI with Chrome and Node 22+.

## Licenses and attribution

- Ruach Studio and this fork's changes: **AGPL-3.0-or-later**, preserving [LICENSE](LICENSE), copyright notices and source availability. The embedded engine/GGML and other third-party code keep their own included licenses.
- Original YuE2 models: **MAP / m-a-p**, [YuE2-3B](https://huggingface.co/m-a-p/YuE2-3B) and [YuE2-Vae](https://huggingface.co/m-a-p/YuE2-Vae), **CC BY-NC 4.0**. GGUF conversion/quantization: Serveurperso. [The pinned model card](https://huggingface.co/Serveurperso/YuE2-GGUF/blob/64b030e3deb6e8150d2b7c0db641ef5a17eca8a3/README.md) retains these non-commercial terms. Model licenses apply separately from the code license.
- Original Ruach Studio branding/assets by Viktor Zhuromskyy: separate **CC BY-NC-ND 4.0** terms, preserved in [LICENSE-ASSETS.md](LICENSE-ASSETS.md). No original logo is used by the Windows UI. Source assets are unchanged and attributed.
- CUDA is obtained separately from NVIDIA and subject to [NVIDIA's CUDA terms](https://docs.nvidia.com/cuda/eula/index.html). No CUDA binaries or model weights are distributed here.

This repository contains source code and attributed upstream source assets, not trained weights, portable SDKs, generated songs, browser profiles, logs, credentials or local settings.
