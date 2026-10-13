# Windows Music Lab: запуск на Windows

Постоянная папка: `E:\Projects\Ruach_Studio\full-windows-port`.
Локальная ветка: `full-windows-port`, исходная основа `e9874c951fd7a434b41c45928de6e62b610cacee`.
Базовая установка `E:\Projects\Ruach_Studio\source` сохранена отдельно и не изменена.
WSL не требуется. Это локальный срез проверок от12октября. Текущая публикация и инструкция нового clone описаны в ../README.md; cache/state receipts не включаются в Git. Исторические checkpoint SHA относятся к локальному архиву, исходные trees сохранены при замене identities перед публикацией.

На 12 октября 2026 года локальный запуск, автоматический Writer, шесть вкладок и штатная
остановка реально проверены. Изолированные зависимости и все согласованные модели установлены.
Реальные DSP, Whisper, Writer, короткий Listener и DAW-экспорт проверены; подробная матрица ниже.


Новое независимое продолжение: Writer mock draft+notebook, Librarian собственные workspace/trash/restore/pin, Creator ABC/MIDI, CPU Inspect/basic Remaster и10 DAW archives проверены реально. Исправлены short WAV Inspect и mono gain DAW. SDXL снят пользователем из scope, pending test отменён; новый [пакет optional runtime](OPTIONAL_RUNTIME_APPROVAL_RU.md) пока только предложение.

Подробный checkpoint каждой функции и отсутствующих компонентов: [CHECKPOINT_FULL_PORT_RU.md](CHECKPOINT_FULL_PORT_RU.md). Полный порт всех функций не объявляется готовым.

## Запуск и остановка

Откройте `Start-Full.cmd` в этой папке. Либо выполните:

```powershell
Set-Location 'E:\Projects\Ruach_Studio\full-windows-port'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\windows\Start-Full.ps1
```

Интерфейс: **http://localhost:41868**. Окно запуска оставьте открытым.
Lab слушает только `127.0.0.1:41871`, Writer — `http://127.0.0.1:41872/v1` на CPU.
Writer подключается автоматически. Первый запуск проверяет SHA256 базовых GGUF; это может
занять несколько секунд. Занятые порты приводят к отказу без остановки чужих приложений.

Базовые модели читаются из `E:\Projects\Ruach_Studio\source\models`; новые результаты,
настройки, LoRA, библиотека и изображения сохраняются в папке нового проекта.
Если память или проверенные файлы Writer недоступны, Studio продолжает работать,
а причина записывается в `windows/cache/full/writer-error.log`.

Для Studio без дополнительной модели Writer:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\windows\Start-Full.ps1 -WithoutWriter
```

Остановка: Ctrl+C в окне запуска, либо из другого PowerShell:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File 'E:\Projects\Ruach_Studio\full-windows-port\windows\Stop-Full.ps1'
```

Останавливаются только процессы этого запуска. Writer, запущенный отдельно,
останавливается через `windows/Stop-Writer.ps1`; подробности в `windows/WRITER.md`.
В финальной проверке пять собственных PID завершились, порты 41868/41871/41872 освободились.

## Реально проверенные функции

| Часть | Фактический результат | Оставшиеся ограничения |
|---|---|---|
| Creator | Полный UI/HTTP, ABC/MIDI, очередь GPU, отмена/unload и межпроцессный mutex | Новые песни, covers/remixes/LoRA/sliders в этой ветке не проверены реальной генерацией |
| Writer | UTF-8, документы/версии/autosave/import/trash; реальный русский JSON: 4 строки, 115 токенов за 10,55 с; оба локальных CORS-origin; автоматический запуск и остановка | Литературное качество, длинные Muse/Idea и streaming отдельно не оценивались |
| Refiner | Реальные spectrum/debuzz на собственном 5-секундном сигнале: показатель 50,13 →10,41; Whisper распознал все 11 слов синтетической фразы с корректными временами за 18,2 с | Stems/UniverSR требуют дополнительных пакетов и весов; remaster/karaoke полностью не проверены |
| Artist | Комната и Krea/Qwen/gallery/upload/masks/upscale сохранены; SDXL удалён из активной интеграции | Доступного установленного рисовальщика сейчас нет: стандартные Krea/Qwen превышают VRAM или требуют отсутствующих файлов. Image upscale ждёт Spandrel/model approval |
| Librarian | Unicode, коллекции/оценки/заметки/pins/favorites, архивы, junction и сохранение прежних экспортов | Cloud-публикация отключена |
| Trainer | Подготовка наборов, Windows-supervisor, stop/cancel/checkpoint и атомарное сохранение состояния | Новое LoRA-обучение требует минимум 20 000 MiB свободной VRAM; RTX 3060 12 GB не подходит этому профилю |
| Listener | Реальные 29/29 слоёв и аудиоэнкодер CUDA0; native exit 0/5,219 с; на собственной синтетической речи вернул «speech, no music» | Музыкальные теги и 120-секундные записи не проверены. Прежняя галлюцинация жанра/инструментов сохранена отдельно; общий prompt исправлен |
| DAW | Реальный FLAC →FFmpeg →REAPER ZIP/DAWproject: stereo 48 kHz/24-bit PCM, 5 секунд; MIDI/RPP/XML/ZIP и относительные пути | Приложения REAPER/Bitwig/Studio One не запускались |

Последние проверки: 39 runtime, 39 audio/held-reader, 21 Writer/library/DAW,
48 Artist backend/harness и 39 frontend, 13 локальных менеджеров и 8 UI-менеджеров,
42 C++ boundary/queue/mutex, 54 inline-скрипта и 5 реальных HTTP-сценариев.
20 проверок точного времени/PID Writer прошли отдельно в PowerShell 5.1 и 7.6.5,
включая русский формат даты и расхождение на один tick; проверен и реальный работающий PID.

Финальный отдельный Chrome-профиль: шесть вкладок, готовый Writer; этот старый отчёт предшествовал снятию SDXL,
0 JS-ошибок и 0 внешних запросов самого приложения. Скрипт установленного Kaspersky
отдельно отмечен в отчёте; настройки защиты не менялись. Исправлены два обнаруженных
дефекта на предыдущем этапе; последующее снятие SDXL описано в [SDXL_REMOVAL_RU.md](SDXL_REMOVAL_RU.md).

## Artist и память

Пользователь снял SDXL из scope. Pending image test отменён; ответ «готово» и прежний memory-ready blocker больше не требуются. SDXL не выбирается UI, не загружается и не запускается. Его20 уже скачанных файлов и `.venv-art` сохранены; очистка диска не выполнялась.

Artist остаётся: gallery, собственные картинки, metadata/compare, masks/references и протокол поддержанных Krea/Qwen. Генерация сейчас недоступна: подходящего установленного рисовальщика нет. Krea/Qwen не были установлены, стандартные gates превышают12GB; streamed Qwen не подтверждён. Image upscale остаётся отдельным optional Spandrel/RealESRGAN этапом. Общие Torch/diffusers/transformers и другие зависимости не удалены.

Listener краткого теста: наблюдаемый GPU used 8520 MiB, native peak commit 8 769 142 784 B.
Теперь GGUF Listener требует до загрузки минимум 10 ГиБ доступной RAM и 11 ГиБ машинного
commit. Это минимум короткого проверенного случая, а не доказанный предел для длинного аудио.
GPU-модельные проверки выполнялись последовательно через `Local\WindowsMusicLab-GPU0`.

## Зависимости, модели и объём

- `.venv` и `.venv-art`: Torch 2.11.0+cu128/CUDA 12.8; реальные импорты и обе проверки зависимостей прошли. Все 65 wheels проверены по SHA256; среды занимают 9,82 GB.
- Portable FFmpeg/ffprobe 9.0.2 проверены. Системные PATH/CUDA не изменялись; настройки действуют только для процессов проекта.
- Whisper:5 файлов,3 090 835 702 B проверены по SHA256. Исторические20 SDXL файлов/6 941 210 313 B остаются на диске как неактивные данные; новый model-download plan включает только Whisper.
- Writer: pinned llama.cpp v0.6.0; 3687 исходных Git blobs проверены, CPU-бинарник собран; Qwen3-4B Q4_K_M —2 497 280 256 B, лицензия Apache-2.0 проверена.
- Listener: две GGUF и три notices, суммарно 6 231 576 570 B, полные size/SHA проверки; CUDA CLI sm86 собран и реально запускался.
- Согласованные пределы: первоначальные загрузки до 25 GB; Writer+Listener до 9,1 GB и 20 GiB рабочих файлов. Резерв диска ≥50 GiB; на момент итогового документа свободно 56.17 GiB на E:.

Историческая телеметрия загрузок учитывала payload, но тела HTTP302 не измерялись точно.
Неопределённость и резерв явно сохранены в ledgers; оценочный резерв не выдаётся за
доказательство полного прошлого трафика. Будущий транспорт ограничивает/учитывает redirects.
Лимиты не увеличивались, модели повторно не скачивались.

Trainer/MERT, stems, UniverSR, SheetSage, Krea/Qwen-Image и прочие дополнительные варианты
не устанавливались автоматически. Наличие кандидата в `windows/full-audio-models.json`
не означает разрешение скачать его. Для этих вариантов нужны отдельные ресурсы и согласование.
Ключи, платные сервисы, облачная обработка и новые учётные данные не использовались.

## Лицензии и доказательства

Модели, среды, SDK, build, state, cache и результаты исключены из Git.
Windows Music Lab сохраняет исходную атрибуцию Ruach Studio и AGPL-3.0-or-later.
Модели имеют собственные лицензии; сохранённые неактивные SDXL файлы сохраняют CreativeML Open RAIL++-M,
Writer/Listener Apache-2.0, llama.cpp MIT; FFmpeg GPL-3. Notices и revisions сохранены.

- `windows/cache/full-supervisor-test/auto-writer-final.json`: запуск, точная принадлежность процессов, шесть вкладок, Writer и остановка (исторический SDXL selection снят из текущего scope).
- `windows/cache/full-ui-qa-complete/`: шесть PNG и отчёт Chrome.
- `windows/cache/validation-runtime/ready.json`, `completion-report.json`: зависимости и FFmpeg.
- `windows/cache/validation-models/verified.json`: все 25 файлов SDXL/Whisper.
- `windows/cache/real-audio/dsp-report.json`, `whisper-report.json`: реальные audio tests.
- `windows/cache/real-daw/report.json`: реальные DAW-экспорты.
- `windows/state/writer/ready.json`, `http-check.json`, `browser-check.json`: реальная модель Writer.
- `windows/cache/listener/pilot/windows-listener-pilot-20261012-205111-9b08f8/attempt-20261012-230751-c4e836/metrics.json`: короткий Listener, CUDA, счётчики и ограниченная проверка качества.
- `windows/cache/listener/final-verification.json`: Listener install/build и лёгкие проверки.
- `windows/cache/full-suite/`: независимые тесты и итоговый summary.
