"""Bounded standard MIDI reader shared by score import and DAW exports (stdlib)."""
MAX_BYTES = 32 * 1024 * 1024
MAX_EVENTS = 262144


def tracks(data):
    data = bytes(data)
    if len(data) > MAX_BYTES or len(data) < 14 or data[:4] != b"MThd":
        raise ValueError("not a complete MIDI file (32 MiB maximum)")
    header = int.from_bytes(data[4:8], "big")
    if header < 6 or 8 + header > len(data):
        raise ValueError("broken MIDI header")
    fmt, count, division = (int.from_bytes(data[i:i + 2], "big") for i in (8, 10, 12))
    if fmt not in (0, 1) or not 1 <= count <= 1024 or (fmt == 0 and count != 1):
        raise ValueError("only synchronous MIDI format 0/1 (1-1024 tracks) is supported")
    if not division or division & 0x8000:
        raise ValueError("MIDI needs a nonzero PPQ; SMPTE timing is unsupported")
    position, result = 8 + header, []
    for _ in range(count):
        if position + 8 > len(data) or data[position:position + 4] != b"MTrk":
            raise ValueError("missing MIDI track")
        end = position + 8 + int.from_bytes(data[position + 4:position + 8], "big")
        p = position + 8
        if end > len(data):
            raise ValueError("truncated MIDI track")
        now, running, name, events, metadata = 0, None, "", [], []

        def take(length):
            nonlocal p
            if length < 0 or p + length > end:
                raise ValueError("MIDI ends inside an event")
            value = data[p:p + length]
            p += length
            return value

        def vlq():
            value = 0
            for _ in range(4):
                byte = take(1)[0]
                value = value << 7 | byte & 127
                if not byte & 128:
                    return value
            raise ValueError("MIDI variable integer exceeds four bytes")

        total = 0
        while p < end:
            total += 1
            if total > MAX_EVENTS:
                raise ValueError("too many MIDI events")
            now += vlq()
            status = data[p] if p < end else take(1)[0]
            if status & 128:
                take(1)
            elif running is not None:
                status = running
            else:
                raise ValueError("MIDI running status has no channel event")
            if 0x80 <= status <= 0xEF:
                running = status
                body = take(1 if status >> 4 in (0xC, 0xD) else 2)
                if any(byte & 128 for byte in body):
                    raise ValueError("MIDI channel data is not seven-bit")
                events.append((now, bytes([status]) + body))
            elif status == 0xFF:
                kind = take(1)[0]
                body = take(vlq())
                metadata.append((now, kind, body))
                if kind == 3 and not name:
                    name = body.decode("utf-8", "replace")
                if kind == 0x2F:
                    if body or p != end:
                        raise ValueError("invalid MIDI end-of-track")
            elif status in (0xF0, 0xF7):
                running = None
                take(vlq())
            else:
                raise ValueError("unsupported MIDI system event")
        result.append({"name": name, "ticks": now, "events": events, "metadata": metadata})
        position = end
    if position != len(data):
        raise ValueError("trailing bytes after MIDI tracks")
    return fmt, division, result