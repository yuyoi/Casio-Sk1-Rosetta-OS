# Live slots: record on the SK-1, push into a ROM slot, wave-sequence (plan 2026-10-26)

**PARKED 2026-10-26: user: "annoying build, no thanks". Don't push it again unless they bring it up.**

## Idea (user's)
Sample with the SK-1's own record button, then the sound gets pushed into one of the 8 preset slots, and slots can be chained or sequenced.

## Why the stock parts can't
- The CPU never writes to the ROM area (the ROM socket has no /WE), and its code is sealed inside the MSM6283.
- The W27C512 needs about 12 V to program, so it can only be written in the T48.

## How it works anyway: one RP2040 in the ROM socket
The RP2040 *is* the ROM, and it also watches the bus.

1. **Serve ROM reads.** PIO watches A0-A14 + /CE and puts the byte from its own RAM on D0-D7. RP2040 ROM emulators already exist (e.g. PicoROM), so this is a known trick.
2. **Catch the recording.** The same PIO sees every RAM write (/WE + A15 low). While the SK-1 samples, it copies each byte as it goes into RAM: 13,568 bytes = 1.4 s.
3. **Push into a slot.** Press a button on the card (or a key combo the RP2040 sees on the bus) → the copied sound is written into slot N in the RP2040's ROM image + saved to its flash. It plays as a preset straight away.
4. **Bigger slots.** Slots can be up to 3.2 s (proven on hw). The SK-1 records 1.4 s max, so a slot can also hold several recordings back to back.
5. **Wave sequence.**
   - Fixed: recordings placed back to back without FF FF play in a row (works now with sk1rom.py).
   - Live: the RP2040 sees which table entry (0x085C + 2n) the CPU reads at each note and swaps the pointer for the next note: round-robin, step sequence, etc.
6. **Banks.** 2-16 MB flash on the Pico → many banks of 8 slots, loaded into RAM on demand.

## Pins (RP2040 has 30 GPIO)
| Signal | Pins | Direction | From |
|---|---|---|---|
| A0-A12 | 13 | in | shared CPU bus (ROM + RAM) |
| A13, A14 | 2 | in | ROM socket pins 26, 27 |
| A15 | 1 | in | CPU (ROM pin 22 is GND on this board, so wire from IC3 / CPU) |
| D0-D7 | 8 | in/out | ROM socket |
| /CE | 1 | in | ROM pin 20 |
| /WE | 1 | in | RAM pin 27 |
| button / LED | 2 | | card |
| **total** | **28** | | |

## Level shifting (SK-1 bus is 5 V)
- Inputs (address, /CE, /WE, data when sniffing): 74LVC245 (5 V-tolerant inputs) → 3.3 V.
- Data out to the bus: 74HCT245 (takes 3.3 V in, gives 5 V out), enabled only while /CE is low (ROM read).
- Check before building: the MSM6283's input-high threshold. If 3.3 V counts as high, the HCT245 can go.
- Alternative: RP2350 (Pico 2) has 5 V-tolerant inputs, which drops the input buffers.

## Timing budget from datasheets (2026-10-26)
- Stock ROM = NEC µPD23C256E, standard grade (no -1): **tACC 200 ns, tCE 200 ns, tOE 100 ns** at 5 V (`docs/datasheets/upd23c256e.pdf`). The RAMs are D4168C-**20** = 200 ns too. So the SK-1 bus is built to wait ≥ 200 ns.
- Same datasheet: OE active level is a mask option (1, 0 or don't-care), which explains pin 22 on GND.
- Same datasheet: ROM outputs are TTL (VOH min 2.4 V), so the CPU must accept 2.4 V as high → 3.3 V from the RP2040 is enough, **no HCT245 needed**.
- RP2040 ROM emulation (PicoROM): 70-100 ns quoted by the project.
- 74LVC245 in the path: ~5-7 ns each way.
- Worst case: 100 + 7 + 7 ≈ 115 ns vs 200 ns → **~85 ns spare (≈1.7x)**. With PicoROM's 70 ns figure: ~2.4x.
- Buffers: 74LVC245 only (5 V-tolerant in, 3.3 V out): address/CE/WE in, one bidirectional for data.

## Risks / first tests
1. **Timing:** can PIO answer a ROM read fast enough at this CPU clock? Measure the /CE low time on the scope or the logic analyser first. This decides everything.
2. Which bus cycles are sample writes vs. song/sequencer writes: filter by address (sample = 0x0000-0x1FFF + 0x2B00-0x3FFF).
3. Does the CPU read the start table once per note or once per preset change (live sequencing depends on it).

## Parts
Raspberry Pi Pico (or Pico 2), 74LVC245 x3, 74HCT245 x1, 28-pin turned-pin header plug for the ROM socket, button, LED. All through-hole.
