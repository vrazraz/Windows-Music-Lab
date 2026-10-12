# SDXL снят из Windows Music Lab

По прямому указанию пользователя SDXL удалён из активной интеграции в `E:\Projects\Ruach_Studio\full-windows-port`. Pending image test отменён; «готово» и прежний memory-ready blocker больше не требуются.

Удалены SDXL painter/readiness/sampling/resolution/profile/LoRA family, worker `lab/artist_sdxl.py`, SDXL fallback в take artwork и model scan, обязательный StableDiffusionXL import, активная memory policy, выбор в обеих UI selectors, SDXL auto-download/selection в Windows и старом artwork fetch fallback. One-frame harness оставлен только как безопасное уведомление об отмене; run отказывает до любых model/runtime imports. Старые SDXL API requests получают400 до queue/worker/files.

Artist и остальные модули сохранены: Krea/Qwen backends, references/masks/outpaint, gallery/upload/metadata/compare, image upscale и поддержка загрузки остальных LoRA families. Каталог адаптеров не требует скачивать чужие голоса. Сейчас подходящего установленного рисовальщика нет; UI показывает «Рисовальщик недоступен» и видимую причину, скрывает пустой fine-tune, отключает Draw/Again для снятой модели. Стандартные Krea/Qwen требуют отсутствующие веса и больше VRAM; streamed Qwen не подтверждён. Spandrel/image-upscale остаётся отдельным optional этапом.

Физически сохранены20 уже скачанных SDXL файлов суммарно6 941 210 313 B, selector JSON, historical claims/logs/run, обе `.venv`/`.venv-art` и общие Torch/diffusers/transformers/vision dependencies. Очистки диска не было; baseline `source` и пользовательские outputs не менялись. Новый Windows model-download plan содержит только5 Whisper files/3 090 835 702 B; автоматической загрузки из UI нет. Shared Artist env больше не обязательна для core Studio launch, но сохранённая среда проверяется как общая, безSDXL profile.

Реально проверены22 backend synthetic tests,70 frontend assertions,39 runtime,13 manager+8 UI checks,54 inline scripts и5 actual stdlib HTTP checks. Полный native UI запущен с `-WithoutWriter` для лёгкой проверки:6 tabs,0 JS exceptions,0 application external requests,0 generation requests; planted legacy SDXL preferences не вернули выбор. Два отказа соединения относятся к намеренно не запущенному Writer; прежний реальный Writer checkpoint сохранён. Финальный скриншот Artist осмотрен. Все собственные Studio/Chrome остановлены;3 порта свободны.

Единый proof: [complete-summary.json](cache/sdxl-removal/sdxl-removed-b768dbf175/complete-summary.json). Реальные UI/API/shutdown paths перечислены внутри; исторические receipts не перезаписаны. Это проверка удаленияSDXL, а не новый Krea/Qwen/AI run.

Запуск остаётся прежним: `Start-Full.cmd` или `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\windows\Start-Full.ps1`; интерфейс `http://localhost:41868`. Остановка: Ctrl+C либо `powershell.exe -NoProfile -File .\windows\Stop-Full.ps1`.
