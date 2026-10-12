# Writer AI — отдельный пакет на согласование

**Статус 12.10.2026: установка Writer после подтверждения выполняется.
Готовность будет отмечена только после сборки и реальных локальных тестов.**

Предлагается локальный CPU llama-server с Qwen3-4B Q4_K_M. Нужны согласие на
скачивание, исполнение CMake/сборку стороннего runtime, запуск и короткий
синтетический тест. Python/PyTorch, WSL, драйвер, системный установщик и новые
credentials для этого варианта не требуются. GPU остаётся для музыки/Artist/Refiner.

## Источники и pins

| Артефакт | Закреплённые данные |
| --- | --- |
| Основная модель | [Официальный Qwen/Qwen3-4B-GGUF](https://huggingface.co/Qwen/Qwen3-4B-GGUF/tree/bc640142c66e1fdd12af0bd68f40445458f3869b), revision **bc640142c66e1fdd12af0bd68f40445458f3869b**. Qwen3-4B-Q4_K_M.gguf: **2 497 280 256 bytes**, 2.497 GB / 2.326 GiB. Apache-2.0; LICENSE той же ревизии: 11 544 bytes. |
| SHA256 основной модели | **7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5**, из LFS metadata официального HF API. |
| Runtime | [Официальный llama.cpp v0.6.0](https://github.com/ggml-org/llama.cpp/releases/tag/v0.6.0), опубликован 05.10.2026, commit **8345f333951c661d166b00e6f9362e553768f292**. [MIT LICENSE](https://github.com/ggml-org/llama.cpp/blob/8345f333951c661d166b00e6f9362e553768f292/LICENSE). Git tree: 3 687 файлов, сумма blob sizes **175 814 070 bytes**. Это объём исходных файлов, не измеренный сетевой объём клонирования. |
| Меньший вариант вместо 4B | [Официальный Qwen/Qwen3-1.7B-GGUF](https://huggingface.co/Qwen/Qwen3-1.7B-GGUF/tree/90862c4b9d2787eaed51d12237eafdfe7c5f6077), revision **90862c4b9d2787eaed51d12237eafdfe7c5f6077**. В этой ревизии есть только Q8_0: Qwen3-1.7B-Q8_0.gguf, **1 834 426 016 bytes**, SHA256 **061b54daade076b5d3362dac252678d17da8c68f07560be70818cace6590cb1a**, Apache-2.0. |

Пакет скачивает только 4B. Альтернатива 1.7B экономит 662 854 240 bytes, но содержит
меньше параметров; возможное ухудшение сложной правки/русских рифм — предположение,
не результат теста. При 32 GB RAM основной вариант 4B разумнее этой небольшой экономии.
[Карточка Qwen](https://huggingface.co/Qwen/Qwen3-4B-GGUF) описывает multilingual/creative
writing и thinking/non-thinking; качество песен этого порта пока не измерено.

Pin llama.cpp общий с предложением Listener; CPU Writer и CUDA Listener должны иметь
разные build directories. Этот GGUF не заменяет safetensors Qwen3-4B-Instruct-2507,
который Artist использует для подготовки обложек: там другой runtime.

## Бюджет

Проверенный CPU: i7-11700F, 8 cores / 16 threads; RAM 32 GB. Начальная конфигурация:
4 threads, 1 slot, context 8192, batch 256 / ubatch 128, f16 KV, GPU layers 0.

4B: 36 layers × 8 KV heads × head_dim 128 × 8192 tokens × 2(K+V) × 2 bytes
= **1.125 GiB** расчётного KV cache. Плюс 2.326 GiB весов и graph/buffers:
предварительно **4–6 GiB RAM процесса**, резервировать **8 GiB**. Это расчёт, не
измеренный peak/скорость. CPU-only build не требует VRAM.

Перед тяжёлым этапом повторить check: workspace working budget **≤10 GiB**, при сохранении общего ранее согласованного
остатка **≥50 GiB free** на диске на каждом тяжёлом этапе; **10 GiB physical
RAM available**, **8 GiB commit headroom**. Если меньше, не запускать. Чтение
12.10.2026 показывало около 15.1 GiB physical available, 7.88 GiB commit headroom и 107.9 GiB E:
free. Последний точный PerfOS counter: CommitLimit 39 465 603 072 bytes, CommittedBytes 31 009 112 064 bytes. На этом снимке commit headroom ниже порога 8 GiB: тяжёлый этап пока не запускать; повторить проверку в простое/после закрытия тяжёлых приложений. Показатели меняются. Сборка в один job; её RAM/время пока не измерены.
Сначала тестировать Writer в простое; остановить его перед тяжёлым Artist/Trainer,
если общий memory budget не проходит.

CPU может отвечать медленно. Writer Max output tokens: начать с 512–1024.
Исходный default 8192 плюс prompt не помещается в выбранный context. Creator Idea/Muse
просит 4096 tokens; длинный knowledge/prompt может вызвать context error. Это нужно
проверить после согласования, а не заявлять заранее, что длинные задачи работают.

## Команды только после согласования

Из корня отдельной ветки, в новом PowerShell процессе. Все данные внутри проекта.
models/, vendor/, windows/build/ и windows/cache/ уже исключены из Git.
Ниже показан план; ни одна команда клонирования/загрузки/сборки/запуска не выполнена.

Изолировать временные файлы и клонировать pin. Перед загрузкой требуется общий byte-ledger/cap wrapper родителя, описанный ниже:

~~~powershell
$ErrorActionPreference = 'Stop'
$writerRoot = (Get-Location).Path
$writerCache = Join-Path $writerRoot 'windows\cache\writer'
New-Item -ItemType Directory -Force -Path $writerCache | Out-Null
$env:TEMP = $writerCache
$env:TMP = $writerCache
$env:LLAMA_CACHE = Join-Path $writerCache 'llama-cache'
$env:HF_HOME = Join-Path $writerCache 'hf'
$env:GIT_TERMINAL_PROMPT = '0'
git -c credential.helper= clone --depth 1 --single-branch --filter=blob:none --branch v0.6.0 https://github.com/ggml-org/llama.cpp.git .\vendor\llama.cpp
if ($LASTEXITCODE -ne 0) { throw 'llama.cpp clone failed' }
$writerPin = (git -C .\vendor\llama.cpp rev-parse HEAD).Trim()
if ($writerPin -ne '8345f333951c661d166b00e6f9362e553768f292') {
    throw 'Unexpected pin; do not configure/build/run'
}
~~~

Если vendor/llama.cpp уже существует, не удалять/не перезаписывать: проверить commit
и отдельно решить reuse. Несовпадающий pin блокирует исполнение.

Сборка существующими MSVC2022 BuildTools/CMake:

~~~powershell
$writerVs = Join-Path ([Environment]::GetFolderPath('ProgramFilesX86')) 'Microsoft Visual Studio\2022\BuildTools'
$writerCMake = Join-Path $writerVs 'Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe'
if (-not (Test-Path -LiteralPath $writerCMake)) { throw 'Existing CMake absent; no installer is allowed' }
$writerBuildArgs = @(
    '-S', '.\vendor\llama.cpp', '-B', '.\windows\build\writer-cpu',
    '-G', 'Visual Studio 17 2022', '-A', 'x64',
    '-DGGML_CUDA=OFF', '-DGGML_VULKAN=OFF', '-DGGML_RPC=OFF', '-DGGML_OPENMP=OFF',
    '-DBUILD_SHARED_LIBS=OFF', '-DLLAMA_BUILD_IS_DEV=OFF',
    '-DLLAMA_BUILD_COMMON=ON', '-DLLAMA_BUILD_SERVER=ON', '-DLLAMA_BUILD_TOOLS=ON',
    '-DLLAMA_BUILD_TESTS=OFF', '-DLLAMA_BUILD_EXAMPLES=OFF', '-DLLAMA_BUILD_APP=OFF',
    '-DLLAMA_BUILD_UI=OFF', '-DLLAMA_USE_PREBUILT_UI=OFF',
    '-DLLAMA_OPENSSL=OFF', '-DLLAMA_BUILD_BORINGSSL=OFF', '-DLLAMA_BUILD_LIBRESSL=OFF',
    '-DLLAMA_LLGUIDANCE=OFF', '-DLLAMA_SUBPROCESS=OFF'
)
& $writerCMake @writerBuildArgs
if ($LASTEXITCODE -ne 0) { throw 'Writer configure failed' }
& $writerCMake --build .\windows\build\writer-cpu --config Release --target llama-server --parallel 1
if ($LASTEXITCODE -ne 0) { throw 'Writer build failed' }
~~~

В [закреплённом CMakeLists](https://github.com/ggml-org/llama.cpp/blob/8345f333951c661d166b00e6f9362e553768f292/CMakeLists.txt)
server вложен в tools, поэтому tools=ON нужен; собирается только llama-server.
Отключены UI/npm/HF prebuilt UI, LLGuidance/Rust, SSL-library fetch и subprocess.
[UI provisioning script](https://github.com/ggml-org/llama.cpp/blob/8345f333951c661d166b00e6f9362e553768f292/scripts/ui-assets.cmake)
с UI/HF flags OFF разрешает API-only сборку без скрытого скачивания assets.
Actual MSVC build этого pin ещё не проверен.

Загрузка через существующий SHA256-загрузчик порта:

~~~powershell
. .\windows\Common.ps1
$writerModelArgs = @{
    Url = 'https://huggingface.co/Qwen/Qwen3-4B-GGUF/resolve/bc640142c66e1fdd12af0bd68f40445458f3869b/Qwen3-4B-Q4_K_M.gguf'
    Destination = (Join-Path $writerRoot 'models\writer\Qwen3-4B-Q4_K_M.gguf')
    Size = 2497280256
    Sha256 = '7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5'
}
Receive-RuachFile @writerModelArgs
Invoke-WebRequest -Uri 'https://huggingface.co/Qwen/Qwen3-4B-GGUF/resolve/bc640142c66e1fdd12af0bd68f40445458f3869b/LICENSE' -OutFile (Join-Path $writerRoot 'models\writer\LICENSE-Qwen3.txt')
~~~

Загрузчик не заменяет неожиданный существующий файл; валидный использует повторно.
.part переименовывается лишь после проверки размера и SHA256. Лицензии runtime/vendor
сохраняются из clone; LICENSE модели сохраняется отдельно.

Foreground запуск: Ctrl+C останавливает только Writer. Предлагаемый порт 41872
не пересекается с full engine 41868 и lab 41871; занятый порт не освобождать чужим kill.

~~~powershell
if (Get-NetTCPConnection -State Listen -LocalPort 41872 -ErrorAction SilentlyContinue) {
    throw 'Writer port occupied; existing process is untouched'
}
Remove-Item Env:LLAMA_ARG_TOOLS, Env:LLAMA_ARG_MCP_SERVERS_CONFIG, Env:LLAMA_ARG_MCP_SERVERS_JSON, Env:LLAMA_ARG_TOOLS_RUNTIME -ErrorAction SilentlyContinue
$writerServerArgs = @(
    '-m', '.\models\writer\Qwen3-4B-Q4_K_M.gguf',
    '--alias', 'Windows-Music-Lab-Writer', '--host', '127.0.0.1', '--port', '41872',
    '--device', 'none', '--n-gpu-layers', '0', '--no-kv-offload',
    '--ctx-size', '8192', '--parallel', '1', '--threads', '4', '--threads-batch', '4',
    '--batch-size', '256', '--ubatch-size', '128', '--cache-type-k', 'f16', '--cache-type-v', 'f16',
    '--jinja', '--reasoning', 'off', '--reasoning-budget', '0',
    '--offline', '--no-agent', '--no-ui', '--no-ui-mcp-proxy', '--no-cors-credentials',
    '--cors-origins', 'http://localhost:41868,http://127.0.0.1:41868',
    '--cors-methods', 'GET,POST,OPTIONS', '--cors-headers', 'Content-Type',
    '--temp', '0.7', '--top-p', '0.8', '--top-k', '20', '--min-p', '0',
    '--presence-penalty', '1.5', '--log-verbosity', '2'
)
& .\windows\build\writer-cpu\bin\Release\llama-server.exe @writerServerArgs
~~~

Флаги сверены с [README сервера в том же pin](https://github.com/ggml-org/llama.cpp/blob/8345f333951c661d166b00e6f9362e553768f292/tools/server/README.md).
Нет router/autoload, tools, API key или cloud provider. Очистка этих env-параметров
касается только нового PowerShell процесса, credentials не читаются/сохраняются.
Если порт studio меняется, обновить CORS origins. Не использовать wildcard/bind 0.0.0.0.

## Контракт и проверка

Прочитан build/tools/console/app.js: chatBase() добавляет /v1; chatStatus() вызывает
GET /v1/models; chatComplete() — POST /v1/chat/completions, model/messages/max_tokens,
stream:false, результат choices[0].message.content. Schema rejection вызывает plain
chat fallback. Ожидаемые 404 /api/v0/models и /api/ps не мешают выбору модели из /v1/models.
Браузер делает direct fetch — CORS необходим.

Engine → Chat server: **http://127.0.0.1:41872/v1**.
Writer provider: **Chat server under Engine**, select value **engine**.
Draft: четыре string fields title/style/lyrics/notes, style_tags опционален.
Windows local mode допускает loopback и блокирует внешний OpenRouter.

После согласования:
1. Проверить --version, /health и /v1/models с единственным alias.
2. Проверить OPTIONS/GET/POST Origin localhost:41868 и отказ CORS внешнему origin.
3. Короткий синтетический русский запрос, до 128 tokens, затем четырёхпольный JSON;
   пользовательские песни/документы не отправлять, музыкальный autoRun выключить.
4. Проверить Writer parse(), schema fallback и Creator Idea token budget.
5. Измерить CPU/RAM/commit/latency, отсутствие GPU allocations; остановить и проверить порт.

**Ещё не проверены:** MSVC-сборка, ответы/качество русского текста, скорость и peak RAM,
CORS браузера, JSON schema compatibility, Idea/Muse context budget и освобождение ресурсов.
Writer AI пока нельзя обозначать как установленный/проверенный.
## Дополнительный бюджет к ранее согласованному пакету 25 GB

Writer отдельный **сетевой cap: 2 800 000 000 bytes**. Внутри него:
- GGUF: 2 497 280 256 bytes.
- LICENSE: 11 544 bytes.
- Остаток на source/git/metadata/overhead/retries: **302 708 200 bytes**.
- Дополнительные wheels, CUDA, FFmpeg, npm/UI, SSL, Rust/LLGuidance: **0 bytes**.

Файлы модели+LICENSE+исходника занимают 2 673 105 870 bytes до .git и сборки.
175 814 070 source bytes — сумма uncompressed Git blobs, не размер git pack.
Git использует depth=1, single-branch и blob:none, потом checkout только этого pin:
полная история/другие ветки не нужны. Фильтр не гарантирует размер transfers.

**Перед исполнением root обязан внедрить общий byte-ledger и abort по cap**.
Указанные выше clone/Receive-RuachFile — контракты команд, пока не бюджетированный
installer. В частности, существующий Receive-RuachFile делает curl retries: его
нельзя считать доказательством сетевого лимита. Root должен считать каждый transfer
и retry/resume; при нехватке cap остановиться без перехода на другую модель/версию.
Не суммировать размеры конечных файлов как «сколько скачано».

Альтернативный source transport — один официальный ZIP:
https://codeload.github.com/ggml-org/llama.cpp/zip/8345f333951c661d166b00e6f9362e553768f292 .
Размер такого архива **не измерен**; release API v0.6.0 публикует только nightly-tag.txt,
а не source ZIP с независимым SHA256. Поэтому нельзя выдумывать expected archive SHA.
При выборе archive route root должен ограничить transfer остатком source budget,
проверить безопасные relative entries/содержимое против pinned Git tree и только
затем исполнять CMake. Локальный SHA256 после скачивания — fingerprint, не независимая
проверка publisher checksum.

Установленный curl 8.21.0 поддерживает max-filesize даже без Content-Length.
[Документация curl](https://curl.se/docs/manpage.html#--max-filesize) подтверждает
abort в процессе transfer, но **один per-file max-filesize не заменяет общий
ledger нескольких requests/retries**. Record size_download каждого запроса и
byte counter процесса остаётся задачей root.

Если предыдущие 25 GB = 25 000 000 000 bytes, Writer-only потолок становится
**27 800 000 000 bytes**, не 25 GB. Если Listener также является новым add-on сверх
25 GB, его bytes надо прибавить отдельно по проверенному approval package audio agent;
не считать его согласованным по наличию записи в manifest. Пока не подтверждена
Omni backend compatibility, Listener runtime/model не получают статус готовности.

Writer **workspace working budget ≤10 GiB** включает source/.git/build,
GGUF/.part/cache/logs. Это расход рабочего каталога, **не новый свободный резерв**.
На всём протяжении сохраняется ранее согласованный общий остаток **≥50 GiB free**.
Перед этапом учитывать ещё не скачанную часть общего пакета и уже занятый рабочий
каталог; если projected free становится <50 GiB, остановиться. Дисковый budget и
сетевой cap считаются отдельно: unpack/компиляция не скачивают bytes, но занимают диск.

## Совместимость среды и FFmpeg

lab/platform_runtime.py job_environment() уже направляет TEMP/TMP в lab/cache/tmp,
HF/Torch/XDG/CUDA caches в lab/cache/* и добавляет единственный
toolchain/ffmpeg/bin в child PATH. Writer использует свою поддиректорию
windows/cache/writer для TEMP/TMP/LLAMA_CACHE/HF_HOME: обе схемы остаются в проекте.
Это не меняет globals, исходную базовую установку, песни или модельные каталоги других
модулей. Загрузчик модели кладёт файл только в models/writer.

Для текстового Writer FFmpeg вообще не требуется. Уже согласованный FFmpeg можно
добавить в PATH нового процесса, если каталог существует, **без повторной загрузки**:

~~~powershell
$writerFfmpeg = Join-Path $writerRoot 'toolchain\ffmpeg\bin'
if (Test-Path -LiteralPath $writerFfmpeg) {
    $env:PATH = $writerFfmpeg + ';' + $env:PATH
}
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
$env:HF_HUB_DISABLE_TELEMETRY = '1'
$env:NO_PROXY = 'localhost,127.0.0.1,::1'
~~~

CPU Writer не требует torch/nvidia DLL directories; он не меняет среду GPU lab.
Если Listener нуждается в FFmpeg, тот должен получать тот же project PATH через
native runtime — второй FFmpeg/python environment ради Writer не нужен.
Все launch env изменения должны выполняться в новом process scope и исчезать вместе
с ним. Общая политика local-only и --offline сохраняется; загрузка утверждённых
артефактов — отдельный controlled step, не автоматический download из runtime.
## Сводный Writer + Listener add-on: уточнение выбранного профиля

Read-only проверка audio agent: pinned llama.cpp v0.6.0 документирует Qwen2.5-Omni
audio input и --audio/--mmproj; отсутствующий --mmproj-ntoken здесь не используется.
Это подтверждение API/исходника, **не успешный Windows CUDA pilot**.
Listener требует отдельной согласованной CUDA-сборки и короткого synthetic audio test.
Writer использует CPU-сборку; нельзя держать два тяжёлых build/GPU tests одновременно.

Listener два GGUF: **6 231 560 992 bytes**. Эти файлы уже указаны в исходном
27-file full-audio-models.json, но manifest сам по себе не доказывает, что они были
включены в выбранный пользователем профиль 25 GB. Перед запросом подтверждения root
сверяет selected profile и не скачивает валидные существующие веса повторно.
Лицензии/атрибуции GGUF/projector остаются в отдельном Listener package; Apache-2.0
текстового Writer нельзя распространить на все Listener конвертации.

| Согласованный исходный профиль | Новое дополнение | Новый общий cap, если 25 GB = 25 000 000 000 bytes |
| --- | ---: | ---: |
| Listener веса уже входят в 25 GB | Writer **2 800 000 000 bytes**; Listener только experimental runtime/build approval, без повторных весов | **27 800 000 000 bytes** |
| Listener веса не входят в 25 GB | Writer **2 800 000 000** + Listener pilot **6 300 000 000 bytes** | **34 100 000 000 bytes** |

Listener cap 6.3 GB оставляет **68 439 008 bytes** на notices/metadata/retries сверх
двух моделей, без второй копии source. Общие исходники llama.cpp учитываются **один
раз** внутри Writer cap. Двойная сборка CPU/CUDA увеличивает диск/время, не требует
двойного скачивания source.

Резерв рабочего пространства Writer ≤10 GiB; Listener provisional ≤10 GiB.
Совмещённый working budget ≤20 GiB сохраняет общий ≥50 GiB free после projected
остальных частей пакета. RAM/commit/GPU guards и actual byte ledger проверяются
перед этапами; Writer+Listener нельзя обозначать готовыми до реальных synthetic tests.

## Download accounting correction (12.10.2026)

The verified artifact/cache bodies total 2,545,424,505 B. Earlier interrupted
source reads retain a 1,048,576 B uncertainty reserve. Historical redirect
response bodies were not captured: urllib's default handler drains them and
curl's size_download reports the final response body. A loopback fixture proved
26 B total versus curl's 5 B; the current official HF HEAD declares 1,060 B for
the initial redirect.

An additional 100 MiB (104,857,600 B) allowance is retained within the already
approved Writer allocation. Total charged/reserved: 2,651,330,681 B of 2.8 GB.
This is a conservative allowance, not a retrospective proof of exact HTTP
traffic. Artifact hashes and payload sizes are verified; HTTP headers/TLS
overhead are excluded from these payload counters.

Future Writer transfers resolve HTTPS redirects with HEAD only (no response
body drain), at most five hops, preserving Range headers. The final GET has no
automatic redirects; unexpected redirects fail with their existing reservation
retained. No weights were downloaded again to fix this accounting limitation.


## Completed local pilot — 2026-10-12

The approved source/model/build stages and real local pilot completed. Readiness is
recorded in `windows/state/writer/ready.json` schema 1 with `verified: true`.
The source proof verifies all 3687 pinned Git blobs; the explicitly generated
`vendor/llama.cpp/build` subtree belongs to the separate completed Listener build.
CPU Writer binary version and SHA match the source pin; no vendor files were edited.

Actual local Writer response: 100 prompt tokens, 115 completion tokens, finish reason
`stop`, 10.547 seconds total, reported generation 12.2939 tokens/second. The exact
frontend `brief` JSON-schema shape produced title/style/lyrics/notes and four Russian
lines. This establishes structured Russian output; the sample contains awkward
creative wording and does not establish literary quality, rhyme, long Muse/Idea
prompts, streaming, tool calls or parallel slots.

Peak Writer working set during the synthetic HTTP request was 5,558,034,432 B;
private bytes 3,142,823,936 B. Startup passed native machine-wide memory checks
with 10,281,820,160 B commit headroom and 17,835,704,320 B physical RAM available.
The CPU build has CUDA disabled and the command explicitly selects device none.

Real isolated Chrome requests and actual Studio engine-provider readiness both
passed for http://localhost:41868 and http://127.0.0.1:41868. Initial real preflight
revealed that this pin emits a comma-separated origins option literally. The
supported `--cors-origins localhost` mode reflects only exact localhost/127.0.0.1/::1
hosts on ANY local port, with credentials disabled; external and two lookalike
origins were confirmed not granted. The server itself binds IPv4 loopback only.
Failure observations are retained in `first-cors-failure.json` from captured tool
output; the original raw log had already been overwritten on the first rerun.
Future test runs preserve previous owned synthetic HTTP logs before redirection.

Owned stop passed. Writer server PID 52376 and supervisor PID 47672 exited and
port 41872 had zero listeners. Root's Studio processes were left untouched.
The common Studio automatic lifecycle is owned and verified separately by Root.

Evidence: `windows/state/writer/http-check.json`, `browser-check.json`, `ready.json`,
`first-cors-failure.json`, `windows/cache/writer/build-proof.json`, `model-proof.json`,
`network-ledger.json`, `vendor/llama.cpp/source-pin.json`, configure/build logs.
The traffic record remains recorded payloads plus explicitly unmeasured historical
redirect allowances; it is not retrospectively exact total HTTP traffic. No further
model download or network operation was needed for this completed pilot.
