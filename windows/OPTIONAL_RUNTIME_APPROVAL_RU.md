# Дополнения Ruach Studio: пакет согласования Windows / RTX 3060 12 ГБ

**Это предложение, а не выполненная установка.** Проект: `E:\Projects\Ruach_Studio\full-windows-port`; аудитная база `ff5c470271057e046179e13394e710f3a67a1e8c`. Полный список: [optional-runtime-package.json](optional-runtime-package.json). Сейчас прочитаны реальные locks, локальный код, публичные JSON, небольшие исходники/лицензии/config. Новые модели и wheel bodies не скачивались; imports, сборка, GPU-запросы и инференс не выполнялись.

Предлагается **одно ограниченное разрешение на последовательные этапы ниже**: максимум **3 000 000 000 байт HTTP-тел** с повторами/частями; максимум **5 000 000 000 байт новых выделений E:**; всегда сохранить **50 ГиБ = 53 687 091 200 байт** после учёта оставшихся записей всех задач. Никаких секретов, новых аккаунтов, платных сервисов, облачного инференса, глобальных PATH/CUDA/драйверов/защиты/сети. Неподтверждённые части не становятся готовыми от одного разрешения.

## Включённые функции и ограничения

| Функция | Конкретный вариант | Состояние |
|---|---|---|
| Вокал / инструментал; 4 stems | audio-separator 0.47.0, BS-RoFormer ep317, htdemucs_ft | Windows wheels закреплены; оригинальные условия RoFormer unresolved; реального запуска нет |
| Creator: ноты из записи | SheetSage2-Q8_0.gguf; существующий yue-server.exe /transcribe | Модель закреплена, CC BY-NC 4.0; native peak не измерен |
| Аудио upscale | UniverSR 0.1.5, universr-audio | Нет опубликованного wheel версии; нужен полный source audit/local packaging; VRAM gate сейчас блокирует |
| Изображение upscale | Spandrel 0.4.2 + einops 0.8.2; официальный RealESRGAN_x4plus | Два ART wheels, 386 449 байт; Windows inference ещё не проверен |
| SDXL / Creator адаптеры | Конкретный файл не выбран | Два необязательных unresolved slots, **0 байт квоты**, excluded |

Trainer BF16 требует 20 000 МиБ; Krea Q4/Q8 — 12 500/18 500; стандартные Qwen — 15 500–22 500. Они исключены. MERT custom Python/обучение, paid Civitai, случайные LoRA, LCM/Lightning shortcuts и streamed Qwen сюда не входят. SDXL worker не реализует LCM sampler; популярность адаптера не доказывает совместимость. Existing Writer/Listener/Whisper/SDXL повторно не скачиваются.

## Закреплённые модели

Все **11 файлов**, exact paths/URL/размер/полный SHA-256 указаны в JSON; всего **2 229 584 124 байта**.

| Файлы | Байты | Pin / условия |
|---|---:|---|
| SheetSage2-Q8_0.gguf | 957 571 488 | Serveurperso/YuE2-GGUF @ 64b030e3deb6e8150d2b7c0db641ef5a17eca8a3; конверсия m-a-p/SheetSage2 + MERT; CC BY-NC 4.0 |
| UniverSR config.yaml + pytorch_model.bin | 229 072 928 | woongzip1/universr-audio @ 1c3294844285af851b6ffa56cbde4e43cd41fc2b; CC BY 4.0 weights, MIT code |
| BS-RoFormer .ckpt + .yaml | 639 333 486 | .ckpt original TRvlvr release; SHA/YAML из Eddycrack864 mirror @ 4a3768dfdd3c74104f63b9edda5b1efc8bd29f2c |
| htdemucs_ft: четыре .th + YAML | 336 565 233 | Оригинальные .th dl.fbaipublicfiles.com/demucs; YAML TRvlvr; Meta Demucs MIT repository, retain notices |
| RealESRGAN_x4plus.pth | 67 040 989 | Оригинальный xinntao/Real-ESRGAN release v0.1.0; upstream repository BSD 3-Clause |

**RoFormer licence hold:** original release body пуст; явные условия checkpoint не найдены. MIT у separator/mirror не доказывает условия оригинальных весов. Загрузка/исполнение этой части удерживаются до выяснения условий либо отдельно оговорённого личного оценочного использования с явным признанием неопределённости. Коммерческая готовность не заявляется.

**Hash provenance:** GitHub старых assets возвращает digest=null. Ожидаемый RealESRGAN SHA `4fa0d38905f75ac06eb49a7951b426670021be3018265fd191d2125df9d682f1` подтверждён LFS metadata unchanged mirror lllyasviel/Annotators @ ee6ef4211a08a40873a0710815b682ecc98bccab; размер original asset совпал. Demucs full hashes берутся из existing pinned mirror-manifest; original filenames дополнительно содержат 8 символов SHA. Это ожидаемые хеши с указанным происхождением, **не уже проверенные original bytes**. Future receiver скачивает оригиналы и сверяет полный SHA до rename/import. BSD notice RealESRGAN прочитан в исходнике @ a4abfb2979a7bbff3f69f58f58ae324608821e27; original release не содержит per-asset licence field. Не заменять исходные notices лицензией общего mirror.

Источники: [SheetSage metadata](https://huggingface.co/api/models/Serveurperso/YuE2-GGUF/revision/64b030e3deb6e8150d2b7c0db641ef5a17eca8a3?blobs=true), [UniverSR metadata](https://huggingface.co/api/models/woongzip1/universr-audio/revision/1c3294844285af851b6ffa56cbde4e43cd41fc2b?blobs=true), [original RoFormer release](https://api.github.com/repos/TRvlvr/model_repo/releases/tags/all_public_uvr_models), [Meta publisher](https://github.com/facebookresearch/demucs), [original RealESRGAN release](https://api.github.com/repos/xinntao/Real-ESRGAN/releases/tags/v0.1.0), [RealESRGAN expected SHA metadata](https://huggingface.co/api/models/lllyasviel/Annotators/revision/ee6ef4211a08a40873a0710815b682ecc98bccab?blobs=true).

## Windows binary-only dependency plan

Сохраняются .venv/.venv-art, Python 3.10, Torch 2.11.0+cu128, NumPy 2.2.6 и **все existing distribution versions**. Не создаётся третий полный Torch environment. Original validation locks не переписываются; после разрешения создаются отдельные extension locks/snapshots/receipt.

JSON закрепляет **33 unique wheel records**: filename, size, SHA256, environment, primary release JSON URL. Уже проверенный официальный cached torchvision 0.26.0+cu128 нужен только CORE; ART его содержит. **32 новых сетевых wheels = 65 717 170 байт**; unique compressed с cached torchvision = **74 717 004**. Один einops-файл используется обеими средами. CORE huggingface-hub остаётся 0.36.2, ART — 1.33.0.

Полный граф указан в JSON. numba 0.61.2 требует NumPy <2.3 и llvmlite <0.45: текущий 2.2.6/выбранный 0.44.0 подходят. julius 0.2.8 имеет wheel; source-only 0.2.7 не используется. Cython — готовый cp310 Windows wheel для metadata dependency diffq-fixed; **компиляция расширений не разрешена**.

**Почему prerelease ONNX:** [audio-separator 0.47.0](https://pypi.org/pypi/audio-separator/0.47.0/json) и [onnx2torch-py313 1.6.0](https://pypi.org/pypi/onnx2torch-py313/1.6.0/json) явно требуют distribution name onnx-weekly. Stable onnx 1.20.1 не удовлетворяет этому имени, хотя импорт тоже onnx. Проверенные 0.45/0.46 также требуют weekly. Выбран **1.24.0.dev20260928 cp310 Windows**, Python >=3.10; latest 20261012 требует >=3.11. METADATA не патчится, конфликтующие onnx distributions одновременно не устанавливаются. Это осознанная prerelease-зависимость, требующая теста.

[gpu]/[dml] extras не нужны выбранным Torch RoFormer/Demucs: CPU onnxruntime 1.23.2 сохраняется; Torch CUDA уже есть. ONNX CUDA, DirectML, train/dev/test/docs, pretty-midi, torchcodec, wandb, global CUDA/cuDNN не добавляются. UniverSR worker использует soundfile/tensor, без codec load/save path.

**Лицензии deps:** diffq-fixed 0.2.4 declares **CC BY-NC 4.0** — stems runtime содержит NC dependency. samplerate 0.1.0 declares MIT wrapper, но universal wheel с native library требует чтения bundled DLL terms и проверки architecture. У soxr 0.5.0.post1 licence fields null; wrapper/bundled terms не угадываются. LLVM/BSD notices llvmlite сохраняются. До imports ZIP audit должен подтвердить exact METADATA/RECORD/LICENSE, contained paths, .pth/startup hooks и Windows DLL architecture. Если условия/ABI/closure не подтверждены, остановить компонент, без source-build обхода.

**Метаданные не равны выполненному pip resolver/install/check.** Перед offline install сравнить полный граф с exact baseline versions; никакие implicit installs/downloads не допускаются.

## UniverSR source-only exception

[Source pin d8636623fe0c0704296239c1d3d3c5b911ecb2e0](https://github.com/woongzip1/UniverSR/tree/d8636623fe0c0704296239c1d3d3c5b911ecb2e0), version 0.1.5, MIT; PyPI version endpoint вернул 404. Tree metadata: 1 007 960 байт всех blobs. Это **не опубликованный wheel**.

После разрешения получить только pinned package .py/config/license/metadata в contained vendor/UniverSR, проверить Git blob OIDs и весь selected import path. Собственным проверенным stdlib ZIP/RECORD packager создать deterministic pure wheel **без исполнения upstream setup.py/PEP517 backend**; записать local wheel size/SHA/Requires-Dist до install/import. No unpinned git install, no native/CUDA build. Если аудит/упаковка не завершаются, компонент остаётся blocked. Сейчас прочитаны inference.py/unet.py/pyproject, но **полный source audit ещё не выполнен**.

Selected `universr/inference.py::from_pretrained(local_directory)` применяет `torch.load(weights_only=True)`. Training `from_local` применяет weights_only=False и исключён. Upstream paper uv constraints Torch2.7.1; broad runtime>=2 допускает2.11, фактическая совместимость ещё не проверена.

Spandrel0.4.2 source @724cca389f28c38e1050689d4862a452fd644484 для .pth использует RestrictedUnpickle. Это уменьшает риск, но не заменяет аудит. Для будущего RoFormer/Demucs wheel audit проверить actual checkpoint loader; нельзя молча включать unrestricted pickle/trust_remote_code.

## VRAM и 50 GiB disk reserve

Root snapshot: **10 590 − 512 = 10 078 МиБ** WDDM aggregate admitted free. Здесь новых GPU запросов не было. Stems gate8000 и image gate4000 численно проходят snapshot; реальных peaks нет. **Audio UniverSR gate11000 блокирует.** Теоретическая idle карта:12288−512=11776; existing empty_fits требует no foreign GPU processes/no limit/free>=11264. Такие условия и результат на12GB здесь не проверены; gate не снижается из-за теории.

SheetSage дополняет любой звук до **300 секунд**: короткий файл не доказывает малый native peak. Root должен освободить собственные models, взять эксклюзивный lease, проверить RAM/commit и native admission. Найден только windows/build/full-engine/yue-server.exe; standalone yue-transcribe.exe не предполагается.

JSON snapshot free E:**59 925 880 832 байта**; минус worst new disk5GB =**54 925 880 832**, над50GiB остаётся**1 238 789 632**. Это без неизвестных future writes других задач, поэтому `diskAdmitted=false`. Перед каждой записью всё измерить заново.

Known successful payload **2 295 301 294 B** (models+new wheels). Source/metadata allowance20MB; unpack+pip temp allowance1.5GiB; pilots/outputs256MiB; общий write cap5GB. Перед pip прочитать ZIP Entries uncompressed totals и подтвердить пик. На E применять atomic .part->final rename, не создавать вторую копию models; resume prefix не дублировать. При unknown pending/большем пике/исчерпании квоты — stop, сохранить partial. Старые caches/outputs/models/другие проекты не удалять.

## Конкретные последовательные этапы после нового разрешения

1. Прочитать текущий HEAD и заново проверить relevant source/lock hashes, historical ready, disk и все other pending writes. ff5c470 — база аудита; будущий combined commit не обязан равняться ей. Проверка не требует circular commit SHA. Old ready hash differences объясняются CRLF->LF normalization: **windows/cache/checkpoint/text-normalization.json**, backups before-text-normalization. Версии/модельные и wheel hashes не менялись.
2. Для каждого JSON wheel получить exact metadataUrl, выбрать exact filename+size+SHA и URL files.pythonhosted.org; создать отдельный hashes-required direct-URL download lock по environments. Cached torchvision брать из windows/cache/validation-runtime/wheels с SHA. До каждого HTTP тела проверять received ledger/cap и disk forecast.
3. Download-only cache, static wheel/license/ABI/source audit; завершить gates. Review/package local UniverSR wheel с новым SHA. Получить pinned models, соблюдая RoFormer licence hold. Никаких auto model downloads.
4. Offline install только extension lists, затем pip check и offline imports/version checks по очереди. Сравнить все baseline versions, сохранить новые extension snapshots/ready receipt; historical ready/locks не менять.
5. Root штатно останавливает свои модели, берёт GPU lease и fresh VRAM/RAM/commit guards. Только допущенные profiles получают один synthetic pilot из JSON acceptance. Stop на fail/OOM/no admission; файлы сами по себе не доказывают работу.

Команды ниже **не исполнялись**; extension locks пока не созданы, их нужно получить из JSON и audit receipt:

```powershell
Set-Location 'E:\Projects\Ruach_Studio\full-windows-port'
$p = Get-Content .\windows\optional-runtime-package.json -Raw | ConvertFrom-Json
git rev-parse HEAD
# Перед каждой записью учесть ВСЕ другие задачи; неизвестное не равно нулю.
$otherPending = $null
if ($null -eq $otherPending) { throw 'Нужен объём оставшихся записей других задач' }
$remainingOptional = [long]$p.bounds.maxNewDiskAllocationBytes
if ((Get-Volume -DriveLetter E).SizeRemaining - $remainingOptional - $otherPending `
    -lt [long]$p.bounds.diskReserveBytes) { throw 'Недостаточно резерва 50 GiB' }

# AFTER generated extension locks and exact cache/source/licence audit:
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

Download locks используют exact released URL+SHA: `pip download --no-deps --only-binary=:all: --require-hashes --no-cache-dir -r <download.lock>` допускается только через quota-aware receiver/ledger. Обычный pip/curl без учёта всех тел не доказывает3GB limit. Source wheel audit является отдельным prerequisite, в extension lock включается только после known local hash.

Окончание подтверждается model hashes/notices, binary closure/source wheel receipt, сохранёнными baseline versions, pip check/imports и **реальными результатами каждого допущенного pilot**. Adapters/аппаратно blocked функции остаются unresolved/blocked. Сейчас этих результатов для пакета нет.

Автоматическая проверка отклонила raw .pth read из-за риска получить полный вес; команда не выполнялась. Safe /api/models JSON дал size/SHA. Установочные ограничения не обходились.
