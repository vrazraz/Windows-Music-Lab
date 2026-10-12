# Локальный Writer на Windows

Установлено и проверено в E:\Projects\Ruach_Studio\full-windows-port.
Официальные llama.cpp v0.6.0 и Qwen3-4B Q4_K_M работают на CPU: 4 потока,
одна очередь запросов, контекст 8192 токена. Модель занимает 2,50 ГБ;
ключи и платные сервисы не нужны. Лицензия модели Apache-2.0 сохранена рядом.

Запуск из PowerShell:

~~~powershell
Set-Location E:\Projects\Ruach_Studio\full-windows-port
powershell.exe -NoProfile -File .\windows\Start-Writer.ps1 -NoBrowser
~~~

Окно обслуживает Writer. API: http://127.0.0.1:41872/v1;
проверка состояния: http://127.0.0.1:41872/health.
В Studio выберите Writer/Engine и адрес http://127.0.0.1:41872 — интерфейс
добавляет /v1. Начните с max_tokens=256. Проверенная отметка готовности
windows/state/writer/ready.json позволяет общему запуску Studio подключить Writer.

Остановка из другого PowerShell окна:

~~~powershell
Set-Location E:\Projects\Ruach_Studio\full-windows-port
powershell.exe -NoProfile -File .\windows\Stop-Writer.ps1
~~~

Ctrl+C в окне Start-Writer также останавливает его сервер. Проверяются путь
процесса, PID и время создания; другие серверы не затрагиваются.

Повторная установка из проверенного кеша и проверка:

~~~powershell
powershell.exe -NoProfile -File .\windows\Install-Writer.ps1 -Stage All -PendingReservedBytes 0
powershell.exe -NoProfile -File .\windows\Test-Writer.ps1 -StopAfter
~~~

Test-Writer требует запущенные Writer и Studio на порту 41868. Он отправляет
синтетические тексты, проверяет JSON на русском, CORS и статус Writer в Chrome
с обоих адресов Studio, затем останавливает Writer. Журналы находятся в
windows/cache/writer/, результаты — в windows/state/writer/. Перед запуском
нужны минимум 10 GiB свободной RAM и 8 GiB системного commit; сохраняется
минимум 50 GiB свободного диска. PendingReservedBytes — ещё не записанные
данные других этапов; после завершённой установки значение 0.

12 октября 2026 года: реальный ответ — 115 токенов за 10,55 с (12,29 токена/с),
JSON с title/style/lyrics/notes и четырьмя русскими строками. Пиковый RSS Writer
5,56 ГБ, private bytes 3,14 ГБ. CORS и статус провайдера проверены в Chrome для
http://localhost:41868 и http://127.0.0.1:41868. Внешние и похожие на localhost
адреса не получили CORS. Штатная остановка проверена; сервер оставлен выключенным.

CORS использует штатный режим localhost: допускаются точные имена localhost,
127.0.0.1 и ::1 с любым локальным портом; credentials отключены. Сам сервер
слушает только 127.0.0.1:41872. Список двух адресов через запятую в этой версии
даёт некорректный заголовок, поэтому выбран проверенный режим localhost.

Проверены формат и русский язык короткого черновика. В тексте встречаются
неестественные обороты; литературное качество и рифма не подтверждены.
Длинные Muse/Idea prompts и потоковая генерация требуют отдельной проверки.
Перед отдельно согласованным тяжёлым GPU этапом других моделей остановите Writer, чтобы освободить RAM.

Артефакты: models/writer/ — GGUF и лицензия; vendor/llama.cpp/source-pin.json —
происхождение исходников; windows/build/writer-cpu/ — CPU сборка.
