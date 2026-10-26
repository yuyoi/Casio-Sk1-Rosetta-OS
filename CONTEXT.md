# Casio SK-1 — ROM / OS mod / more sample RAM (context, 2026-10-26)

## Files
- `docs/casio-sk1-service-manual.pdf` — Realistic Concertmate-500 (= SK-1) service manual, 31 p, scanned (no text layer)
  - p10 sample input + sample-time formula, p11 ROM/RAM access + **memory assignment table**, p12 ROM select + PSU,
    p17-18 PCB, p19-24 parts, p27 **IC pinouts**, p28-30 schematic
  - `docs/pages/hi_pNN.png` = every page at 200 dpi
- `docs/casio-sk1-manual.pdf` — user manual
- Source: polynominal.com/casio-sk-1

## Hardware (service manual, verified by reading the pages)
| Ref | Part | Role |
|---|---|---|
| LSI1 | MSM6283-01GS (OKI/Casio, 100-pin QFP) | CPU + sound + 8-bit ADC, 7.24 MHz LC osc |
| LSI2 | µPD23C256EAC-011 | 32 KB mask ROM, DIP-28 |
| LSI3, LSI4 | µPD4168C | 8 KB x8 pseudo-static RAM (manual says "dynamic 64 Kbit"), DIP-28 |
| IC3 | TC74HC02 | chip-select NOR logic (A13/A14/A15) |
| IC2 | TC50H4066 | analog switch (filters) |
| IC1 | LA4138 | speaker amp |

- CPU bus: A0-A15, D0-D7, /CE, /OE, /WE, /RFSH. Only A0-A12 go to RAM/ROM address pins; A13/A14/A15 do the selects.
- Supply is ground-referenced odd: CPU sits between VA (5 V) and VDD1 (GND); manual draws Vin vs -5 V VDAC.

## Memory map (p11-12)
| Chip | A15 | A13 | CPU range (A14=0) | Use |
|---|---|---|---|---|
| RAM2 (LSI3) | L | L | 0x0000-0x1FFF | 8 KB, all sampling |
| RAM1 (LSI4) | L | H | 0x2000-0x3FFF | low 2816 B (22,528 bit) = demo / memory-play (sequencer); upper 5376 B (43,008 bit) = sampling |
| ROM (LSI2) | H | – | 0x8000-0xFFFF | 32 KB |
| (unused) | L | – | 0x4000-0x7FFF | nothing decoded (A14=1) |

- Sample = 108,544 bit = **13,568 B** of the 16,384 B RAM, 8-bit @ 9.387 kHz = 1.445 s.
- So sampling already takes 83 % of the RAM. Taking the sequencer area too = +2,816 B = **+0.30 s → 1.75 s max**, and kills memory-play/demo.
- MAME's `sk1.cpp` map (ROM 0x0000, RAM 0x8000) is marked provisional; trust the service manual table over it.

## Where the "OS" lives — the blocker
- Service manual p12: ROM "contains the program for system execution".
- MAME (Vas Crabb, `src/mame/casio/sk1.cpp`): CPU core **unidentified**; real microcode likely **inside the MSM6283** (listed as 0x1000-byte internal ROM, NO_DUMP for SK-1/2/5/10). External ROM is "mostly samples": sample start table at 0x085C, PCM from 0x0B00.
- So 0x0000-0x0B00 of the external ROM (2.8 KB) is the only place code could be, and nobody has shown it is code. If the sampler loop and its end address sit in internal mask ROM, **sample length cannot be changed by any ROM mod**.
- MAME hash to verify a dump: `sk1.lsi2` 0x8000 bytes, CRC32 `d615963c`, SHA1 `0dbf2d1c4c776f1a1c35dd2be4d6ca03882afd4c`.

## DUMPED 2026-10-26
- `rom/sk1_lsi2.bin`, user's own LSI2, read twice identical on the T48 (`minipro -p AM27C256@DIP28 -x -r`, from rosetta_rom/tools/minipro_win). CRC `d615963c` = MAME match.
- **Plain 27C256 read worked**, so the pin-22 OE-active-high worry below was wrong (or the T48 read doesn't care). No adapter needed.
- 0x0000-0x0A62 = small scattered blocks on aligned offsets with FF padding (biggest 832 B at 0x4DC). Looks like parameter / rhythm / demo tables, not CPU code (code would be one dense run). PCM from 0x0B00. → program almost certainly inside the MSM6283; one longer clean sample stays blocked. Not proven until a block is decoded.

## Winbond / EPROM in LSI2 (schematic p28 checked 2026-10-26)
- **HW CHECK 2026-10-26: LSI2 pad 22 = GND via a wire-link jumper** (beeps to IC3 pin 7). Service manual fig 6 (A15 → OE) is wrong for this board. EPROM/Winbond = drop-in, only pin 1 (VPP) → pin 28. Everything below about inverting A15 is obsolete.
- p28: LSI2 pin 1 = NC (no trace), pin 28 = VA, pin 20 /CE = CPU /CE (shared with both RAMs), pin 22 = separate line (A15 per fig 6).
- /CE is shared, so the ROM must be gated by pin 22 = A15 (active-high OE on the mask), else it fights the RAMs on the bus. The T48 plain read still worked, so that's not 100 % settled: scope pin 22 vs /CE in circuit before building.
- W27C257 / W27E257 (32 K) or W27C512 (64 K): pin 22 needs **inverted A15** (all 4 HC02 gates are used → add 74HC04 or 1 NPN inverter). W27C257 pin 1 (VPP) → VCC. W27C512 pin 1 = A15 → switch = 2 preset banks.
- Payoff: 8 preset sounds become your own. PCM area 0x0B00-0x7FFF ≈ 29 KB ≈ 3 s total, start table at 0x085C (not decoded yet).

## Dumping / replacing the ROM
- µPD23C256 pinout = 27C256 except pin 1 (NC on mask ROM, VPP on 27C256). A 27C256 EPROM (or 27C256-pinout flash) drops in with pin 1 tied to VCC.
- **OE looks active-HIGH on this mask ROM**: p11 fig 6 wires CPU A15 to ROM pin 22 (OE), and the ROM is selected when A15=H. A plain 27C256 read (OE low) then gives all FF. Read with pin 22 tied to VCC (adapter socket or bent-out leg). CE pin 20 = active low (table: CE=L).
- Same reason an EPROM swap needs pin 22 driven by inverted A15 (spare gate / 74HC04), or the EPROM never outputs.
- User's board (photos 2026-10-26): M3129-MAIN, LSI2 = NEC D23C256EAC-011 (8712), LSI3/4 = NEC D4168C-20 (200 ns, 8706), IC3 = MN74HC02. All soldered, no sockets. LSI1 (CPU QFP) is on the solder side.

## RAM swaps (p27 pinouts)
- µPD4168C = 6264 pinout except: pin 1 /RFSH (6264: NC → ignored), pin 26 CS active-high (6264: CS2 active-high → same). **6264 should drop in**; refresh cycles just do nothing to SRAM.
- To verify on the bench before trusting it: scope /CE, CS, /WE, /RFSH on a refresh cycle — make sure /WE never goes low during refresh, and the address bus stays stable while /CE is low (4168 latches on /CE fall; SRAM doesn't).

## Routes ranked
1. **Bank-switched SRAM (best real "use more RAM")**: on each RAM socket a DIP-28 → DIP-32 adapter with an AS6C1008 (128 K x8, 5 V, 55 ns, THT). CPU A0-A12 → A0-A12, 4168 CS → CE2 (pin 30), /CE → /CE1 (pin 22), SRAM A13-A16 → shared bank switch (rotary/BCD). = 16 banks, each = full 1.4 s sample + own memory-play song. Optional: CR2032 + diode on SRAM VCC and a pull-down on CE2 → samples survive power-off. Switch banks only when idle.
2. **Sample-clock mod**: slow the 7.24 MHz LC osc while sampling → longer time at lower rate (half clock = ~2.9 s @ ~4.7 kHz), plays back pitched up at normal clock. Classic bend; also detunes everything else.
3. **OS mod for +0.3 s**: needs (a) the sampler code to be in the external ROM, (b) the unknown CPU ISA cracked, (c) memory-play sacrificed. Lowest payoff, highest risk.
4. **Longer single sample into 0x4000-0x7FFF**: hardware side is easy (free address space, extra SRAM decoded on A14), but it needs the same OS change as 3, so same blocker.

## Next steps (not started)
- Dump own LSI2, check against the MAME hash, look at 0x0000-0x0B00 for code-like bytes vs. tables.
- Read the schematic pages (28-30) for the exact NOR wiring if route 1 is built.
