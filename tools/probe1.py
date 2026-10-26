"""Probe ROM 1: which button plays which table entry, and does the end-of-ROM loop work?

- Drum area 0x0B00-0x0FFF and table entries 5-7 stay stock (rhythms keep their drums).
- Entries 0-4 say "one" .. "five" so each PCM preset button can be matched to its entry.
- Entry 4 says "five", then a steady saw runs to 0x7FFF with NO end marker.
  Entry 8 (0x086C, the stock 0x7EB2 loop start) points at the last 512 bytes of that saw.
  If the key keeps sounding while held, the CPU loops at end-of-ROM back to entry 8.

Usage: python probe1.py BASE.bin WAVDIR OUT.bin
"""
import os
import struct
import sys

import numpy as np

from sk1rom import RATE, TABLE, ROM_SIZE, END, fit, load_wav, to_pcm

WORD_MAX = 0.5  # seconds per spoken ID

DRUM_END = 0x1000
LOOP_LEN = 512
SAW_PERIOD = 64  # 146.7 Hz, 8 whole cycles per loop so the seam is clean


def main():
    base_path, wav_dir, out_path = sys.argv[1:4]
    rom = bytearray(open(base_path, "rb").read()[:ROM_SIZE])
    rom[DRUM_END:] = b"\x80" * (ROM_SIZE - DRUM_END)
    addr, starts = DRUM_END, []
    for word in ("one", "two", "three", "four", "five"):
        x = load_wav(os.path.join(wav_dir, f"id_{word}.wav"))
        loud = np.nonzero(np.abs(x) > 0.02)[0]
        x = fit(x[:loud[-1] + 1], int(WORD_MAX * RATE))  # drop TTS tail silence, cap length
        pcm = to_pcm(0.9 * x)
        starts.append(addr)
        rom[addr:addr + len(pcm)] = pcm
        addr += len(pcm)
        if word != "five":
            addr += addr & 1  # keep the marker on an even address, like every stock marker
            rom[addr:addr + 2] = END
            addr += 2
        print(f"  entry {len(starts) - 1}: 0x{starts[-1]:04X} '{word}' {len(pcm) / RATE:.2f} s")
    # steady saw from after "five" to the end of the ROM, no marker
    n = ROM_SIZE - addr
    assert n > LOOP_LEN, "words too long, no room for the saw"
    phase = (np.arange(n) % SAW_PERIOD) / SAW_PERIOD
    saw = to_pcm(0.7 * (2 * phase - 1))
    rom[addr:] = saw
    loop = ROM_SIZE - LOOP_LEN
    print(f"  saw 0x{addr:04X}-0x7FFF ({n / RATE:.2f} s), loop start 0x{loop:04X}")
    for i, a in enumerate(starts):
        struct.pack_into("<H", rom, TABLE + 2 * i, a)
    struct.pack_into("<H", rom, TABLE + 16, loop)
    open(out_path, "wb").write(bytes(rom) * 2)
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
