# Listener AI — аудит и пакет для согласования пилота

**12.10.2026: статический аудит официальных исходников, лицензий и GGUF-структуры завершён. Отдельный Writer+Listener пилот согласован: +9.1 GB сети и +20 GiB рабочего диска, с сохранением минимум 50 GiB после ожидаемого роста. Все пять Listener-файлов полностью size/SHA проверены. Реальная native sm86 CUDA сборка и короткий SAPI audio decode завершены; речь без музыки классифицирована корректно. Общее качество музыкальных тегов и120s UI job не проверены. Исторический redirect traffic не измерялся; ограничение учёта описано ниже.**

## Поддержка и текущий контракт

Общий с Writer источник — **llama.cpp v0.6.0**, commit `8345f333951c661d166b00e6f9362e553768f292`, MIT. [Закреплённая документация](https://github.com/ggml-org/llama.cpp/blob/8345f333951c661d166b00e6f9362e553768f292/docs/multimodal.md) явно перечисляет Qwen2.5-Omni 3B/7B с audio input. [clip loader](https://github.com/ggml-org/llama.cpp/blob/8345f333951c661d166b00e6f9362e553768f292/tools/mtmd/clip.cpp) поддерживает `qwen2.5o` и направляет аудиочасть в QWEN2A. Прочитанный clip.cpp сверён с Git blob выбранного commit: `50fb6c408aaa9973f0c846dd190efd959dddf775`, совпадает.

[Парсер](https://github.com/ggml-org/llama.cpp/blob/8345f333951c661d166b00e6f9362e553768f292/common/arg.cpp) принимает `--audio`, `--mmproj`, `--n-gpu-layers`, `--ctx-size`, `--n-predict`, `--temp`. **`--mmproj-ntoken` отсутствует и не поддерживается.** Он не входит в команду нашего Listener. `--image-max-tokens` относится к изображению и не является ограничителем аудио.

Фактический файл нашего порта — `lab/listener.py`, а не `listener_job.py`. Backend `training.listen()` принимает имя локального prepared dataset и выбранный профиль, запускает этот Python-процесс, передаёт GPU/model/mmproj. GGUF-ветка читает WAV локально, ffmpeg вырезает excerpt в mono PCM 16 kHz и передаёт файл в `llama-mtmd-cli.exe --audio <path> -p <tags-prompt>`.

[CLI source](https://github.com/ggml-org/llama.cpp/blob/8345f333951c661d166b00e6f9362e553768f292/tools/mtmd/mtmd-cli.cpp) помещает media marker в user message, применяет chat template, интерпретирует аудио через mtmd и выдаёт текст. Здесь **нет OpenAI audio JSON/base64, upload или облачного API**. Writer использует отдельный локальный llama-server с текстовым `/v1/chat/completions`; нельзя направлять его Qwen3 текстовый endpoint на аудио Listener.

Текущая команда Listener: `-m MODEL --mmproj PROJECTOR --audio EXCERPT -p PROMPT -ngl 99 -c 8192 -n 160 --temp 0`. Временный файл — проектный `lab/cache/tmp`; выбранный физический GPU — `CUDA_VISIBLE_DEVICES`. Stdout разбирается как последняя непустая строка тегов, stderr содержит диагностику. Ошибочный exit code помечает track failed; это проверено native mocks и реальным short pilot: styles.json содержит только реальную строку ответа, диагностика сохранена отдельно.

Текущий UI job использует excerpt **120 секунд**. Для первого пилота предлагается **один синтетический excerpt 10 секунд через CLI `--seconds 10 --only 001`**, а не полный UI dataset job. Сначала проверить `--help`/`--version`, затем load/decode, теги, очистку процесса и память. Не использовать пользовательские песни.

## Совместимость Q8-проектора: что доказано

С разрешения на ограниченное чтение заголовков прочитаны HTTP byte ranges; GGUF-файлы на диск не сохранялись. Для проекторов достаточно первых 65 536 байт; таблицы заканчиваются на 58 131 и 58 264 байтах. Заголовок language GGUF прочитан частично в пределах 4 MiB: нужные architecture/embedding поля получены, полный tokenizer/tensor listing в этот лимит не вместился.

Сравнение официального ggml-org F16 mmproj и предлагаемого mradermacher Q8:

- GGUF v3, **1008 тензоров в обоих**, все имена и размеры тензоров совпадают.
- `clip.projector_type=qwen2.5o`, `clip.has_audio_encoder=true` в обоих.
- Audio hidden 1280, 32 blocks, 20 attention heads, 128 mel bins; output projection **3584** — совпадает с `qwen2vl.embedding_length=3584` language model.
- Q8-файл: 586 F32, 35 F16, 387 Q8_0 тензоров. Свёрточные audio weights сохраняют F16; norms/biases — F32.
- Закреплённый [CUDA MMQ source](https://github.com/ggml-org/llama.cpp/blob/8345f333951c661d166b00e6f9362e553768f292/ggml/src/ggml-cuda/mmq.cu) обрабатывает Q8_0 matrix multiplication. Статическая архитектурная/размерная совместимость подтверждена.

Структурная проверка не доказывает численную эквивалентность проекторов или общее качество модели. Полные checksum скачанных весов и CUDA загрузка/декодирование теперь проверены; точный непрерывный пик VRAM и длинные120s excerpts не проверялись. Отдельный upstream Linux benchmark не заменяет проверку данного pin на этом компьютере. Доказательство: `windows/cache/listener_static_headers.json` (только разобранные metadata/tensor descriptors).

## Точные файлы и лицензии

| Артефакт | URL / размер / ожидаемый SHA256 |
| --- | --- |
| Language Q4_K_M | `https://huggingface.co/ggml-org/Qwen2.5-Omni-7B-GGUF/resolve/89b785438c8901d4635e42f50480ba5985a1bbf1/Qwen2.5-Omni-7B-Q4_K_M.gguf` — **4 683 072 384 bytes**, SHA256 `09883dff531dc56923a041c9c99c7c779e26ffde32caa83adeeb7502ec3b50fe`. |
| Projector Q8_0 | `https://huggingface.co/mradermacher/Qwen2.5-Omni-7B-GGUF/resolve/658a1c70e91733330bcad348eead24bb4d15d9eb/Qwen2.5-Omni-7B.mmproj-Q8_0.gguf` — **1 548 488 608 bytes**, SHA256 `858f1ff0dab23c9139a20a3ef44cdeff85fd392c401ffcf436fe647d3496fdea`. |
| Оригинальная Apache-2.0 license | `https://huggingface.co/Qwen/Qwen2.5-Omni-7B/resolve/ae9e1690543ffd5c0221dc27f79834d0294cba00/LICENSE` — **11 343 bytes**, SHA256 `8d5eb5f806d01e8f5ea2c5a52f7d68ebc54b196b1cfbe1cd5dfa4b94e482a9c6`. Это закреплённая историческая revision основного автора от 30.04.2025. |
| ggml-org conversion notice | `https://huggingface.co/ggml-org/Qwen2.5-Omni-7B-GGUF/resolve/89b785438c8901d4635e42f50480ba5985a1bbf1/README.md` — **471 bytes**, SHA256 `e7411584ea811a7e153c11b531977f098e90e488503b904fccaa3dc52c7c7c33`. |
| mradermacher conversion notice | `https://huggingface.co/mradermacher/Qwen2.5-Omni-7B-GGUF/resolve/658a1c70e91733330bcad348eead24bb4d15d9eb/README.md` — **3764 bytes**, SHA256 `e9e1bda88620153be5f14809a3fd585d4ad91739ce5a5ff60c1d85ff172a3039`. |

SHA весов — ожидаемые значения из закреплённой LFS metadata; полный локальный hash должен совпасть после отдельно согласованной загрузки. Лицензия/карточки прочитаны целиком как текст и их SHA подсчитаны при аудите.

Историческая исходная revision от **26.03.2025** `4728b48bcd588a84f0353426515f27f5db911d8a` также содержит [тот же Apache-2.0 LICENSE](https://huggingface.co/Qwen/Qwen2.5-Omni-7B/resolve/4728b48bcd588a84f0353426515f27f5db911d8a/LICENSE): **11 343 bytes**, SHA256 `8d5eb5f806d01e8f5ea2c5a52f7d68ebc54b196b1cfbe1cd5dfa4b94e482a9c6`. Оба текста прочитаны полностью и совпадают по байтам; таким образом, Apache-2.0 подтверждён и для первоначальной публикации, и для revision от 30.04.2025. Повторная загрузка второй копии лицензии не требуется.

[Исходная лицензия Qwen](https://huggingface.co/Qwen/Qwen2.5-Omni-7B/blob/ae9e1690543ffd5c0221dc27f79834d0294cba00/LICENSE) — Apache-2.0, copyright Alibaba Cloud 2025. Конверсия ggml-org хранит старый label `qwen-research`, но её link указывает на оригинальный Qwen LICENSE; GGUF metadata обоих проекторов и language-файла указывает `apache-2.0`. mradermacher card также указывает Apache-2.0. Сохранять оригинальную LICENSE **и обе conversion notices**, не заменять исходные labels собственной интерпретацией. Логотипы/марки не включаются; веса не публикуются в Git. Эта запись фиксирует источники, без юридической гарантии.

## Добавочный бюджет к уже согласованному пакету

Родитель подтвердил: уже согласованный пакет 25 GB/runtime содержит SDXL + Whisper; **Listener в него не входит**.

- Listener weights: **6 231 560 992 bytes**, с license/notices **6 231 576 570 bytes**. Предельный сетевой бюджет **+6.3 GB**.
- Writer Qwen3 4B + shared llama.cpp source: отдельный cap **+2.8 GB**. Исходник llama.cpp (175 814 070 bytes файлов по Git metadata) учитывается **один раз**; обе сборки используют тот же checkout.
- Совместный новый сетевой cap **+9.1 GB** к уже согласованным 25 GB. Дополнительных новых моделей сверх названных нет; при недоступном URL не выбирать другой repo/quant автоматически.
- Рабочий диск: **+20 GiB** суммарно Writer 10 + Listener 10 (веса, Git/source, две build-папки, временные файлы/кеши). Перед этапом требуется **не менее 50 GiB свободного диска глобально**, после завершения ранее согласованных загрузок/установки; текущий снимок свободного диска не является разрешением пропустить новый preflight.

Текущий Windows GGUF admission перед model import/load: physical RAM available >=10 GiB и machine-wide commit headroom >=11 GiB. Это минимум по фактическому короткому пилоту, не доказательство ресурсов120s; при отсутствии machine-wide counters запуск прекращается. Для compiler admission отдельно6GiB RAM/4GiB commit и live critical floors4GiB/2GiB. Listener: минимум upstream gate **8200 MiB свободной VRAM**, для первой Windows проверки желателен запас >=9000 MiB; это пороги допуска, не ограничитель памяти. Linux upstream peak 7480 MB при 120s — лишь ориентир. В Windows short pilot наблюдалось до8520MiB общей GPU memory.used; выборки не доказывают точный пик. CPU/RAM Listener оценочно резервировать 10 GiB, Writer остановить на время первого пилота. CUDA/Creator/Artist jobs сериализуются; idle Creator/Artist cache освобождается, потом свободная VRAM проверяется снова. При нехватке памяти этап останавливается, без изменения pagefile/драйверов/системных настроек.

## Проверенная сборка и команды для повторной установки

Shared source: `vendor/llama.cpp`, commit `8345f333951c661d166b00e6f9362e553768f292`, verified Git tree `88538af4019aa9d18026ff43e446c34fb7456adf`. Все 3687 source blobs проверены по Git SHA1/size/mode; checkout получен из официального codeload archive, фиктивный Git HEAD не создавался. `source-pin.json` хранит вычисленный archive SHA256 `ea153f18923e18f47d8c52c55cde0fbc446102cccfa83356964fe7620b7c8898` (publisher checksum отсутствует). Writer CPU build — `windows/build/writer-cpu`. Первая успешно завершённая CUDA сборка сохраняет `vendor/llama.cpp/build`; это явно исключённое generated subtree, исходные blobs не изменяются. Опубликованный runtime и следующие свежие CUDA builds используют `windows/build/listener-cuda`; locator разрешает только эти два bounded build paths.

CUDA использовать только уже имеющуюся portable 12.8.1 + MSVC2022/Ninja, архитектура **86**. Ninja избегает регистрации portable CUDA в Visual Studio/MSBuild. Собирать только `llama-mtmd-cli`, parallel 1. Согласованный one-job build завершился успешно в прежнем vendor/llama.cpp/build; runtime отдельно опубликован в windows/build/listener-cuda/bin. Ниже параметры для будущей свежей сборки в canonical output, запускать её сейчас повторно не требуется:

```powershell
. .\windows\Common.ps1
$listenerTools = Get-RuachToolchain
Import-RuachCompiler -Tools $listenerTools
$env:TEMP = Join-Path (Get-Location).Path 'windows\cache\listener-build'
$env:TMP = $env:TEMP
$env:CUDA_CACHE_PATH = Join-Path (Get-Location).Path 'windows\cache\listener-cuda'
New-Item -ItemType Directory -Force -Path $env:TEMP, $env:CUDA_CACHE_PATH | Out-Null
$listenerArgs = @(
 '-S', '.\vendor\llama.cpp', '-B', '.\windows\build\listener-cuda', '-G', 'Ninja',
 '-DCMAKE_BUILD_TYPE=Release', "-DCMAKE_MAKE_PROGRAM=$($listenerTools.Ninja)",
 "-DCMAKE_CUDA_COMPILER=$(Join-Path $listenerTools.CudaRoot 'bin\nvcc.exe')",
 "-DCUDAToolkit_ROOT=$($listenerTools.CudaRoot)", '-DCMAKE_CUDA_ARCHITECTURES=86',
 '-DGGML_CUDA=ON', '-DGGML_CUDA_NCCL=OFF', '-DGGML_CUDA_CCCL_VERSION=',
 '-DGGML_CUDA_FA=ON', '-DGGML_CUDA_FA_QUANTS=f16-f16',
 '-DGGML_OPENMP=OFF', '-DGGML_VULKAN=OFF', '-DGGML_RPC=OFF', '-DBUILD_SHARED_LIBS=OFF',
 '-DLLAMA_BUILD_IS_DEV=OFF', '-DLLAMA_BUILD_COMMON=ON', '-DLLAMA_BUILD_TOOLS=ON',
 '-DLLAMA_BUILD_SERVER=OFF', '-DLLAMA_BUILD_TESTS=OFF', '-DLLAMA_BUILD_EXAMPLES=OFF',
 '-DLLAMA_BUILD_APP=OFF', '-DLLAMA_BUILD_UI=OFF', '-DLLAMA_USE_PREBUILT_UI=OFF',
 '-DLLAMA_OPENSSL=OFF', '-DLLAMA_BUILD_BORINGSSL=OFF', '-DLLAMA_BUILD_LIBRESSL=OFF',
 '-DLLAMA_LLGUIDANCE=OFF', '-DLLAMA_SUBPROCESS=OFF', '-DFETCHCONTENT_FULLY_DISCONNECTED=ON'
)
& $listenerTools.CMake @listenerArgs
if ($LASTEXITCODE -ne 0) { throw 'Listener configure failed; no new dependency fallback' }
& $listenerTools.CMake --build .\windows\build\listener-cuda --target llama-mtmd-cli --parallel 1
if ($LASTEXITCODE -ne 0) { throw 'Listener build failed' }
```

В закреплённом ggml CCCL-fetch включается только при непустом `GGML_CUDA_CCCL_VERSION`; здесь он пустой, используется CCCL существующего SDK. NCCL, UI/HF assets, Rust/LLGuidance и SSL-library fetch выключены. CMake 3.31.6 подходит для явно заданной 86; замечание source о новых Blackwell архитектурах/3.31.8 не применяется. Совместимость этого pin подтверждена фактической Release/sm86 сборкой с MSVC19.44.35223.0 и NVCC12.8.93 (CUDA12.8.1), все332 шага завершились успешно.

Загрузка завершена собственным bounded stdlib installer с точными URL/size/SHA выше; language в `checkpoints/Qwen2.5-Omni-7B-GGUF/`, projector в его `mradermacher/`. Существующие валидные файлы не перекачивать и не заменять. Сохранить license/cards рядом. Веса, vendor source, cache/build/logs в Git не включать.

Согласованный pilot использовал один собственный SAPI prepared track. Для ручного запуска Listener на уже подготовленном локальном наборе из корня проекта (занятость GPU и память проверять заранее):

```powershell
.\.venv\Scripts\python.exe .\lab\listener.py SYNTHETIC_SET --gpu 0 --seconds 10 --only 001 `
 --model .\checkpoints\Qwen2.5-Omni-7B-GGUF\Qwen2.5-Omni-7B-Q4_K_M.gguf `
 --mmproj .\checkpoints\Qwen2.5-Omni-7B-GGUF\mradermacher\Qwen2.5-Omni-7B.mmproj-Q8_0.gguf
```

Offline wrapper уже закреплён и проверен: model/projector разрешены только внутри `checkpoints`, WAV внутри подготовленного dataset, временный excerpt внутри `lab/cache/tmp`, CLI внутри опубликованного `windows/build/listener-cuda` или сохранённого `vendor/llama.cpp/build`; argv содержит абсолютные пути. URLs/UNC и выход из этих каталогов отклоняются до запуска. Унаследованные `LLAMA_*`, `MTMD_*`, RPC, HF endpoint/token, OpenAI credentials и proxy overrides удаляются из окружения дочернего CLI. Флаги `--offline`, `--jinja`, batch 256 / ubatch 128 / threads 4 подтверждены parser выбранного pin; `--simple-io` ограничен другими examples и здесь не используется.

Одноразовый native child получает `stdin=DEVNULL`, отдельную process group и скрытое окно; непустые prompt+audio включают single-turn ветку mtmd. CLI сам добавляет media marker, применяет встроенный в GGUF chat template и после генерации завершает работу. При timeout/прерывании wrapper очищает только собственное дерево Popen через платформенный helper. `lab/cache/listener/listener-*/0001/` сохраняет argv/exit/time и раздельные stdout/stderr, без сохранения полного окружения или секретов. Неуспешный CLI/пустой ответ не публикует tags.

Проверено **37 native stdlib synthetic/mocked +2 actual held-reader тестами**, включая argv, local containment, удаление remote/secret overrides, закрытый stdin, очистку собственного child по timeout и worker failure, Windows atomic JSON publication. Согласованный сторонний CLI теперь реально собран и выполнил decode ниже. Дополнительно12 installer,1 owned build-memory cleanup и4 evidence parser/semantic tests прошли без запуска моделей.

Принятие пилота: exit0, audio encoder/правильный projector в диагностике, отсутствует внешняя сеть/скачивание, styles.json содержит только результат модели, время/RAM/VRAM измерены, GPU lease освобождён и процесс закончился. Контекст/аудиобюджет и качество тегов на 120s UI job проверяются отдельно после успешного короткого пилота. Переключение на F16/другой backend или изменение memory gates требует отдельного решения, не автоматического скачивания.


## Выполнение согласованного пилота

`windows/Install-ListenerPilot.ps1` имеет отдельные этапы, по умолчанию только `Status`. Download/Build/Pilot уже выполнены; ниже справочные команды, повторять их сейчас не требуется:

```powershell
.\windows\Install-ListenerPilot.ps1 -Mode Status
.\windows\Install-ListenerPilot.ps1 -Mode Download -PendingCoreBytes 0
.\windows\Install-ListenerPilot.ps1 -Mode Verify
# Build и Pilot запускаются по координации с остальными тяжёлыми задачами:
.\windows\Install-ListenerPilot.ps1 -Mode Build -PendingCoreBytes 0
.\windows\Install-ListenerPilot.ps1 -Mode Fixture
.\windows\Install-ListenerPilot.ps1 -Mode Pilot -PendingCoreBytes 0
```

Сетевой ledger — `windows/cache/listener/network-ledger.json`: перед каждым HTTP запросом весь запрошенный диапазон консервативно списывается в предел **6 300 000 000 bytes**. Незавершённый/прерванный запрос не возвращает этот резерв. HTTPS/206/Content-Range/длина проверяются, автоматических retry нет. Не более шести диапазонов по 16 MiB одновременно, staging не более одного такого окна; части копируются в contiguous prefix и удаляются только после записи. Final filename появляется после полного size/SHA256; существующие несовпадающие файлы сохраняются. Двенадцать no-network тестов установщика подтвердили cap-before-request, resume, hashing, bounds, disk guard и параллельную сборку.

Download phase каждый раз проверяет реальный свободный диск и актуальные pending allocations. После завершения основной установки core, Writer weights/source/CPU build уже размещены: `PendingCoreBytes=0`; остаточный CUDA/temp/pilot reserve `AdditionalAiReserveBytes=3221225472` (3 GiB), согласованный в пределах общего 20 GiB cap. Уже записанные данные повторно не резервируются. При исчерпании места или byte cap downloader останавливается, сохраняя prefix/chunks/ledger; новый запуск продолжает только недостающие байты.

Подготовка fixture уже реально проверена: `datasets/prepared/windows-listener-pilot-20261012-205111-9b08f8/001.wav`, **10.27 s, PCM16 mono 16000 Hz**, синтез установленным локальным Windows SAPI голосом. Пользовательские записи и cloud TTS не используются. Pilot stage создаёт своё новое fixture (или напрямую listener_pilot.py --dataset повторно использует собственный SAPI fixture с сохранением предыдущих результатов), проверяет все пять SHA256, собирает только дерево собственного wrapper/CLI, RAM/commit и наблюдаемые GPU значения. Отчёт — `windows/cache/listener/pilot/<dataset>/attempt-<time>-<id>/metrics.json`, stdout wrapper — рядом, точные CLI argv/stdout/stderr — в `lab/cache/listener/`. Child получает фиксированный общий GPU0 mutex и engine port41868; реальная GPU free проверка выполняется после lease и передачи idle engine cache. Значения с интервалом опроса являются наблюдаемыми максимумами, а не гарантированным точным пиком памяти.

При принятии GPU-результата wrapper требует реальный CUDA0 buffer и полное `offloaded N/N layers to GPU` из pinned loader diagnostics. Exit0 с CPU/частичным offload не публикует новые tags; `backend=cuda` сохраняется только после этой проверки. Проверка основана на выбранном `src/llama-model.cpp`, а не на одном лишь запрошенном `-ngl 99`.

## Фактически завершённая загрузка

Оба GGUF и все три license/card files полностью проверены по указанным size/SHA256; downloader завершился с exit0. Получено **6 231 576 570 bytes**; консервативно списано **6 248 286 558 bytes**, включая незачтённый обратно прерванный диапазон. До учёта оценочной redirect allowance artifact-only остаток51 713 442bytes; ledger не сбрасывался. `windows/cache/listener/network-ledger.json` содержит verified=true и SHA каждого файла. Это отдельная проверка данных; фактический inference описан ниже.

Во время завершённой one-job сборки действовал native GetPerformanceInfo live guard:2GiB machine commit /4GiB availableRAM critical floors; breach завершает только собственное дерево compiler и сохраняет completed objects. Следующий свежий Build использует `listener_resources.py` и canonical output folder. Реальный stdlib child cleanup при искусственном critical memory reading проверен командой `py -3.10 windows/test_listener_resources.py` (1PASS); никаких CUDA моделей этот тест не запускал. Начальные6/4GiB admission и live floors не являются hard memory limits.

## Уточнение HTTP accounting после завершения

`received_payload_bytes=6231576570` — реальные байты пяти конечных файлов. `charged_payload_upper_bound=6248286558` — консервативно зарезервированные конечные responses, включая прерванный диапазон. Первоначальный urllib handler отдельно не регистрировал тела промежуточных redirects, поэтому эти поля **не доказывают общий объём всех HTTP bodies**. Исходный журнал сохранён byte-for-byte в `windows/cache/listener/network-ledger-before-redirect-review.json`; quota не сбрасывалась, файлы повторно не загружались.

Для планирования в оставшемся лимите выделено **48MiB=50331648bytes** на прежние redirects: оценка384requests ×2hops ×64KiB/body. При этих предположениях сумма6298618206bytes остаётся внутри6.3GB, остаток1381794bytes. Предположения не являются измерением или гарантированным историческим upper bound; ledger явно содержит `historical_all_http_body_cap_verified=false`. Точный прошлый redirect traffic нельзя восстановить из сохранённых журналов. SHA/size proofs файлов остаются действительными.

Будущий transport разрешает максимум2HTTPS redirects, ограничивает каждое redirect body64KiB, зарезервирует бюджет до чтения и регистрирует полученные байты отдельно. Все параллельные ledger mutations используют один lock. Общий planning cap учитывает прежнюю оценочную allowance и новые redirect reserves.12no-network installer tests прошли, включая byte count, oversized redirect и cap-before-read. Это HTTP-body accounting; headers/TLS overhead не выдаётся за измеренный трафик.


## Итог реального Windows пилота

Runtime: `windows/build/listener-cuda/bin/llama-mtmd-cli.exe`, **58 963 968bytes**, SHA256 `52a050560da6c9a36c7dfa986cdb454ff39a8bd7a264be297d3dbde8dd8ffa1b`. Реальный `--version` сообщает v0.6.0/commit8345f333951c661d166b00e6f9362e553768f292; `--help` успешен. Source/provenance, flags, binary SHA и inference evidence: `windows/build/listener-cuda/runtime-proof.json`. Существующие CUDA DLLs найдены через process-local environment, новые драйверы/DLL в Windows не устанавливались.

Сборка завершилась с exit0; compiler и memory guard завершены. Из454 наблюдений guard: минимум machine commit headroom3 042 590 720bytes, available RAM12 747 202 560bytes; critical floors2GiB/4GiB не нарушались. Журнал `windows/cache/listener/build-memory.json`. Admission6/4GiB и floors не являются hard memory caps.

Финальный отчёт: `windows/cache/listener/pilot/windows-listener-pilot-20261012-205111-9b08f8/attempt-20261012-230751-c4e836/metrics.json`. Исходный report до лёгкого исправления parser сохранён в `metrics-before-evidence-review.json`; модель для пересчёта counters не запускалась. Native argv/stdout/stderr: `lab/cache/listener/listener-_v_5vrbl/0001/`.

- Один excerpt10s из собственного SAPI WAV10.27s; stdin DEVNULL, local absolute weights/projector/audio, `--offline --jinja --verbosity4 --perf`, общий GPU0 mutex, engine port41868. Отсутствуют URL/HF download arguments; network trace всей системы не выполнялся.
- Native exit0 за**5.219s**, wrapper**9.312s**; loader: **offloaded29/29 layers**, CUDA0 buffer4168.09MiB, audio encoder найден, оба CLIP contexts наCUDA0. CPU/partial-offload fallback не выдаётся за CUDA успех.
- Native counters: prompt eval**942tokens /701.39ms /1343.05tokens/s**; generation eval**4runs /71.88ms /55.65tokens/s**. Runs — значение loader, не самостоятельно посчитанные output tokens.
- Реальный ответ: **`speech, no music`**. Прошёл узкий тест speech/spoken-word без придуманных жанров/инструментов. Это не проверка общего понимания музыки, инструментов, жанров или 120s UI job.
- Наблюдаемый max общей GPUmemory.used**8520MiB**; native process peak working set**4 823 511 040bytes**, peak commit**8 769 142 784bytes** по доступным process counters. Минимум machine commit headroom**2 988 544 000bytes**, available RAM**13 496 246 272bytes**. Значения ограничены интервалом выборок; другие desktop consumers входят в общие GPU/system readings. После child exit отчёт показывает GPUfree10589MiB и commit11 775 356 928bytes; отдельная последующая проверка не обнаружила owned CLI/Python.

Первый реальный decode со старым music-biased prompt выдал `electronic, synth-pop, dreamy, female vocal, belted, synthesizer, electric guitar, reverb-heavy, slow, minor` для речи без музыки: **провал качества**, полностью сохранён в attempts230028/230417 и `styles.before-speech-prompt-e3a70e4f.json`. Первый wrapper отказал до CLI из-за отличавшегося WDDM admission policy; затем использован уже принятый Studio `aggregate` с veto известных чужих тяжёлых процессов. Финальный общий prompt допускает speech/no-music и не содержит текста/названия fixture. Подбор prompt на этом завершён.

Pilot и production GGUF listener теперь требуют исходный machine-wide commit headroom**не менее11GiB** и available RAM**10GiB** до импорта/загрузки, учитывая измеренный native peak commit≈8.17GiB и запас; первоначальные8GiB были оценкой. Текущий gate8200MiB VRAM остаётся admission, не гарантией для длинного excerpt. Освободить другие модели и проверять ресурсы; не запускать параллельно Creator/Artist. Если процесс запущен вручную в foreground, остановка — Ctrl+C; wrapper очищает собственное дерево. Для Studio — штатный Stop-Full.ps1. Повторная установка/скачивание/сборка сейчас не нужны.

Лёгкая повторяемая проверка из корня (без vendor/model execution):

```powershell
.\.venv\Scripts\python.exe -m unittest lab.test_native_audio lab.test_atomic_audio -v
.\.venv\Scripts\python.exe .\windows\test_listener_installer.py
.\.venv\Scripts\python.exe .\windows\test_listener_resources.py
.\.venv\Scripts\python.exe .\windows\test_listener_pilot.py
```

Два held-reader checks отдельно: `py -3.10 -m unittest lab.test_atomic_audio -v` (Windows CreateFileW reader без FILE_SHARE_DELETE; release/retry/no partial JSON и exhaustion/preserved part). Эти тесты не являются paired model/optimizer transaction.
