# Проверяемый checkpoint Windows port — 12 октября 2026

**Полный порт всех обещанных функций не готов.** Подтверждены локальный запуск и отдельные
случаи обработки или inference. Многие сценарии только адаптированы в коде; часть пакетов
и моделей отсутствует. Оценка относится к существующим upstream функциям и согласованному перечню.
Файл модели, успешный import или ответ health не доказывают работу всех функций модуля.

## Ветка и сохранение

- Рабочая папка: `E:\Projects\Ruach_Studio\full-windows-port`; ветка `full-windows-port`.
- Исходная база: `e9874c951fd7a434b41c45928de6e62b610cacee` — HEAD до checkpoint commit.
- Базовый проект `E:\Projects\Ruach_Studio\source` сохранён без изменений. SHA256 его бинарника: `7A1E8107149E3D129221BBA551D3BD881A3D7A0522DC27011D0942FD272B5976`.
- Код и инструкции сохраняются локальным checkpoint commit. После успеха точный SHA, дерево и список файлов записываются в `windows/cache/checkpoint/git-state-final.json`. Также можно выполнить `git rev-parse HEAD` и `git status --short`. Push и PR не выполняются.
- Модели, среды, SDK, build, state, cache, fixtures и результаты остаются на диске и исключены из Git. Они не входят в commit.
- Первый checkpoint ff5c470 сохраняет123 text-файла. Новое независимое продолжение добавляет проверенные fixes/harness/docs; точный итоговый SHA и список в checkpoint JSON. Чужих staged-изменений не было.

## Запуск и остановка

Двойной клик `E:\Projects\Ruach_Studio\full-windows-port\Start-Full.cmd`, либо:

```powershell
Set-Location 'E:\Projects\Ruach_Studio\full-windows-port'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\windows\Start-Full.ps1
```

Интерфейс: `http://localhost:41868`. Lab: `http://127.0.0.1:41871`.
CPU Writer: `http://127.0.0.1:41872/v1`. Окно запуска оставьте открытым.
Запуск проверяет SHA256 базовых GGUF; Writer подключается автоматически, если готов
и хватает памяти. Для запуска без Writer:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\windows\Start-Full.ps1 -WithoutWriter
```

Остановка из другого окна:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File 'E:\Projects\Ruach_Studio\full-windows-port\windows\Stop-Full.ps1'
```

Ctrl+C предусмотрен кодом; фактически проверена команда Stop-Full. Она остановила
пять собственных процессов и освободила все три порта. Writer, запущенный отдельно:

```powershell
powershell.exe -NoProfile -File 'E:\Projects\Ruach_Studio\full-windows-port\windows\Start-Writer.ps1' -NoBrowser
powershell.exe -NoProfile -File 'E:\Projects\Ruach_Studio\full-windows-port\windows\Stop-Writer.ps1'
```

Image test приостановлен до ответа пользователя «готово». Фонового цикла запусков или
замеров нет. Claim сохранён и блокирует автоматический повтор. Перед продолжением нужно
проверить зафиксированную остановку до загрузки модели и сохранить историю попытки.


Оценка не добавляет новые обязательные функции: piano-roll, streaming chat, свободные tags и отдельная история редакций take отсутствуют в проверенном upstream workflow и не входят в согласованный перечень. Их отсутствие не считается дефектом переноса.

## Статусы

- `real`: целевая обработка, inference либо настоящий native HTTP/browser/lifecycle выполнен. Аудиовходы созданы нами синтетически, но исполнялся настоящий код, а не mock. Вывод о качестве ограничен этим входом.
- `synthetic`: unit/mock и искусственные файловые/протокольные/очередные случаи. Некоторые выполняют реальные операции с файлами, но не целевую ML-функцию и не весь сценарий интерфейса.
- `notrun`: полный сценарий не запускался; код может присутствовать.
- `hardwareblocked`: действующий профиль кода исключает RTX 3060 12 GB. `resourceblocked(now)` означает текущий недостаток памяти.
- `missing`: отсутствует пакет, модель или отдельная реализация; это не просто непроверенная готовая функция.

## Общий запуск и среда

| Функция | Реализация | Статус проверки | Доказательство / ограничение |
|---|---|---|---|
| Native Windows launcher / engine / Lab / Writer | Реализовано | real | Реальный старт, точная принадлежность PID, health, автоматический Writer, остановка 5 PID и освобождение 3 портов; R1 |
| Шесть вкладок / локальный режим | Реализовано | real | Chrome: 6 вкладок, Writer ready, SDXL выбран, 0 JS-ошибок/0 внешних запросов приложения; R2. Это не исполнение всех кнопок/ML-функций |
| GPU FIFO / handoff / unload / отмена / исключения | Реализовано | synthetic | 42 native C++ checks с искусственной работой и abandon-mutex; не music inference. R3 |
| Python subprocess / Unicode / watchdog / loopback guards | Реализовано | synthetic | 39 runtime checks, собственные stdlib child processes; не доказательство работоспособности optional ML |
| ML dependencies / CUDA / FFmpeg | Частичный согласованный набор установлен | real | Две изолированные среды, 65 SHA-verified wheels, pip checks/imports и CUDA metadata; FFmpeg9.0.2 actual version. R4. Полный requirements-core/art candidates НЕ установлен |
| Models manager / updater | Локальная проверка присутствия; manual update | synthetic; notrun(fetch) | 13 backend+8 UI checks; fetch/upload/автообновление upstream отключены. Presence/size не заменяют SHA-verification |

## Creator

| Функция | Реализация | Статус проверки | Доказательство / ограничение |
|---|---|---|---|
| Новая песня text/style/lyrics →YuE2 | Native core/backend сохранены | notrun | В full-windows-port настоящая генерация песни не выполнялась. Имеются base Q8_0+VAE из source; GUI/health и очередь не доказывают renderer |
| ABC score input / validation / chords | Ограниченный 2-voice dialect | synthetic | ABC parser/chord preservation/score events проверены в 21 library tests. Не arbitrary ABC standard; R5 |
| ABC editor / staff SVG / transpose / voice shift / печать / markers | Исходный UI сохранён | real(UI subset); notrun(print/markers editing) | Native selected take→локальный ABCJS staffSVG; C→D обоих voices, Vocal octave shift при unchanged Ins/chords; R14. В существующей форме statistical report, staff у selected take |
| MIDI import →ABC | Python и frontend parsers присутствуют | real(browser own SMF); synthetic(edge cases) | Реальный DOM file upload: SMF2 voices→native ABC; report и note bytes проверены. R14. Format0/1/PPQ/overlap/bad inputs: R5; SMPTE не поддерживается |
| MIDI browser export | Реализован SMF из2 voices | real(browser artifacts) | Actual take MIDI243 B и imported form MIDI158 B, PPQ480, voices/note pitch/timing/channels/velocity parse checks; R14 |
| Cover/remix из существующего score/ABC/MIDI | Исходный workflow сохранён | real(UI score); notrun(new audio) | Native coverFromTake, exact chord-strip с сохранением header/voices, transpose и MIDI form export; R14. /synth и /transcribe не вызывались; нового cover-аудио нет |
| Cover/transcribe из аудиозаписи | Условный SheetSage route; сейчас unavailable | notrun; missing(model) | SheetSage2-Q8_0.gguf отсутствует; UI без transcriber disabled. Кандидат 957571488 B, CC-BY-NC4, отдельное согласование. Не Whisper/Listener |
| Creator LoRA применение / blend strength | Loader/catalog/request code присутствует | notrun; missing(adapters) | В root/loras лишь metadata/.gitkeep, ни одного.safetensors; новая LoRA не обучена. Нужны конкретный adapter, license/pin и согласование inference |
| Voice/genre sliders | Catalog/GGUF loader присутствует | notrun; missing(weights) | root/sliders содержит catalog, но GGUF нет. Metadata не означает установленную функцию |
| Decoder/VAE alternatives / durations / batch / seed variants | Исходные параметры сохранены | notrun | Проверен запуск со standard VAE; legacy/blend не установлены. Runtime max-batch1; качество/варианты/длинные песни не проверены |

## Writer

| Функция | Реализация | Статус проверки | Доказательство / ограничение |
|---|---|---|---|
| Title/style/lyrics/Markdown notes/params/take links | Реализовано | real(UI subset); synthetic(params/links) | Chrome: editing, markdown preview, persisted own scoped doc и handoff в Creator; R13. Params/take links отдельно fixture-tested; R5 |
| Версии / named snapshot / restore | Реализовано | real(UI) | Native UI: named snapshot→readonly view→restore; предыдущий current сохранён. R13. Граница 100 версий отдельно не проверялась |
| Autosave | Frontend debounce1.5 s/backend merge | real(UI); synthetic(history policy) | Настоящее ожидание debounce и чтение сохранённого scoped doc; R13. 600 s history threshold не ожидали |
| JSON backup/import/conflicts/trash | Реализовано | real(UI export/repeat import); synthetic(conflicts/trash) | Реальное Chrome download JSON + DOM file upload; одинаковый backup не дублирует документы. R13. Conflicts/trash: R5; универсального DOCX/MD/TXT importer нет |
| Удаление документов / backup trash | Исходный workflow сохранён | synthetic | Перенос и включение trash в backup проверены. Отдельная новая UI-функция restore удалённого документа не входит в checkpoint |
| CPU Writer short JSON / CORS / lifecycle | Установлен llama.cpp+Qwen3-4 B | real | Русский JSON4 строки/115 tokens/10.55 s, два Studio origins, actual Chrome и owned stop; R6. Литературное качество ограничено |
| Muse/Idea/preferences/draft apply/retries | UI/prompts сохранены | real(mock draft UI); notrun(full AI/Muse/Idea/retries) | Локальный явно обозначенный mock ответ→draft parse→apply→undo в Chrome; R13. Это не проверка creative AI quality и не новая weighted inference |

## Refiner

| Функция | Реализация | Статус проверки | Доказательство / ограничение |
|---|---|---|---|
| Spectrum / Welch | Нативный worker | real | Собственный 5 s stereo 48 k signal: HSP1, 118 frames/1025 bins, finitevalues/size; R7 |
| Debuzz / framebuzz cleanup | Нативный worker | real | Synthetic5 s: frame fold depth50.13→10.41, длительность/каналы сохранены. Это НЕ SNR и не оценка музыкального качества; R7 |
| Inspect: tones/clicks/clipping / dropouts/DC/stereo/LUFS | Нативный worker, short-clip fix | real(CPU) | 8 s known artifacts +100 ms short WAV, finite JSON; найдены и исправлены STFT IndexError и sub-LSB false clicks. R15. Качество реальной музыки не оценено |
| Debunker full pipeline | Частично: basic FFmpeg flow +optional branches | notrun; missing(optional) | CalfLV2 отсутствует/не проверен. Generic --split использует обычный Separator, не локальный resolver stems_job |
| Remaster: levels/merge/trim/cleanup/fade/deess/432 Hz/loudnorm/export | Worker реализован | real(basic); notrun(optional branches) | Настоящий worker: 6→4.000 s, stereo48 kHz PCM24 WAV/FLAC,−18.03 LUFS/−14.84 dBTP, fades/DC/metadata checks; R15. Deess/432 Hz/stem mix/MP3/limiter at ceiling не проверены |
| Stems vocals: BS-Roformer | Worker/local resolver/guards реализованы; runtime missing | synthetic; notrun; missing(deps+model) | audio-separator не установлен; Roformer639331213 B+YAML2273 B отсутствуют. Нужны Windows wheel closure/model/license approval; R10 |
| Stems four: Roformer→Demucs | Workflow реализован; runtime missing | synthetic; notrun; missing(deps+model) | Всё для vocals +4×84141271 B Demucs .th/YAML149 B отсутствуют. ZIP export existingstems не separation inference |
| Audio upscale: UniverSR/subtle/normal/high/extreme/chunks/crossover | Worker реализован; vendor/model missing | synthetic(guard); notrun; resourceblocked(now) | universr source/deps не установлены; model229072395 B/config533 B отсутствуют.11000 MiB gate выше нынешнего effective10078 MiB room. Не вечный hardwareblock: инициализация/VRAM ещё не валидированы |
| Whisper transcript +word times | Локальный CT2 model установлен | real | CUDA SAPI English5.05 s: 11/11 words/wordRecall1.0+correct timestamps, overall18.2 s; R8. CPUint8/music/другиеязыки не проверены |
| Lyrics check / gloss / textend / trimming | Код реализован | notrun | Whisper transcript не доказывает lyrics matching/повторы/обрезку. Existinglocal model допускает новый ML test только после GO |
| Karaoke JSON/LRC/SRT / guessed lines / playback | Alignment/export code присутствует | notrun | Проверены лишь входные Whisperwordtimes; karaokealignment/LRC/SRT/playback не проверены |
| Post chain debuzz→upscale→stems→remaster→inspect→gloss | Оркестрация присутствует; stages partial | notrun; missing(stages) | Полная chain недоступна без separation/UniverSR; ни одного end-to-end chain test |

## Artist

| Функция | Реализация | Статус проверки | Доказательство / ограничение |
|---|---|---|---|
| SDXL text-to-image512 sequential validation | Worker/profile реализован; модель установлена | synthetic; resourceblocked | Единственный real attempt20261012-233238-7136 остановлен after_import, до painter/model load.0 weights/0 steps/0 PNG; R11 |
| SDXL512 production component mode /1024 component mode | Код реализован | synthetic; notrun | Pipeline calls/геометрия mocked; реальный ML не запускался.11.5 GiB оценка относится только к sequential512 test, не validatedproduction budget |
| References input/strength /img2 img | API/files+Img2 ImgPipeline | synthetic; notrun(ML) | Syntheticreference/maskbytes/pathguards+mock image/strength; реальные пиксели негенерировались |
| Mask /inpaint /grow /feather /composite | InpaintPipeline и pixel operations | synthetic; notrun(ML) | Mock mask/composite calls; actual inpaint quality отсутствует |
| Outpaint /fit /place /canvas | Geometry/pad/mask/crop code | synthetic; notrun(ML) | Параметрыгеометрии проверены; настоящеедорисовывание/visualquality нет |
| Differential diffusion | Исходные ограничения семейства сохранены | synthetic(rejection);notrun(Krea/Qwen) | SDXL не поддерживает этот режим по явному ограничению; это не новая обязательная SDXL-функция. Исходные Krea/Qwen пути требуют отсутствующих моделей |
| Variants1–4 / seeds /square-wide-portrait | Реализовано | synthetic; notrun(ML) | 512 buckets512²/672×384/384×672; 1024 buckets1024²/1344×768/768×1344. Validation разрешает только count1 square |
| Live previews /12 step callbacks | Код/protocol реализован | synthetic; notrun(latents) | Настоящие latents→JPEG не проверены. Attempt preview=false, до steps не дошёл |
| Samplers/defaults/simple/Karras | SDXL Euler/EulerSDE/DPM++/Heun | synthetic; notrun(quality) | Метаданные/API frontend gates проверены; Karras только DPM++; реальные samplers не сравнивались |
| SDXL LoRA library/load/weights/strength | Реализовано | synthetic; notrun; missing(adapters) | Metadata/pathguards и mock load_lora_weights / set_adapters; artwork/loras adapters отсутствуют. Validation LoRA запрещает |
| Civitai search/download | Исходный код; local-only disables | synthetic(rejection); disabled | Никаких внешних поисков/скачиваний/secretkeys; это недоступная online функция |
| Model selection /alternateSDXL /single-file | FolderJSONselector реализован; alternatecode | real(UI); synthetic; notrun(alternates) | ActualChrome выбирает installedSDXL. Alternatecheckpoint не проверен; single-file требует отсутствующие localCyberRealistic configs |
| Krea /Qwen2512 /Qwen2.1 painters | Исходные loaders; runtime notinstalled | notrun; hardwareblocked(standard profiles) | KreaQ4 gate12500>12288 MiB, QwenQ4 gate15500; Qwen2.1 gate21000. FP8 streaming6000 fallback естьвкоде, но RAM/Windows inference не валидированы; доступным не объявляется |
| Image upscale×2/×4/2 K/4 K | Spandrel/tiledworker | synthetic(path); notrun; missing(deps+model) | Нет spandrel и upscaler.pth/.safetensors; конкретная approvedmodel невыбрана |
| Gallery/files/star/compare | Исходный frontend/backend | synthetic(protocol); notrun(realgallery) | JSONrun metadata проверены; настоящих Artist картинок нет |
| Artist trash/restore/permanent removal | Исходный workflow | notrun(integration) | Отдельных Windows integration tests этихоперацийнет; пользовательскиефайлы не удалялись |
| Stop/cancel/watchdog/timeout | Ownedprocess cleanup/queuecancel | synthetic; notrun(real ML stop) | Реальные stdlibchildren/Unicode/errors/watchdog; standalone timeout mocked. Активный MLdenoising неостанавливался |

## Librarian

| Функция | Реализация | Статус проверки | Доказательство / ограничение |
|---|---|---|---|
| Takes/save/catalog/audio/request/meta | Engine/Python catalog реализованы | real(own fixture UI); notrun(new render) | Native loopback library/request на двух собственных WAV takes; selected score в Creator, организации в Librarian; R13/R14. Новый нейросетевой take не создавался |
| Workspaces/sections/ratings/notes/pins/favorites/locks/freeze | Реализовано | real(UI subset); synthetic(sections/locks/freeze) | Chrome: own workspace/assignment/favorite/like/note, pin→reload→unpin; R13. Sections/locks/freeze сохраняют только fixture coverage |
| Trash/list/restore/retention/permanentdelete | Реализовано | real(UI move/restore); synthetic(guards); notrun(retention/permanent UI delete) | Только собственный take: checkbox→trash→list→restore с metadata; R13. Retention уже0 и не менялась; permanent removal запрещён harness |
| ZIP/WAV export/derived files | Реализовано | synthetic | Реальный WAVZIP/names/integrity/pathguards; FLACcollectionZIPconversion в этомпути mocked; не смешивать с realDAW R9 |

## Trainer и Listener

| Функция | Реализация | Статус проверки | Доказательство / ограничение |
|---|---|---|---|
| Dataset wizard prepare/captions/manifest/FFmpegPCM24 | Кодреализован | synthetic(parts); notrun(fullwizard) | GTSinger UnicodePCMjoinfixture проверен; wizardprepare другойпуть, не проверен. GTSingerdownloads local-only disabled |
| Latent/semantic cache VAE+MERT+head | Local-only loader/atomicparts | notrun; missing(weights+runtime) | Нет bf16 checkpoint/MERT+customPython/head; Artisttransformers в другой venv не coreMERT runtime |
| Train /LoRA backprop | Own native Trainer код/supervisor | hardwareblocked; notrun(ML) | Gate20000 MiBfreeVRAM, RTX 3060 total12288. Int8 baseunpacksbf16 и gate неснимает. Ниодна LoRA не обучена |
| Supervisor status/launch/failure/stop/cancel | Windows замена systemd | synthetic | Настоящие tiny Python fixtures: cooperativestop/checkpointrequest/forcedstop/queuecancel. Это не trainingstep |
| Model/optimizer checkpoint /resume /publishCreator | Код save/parts/list/copy-link | synthetic(parts); notrun(neural) | JSONheld-reader/pathchecks прошли; realneuralcheckpoint/resume/publish не проверены; model+optimizer необщаятранзакция |
| OptionalAI-Toolkit | Опциональныйпуть | missing; notrun | Vendor/toolkit не установлен; own Trainer неиспользует PEFT |
| ListenernativeCUDAandshortspeech | Q4+Q8 projector/llamaCPP установлены | real | Actualexit0/5.219 s, 29/29 language layers+audioencoder/CLIPCUDA0; speech, no music на own10 sSAPI; R12 |
| Listener hallucination correction | Genericprompt исправлен | real(limitedquality) | Старый prompt реальновыдумывал synth-pop/guitar. Исправленныйответпрошёлтолько speech-vs-music criterion; старые logs/styles сохранены |
| Listener music/instruments/genre/120 s/multi-track | Кодприсутствует | notrun | Общееаудиопонимание/музыкальный tagging не подтверждены; 11 GiBcommit/10 RAM это short-test minimum |
| Listener wizard: status/styles/apply | Исходный workflow сохранён | notrun(wizard) | Standalone pilot не проверяет multi-track/default120s/apply. Отдельный новый stop endpoint не является обязательным пробелом переноса |

## DAW

| Функция | Реализация | Статус проверки | Доказательство / ограничение |
|---|---|---|---|
| REAPER ZIP/RPP/mix/relativeaudio | Реализовано | real(artifacts) | R9 и R16: настоящие PCM/FLAC/MP3 conversion, relative references, waveform identity и ZIP integrity; DAW app не запускалась |
| DAWproject ZIP/XML/audio | Реализовано | real(artifacts) | R16: project/metadata XML refs/notes/lyrics/tempo/audio, все10 exports. XSD/application import не проверены |
| Existingstems/MIDIvoices/lyrics/regions | Реализовано | real(own synthetic artifacts) | 5 cases/10 archives: own actual WAV/FLAC/MP3 stems, newest mode selection, mix muted,2 MIDI voices/channels/velocity, timed lyric items/regions. R16. Это не ML separation |
| PCM16/24/32 mono/stereo→48 kstereoPCM24 | Стандартнаябиблиотека | synthetic | Точные positive/negative samples/mono duplication/24 bitcopy; R5 |
| Compressed FLAC conversion | FFmpegfallback +full gain mono | real | Actual FLAC/MP3/float32mono44.1 kHz resampling; исправлена≈3 dB mono attenuation, RMS0.144341→0.144284. Corrupt stem failure сохраняет previous2 archives и удаляет tmp; R16 |
| Tempo/meter/beat-time map | ABC Q:/M: или style/default | real(artifact mapping); missing(audioBPM/variablemap) | Проверены ABC quarter tempo/meter, style97 fallback, stale timing/default120, note/lyric beat times; R16. Audio BPM detector/full variable tempo map exporter отсутствуют |
| DAWdiscovery/version | Windowsinstallpaths/PATH | synthetic; notrun(app) | Syntheticinstallationfixture; не подтверждает installedREAPER/Bitwig/Waveform |
| Открытие/import в REAPER/Bitwig/StudioOne/etc | Exportfiles есть | notrun | Ниодна DAW не запускалась. Комментарии upstream о REAPER7.81 не evidence этоймашины |

## Недостающие зависимости и согласование

Фактический core — только DSP/Whisper subset: 41 distribution с pip. Art — SDXL subset:
50 с pip. В core отсутствуют `audio-separator`, `demucs`, `onnxruntime-gpu`, `transformers`,
`torchvision`, `accelerate`, `peft` и `UniverSR`. Установленный обычный `onnxruntime==1.23.2`
не заменяет separator или GPU-пакет. В art есть Torch/Torchvision, Diffusers, Transformers,
Accelerate и PEFT, но нет Spandrel, GGUF и Kernels. Candidate requirements не равны installed lock.

| Профиль | Что отсутствует | Что нужно перед запуском |
|---|---|---|
| Stems | `audio-separator[gpu]==0.47.0` и полный Windows dependency closure; Roformer/YAML; четыре Demucs `.th` и YAML | Wheel/hash/license audit и отдельное approval на загрузку, установку и inference. Семь файлов около 0,976 GB; точные размеры, SHA и pins в `full-audio-models.json` |
| Audio upscale / UniverSR | Vendor MIT, зависимости, модель 229 072 395 B и config 533 B, веса CC BY 4.0 | Проверка pinned vendor-кода и closure, новое согласование. Текущий gate 11 000 MiB свободной VRAM не проходит |
| SheetSage | Q8-модель 957 571 488 B | Отдельное согласование загрузки и native inference; CC BY-NC 4.0. Сейчас audio cover/transcription отключены |
| Trainer | bf16 base 7 799 983 228 B; MERT 2 529 812 848 B с configs/custom Python; head 171 305 291 B; core Transformers runtime | Audit и новое approval, особенно MERT `trust_remote_code=True`. CC BY-NC 4.0. Помимо установки требуется ≥20 000 MiB свободной VRAM; RTX 3060 12 GB не проходит. Int8 base распаковывается в bf16 |
| Image upscale | Spandrel и конкретная `.pth`/`.safetensors` модель | Выбор pin/license/size, Windows closure и approval. Requested 4000 MiB не является измеренным peak |
| Creator/Artist LoRA и sliders | Конкретные согласованные adapters/GGUF | Model/license/pin audit и отдельный inference GO. Metadata catalog не является весами |
| Krea/Qwen | GGUF/parts/filter/configs и optional packages | Не входят в SDXL approval. Krea Q4 gate 12 500, Qwen Q4 15 500 MiB выше 12 288 MiB полной VRAM. FP8 streaming fallback не валидирован; доступным не объявляется |

При сохранённом GPU free 10 590 MiB и WDDM reserve 512 MiB effective room был 10 078 MiB.
Stems gate 8000 потенциально помещается, UniverSR gate 11 000 не проходит. Эти gates не
равны измеренным peaks; known-heavy veto и назначенный лимит могут дополнительно отказать.
Глобальные CUDA/PATH, сеть, защита и pagefile не менялись. Ключи, платные сервисы и новые
учётные данные не использовались. HTTP302 bodies старых скачиваний не измерялись точно;
ledgers сохраняют неопределённость и planning allowance, а не доказательство всего прошлого
трафика. В этом checkpoint новых загрузок и бюджетов нет.

## Работа, независимая от image test

После отдельного разрешения выполнены независимые проверки без новых пакетов/моделей: Writer mock UI, Librarian own fixture trash/restore/pin, Creator ABC/MIDI, CPU Inspect/basic Remaster и расширенный структурный DAW export; R13–R16. Нового нейросетевого inference не было.
Остаются отдельные сценарии:

1. Без новых пакетов: дополнительные optional DSP branches/полный Debunker и ещё не проверенные existing UI actions. Basic Inspect/Remaster, Notebook/Collection и ABC/MIDI уже имеют реальные scoped artifacts.
2. С уже установленными моделями: Muse/Idea/draft apply/длинный Writer; Whisper textend/gloss/karaoke; Listener музыка/120s/wizard; Creator песня/ABC cover. Это новые ML-прогоны: нужен отдельный GO и последовательный доступ к GPU с проверкой ресурсов. Сейчас они не запускались.
3. Без исполнения нового vendor-кода: source/license/pin/Windows wheel audit и точный план stems, UniverSR, SheetSage, upscaler или LoRA. Загрузку, установку и запуск optional-компонентов согласовать отдельно.
4. Открытие экспортов в выбранной DAW: нужен отдельный запуск приложения; если DAW отсутствует, отдельно согласовать установку. Сейчас никакая DAW не запускалась.

## Image checkpoint и пределы выводов

Единственная попытка `20261012-233238-7136`: до import commit 12 012 298 240 B,
после import 9 904 226 304 B (9,224 GiB), ниже guard 10 200 547 328 B (9,5 GiB).
Недостаток — 296 321 024 B. Private commit достиг 2 140 987 392 B, около 1,994 GiB.
Веса модели не загружались; denoising не начинался; PNG — 0. Status claim:
`blocked_before_model_load`. Оригинальный claim, stdout и stderr сохранены.

Будущий admission — 11,5 GiB с allowance импорта 2 GiB. После импорта остаётся guard
9,5 GiB, во время работы — 2 GiB. Это оценка специального sequential512 профиля;
успешного измерения production component1024 режима нет.

Последний сохранённый замер — **20:37:45 UTC**: RAM 18 569 760 768 B (17,294 GiB),
machine commit 12 031 754 240 B (11,205 GiB), GPU free 10 590 MiB. До 11,5 GiB
не хватало 316 276 736 B (0,295 GiB). Родитель уже попросил освободить память с ориентиром
1 GiB и ответить «готово». Новых замеров, повторов и автоматизаций не назначено.
Пользовательские приложения не закрывались.

Whisper подтверждён на 11 словах английской SAPI-фразы. Listener подтвердил только
speech-versus-music после общего исправления prompt; прежняя hallucination synth-pop/guitar
сохранена. Writer подтвердил короткий JSON, не качество полного творческого сценария.
Первый real DAW fixture R9 был mix-only. Новая серия R16 добавляет собственные stems, MIDI и timed lyrics в реальные10 exports с настоящим FFmpeg. Это не нейросетевое разделение и не import/playback в DAW-приложении.

## Новое независимое продолжение

На 2026-10-12 UTC исправлены два измеренных дефекта: short-clip Inspect и≈3 dB mono loss в FFmpeg fallback DAW. UI прошёл18 функциональных workflows без weighted AI:8 Writer/Librarian,1 pin lifecycle и9 Creator ABC/MIDI; mock health isolation проверена отдельно. Использованы собственные WAV/SMF/docs и уникальный scope `uiqa-aca129d0bafa`; user profiles/takes не удалялись. SDXL повторно не запускался. Один будущий dependency/model package: [OPTIONAL_RUNTIME_APPROVAL_RU.md](OPTIONAL_RUNTIME_APPROVAL_RU.md); до нового разрешения не установлен.

## Проверяемые свидетельства

| ID | Файл и область доказательства |
|---|---|
| R1 | `windows/cache/full-supervisor-test/auto-writer-final.json`: startup, UI, stop, 0 оставшихся PID и портов |
| R2 | `windows/cache/full-ui-qa-complete/full-ui-check.json` и шесть PNG: UI only, `inferenceJobs=0` |
| R3 | `windows/cache/full-suite/engine-latest.log`, `windows/native-engine/README.md`: 42 synthetic native checks, без inference |
| R4 | `windows/cache/validation-runtime/ready.json`, `completion-report.json`, validation locks: реально установленный subset |
| R5 | `lab/test_windows_library.py`, `windows/PORT_LIBRARY_DAW.md`: 21 файловый/MIDI/PCM/XML/RPP fixture test |
| R6 | `windows/state/writer/ready.json`, `http-check.json`, `browser-check.json`; `windows/tests/Test-WriterIdentity.ps1` |
| R7 | `windows/cache/real-audio/dsp-report.json`: настоящий Spectrum/Debuzz на synthetic 5s |
| R8 | `windows/cache/real-audio/whisper-report.json`: настоящий CUDA Whisper / English SAPI |
| R9 | `windows/cache/real-daw/report.json`: FLAC/FFmpeg/mix-only REAPER ZIP и DAWproject |
| R10 | `windows/full-audio-models.json`; candidate versus installed requirements; `lab/separation_local.py` |
| R11 | `windows/cache/artist-one-frame/claim.json`, original claim, `resources-20261012-203745.json`, `artist/20261012-233238-7136/`, `windows/artist-memory-policy.json` revision2 |
| R12 | `windows/cache/listener/pilot/windows-listener-pilot-20261012-205111-9b08f8/attempt-20261012-230751-c4e836/metrics.json`; old attempts 230028/230417; `windows/build/listener-cuda/runtime-proof.json` |
| R13 | `windows/cache/independent-ui/uiqa-aca129d0bafa/writer-collection-d99dc31c/report.json` и `windows/cache/independent-ui/uiqa-aca129d0bafa/collection-pin-final-199ec956/report.json`:8 notebook/mock draft/library UI workflows+pin; собственные docs/takes,0 JS exceptions |
| R14 | `windows/cache/independent-ui/uiqa-aca129d0bafa/creator-2026-10-12T21-39-58-736Z-c13bf180/creator-workflows-check.json`:9 real browser score/MIDI workflows;3 PNG/download bytes, no inference requests |
| R15 | `windows/cache/refiner-independent/20261013-002459-c13983/report.json`, `windows/REFINER_INDEPENDENT_RU.md`:9 actual worker/FFmpeg commands +4 regression tests |
| R16 | `windows/cache/daw-structural/20261012T213117Z-9060b9ed/report.json`:10 REAPER/DAWproject exports,23 regressions, actual codec/signal/failure preservation |
| R17 | `windows/cache/independent-ui/uiqa-aca129d0bafa/complete-summary.json` и `shutdown-proof.json`:scope/источники/границы,0 own PIDs/Chrome/ports после stop |
| R13 | `windows/cache/full-suite/current-summary.json`, `final-closure.json`; `windows/cache/listener/final-verification.json` |

Реализация: `lab/platform_runtime.py`, `windows/Start-Full.ps1`, `build/tools/yue-server.cpp`,
Creator/Writer UI `build/tools/console/app.js` и `heresy-*.js`. Notebook/MIDI/DAW:
`lab/writer.py`, `collection.py`, `midi_io.py`, `midi_score.py`, `rpp.py`, `dawproject.py`,
`daw_audio.py`, `dawbridge.py`. Refiner: `spectrum_job.py`, `debuzz.py`, `inspect_job.py`,
`debunker.py`, `remaster_job.py`, `stems_job.py`, `separation_local.py`, `upscale_job.py`,
`whisper_job.py`, `textend_job.py`, `timing.py`. Artist: `artist.py`, `artist_job.py`,
`artist_sdxl.py`, `artist_upscale.py`, `artist_loras.py`. Trainer/Listener: `training.py`,
`training_supervisor.py`, `trainer/cache.py`, `semantic.py`, `train.py`, `control.py`, `listener.py`.

Сохранённые проверки: runtime39; audio37+2 held-reader; Artist48+frontend39;
library21; managers13+8UI; C++42; bundled JS54; HTTP5; Writer identity20 отдельно PS5/PS7;
Listener12 installer+1 guard+4 evidence входят в56 total. В этом checkpoint тесты не повторялись.
Исходная атрибуция и AGPL сохранены; model-specific licenses/notices остаются отдельными.
