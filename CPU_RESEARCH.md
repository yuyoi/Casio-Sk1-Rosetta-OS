# MSM6283 (SK-1 CPU) research, 2026-10-26

## What's public
- OKI-made Casio custom SoC. Variants: -01GS SK-1 (MAME), -03 SK-1 (kbswiki), -05 SK-5/SK-8, -07 SK-2. Same chip, different internal programs.
- No datasheet anywhere (alldatasheet has only an index entry for -05). The CPU core is unidentified (MAME uses a dummy CPU). One Bannister forum post claims the SK-1 CPU "has already been decapped", with no photos or write-up.
- MAME devs (cuavas) and Hackaday commenters (Yarr) think the external ROM = **samples + interpreted bytecode**, with the real program in the chip. The service manual says the ROM holds "the system program". Unresolved.
- Nick Price (2018) put an Arduino in place of the ROM: sound came out distorted because it was too slow. Real-world proof that ROM timing matters.
- Pin hints (circuitbenders pin list): timer pins TIN/TC0/TC1/TOUT/ADCTR (unused on the SK-1), TEST (42), a second bus (aux D0-D7, CE2, C1/C2/OP) used for the SK-5 demo ROM and percussion chip. It looks like a general MCU core plus Casio sound hardware.

## Service manual pin table (p6-7, read 2026-10-26)
- Casio lists pins **33-39, 41-42 (incl. TEST), 44-56, 59, 62-66, 85, 87 as "No function"**. The test, timer and aux-bus pins are hidden in the SK-1 manual.
- **KO9..KO0 = pins 67..76** (KO0 is pin 76), **KI1..KI8 = pins 77..84**, KO15 = pin 61 (filter control), PO1 = pin 86 (APO), PO3 = pin 88 (filter).
- The sound out is per channel: SE-SH = pitch signal and EE-EH = envelope signal for melody/obbligato/chord/bass. **The envelopes are applied outside the chip** (transistors T12-T23 + 4066). SC (pin 97) = percussion out.
- Negative logic: 0 V on VDD1, +5 V on the "GND" terminal.
- No test mode is documented anywhere in the SK-1 service manual.
- The SK-5 service manual exists (soundprogramming.net `/manuals/keyboard/Casio_SK-5_ServiceManual.pdf`), but a script download redirects to the homepage. Grab it from a browser. It may document the pins the SK-1 manual hides.

## SK-5 service manual (docs/casio_sk-5_sm.pdf, user-supplied, read 2026-10-26)
- CPU = **MSM6283-05GS**, clock **7.277 MHz**. Pin functions differ from the -01: the mask also sets pin roles (SK-5: pin 30 = memory /OE, pin 19 unused; SK-1: pin 19 = /OE, pin 30 = A15).
- SK-5 extras on the "hidden" SK-1 pins: CE1 (39) percussion chip MSM6294-02 write, CE2 (41) ROM pack select, CP1/CP2 (46/47) ROM pack clock, OP (48) demo ROM address/data switch, D0-D7 (49-56) aux bus to the percussion chip + demo music ROM MSM5268, MI (59) power-on detect, KO13 (63) ROM/RAM chip select, KO12 (64) APO, PO0 (85) percussion reset.
- **Pin 42 is "No function" in the SK-5 manual too**: TEST stays undocumented. No test mode in the SK-5 troubleshooting either.
- **The SK-5 uses ONE 32 KB SRAM (µPD43256C-12L, 120 ns), battery-backed** ("kept even power switch OFF as long as DC 7.5 V is provided"), selected by A15 = L. So this CPU family drives plain SRAM fine (no refresh needed), and the -05 program uses about 26 KB of it for 4 x 0.7 s samples. The SK-1's -01 program is hard-limited to its 13.5 KB.
- **Bus timing chart (p17):** each memory cycle is about 8t (t = 1/f_osc).
  - /CE goes low at 2t and stays low 4t; /OE goes low at 3t; data is latched about 3t after /CE and 2t after /OE.
  - A refresh pulse rides on every cycle ("+ pulse refresh").
  - At the SK-1's 7.24 MHz (t = 138 ns): **about 410 ns from /CE to data latch, about 275 ns from /OE**, if the -01 matches the -05.
  - **Consequences:**
    - The 200 ns ROM/RAM had about 2x margin, so memory isn't the overclock limit until about 2x clock.
    - A ROM emulator gets about 3.5x margin against 115 ns.
    - DRAM refresh happens every bus cycle, so slow clocks don't starve refresh (CLOCK_MOD.md's refresh worry is mostly void).
- Casio again says the ROM holds "preset tone, percussion data, and system execution program". Same wording as the SK-1 manual; the pointer and code analysis still says data/bytecode.

## In-circuit dump routes (no chip removal)
| Route | Risk | Odds | Notes |
|---|---|---|---|
| **Sample-pointer exploit** (probe 5) | none (ROM data only) | low-medium | "trick it into playing program ROM as audio" is the classic MAME-scene route. Pointers ≥ 0x8000 may wrap below the ROM. If one plays structured noise, record the line out and decode. |
| Bytecode decode (mutation tests) | none | medium | If the 0x000-0xA62 region is bytecode, we learn the interpreter's instruction set by changing bytes and listening. That's partial control of behaviour without the code. |
| Bus logger on the ROM socket | none (read-only) | gives behaviour, not code | Logs which ROM bytes the CPU reads, when (boot, Demo, key). Maps the bytecode. Internal fetches don't show. |
| TEST pin 42 | small (10k pull) | unknown | User said no. |
| Decap | chip destroyed | high | User said no. |

## Probe 5 (`tools/probe5.py`, upper half of `rom/probe15_w27c512.bin`)
- Entries 0-4 = 0x8000, 0xC000, 0xD000, 0xE000, 0xF000. ROM 0x4000/5000/6000/7000 hold tones of 300/450/600/800 Hz.
- **Hear the tones** → the CPU ORs A15, so no escape from the ROM.
- **Preset that plays 0x8000 sounds like your last sample** → the pointer wraps into RAM. Then 0xC000-0xF000 read CPU 0x4000-0x7FFF: silence/hiss = nothing there; structured buzzy noise = **possibly internal ROM**. Record the line out at 96 kHz.

## Sources
- MAME wiki MNS: https://wiki.mamedev.org/index.php/MNS
- kbswiki OKI page: https://kbswiki.miraheze.org/wiki/OKI_Semiconductor
- Hackaday 2018 Arduino SK-1 + comments: https://hackaday.com/2018/02/05/circuit-bent-casio-sk-1-gets-an-arduino-brain/
- spun.io SK-1 RE part 1: https://spun.io/2018/02/01/reverse-engineering-the-casio-sk-1-part-1-dumping-the-rom/
- Bannister forum SA-series thread (decap hearsay): https://forums.bannister.org/ubbthreads.php?ubb=showflat&Number=45295
- alldatasheet MSM6283-05 index: https://www.alldatasheet.com/view_datasheet.jsp?Searchword=MSM6283-05
