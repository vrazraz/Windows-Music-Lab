# Независимые UI и artifact проверки

Папка проекта: `E:\Projects\Ruach_Studio\full-windows-port`. Проверка2026-10-12UTC выполнена после отдельного разрешения, без установки пакетов и нового weighted inference. Studio была запущена с `-WithoutWriter`; порт41872 занимал stdlib mock, который помечал health/request как `mock_ai=true`.

Все18 функциональных browser workflows прошли:8 Writer/Librarian,1 pin lifecycle,9 Creator. Writer autosave/snapshot/view/restore/markdown/backup import/export/handoff и mock draft apply/undo работали через существующие UI handlers и native API. Own Librarian workspace/favorite/rating/note и trash→restore сохранили metadata; pin пережил reload и снят. Permanent trash removal и inference endpoints блокировались до отправки.

Creator использовал собственный native two-voice ABC take. Проверены actual local staffSVG, ABC/MIDI download bytes, coverFromTake, transpose/voice shift/chord strip, DOM SMF upload→ABC и MIDI roundtrip. Existing form содержит статистический report; staff доступен у selected take. Form staff preview/новые функции не добавлялись.

Source fixes: Inspect раньше падал на100ms WAV; теперь short STFT padding/явно unavailable framebuzz. Sub-LSB rounding в антифазе больше не считается click. DAW FFmpeg mono fallback раньше уменьшал уровень≈3dB; теперь mono copied into both channels с full gain. Direct CPU workers дали measured4.000s stereo48kPCM24 Remaster WAV/FLAC,−18.03LUFS/−14.84dBTP;10 actual DAW archives имеют свои stems/ABC MIDI/timed lyrics и waveform identity.

Ни Writer mock, ни синтетические stems не доказывают AI quality или нейросетевое разделение. DAW apps не открывались, XSD import не проверялся; deess/432Hz/stem remix/limiter stress тоже вне проверенной области. SDXL не повторялся. Новые optional weights/deps находятся только в [пакете согласования](OPTIONAL_RUNTIME_APPROVAL_RU.md).

Собственный scope `uiqa-aca129d0bafa`, два take и scoped notebook сохранены для воспроизводимости; пользовательские данные и Chrome profiles не удалялись. Собственные hidden headless Chrome profiles закрыты. Test Studio UUID `8cb90db053de400e8c000e825677db99`, supervisor/engine/Lab/mock stopped; порты41868/41871/41872 свободны.

Единый отчёт: [complete-summary.json](cache/independent-ui/uiqa-aca129d0bafa/complete-summary.json); там точные paths всех reports, sourceSHA и shutdown proof. Каждый промежуточный test/fixture failure сохранён; selector/i18n/repaint/click corrections касались только helpers, production UI не менялся.

## Повторение только после отдельного GO

`windows/qa-creator-workflows.mjs APP_URL FIXTURE_PREFIX` создаёт собственный Chrome profile; APP_URL должен быть loopback41868 с unique scope, FIXTURE_PREFIX—существующий собственный `uiqa-...score` native take. Перед повторением проверить, что Studio разрешена, файлы относятся кQA и heavy endpoints intercepted.

`windows/qa-writer-collection-workflows.mjs CONFIG.json [--pin-only]` требует собственную blank Chrome DevTools session и JSON{profile,output,appUrl,scope,take}; scope строгийuiqa-hex, take в этом scope,41872healthmock_ai=true. Output/downloads должны быть в отдельной QA cache-папке. Он закрывает только соединённый собственный Chrome через Browser.close. Для удобства exact original owned-launch.json и fixtures.json остаются в cache; не переподключать пользовательскую вкладку/profile.

Этиhelpers не installers и сами не запускают Studio/mock/GPU; согласование будущих запусков остаётся у root. CPU Refiner reproduce commands в [REFINER_INDEPENDENT_RU.md](REFINER_INDEPENDENT_RU.md); DAW validator—`windows/validate_daw_real.py --run` с существующей `.venv` и FFmpeg.
