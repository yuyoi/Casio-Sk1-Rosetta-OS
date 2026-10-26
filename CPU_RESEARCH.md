# MSM6283 (SK-1 CPU) research, 2026-10-26

## What's public
- OKI-made Casio custom SoC. Variants: -01GS SK-1 (MAME), -03 SK-1 (kbswiki), -05 SK-5/SK-8, -07 SK-2. Same chip, different internal programs.
- No datasheet anywhere (alldatasheet has only an index entry for -05). The CPU core is unidentified (MAME uses a dummy CPU). One Bannister forum post claims the SK-1 CPU "has already been decapped", with no photos or write-up.
- MAME devs (cuavas) and Hackaday commenters (Yarr) think the external ROM = **samples + interpreted bytecode**, with the real program in the chip. The service manual says the ROM holds "the system program". Unresolved.
- Nick Price (2018) put an Arduino in place of the ROM: sound came out distorted because it was too slow. Real-world proof that ROM timing matters.
- Pin hints (circuitbenders pin list): timer pins TIN/TC0/TC1/TOUT/ADCTR (unused on the SK-1), TEST (42), a second bus (aux D0-D7, CE2, C1/C2/OP) used for the SK-5 demo ROM and percussion chip. It looks like a general MCU core plus Casio sound hardware.

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
