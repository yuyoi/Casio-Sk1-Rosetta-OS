"""Replace the SK-1's 5 PCM presets with Roland S-770 CD samples (and WAVs), keep the drum kit.

Each new sound is pitched to the stock sound in its slot (measured: entries 0/2/4 ~447 Hz, 1 ~224 Hz,
3 ~144 Hz), so it plays in tune on the same keys. FX keep their own speed.
The last sound runs to 0x7FFF without an end marker and gets a crossfaded loop; table entry 8
(the stock end-of-ROM loop start) points at it, so that preset sustains if the loop theory holds.

Usage: python roland_presets.py BASE.bin ROLAND_CD_DIR U110_SRC_DIR AUDITION_DIR OUT.bin
"""
import os
import struct
import sys
from fractions import Fraction

import numpy as np
from scipy.signal import resample_poly

from sk1rom import RATE, TABLE, ROM_SIZE, END, fit, load_wav, to_pcm

# entry: (source, where, name, source note as MIDI or None, target Hz or None, bytes incl. marker)
# The source note comes from the sample's name (autocorrelation locks onto overtones on these).
# The None-size one goes last and loops.
PICKS = {
    0: ("roland", "LCDP02 Guitar and Bass.iso", "GTR:Strat F_4", 65, 447.0, 5120),
    2: ("wav", "pad", "054_Best_Service_ProSamples__CRYSTAL_ICE_49H_FX12_L.wav", None, None, 4608),
    3: ("wav", "synth", "141_Ethereal_Atmospheres_06_POLYSYNTH_POLYSYNTC3_L.wav", 48, 144.0, 5632),
    4: ("roland", "Roland L-CDX-02 Keyboard Instruments.iso", "VOX:TrnChrA_4", 69, 447.0, 6144),
    1: ("roland", "Roland L-CDX-02 Keyboard Instruments.iso", "VOX:Chb Ml A_3L", 57, 224.0, None),
}
DRUM_END = 0x1000
LOOP_PERIODS = 24


def plain(name):
    """names vary in spacing and can carry a flag byte >= 0x7F"""
    return "".join(c for c in name if " " < c < "\x7f")


def load_roland(disc_cls, cd_dir, iso, name):
    d = disc_cls(os.path.join(cd_dir, iso))
    try:
        for slot, n in d.entries(0x44):
            if plain(n) == plain(name):
                s = d.sample(slot)
                return s["pcm"].astype(np.float64), s["rate"]
    finally:
        d.close()
    sys.exit(f"{name} not found on {iso}")


def to_slot(x, rate, note, target_hz):
    """resample so the sound's pitch lands on target_hz when played at the SK-1 rate (None = keep speed)"""
    f0 = 440.0 * 2 ** ((note - 69) / 12) if target_hz else None
    ratio = Fraction(RATE * f0 / (rate * target_hz) if target_hz else RATE / rate).limit_denominator(500)
    y = resample_poly(x, ratio.numerator, ratio.denominator)  # small factors keep the filter short
    loud = np.nonzero(np.abs(y) > 0.02 * np.max(np.abs(y)))[0]
    y = y[loud[0]:] / np.max(np.abs(y))
    shift = f"{f0:.0f} Hz -> {target_hz:.0f} Hz" if target_hz else "own speed"
    print(f"    {shift}, {len(y) / RATE:.2f} s available")
    return y


def looped_tail(y, n, target_hz):
    """first n samples of y, the last LOOP_PERIODS periods crossfaded so they loop cleanly"""
    loop_len = int(round(LOOP_PERIODS * RATE / target_hz))
    if len(y) < n:
        sys.exit("last sample too short for its slot")
    y = y[:n].copy()
    ls = n - loop_len
    fade = loop_len // 2
    w = np.linspace(0, 1, fade)
    y[n - fade:] = y[n - fade:] * (1 - w) + y[ls - fade:ls] * w
    return y, ls


def main():
    base_path, cd_dir, u110_src, audition_dir, out_path = sys.argv[1:6]
    sys.path.insert(0, u110_src)
    from roland import Disc

    rom = bytearray(open(base_path, "rb").read()[:ROM_SIZE])
    rom[DRUM_END:] = b"\x80" * (ROM_SIZE - DRUM_END)
    a, ptr = DRUM_END, {}
    for e, (src, where, name, note, hz, size) in PICKS.items():
        print(f"  entry {e}: {name}")
        if src == "roland":
            x, rate = load_roland(Disc, cd_dir, where, name)
            y = to_slot(x, rate, note, hz)
        else:
            y = load_wav(os.path.join(audition_dir, where, name))  # already at RATE
            if hz:
                y = to_slot(y, RATE, note, hz)
        ptr[e] = a
        if size:
            pcm = to_pcm(0.95 * fit(y, size - len(END)))
            rom[a:a + len(pcm)] = pcm
            rom[a + len(pcm):a + len(pcm) + 2] = END
            a += size
        else:
            y, ls = looped_tail(y, ROM_SIZE - a, hz)
            rom[a:] = to_pcm(0.95 * y)
            struct.pack_into("<H", rom, TABLE + 16, a + ls)
            print(f"    loops 0x{a + ls:04X}-0x7FFF")
    for e, p in ptr.items():
        struct.pack_into("<H", rom, TABLE + 2 * e, p)
    print("  table:", " ".join(f"{e}=0x{p:04X}" for e, p in sorted(ptr.items())))
    assert len(rom) == ROM_SIZE
    open(out_path, "wb").write(bytes(rom) * 2)
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
