# Необязательные функции Ruach Studio: минимальный пакет Windows

Проект: `E:\Projects\Ruach_Studio\full-windows-port`. Это **готовый запрос на отдельное разрешение**, а не выполненная установка. SDXL снят отдельным commit `3791c177c9f34eee6444a29af1aa7959332aa6d2`; его тест и memory-ready ожидание отменены. Другие модули сохранены. Точный каталог URL, размеров и SHA: [optional-runtime-package.json](optional-runtime-package.json). Поля `approvalScope` отделяют предлагаемые файлы от отложенных; наличие pin не разрешает загрузку.

Предлагается один последовательный этап: stems и увеличение изображений. Предел **1 500 000 000 B полученных HTTP-тел**, включая повторные попытки и metadata; **3 500 000 000 B новых выделений на E:**, включая распаковку, pip temporary и outputs; после оставшихся записей этого этапа и других задач всегда **50 GiB = 53 687 091 200 B резерва**. Секреты, платные сервисы, cloud inference, системный PATH/CUDA/драйверы/защита/сеть не требуются. Разрешение на статический аудит не считается разрешением на install/import/pilot.

| Активная функция | Точный набор | Размер моделей/config | Условия |
|---|---|---:|---|
| Vocals/Instrumental | audio-separator0.47.0 + BS-RoFormer ep317 | 639 333 486 B,2 файла | Неустановленный runtime; **original checkpoint licence hold**; gate8000 MiB |
|4 stems | Предыдущий этап + htdemucs_ft,4 Meta `.th` и YAML | 336 565 233 B,5 файлов | Зависит от RoFormer; Demucs MIT; gate8000 MiB |
| Увеличение изображения4x | Spandrel0.4.2 + einops0.8.2 + официальный RealESRGAN_x4plus | 67 040 989 B,1 файл |2 ART pure wheels =386 449 B; gate4000 MiB; реальный Windows pilot ещё не выполнен |

Все8 активных model/config файлов: **1 042 939 708 B**. Минимальная closure: **31 unique wheel records**,3 уже cached,28 ещё не получены, их compressed transfer **58 922 892 B**. Суммарный ожидаемый успешный payload нового этапа **1 101 862 600 B**;1.5GB cap включает запас, но не обещает бесконечные retries. Официальный cached torchvision0.26.0+cu128 всё ещё нужен CORE, потому что его требует onnx2torch-py313; ART уже содержит его. Два вновь статически прочитанных маленьких wheels повторно не скачиваются после проверки SHA. Сеть и новые выделения учитываются отдельно.

Три блока отложены из этого разрешения: SheetSage transcription (957 571 488 B, CC BY-NC4.0), UniverSR audio upscale (229 072 928 B model/config, MIT code/CC BY4.0 weights), Creator external adapters (**0 B**). Их pins и загрузчики сохранены. Каталог адаптеров не требует загружать чужие голоса или style weights; структурная поддержка проверяется без этих весов. `timm` и `torchdiffeq` относятся только к отложенному UniverSR и не входят в минимальную установку.

## Лицензии и происхождение

**RoFormer — реальный остаточный blocker.** Original publisher [TRvlvr release](https://api.github.com/repos/TRvlvr/model_repo/releases/tags/all_public_uvr_models) имеет пустой body и не даёт явных условий Viperx checkpoint. MIT у [audio-separator](https://pypi.org/pypi/audio-separator/0.47.0/json) и mirror Eddycrack864 не доказывает лицензию оригинальных весов. Его загрузка/использование удерживаются до выяснения условий либо отдельного явного решения человека о ограниченной личной проверке с принятием этой неопределённости. Такое решение не создаёт прав и не доказывает коммерческую готовность. Никакая случайная replacement-модель не выбиралась. При удержании stems этап image-upscale можно завершить самостоятельно.

Demucs original weights: [Meta publisher](https://github.com/facebookresearch/demucs), `dl.fbaipublicfiles.com/demucs/hybrid_transformer`; исходное MIT notice сохраняется. Full SHA взяты из pinned unchanged mirror-manifest, оригинальные имена содержат8символьный SHA prefix; original bodies пока не читались. RealESRGAN берётся только из [официального release v0.1.0](https://api.github.com/repos/xinntao/Real-ESRGAN/releases/tags/v0.1.0), BSD3 notice из [pinned upstream LICENSE](https://github.com/xinntao/Real-ESRGAN/blob/a4abfb2979a7bbff3f69f58f58ae324608821e27/LICENSE). Ожидаемый SHA `4fa0d38905f75ac06eb49a7951b426670021be3018265fd191d2125df9d682f1` подтверждён [LFS metadata неизменённого mirror](https://huggingface.co/api/models/lllyasviel/Annotators/revision/ee6ef4211a08a40873a0710815b682ecc98bccab?blobs=true); GitHub asset digest=null. Это provenance ожидаемого хэша, а не уже проверенные bytes. Future receiver сверяет полные SHA до rename/import.

`diffq-fixed0.2.4` декларирует **CC BY-NC4.0**, поэтому stems dependency set содержит NC компонент. `samplerate0.1.0` wrapper декларирует MIT, bundled **libsamplerate0.1.9 — BSD2**: подтверждено embedded version и [original COPYING](https://github.com/libsndfile/libsamplerate/blob/f6730d03c3e7660bb6ecad8816f1b09c5825142a/COPYING). Это не LGPL/GPL библиотека в данном pin. Wheel не включает полный wrapper copyright notice; exact notice надо получить до распространения, BSD COPYING сохранён отдельно. Это отдельный redistribution hold, а не установленная ошибка локального импорта.

`soxr0.5.0.post1` wrapper и embedded libsoxr: **LGPL2.1-or-later**; PFFFT/FFTPACK permissive notice сохранён. В wheel одна `.pyd`, отдельного libsoxr DLL нет, поэтому нельзя обещать простую динамическую замену. Для распространения нужны notices, applicable corresponding source и replacement/relinking/source/object mechanism LGPL sections4/6; такой комплект сейчас не собран. Внутреннее локальное выполнение и публичное распространение рассматриваются отдельно. Точные notices доступны в [static native receipt](cache/optional-review/88a1b1fc-a4b5-4372-bb16-e7d08d8e687b/native-dll-audit.json).

## Что закрыто статически, что ещё не проверено

Native audit получил **4 227 343 B** wheel/licence/API тел под8MiB cap; исходников/API audit получил **302 299 B** под16MiB cap. Ранний общий metadata traffic не был полностью измерен; общего точного network total не заявляем. **Новых весов, установки, DLL loading, vendor imports, compilation, GPU queries и optional inference не было.**

Два exact wheels сверены по размерам/SHA и разобраны как ZIP/PE. AMD64 libsamplerate imports KERNEL32/msvcrt, CFFI declarations соответствуют exports; wheel METADATA требует cffi>=1 и NumPy — baseline cffi2.1.1/NumPy2.2.6 удовлетворяет этим constraints. Будущий import обязан подтвердить bundled AMD64 DLL path: upstream `find_library` может выбрать global library. SoXR exact cp310 AMD64 `.pyd` imports python310/MSVC/UCRT; named exports и фактическая Windows API-set mapping соответствуют имеющимся файлам Windows11/CPython3.10.11. **Это static ABI, не runtime NumPy/CFFI ABI, resampling или загрузка DLL.** Receipt SHA `73d5ef5c6d4b6f0a9f04c3e84f101223f960a4d9d1d0be96c4625b2dbde03f9d`.

Остальные wheel bodies ещё не audited. Metadata Windowscp310 closure pinned; current Torch2.11.0+cu128/NumPy2.2.6 и **все existing versions сохраняются**. Numba0.61.2 требует NumPy<2.3 и llvmlite0.44; выбранные версии подходят декларациям, реальные native imports не выполнены. Julius0.2.8 имеет wheel, source-only0.2.7 не используется. Cython — готовый Windows wheel для dependency diffq, compilation запрещена.

ONNX prerelease **1.24.0.dev20260928** выбран потому, что audio-separator0.47.0 и [onnx2torch-py3131.6.0](https://pypi.org/pypi/onnx2torch-py313/1.6.0/json) требуют distribution **onnx-weekly**. Stable `onnx` не удовлетворяет этому имени. Latest20261012 требует Python>=3.11; fixed selected cp310 wheel требует>=3.10. No metadata patch/source workaround. CPU onnxruntime1.23.2 сохраняется; [gpu]/[dml], новые CUDA/cuDNN/torchcodec, train/dev/test/docs extras не устанавливаются. Metadata pins не равны выполненному pip resolver/install/check.

## UniverSR: аудит закончен, выполнение отложено

[UniverSR pin d8636623fe0c0704296239c1d3d3c5b911ecb2e0](https://github.com/woongzip1/UniverSR/tree/d8636623fe0c0704296239c1d3d3c5b911ecb2e0), version0.1.5, MIT. Published PyPI wheel нет (version endpoint404).14 package `.py` получены как текст с Git blob OID verification; весь selected inference import/call path прочитан. Для future inference-only wheel нужны9 `.py`, **42 814 B**, плюс original LICENSE/README и metadata. [Source audit/packaging manifest](cache/optional-review/sources-19ca8abed9/selected-source-audit.json), SHA `33d4a255ff1a1ec8d35b02de5c28b0dda9ac2973058501c285dfae29d303d955`. Это selected path audit; training/generic factory APIs не заявляются проверенными.

`from_pretrained(existing local directory)` применяет `yaml.safe_load`, `torch.load(weights_only=True,map_location=cpu)` и fixed classes. Remote hf_hub_download fallback существует, поэтому обязательны проверенные local config/bin и process offline guard. Training `from_local(weights_only=False)` и dynamic `flow.path.get_path`, trainer APIs исключены. `torchinfo` нужен только `unet.main()` dummy test, import/inference его не вызывает. Torch paper environment2.7.1, metadata>=2 допускает2.11, но реальная совместимость ещё не проверена.

Готов рецепт собственного deterministic stdlib ZIP/RECORD packager: exact source bytes, original MIT notice, fixed timestamps/order/modes, WHEEL/METADATA/RECORD, final wheel SHA до install. **Wheel не построен и не установлен**; upstream setup.py/PEP517 backend/native CUDA build не запускается. Audio profile не входит в текущее разрешение.

Источник показывает: midpoint4 steps/CFG1.5 default, minimum32768 samples, ODE solver сохраняет **все steps+1 states**, затем клонирует последний; CFG делает два forward paths. Existing worker —20s chunks/1s overlap, stereo sequential; upstream комментарий «около10GB на3090» не является измерением3060. **Gate11000 MiB сохранён**, supplied admitted free10590−512=10078 → blocked. Теоретический idle12288−512=11776 не доказывает fit и не требует автоматически24GB: нужны отдельное разрешение, exclusive lease, fresh VRAM/RAM/commit admission и реальные short/20s peaks. Gate не снижается.

## Ресурсы и точный будущий порядок

| Блок | Решение для RTX3060 12GB |
|---|---|
| Stems8000 / image4000 MiB | supplied10078 snapshot пропускает численный gate; actual peak/pilot неизвестны |
| UniverSR11000 MiB | supplied snapshot blocked, отдельная idle-card проверка отложена |
| SheetSage | fixed300s padded native window; краткое аудио не доказывает малый peak; отложено |
| Trainer BF16 |20000 MiB: требуется24GB класс, исключён из этого этапа |
| Standard Krea/Qwen | Krea Q4/Q8 12500/18500, Qwen15500–22500 MiB: текущая12GB карта ниже gate; streamed paths не подтверждены |

Fresh disk snapshot `2026-10-12T22:29:41.154855+00:00`: **59 797 303 296 B** свободно E:. После3.5GB максимального нового выделения остаётся **56 297 303 296 B**, ещё **2 610 212 096 B** над50GiB до учёта других pending writes. Их объём неизвестен, поэтому `diskAdmitted=false`. Cap включает source/metadata20MB, unpack+pip temporary1.5GiB и pilots/outputs256MiB; ZIP uncompressed totals проверяются до pip. Если оценка превышаетcap или нет50GiB после всех задач — stop, partial cache сохраняется. Старые weights/outputs/проекты не удаляются; `.part`→final rename на том жеE: без дублирования.

После нового разрешения исполняются только следующие действия, последовательно:

1. Проверить текущий HEAD/relevant source и baseline lock hashes, licences и свежий disk forecast с **известными** other pending writes. Historical audited base `ff5c470...` не является требованием future HEAD equality.
2. Составить отдельные direct-URL/hash-required download и extension locks по active31 records из JSON и exact первичным metadata; оригинальные validation locks не менять. Получить28 отсутствующих wheels через quota-aware receiver. Проверить все ZIP/RECORD/METADATA/.pth/startup/native notices, actual checkpoint loaders и closure. Unrestricted pickle/global side effects — stop для соответствующего профиля, а не source workaround.
3. Offline binary-only `--no-deps --require-hashes` extension install в existingCORE/ART; `pip check`, sequential offline imports/version snapshot; не менять baselineversions. Дополнительная третья venv не создаётся. При runtime ABI/conflict — stop.
4. Получить только8 active model/config files после licence gates, проверить полные SHA и sizes, notices/atomic rename. RoFormerhold сохраняется, если не снят отдельным решением. Никаких automaticdownloads.
5. Остановить только собственные модели, exclusive GPU lease и fresh RAM/commit/VRAM/disk guards. Один synthetic256×256→1024×1024 imagepilot; затем synthetic10s stereo vocals/4stem pilots при licence/admission. Проверить фактические outputs/channels/rate/duration/finite values/timing/peak, не объявлять musicalquality доказанной. Никаких concurrentmodels или deferredpilots.

Команды install **ещё не выполнялись**; указанные extension locks будут созданы на шаге2 и сейчас отсутствуют. Их содержание ограничено active pins; самостоятельный запуск до cache/audit/admission будет ошибкой:

```powershell
Set-Location 'E:\Projects\Ruach_Studio\full-windows-port'
git rev-parse HEAD
# AFTER explicit new approval, exact cached hashes/body audit and disk admission:
.\.venv\Scripts\python.exe -m pip install --no-index `
  --find-links .\windows\cache\optional\wheels --no-deps `
  --only-binary=:all: --require-hashes `
  -r .\windows\requirements-optional-core.lock.txt
.\.venv-art\Scripts\python.exe -m pip install --no-index `
  --find-links .\windows\cache\optional\wheels --no-deps `
  --only-binary=:all: --require-hashes `
  -r .\windows\requirements-optional-art.lock.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv-art\Scripts\python.exe -m pip check
```

Download locks с exact URL/SHA используются только через receiver с ledger: обычный неограниченный pip/curl не доказывает1.5GB cap. Ready receipt появится только после actual import/pilot результатов, failed/held profiles остаются явными blocker. Static research завершён; новые weights, install и ML требуют следующего ограниченного разрешения.

Ранее автоматическая проверка отклонила raw `.pth` read из-за возможной загрузки весов; он не исполнялся. Safe publisher/API JSON дал нужные metadata, поэтому это **не оставшийся blocker** и исключение не запрашивается.
