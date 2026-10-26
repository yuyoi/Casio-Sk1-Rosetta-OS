"""SK-1 ROM builder: put your own sounds into the Casio SK-1 preset ROM (LSI2).

What we know about the ROM (see ROM_MAP.md):
  - 8-bit unsigned PCM, centre 0x80, 9387 Hz
  - a sound ends with the bytes FF FF (so sound data must never contain FF)
  - sample start table: 8 little-endian words at 0x085C, plus 0x7EB2 (loop point?)
  - PCM area starts at 0x0B00; everything below it is tables the CPU reads

Usage:
  python sk1rom.py test-long  BASE.bin OUT.bin           one 3-note test tone filling the whole PCM area
  python sk1rom.py one-long   BASE.bin OUT.bin in.wav [speed]
                                                         one long sound for every preset
                                                         (speed 2 = 6.4 s fits, play it an octave down)
  python sk1rom.py slots      BASE.bin OUT.bin a.wav ... up to 8 sounds, packed back to back

OUT.bin is 64 KB (image twice) for a W27C512 with pin 1 tied either way.
OUT.sst.bin is 512 KB (image x16) for an SST39SF040 burned on the Hex Wizard.
"""
import struct
import sys
import wave

import numpy as np
from scipy.signal import resample_poly

RATE = 9387
TABLE = 0x085C
PCM_START = 0x0B00
ROM_SIZE = 0x8000
END = b"\xff\xff"


def load_wav(path, speed=1.0):
    """Any WAV -> float mono at RATE, peak-normalised to +-1.

    speed 2 stores the sound twice as fast: twice the length fits, play it an octave lower.
    """
    with wave.open(path, "rb") as w:
        ch, width, rate, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        raw = w.readframes(n)
    if width == 1:
        x = np.frombuffer(raw, np.uint8).astype(np.float64) - 128
    elif width == 2:
        x = np.frombuffer(raw, "<i2").astype(np.float64)
    elif width == 3:
        b = np.frombuffer(raw, np.uint8).reshape(-1, 3)
        x = (b[:, 0].astype(np.int32) | (b[:, 1].astype(np.int32) << 8) | (b[:, 2].astype(np.int32) << 16))
        x = np.where(x & 0x800000, x - 0x1000000, x).astype(np.float64)
    else:
        x = np.frombuffer(raw, "<i4").astype(np.float64)
    x = x.reshape(-1, ch).mean(axis=1)
    target = round(RATE / speed)
    if rate != target:
        # resample_poly low-passes before decimating, so no extra anti-alias filter needed
        x = resample_poly(x, target, rate)
    peak = np.max(np.abs(x)) or 1.0
    x = x / peak
    # skip leading silence: ROM space is too tight to waste on it
    loud = np.nonzero(np.abs(x) > 0.02)[0]
    return x[loud[0]:] if len(loud) else x


def to_pcm(x):
    """Float +-1 -> SK-1 bytes. Clipped to 0x01..0xFE so FF never appears inside a sound."""
    return bytes(np.clip(np.round(x * 126 + 128), 1, 0xFE).astype(np.uint8))


def test_tone(seconds):
    """Three equal parts at 220, 330, 440 Hz: hear all three = the whole length played."""
    n = int(seconds * RATE)
    t = np.arange(n) / RATE
    f = np.select([t < seconds / 3, t < 2 * seconds / 3], [220.0, 330.0], 440.0)
    phase = 2 * np.pi * np.cumsum(f) / RATE
    return 0.8 * np.sign(np.sin(phase)) * 0.5 + 0.3 * np.sin(phase)


def write_table(rom, starts):
    for i, a in enumerate(starts):
        struct.pack_into("<H", rom, TABLE + 2 * i, a)


def fit(x, n, fade=0.03):
    """Cut to n samples with a short fade-out so the cut doesn't click."""
    x = x[:n].copy()
    f = min(len(x), int(fade * RATE))
    if f:
        x[-f:] *= np.linspace(1, 0, f)
    return x


def build(base, sounds, same_for_all=False):
    """Pack sounds back to back from PCM_START, each ended with FF FF, and point the table at them.

    With several sounds, each gets an equal share of the room.
    """
    rom = bytearray(base)
    rom[PCM_START:] = b"\x80" * (ROM_SIZE - PCM_START)
    room = ROM_SIZE - PCM_START
    if len(sounds) > 1:
        share = room // len(sounds) - len(END)
        sounds = [fit(x, share) if len(x) > share else x for x in sounds]
    addr, starts = PCM_START, []
    for x in sounds:
        pcm = to_pcm(x)
        free = ROM_SIZE - addr - len(END)
        if free <= 0:
            sys.exit(f"out of room: {room} bytes = {room / RATE:.2f} s total")
        if len(pcm) > free:
            print(f"  cut {len(pcm) / RATE:.2f} s -> {free / RATE:.2f} s")
            pcm = pcm[:free]
        rom[addr:addr + len(pcm)] = pcm
        rom[addr + len(pcm):addr + len(pcm) + 2] = END
        starts.append(addr)
        print(f"  slot {len(starts) - 1}: 0x{addr:04X}, {len(pcm)} B = {len(pcm) / RATE:.2f} s")
        addr += len(pcm) + 2
    if same_for_all:
        starts = starts[:1] * 8
    while len(starts) < 8:
        starts.append(starts[-1])
    write_table(rom, starts)
    return bytes(rom)


def main():
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    cmd, base_path, out_path = sys.argv[1:4]
    base = open(base_path, "rb").read()[:ROM_SIZE]
    full = (ROM_SIZE - PCM_START - len(END)) / RATE
    if cmd == "test-long":
        rom = build(base, [test_tone(full)], same_for_all=True)
    elif cmd == "one-long":
        speed = float(sys.argv[5]) if len(sys.argv) > 5 else 1.0
        rom = build(base, [load_wav(sys.argv[4], speed)], same_for_all=True)
    elif cmd == "slots":
        rom = build(base, [load_wav(p) for p in sys.argv[4:12]])
    else:
        sys.exit(__doc__)
    # .sst.bin = 512 KB for an SST39SF040 burned on the Hex Wizard (image x16, so any A15-A18 wiring works)
    copies = 16 if out_path.endswith(".sst.bin") else 2
    with open(out_path, "wb") as f:
        f.write(rom * copies)
    print(f"wrote {out_path} ({len(rom) * copies // 1024} KB, image x{copies})")


if __name__ == "__main__":
    main()
