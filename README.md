# Casio SK-1 Rosetta OS

Research and mods for the **Casio SK-1** (also sold as the Realistic Concertmate-500), the 1985 sampling keyboard.

Goal: get more sampling out of it, and replace the preset sounds with your own.

**Status: research.** The ROM is dumped and the hardware is mapped. Nothing is built yet.

## What we found

- **RAM:** 2× NEC µPD4168C, 8 KB each, 16 KB total.
- **Stock sample:** 13,568 bytes = 1.4 s, 8-bit at 9.387 kHz. That's 83% of the RAM.
- **The rest of the RAM:** 2,816 bytes for memory-play / demo song data.
- **CPU:** MSM6283-01GS. Its program is almost certainly inside the chip, so it can't be read or changed.
- **External ROM (LSI2, NEC µPD23C256EAC-011):** data only.
  - 0x0000–0x0A62: tables (presets / rhythms / demo, not decoded yet).
  - From 0x0B00: preset PCM sounds. The start table is at 0x085C.
- **So:** one longer clean sample is blocked (the length is set by the CPU's built-in program). More samples and custom presets are not.

## Memory map (service manual p11–12)

| CPU range | Chip | Use |
|---|---|---|
| 0x0000–0x1FFF | RAM2 (LSI3) | sample |
| 0x2000–0x3FFF | RAM1 (LSI4) | 2.8 KB song memory + 5.4 KB sample |
| 0x4000–0x7FFF | — | not decoded |
| 0x8000–0xFFFF | ROM (LSI2) | 32 KB |

## Mod routes

1. **Custom presets.** Swap LSI2 for a 27C256-pinout EEPROM/EPROM (e.g. Winbond W27C257) and burn your own sounds in. Jumper the new chip's pin 1 (VPP) to pin 28 (5 V).
   - Pin 22 (OE) is tied to ground on the board through a wire-link jumper (checked on hardware), so the swap is a drop-in: no inverter needed. Keep that jumper in place.
   - With a W27C512 and a switch on pin 1: 2 preset banks.
2. **Sample banks.** Replace each µPD4168 with an AS6C1008 (128 KB SRAM) on a 28-to-32-pin adapter, and put the extra address lines on a rotary switch. That's 16 banks, each a full 1.4 s sample + song.
3. **Slow clock while sampling.** A switch or pot on the clock (L1). Half clock = about 2.9 s at about 4.7 kHz; play it an octave down for the original pitch.
   - Swap the RAMs for 6264 SRAMs first: the 4168s need refreshing from the clock and may lose data when it's slow.

## Dump your own ROM

The ROM is not included in this repo (Casio copyright). Read your own chip:

- Programmer: XGecu T48 (or a TL866) set to 27C256, read only:
  `minipro -p "AM27C256@DIP28" -x -r sk1_lsi2.bin`
- A good dump has CRC32 `d615963c` and SHA1 `0dbf2d1c4c776f1a1c35dd2be4d6ca03882afd4c`.
- No adapter needed: a plain read works.

## Docs

- Service manual and user manual: [polynominal.com/casio-sk-1](https://www.polynominal.com/casio-sk-1/index.html)
- Detailed notes: [CONTEXT.md](CONTEXT.md)

## Credits

- yuyoi: hardware, dumping, testing
- MAME `sk1.cpp` (Vas Crabb): ROM layout and hashes
- circuitbenders.co.uk forum: MSM6283 pin list
- Built with Claude Code
