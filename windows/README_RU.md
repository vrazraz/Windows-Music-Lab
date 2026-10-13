# Windows Music Lab: полная нативная Windows-ветка

Ветка **`full-windows-port`** сохраняет базовую сборку в `main` и добавляет полный интерфейс Creator/Writer/Refiner/Artist/Librarian/Trainer. Это порт Ruach Studio Виктора Журомского (Viktor Zhuromskyy), upstream `a69739725e81b74921c6e2a24da8e83659f45a3a`. **WSL не нужен; полный профиль использует Python 3.10.**

## Запуск подготовленного проекта

Дважды щёлкните **`Start-Full.cmd`** в папке проекта, оставьте консоль открытой и перейдите на **http://localhost:41868**. Lab:127.0.0.1:41871; установленный и проверенный CPU Writer автоматически подключается на127.0.0.1:41872/v1. Генерация сама не запускается. Занятые порты и чужие процессы не заменяются.

Без загрузки Writer: `Start-Full.cmd -WithoutWriter`. Остановка — Ctrl+C в консоли либо из другого PowerShell в этой папке:

```powershell
powershell.exe -NoProfile -File .\windows\Stop-Full.ps1
```

**Свежий clone ещё не готов к запуску.** В Git нет бинарников, venv, моделей или ready receipts. Full launcher отказывает при отсутствии обязательных файлов и не выполняет скрытую установку/загрузку optional-моделей. Прежний **`Start.cmd`** запускает минимальный интерфейс на41867 и автоматически получает только две недостающие базовые модели (4,34GB) при первом старте; это другой сценарий.

## Подготовка нового clone

Нужны Windows11 x64, NVIDIA Windows driver, Git/curl, Python3.10 x64 с `py.exe`, VS2022 Desktop C++/WindowsSDK/CMake/Ninja. Проверено на RTX3060 12GB, MSVC19.44 и CUDA12.8.1 sm86; другие карты не проверены. Node22+ и Chrome нужны для browser QA. Сборка — один процесс; требуется свободная RAM и системный commit. Для полного профиля оставляйте **50GiB диска после всех оставшихся записей**, плюс место под устанавливаемые данные.

Команды ниже — **явная установка/скачивание/сборка после проверки источников, лицензий и размеров**. Они не исполняются самим Full launcher:

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

Runtime installer проверяет publisher metadata/хеши, получает binary wheels, устанавливает `.venv`/`.venv-art` и FFmpeg и проверяет imports; модельный inference не запускает. Не создавайте ready JSON вручную. Корректные базовые модели из соседнего `source/models` launcher может использовать повторно, иначе нужны модели в текущем `models/`.

| Набор | Объём/источник | Порядок |
|---|---|---|
| YuE2 Q8_0 + VAE F32 |4 340 729 408 B; pinned Serveurperso conversion, original m-a-p; CC BY-NC4.0 | `Download-Models.ps1`; в минимальном Start.cmd — автоматически при отсутствии |
| CUDA12.8.1 |690 522 782 B архивов NVIDIA | `Prepare-Toolkit.ps1`; существующий совместимый toolkit используется повторно |
| Python runtime/FFmpeg | Windows wheels PyTorch/PyPI: прежний audited transfer≈9,82GB; FFmpeg archive114 768 076 B, дополнительно unpack/install space | `Install-ValidationRuntime.ps1 -Phase All`; текущие точные locks/metadata/caches проверяются installer |
| Whisper |3 090 835 702 B,5 pinned Systran files | Только для transcription: `Download-ValidationModels.ps1 -PlanOnly`, затем явный запуск без PlanOnly. SDXL и остальные audio entries не скачиваются |
| Writer |Qwen3-4B Q4_K_M:2 497 280 256 B, Apache-2.0; pinned llama.cpp MIT | [WRITER.md](WRITER.md): отдельные install/build и реальный короткий Test-Writer для ready marker; этот тест генерирует текст |
| Listener |6 231 576 570 B,6 GGUF/notice files | [LISTENER_AI_APPROVAL.md](LISTENER_AI_APPROVAL.md): отдельный review/install/pilot; не обязателен для запуска Full |

Все данные моделей загружаются отдельно, сверяются по size/fullSHA и остаются в ignored local directories. `.part` возобновляется; ошибка проверки блокирует запуск. Секреты, платные сервисы и изменение системных PATH/CUDA/драйверов/защиты/сети не нужны. Большие загрузки и отдельные ML-проверки согласуются отдельно, если установку выполняет агент.

## Что реально проверено

- Шесть вкладок полного native UI и локальные HTTP API; ABC/MIDI roundtrip, staff preview у take, Writer notebook/autosave/version/import/export, собственные Librarian workspace/trash/restore/pin.
- Реальный короткий структурированный русский ответ CPU Writer; его automatic start/stop. Часть независимых UI-сценариев использовала явно обозначенный mock, поэтому это не доказательство AI quality.
- Синтетические DSP/Whisper, short Inspect/basic Remaster,10 структурных DAW archives. DAW приложения не открывались; XSD/import compatibility не подтверждена.
- Listener: native CUDA и короткий speech/no-music pilot; музыкальные теги и длинное аудио не проверены.
- Базовая нативная генерация text/style→audio проверялась ранее в минимальном порте. Advanced covers/remixes/LoRA/sliders и весь inherited Linux функционал не считаются проверенными.

Подробности: [FULL_WINDOWS_STATUS_RU.md](FULL_WINDOWS_STATUS_RU.md), [UI_INDEPENDENT_RU.md](UI_INDEPENDENT_RU.md), [REFINER_INDEPENDENT_RU.md](REFINER_INDEPENDENT_RU.md). Упомянутые там `cache/state` reports/screenshots принадлежат локальной reference installation и **не поставляются с clone**.

## Artist и optional-функции

**SDXL удалён из активной интеграции**, pending test отменён, ожидание memory-ready снято. На reference installation старые weights/venv/user data сохранены; публикация их не содержит. Gallery/upload/metadata/compare и Krea/Qwen orchestration остаются. Сейчас подходящего установленного painter нет, Draw отключён с причиной.

**Image-upscale пока не установлен:** отдельный следующий кандидат — Spandrel0.4.2/einops0.8.2 в ART и официальный RealESRGAN_x4plus;67 427 438 B payload. Нужны отдельное разрешение, wheel-body audit/install/imports и синтетический pilot; публикация ветки этого не разрешает.

Stems удерживаются из-за неизвестных original RoFormer checkpoint terms; runtime/weights/pilots отсутствуют. UniverSR selected source path прочитан, но wheel не построен и runtime не проверен; gate11000MiB не прошёл recorded snapshot. SheetSage native300s peak неизвестен. Стандартные Krea/Qwen выше gates12GB и требуют отсутствующих весов; streaming не подтверждён. Trainer BF16 gate20000MiB требует24GB класс, realtraining не выполнялся. Каталог адаптеров не обязывает скачивать чужие голоса. [Optional audit/proposal](OPTIONAL_RUNTIME_APPROVAL_RU.md) — исследование и pins, **не готовая установка и не разрешение**.

Исходники AGPL-3.0-or-later; third-party notices сохранены. Original attributed branding/assets CC BY-NC-ND4.0; модельные лицензии отдельны (YuE2 CC BY-NC4.0, Writer/Listener Apache-2.0 и прочие по manifests). Подробности/источники в [главном README](../README.md). Ветка публикует source/tests и уже публичные attributed upstream assets; модели, окружения, SDK, build, настройки, логи, QA outputs и пользовательские работы остаются локально.
