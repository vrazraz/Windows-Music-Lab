# Реальная независимая проверка Inspect и базового Remaster

Рабочая папка: `E:\Projects\Ruach_Studio\full-windows-port`. Проверка началась2026-10-12 21:24:59UTC после отдельного согласования на исходной HEADff5c470. Использованы только собственные вновь созданные synthetic fixtures, установленная `.venv` и portable FFmpeg9.0.2. GPU, модели, сеть, новые зависимости и пользовательские файлы не использовались. Studio/порты не задействованы.

## Повторяемый validator

По умолчанию скрипт лишь печатает план. Реальная CPU проверка:

```powershell
Set-Location -LiteralPath 'E:\Projects\Ruach_Studio\full-windows-port'
.\.venv\Scripts\python.exe .\windows\validate_refiner_independent.py --run
.\.venv\Scripts\python.exe .\lab\test_refiner_signal.py
```

Каждый validation создаёт новую уникальную папку в ignored `windows/cache/refiner-independent/`, сохраняет входные WAV, settings, отдельные stdout/stderr, argv/exit/time, результаты и report. Final report: `windows/cache/refiner-independent/20261013-002459-c13983/report.json`. Все9 worker/FFmpeg/FFprobe commands завершились с exit0. Source/fixture SHA и четырёх тестов summary сохранены в отчёте. Первый failure20261013-001750-be7890 сохранён; предыдущие успешные reports тоже не перезаписаны.

## Inspect: что доказано

Реальный stereo48kHzPCM24/8s fixture содержал tone997Hz, mains60Hz,25Hz AM high band,DC,click1s,12sample clipping at2s,100ms dropout at3s,1s reversed stereo at5s. Worker нашёл tone996.3Hz,hum58.6Hz,click1s,оба12sample clipping runs,dropout3.0s/100ms,DC0.019775/0.014775 и correlation−1.0 at5s. Framebuzz25Hz31.6dB выше соседей, mean9.0dB; эти значения сохранены, это анализ искусственного сигнала, не музыкальное/ML понимание. LUFS/LRA/truepeak присутствуют и конечны.

Найдены и исправлены реальные ошибки:

- На100ms WAV STFT16384sample window выходил за4800sample input и падал сIndexError. Теперь одно окно дополняется нулями, истинная длительность сохраняется, ограничение записывается вanalysis_notes.
- Короткий clip не даёт разрешения для узких framebuzz harmonic bands. Неизмеримые значения возвращаются какnull вunresolved_windows; обычныйwindows содержит только измеримые данные, совместимые с существующимUI v.toFixed. Mean=null показывает отсутствие измерения, а не0dB.
- Антифазные24bit channels оставляли sub-LSB mono rounding, которое малый median превращал в ложные clicks. Добавлен только absolute two24bit-LSB floor к существующему40× criterion. В8s fixture исчезли ложные clicks внутри тихого antiphase участка; настоящие injected events сохранились.
- Empty/nonfinite input прекращает worker до публикации; JSON закрывает handle/UTF8 и запрещаетNaN/Infinity. Silent truepeak−infinity представляетсяnull. Неуспешный FFmpeg loudness process теперь даёт отказ, а неok с пустой мерой.

Четыре реальные worker regressions прошли за1.323s:100ms tone,20ms silence/strictJSON,24bit antiphase quantization,empty audio. Общая музыкальная precision/recall детекторов, длинные файлы и browser upload workflow не оценивались.

## Basic Remaster/Debunker: что доказано

Реальный6s собственный stereo48kHzPCM24 signal сDC0.025 и заданными title/comment прошёл `remaster_job.py` → Debunker pipeline. Settings: trim[1,5]s,cleanup=true,fade0.3s,loudnorm−18LUFS/ceiling−1dBTP,formatsWAV+FLAC;deess=false,hz432=false. Никакого stems/separation/Calf/UniverSR.

- Оба файла реально существуют и заявлены worker; **192000frames =4.000s**, stereo48kHzPCM24; все samples конечны. SHA обоих outputs вreport.
- Независимый FFmpeg measurement для обоих: **−18.03LUFS**, truepeak**−14.84dBTP**, worker summary−18.0LUFS. Peak ниже ceiling−1; fixture не доказывает работу limiter на предельном пике.
- Fade: первые/последние10ms RMS≈0.002985/0.003018 против середины0.096998; обе стороны <10% middleRMS.
- DC послеcleanup≈−1.64e−6 на обоих каналах; source title/comment исчезли, output format tags пусты. `debunker.log` сохранён.

Это закрывает short basic WAV/FLAC/trim/fade/cleanup/loudnorm path. **Не проверены** deesser,432Hz,MP3,стемный remix/drift,separation,CalfLV2,UniverSR,Whisper,textend/karaoke,длинные файлы и субъективное музыкальное качество. Для этих возможностей прежние ограничения остаются. Код Remaster/Debunker в этом этапe не менялся: базовый path уже выполнился корректно.
