# Аудиомодули Windows: установленное и проверенное

Рабочая папка: `E:\Projects\Ruach_Studio\full-windows-port`. Изолированный Windows port не меняет исходный `source`, прежние модели/музыку, защиту, драйверы или настройки сети. Root установил согласованный Python3.10 CUDA runtime и portable FFmpeg9.0.2, проверил imports/pip checks. Это текущий итог; начальные requirements/манифест кандидатов не заменяют окончательный runtime lock.

## Проверено

| Возможность | Реальная проверка | Ограничение |
| --- | --- | --- |
| Spectrum, Debuzz | Root: synthetic5s processing, реальный Spectrum payload | Качество пользовательских записей не оценивалось |
| Remaster/Inspect/DAW export | Root: FFmpeg, stereo48k24bit5s WAV/FLAC→REAPER ZIP/DAW project | Без внешних сервисов |
| Whisper | Root: локальный полностью SHA verified large-v3 CT2, реальный CUDA decode синтетической речи/word timings | CPU int8 не тестировался |
| Listener Q4/Q8 | Полные SHA весов/лицензий, native llama.cppv0.6.0 sm86 CUDA build; exit0/5.219s,29/29 layers+audio encoder наCUDA0; `speech, no music` | Прошёл узкий speech-vs-music SAPI10s тест; жанры/инструменты и120s UI job не проверены; прежняя галлюцинация сохранена |
| Stems vocals/four | Native paths, local resolver/network guard и mocks | Пакеты установлены; Roformer/Demucs weights не установлены, real separation не запускался |
| UniverSR | Local snapshot/Windows paths/native job code | Отдельные MIT code и CC BY4.0 weights не установлены/не запускались |
| Trainer | Собственный native supervisor, cooperative checkpoint stop, безопасная публикация JSON/частей проверены | **RTX3060 12GB не поддерживается: free VRAM gate20 000MiB.** LoRA training не запускалось |

Реально прошли37native stdlib tests +2 Windows held-reader checks,12installer,1 owned-memory-guard cleanup,4 perf/semantic evidence tests. Supervisor запускает только собственный child; Stop пишет stop.requested, trainer сохраняет checkpoint на безопасной границе, после60s возможен forced owned-tree stop. Полная гарантия сохранения последнего step и transaction model+optimizer не заявляется. Atomic replace повторяет толькоWinError5/32/33 до1s, сохраняя прежний полный JSON и новый part при исчерпании.

Точная команда двух held-reader checks: `py -3.10 -m unittest lab.test_atomic_audio -v`. Общая native suite: `.\.venv\Scripts\python.exe -m unittest lab.test_native_audio lab.test_atomic_audio -v`.

## Источники и ресурсы

Python3.10 wheels: PyPI/files.pythonhosted.org и официальный download.pytorch.org/whl/cu128. **Установлена CUDA-сборка torch/torchaudio/torchvision +cu128; CPU wheel не подставлялся.** Linux NCCL/Triton freeze не использовался. См. root установщик/lock и `windows/requirements-core-windows.txt` как исходный audit candidate.

Portable FFmpeg9.0.2: https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-9.0.2-essentials_build.zip ,114 768 076B, SHA25660f467265b1e312373dbcd92200c2618a74850f98d3d078e94296bb3fa2047ba, GPLv3. Лицензии сохранены, PATH применяется к процессам проекта.

Listener/Writer shared source: MIT llama.cppv0.6.0 commit8345f333951c661d166b00e6f9362e553768f292;3687 Git blobs проверены, no fabricated GitHEAD. Runtime/weights/projector/licensing proofs и точные URLs: `windows/LISTENER_AI_APPROVAL.md`. Оригинальный Qwen Apache2.0 LICENSE проверен на initial4728b48b и ae9e1690 revisions; обе conversion notices сохранены. Все пять файлов6 231 576 570B полностью SHA verified. Approved Listener cap6.3GB: artifact payload ledger сохранён, исторические302 тела не измерялись;48MiB allowance явно оценочная, не доказательство all-HTTP bytes. Future redirect bodies ограничены/учитываются; повторных загрузок нет.

Короткий Listener наблюдал до8520MiB общей GPU memory.used и8 769 142 784B native peak commit. Pilot и production GGUF listener требуют >=11GiB исходного machine-wide commit headroom /10GiB available RAM до model import/load; это short-test минимум,120s не проверен;8200MiB GPU gate является admission, не пределом расхода/гарантией для120s. Creator/Artist/audio ML сериализуются общим mutex, actual free VRAM перепроверяется после освобождения idle cache.

Optional separation assets: exact pins/SHA/нотисы в `windows/full-audio-models.json`; они ещё не устанавливались. UniverSR код MIT commitd8636623fe0c0704296239c1d3d3c5b911ecb2e0; weights CC BY4.0,229 072 395B+config. Trainer bf16/MERT/head CC BY-NC4.0; int8 own trainer распаковывает вbf16 и20GB gate не снимает. MERT выполняет local custom Python с trust_remote_code=True, поэтому требует отдельного аудита/согласованного исполнения. GTSinger external CC BY-NC-SA4.0 downloads остаются local-only blocked.

Общая матрица: `lab/AUDIO_WINDOWS.md`;27file candidate manifest21 986 084 016B **включает заблокированный Trainer** и не является командой скачивания всего списка. Основной запуск/адреса/остановка — в root Windows README; Listener не держит сервер и завершает native CLI после одного decode. Вручную foreground Stop: Ctrl+C с own-tree cleanup; Studio Stop-Full.ps1.
