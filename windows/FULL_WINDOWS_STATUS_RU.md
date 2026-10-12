# Windows Music Lab: запуск на Windows

Постоянная папка: `E:\Projects\Ruach_Studio\full-windows-port`.
Локальная ветка: `full-windows-port`, исходная основа `e9874c951fd7a434b41c45928de6e62b610cacee`.
Базовая установка `E:\Projects\Ruach_Studio\source` сохранена отдельно и не изменена.
WSL не требуется. Ветка не опубликована; push и PR не выполнялись.

На 12 октября 2026 года локальный запуск, автоматический Writer, шесть вкладок и штатная
остановка реально проверены. Изолированные зависимости и все согласованные модели установлены.
Реальные DSP, Whisper, Writer, короткий Listener и DAW-экспорт проверены; подробная матрица ниже.


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
| Artist | SDXL установлен; worker, refs/masks/geometry, LoRA-протокол и выбор готового SDXL в реальном интерфейсе проверены | Ни одного подтверждённого кадра нет; реальные 1024/LoRA/inpaint/outpaint/upscale не проверены |
| Librarian | Unicode, коллекции/оценки/заметки/pins/favorites, архивы, junction и сохранение прежних экспортов | Cloud-публикация отключена |
| Trainer | Подготовка наборов, Windows-supervisor, stop/cancel/checkpoint и атомарное сохранение состояния | Новое LoRA-обучение требует минимум 20 000 MiB свободной VRAM; RTX 3060 12 GB не подходит этому профилю |
| Listener | Реальные 29/29 слоёв и аудиоэнкодер CUDA0; native exit 0/5,219 с; на собственной синтетической речи вернул «speech, no music» | Музыкальные теги и 120-секундные записи не проверены. Прежняя галлюцинация жанра/инструментов сохранена отдельно; общий prompt исправлен |
| DAW | Реальный FLAC →FFmpeg →REAPER ZIP/DAWproject: stereo 48 kHz/24-bit PCM, 5 секунд; MIDI/RPP/XML/ZIP и относительные пути | Приложения REAPER/Bitwig/Studio One не запускались |

Последние проверки: 39 runtime, 39 audio/held-reader, 21 Writer/library/DAW,
48 Artist backend/harness и 39 frontend, 13 локальных менеджеров и 8 UI-менеджеров,
42 C++ boundary/queue/mutex, 54 inline-скрипта и 5 реальных HTTP-сценариев.
20 проверок точного времени/PID Writer прошли отдельно в PowerShell 5.1 и 7.6.5,
включая русский формат даты и расхождение на один tick; проверен и реальный работающий PID.

Финальный отдельный Chrome-профиль: шесть вкладок, готовый Writer и выбранный SDXL,
0 JS-ошибок и 0 внешних запросов самого приложения. Скрипт установленного Kaspersky
отдельно отмечен в отчёте; настройки защиты не менялись. Исправлены два обнаруженных
дефекта: сравнение времени процесса в PowerShell 7 и выбор отсутствующей Krea вместо SDXL.

## Изображение и память

Один согласованный кадр пока не создан. Защита остановила единственный standalone
worker **после импорта, до загрузки весов и denoising**. PNG нет; автоматического повтора не было.
После импорта: **16,590 ГиБ доступной RAM /9,224 ГиБ commit** при пороге **8/9,5 ГиБ**.
Не хватило **296 321 024 байт commit (0,276 ГиБ)**. Импорт реально занял около **1,994 ГиБ
private commit**, поэтому начальный порог уточнён с 11 до **11,5 ГиБ**; последующие пороги
9,5/2 ГиБ сохранены.

Последний замер после завершения всех собственных сервисов/worker:
**17.294 ГиБ доступной RAM /11.205 ГиБ commit**,
свободная VRAM: `0, 10590, 12288, 1521` (index/free/total/used MiB).
Для завершения теста закройте ненужное тяжёлое приложение и обеспечьте **≥11,5 ГиБ commit
при остановленных Studio и Writer**; сейчас недостаёт примерно
**0.295 ГиБ**. Системные настройки менять не требуется.
Новый GPU-пуск потребует явного продолжения после изучения сохранённого claim;
блокирующий claim и оригинальный отчёт не удалялись.

Проверка с запущенной Studio без Writer также была ниже порога: RAM/commit **16,770/10,068 ГиБ**.
Для минимального расхода собственной памяти тест подготовлен напрямую через тот же production worker.
Последний замер: `windows/cache/artist-one-frame/resources-20261012-203745.json`.
Логи: `artist/20261012-233238-7136/stdout.log` и `stderr.log`;
блок: `windows/cache/artist-one-frame/claim.json`, оригинал claim сохранён отдельно.
Существующий claim нельзя удалять или обходить ради автоматического повтора; сначала нужно
изучить его результат. До claim безопасно повторять только read-only preflight.

Свободная физическая RAM и commit — разные величины. Commit измеряется машинными
счётчиками `GetPerformanceInfo`. Windows COW mmap резервирует commit на весь файл.
Для единственного SDXL512 теста: перед import RAM/commit 9/11,5 ГиБ, после import 8/9,5,
перед inference и на шагах 1/2. Оценка и источники: `windows/artist-memory-policy.json`.
Пороги не уменьшались; пользовательские приложения и файл подкачки автоматически не менялись.

Listener краткого теста: наблюдаемый GPU used 8520 MiB, native peak commit 8 769 142 784 B.
Теперь GGUF Listener требует до загрузки минимум 10 ГиБ доступной RAM и 11 ГиБ машинного
commit. Это минимум короткого проверенного случая, а не доказанный предел для длинного аудио.
GPU-модельные проверки выполнялись последовательно через `Local\WindowsMusicLab-GPU0`.

## Зависимости, модели и объём

- `.venv` и `.venv-art`: Torch 2.11.0+cu128/CUDA 12.8; реальные импорты и обе проверки зависимостей прошли. Все 65 wheels проверены по SHA256; среды занимают 9,82 GB.
- Portable FFmpeg/ffprobe 9.0.2 проверены. Системные PATH/CUDA не изменялись; настройки действуют только для процессов проекта.
- SDXL: 20 файлов, 6 941 210 313 B. Whisper: 5 файлов, 3 090 835 702 B. Все 25 файлов полностью SHA256 проверены; автоматическая загрузка из интерфейса отключена.
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
Модели имеют собственные лицензии: SDXL CreativeML Open RAIL++-M,
Writer/Listener Apache-2.0, llama.cpp MIT; FFmpeg GPL-3. Notices и revisions сохранены.

- `windows/cache/full-supervisor-test/auto-writer-final.json`: запуск, точная принадлежность процессов, шесть вкладок, Writer/SDXL и остановка.
- `windows/cache/full-ui-qa-complete/`: шесть PNG и отчёт Chrome.
- `windows/cache/validation-runtime/ready.json`, `completion-report.json`: зависимости и FFmpeg.
- `windows/cache/validation-models/verified.json`: все 25 файлов SDXL/Whisper.
- `windows/cache/real-audio/dsp-report.json`, `whisper-report.json`: реальные audio tests.
- `windows/cache/real-daw/report.json`: реальные DAW-экспорты.
- `windows/state/writer/ready.json`, `http-check.json`, `browser-check.json`: реальная модель Writer.
- `windows/cache/listener/pilot/windows-listener-pilot-20261012-205111-9b08f8/attempt-20261012-230751-c4e836/metrics.json`: короткий Listener, CUDA, счётчики и ограниченная проверка качества.
- `windows/cache/listener/final-verification.json`: Listener install/build и лёгкие проверки.
- `windows/cache/full-suite/`: независимые тесты и итоговый summary.
