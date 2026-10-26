"""Probe ROM 5: can a sample pointer reach outside the ROM? (in-circuit dump attempt)

Stock pointers are ROM offsets (0x0000-0x7FFF); the CPU must add A15 to reach the ROM at 0x8000.
If it ADDS 0x8000 (16-bit wrap), a pointer >= 0x8000 lands in CPU space below the ROM:
  0x8000 -> CPU 0x0000 = RAM2 = your own sample
  0xC000 -> CPU 0x4000, 0xD000 -> 0x5000, 0xE000 -> 0x6000, 0xF000 -> 0x7000
              = space no external chip answers: floating bus, or the CPU's internal ROM
If it ORs A15 instead, those pointers just read ROM 0x0000 / 0x4000 / 0x5000 / 0x6000 / 0x7000,
so those ROM areas hold four plain tones (300 / 450 / 600 / 800 Hz) to recognise that case.

Drums (0x0B00-0x0FFF, entries 5-7) stay stock.
Usage: python probe5.py BASE.bin OUT32K.bin
"""
import struct
import sys

import numpy as np

from sk1rom import RATE, TABLE, ROM_SIZE, END, to_pcm

POINTERS = [0x8000, 0xC000, 0xD000, 0xE000, 0xF000]
TONES = {0x4000: 300, 0x5000: 450, 0x6000: 600, 0x7000: 800}


def main():
    base_path, out_path = sys.argv[1:3]
    rom = bytearray(open(base_path, "rb").read()[:ROM_SIZE])
    rom[0x1000:] = b"\x80" * (ROM_SIZE - 0x1000)
    for start, hz in TONES.items():
        n = 0x1000 - len(END)
        t = np.arange(n) / RATE
        rom[start:start + n] = to_pcm(0.7 * np.sin(2 * np.pi * hz * t))
        rom[start + n:start + 0x1000] = END
    for i, p in enumerate(POINTERS):
        struct.pack_into("<H", rom, TABLE + 2 * i, p)
    open(out_path, "wb").write(bytes(rom))
    print("entries 0-4 ->", " ".join(f"0x{p:04X}" for p in POINTERS))


if __name__ == "__main__":
    main()
