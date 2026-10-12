"""DAW export audio: local PCM WAV fast path, FFmpeg only for other formats.

The native engine's 48 kHz PCM WAV needs no external tool. Other sample rates,
compressed audio, float WAV and multichannel sources still require approved
FFmpeg. Output is always stereo, 48 kHz, signed 24-bit PCM.
"""
from pathlib import Path
import wave
from platform_runtime import run_process


def to_wav(source, target, root=None):
    source, target = Path(source), Path(target)
    try:
        incoming = wave.open(str(source), "rb")
    except (wave.Error, EOFError):
        incoming = None
    if incoming is not None:
        with incoming:
            channels, width, rate = incoming.getnchannels(), incoming.getsampwidth(), incoming.getframerate()
            if incoming.getcomptype() == "NONE" and channels in (1, 2) and width in (2, 3, 4) and rate == 48000:
                expected, count = incoming.getnframes(), 0
                with wave.open(str(target), "wb") as outgoing:
                    outgoing.setparams((2, 3, 48000, 0, "NONE", "not compressed"))
                    while True:
                        block = incoming.readframes(32768)
                        if not block:
                            break
                        if len(block) % (channels * width):
                            raise ValueError("PCM WAV ends inside a frame")
                        count += len(block) // (channels * width)
                        if width == 2:
                            pcm = bytearray(len(block) // 2 * 3)
                            pcm[1::3], pcm[2::3] = block[0::2], block[1::2]
                        elif width == 4:
                            pcm = bytearray(len(block) // 4 * 3)
                            pcm[0::3], pcm[1::3], pcm[2::3] = block[1::4], block[2::4], block[3::4]
                        else:
                            pcm = block
                        if channels == 1:
                            stereo = bytearray(len(pcm) * 2)
                            for offset in range(3):
                                stereo[offset::6] = pcm[offset::3]
                                stereo[offset + 3::6] = pcm[offset::3]
                            pcm = stereo
                        outgoing.writeframesraw(pcm)
                if count != expected:
                    raise ValueError("PCM WAV is truncated")
                return
    run_process(["ffmpeg", "-v", "error", "-y", "-i", str(source), "-ar", "48000",
                 "-ac", "2", "-c:a", "pcm_s24le", str(target)], check=True, timeout=600, root=root)


def seconds(path, root=None):
    try:
        with wave.open(str(path), "rb") as incoming:
            return incoming.getnframes() / incoming.getframerate()
    except (wave.Error, EOFError):
        value = run_process(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                             "-of", "csv=p=0", str(path)], capture_output=True, text=True,
                            check=True, timeout=60, root=root).stdout.strip()
        return float(value or 0)