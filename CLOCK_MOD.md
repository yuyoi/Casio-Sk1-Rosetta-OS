# SK-1 clock mod: slower = longer samples, faster = better samples (2026-10-26)

## Stock oscillator (service manual p28, read off the schematic)
- LC oscillator on CPU pins **57 (OSI)** and **58 (OSO)**, about **7.24 MHz**.
- **L1 = L10-495**: the silver can with the screw slot next to IC3.
- **VC1**: trimmer cap (the factory tune).
- **C24 56 pF, C25 150 pF, plus a 100 pF**. C26 (to OSO) and C27 values are unreadable in the scan.
- Everything runs off this clock: sample rate (= clock / 771), key pitch, envelopes, vibrato, rhythm tempo, DRAM refresh.

## The trick that makes "fly" work
Recording and playback both scale with the clock. A sample recorded at clock X and played at clock X stays in tune on the keys. Only the ROM presets and the rhythm tempo shift. So you can run her **permanently faster** for cleaner samples, and `sk1rom.py` can pre-tune the ROM presets to match (resample them by 1/ratio).

| Clock | x | Sample rate | Max sample | Notes |
|---|---|---|---|---|
| 1.81 MHz | ÷4 | 2.35 kHz | 5.8 s | proven playable (Jonas Karlsson octave mod); very lo-fi |
| 3.62 MHz | ÷2 | 4.69 kHz | 2.9 s | lo-fi, clean-ish |
| 7.24 MHz | 1 | 9.39 kHz | 1.45 s | stock |
| 9.05 MHz | 1.25 | 11.7 kHz | 1.16 s | to test |
| 10.9 MHz | 1.5 | 14.1 kHz | 0.96 s | to test, CPU limit unknown |

## Limits
- **Too slow:** the D4168 RAMs are dynamic and need a refresh every 2 ms (manual p11). **Update from the SK-5 timing chart:** a refresh pulse rides on every bus cycle (about 1 µs each), so even ÷10 stays far inside 2 ms. Not a real limit. The 6264 swap is optional.
- **Too fast:**
  - Memory: the stock ROM and RAM are 200 ns parts. The W27C512 is much faster already; 6264-70 SRAMs fix the RAM.
  - CPU: the MSM6283's own max speed is unknown, and nobody has published an SK-1 overclock. Find it by sweeping up until it glitches, then back off 10 %.
- **Extremes:** the LTC1799 SA-39 report saw freezes / dead zones at both ends. A power cycle recovers. Nothing permanent.
- **Input filter:** the sample input RC is tuned for 9.4 kHz. Above about 1.3x, a smaller filter cap lets the extra bandwidth through (check values first).

## Build (all through-hole except the LTC kit)
1. **6264 SRAM x2** in sockets in place of the D4168s.
2. **Clock source, pick one:**
   - **LTC1799 oscillator kit:** one resistor-set chip, 1 kHz-30 MHz, one pot. This is what Spunky Toofers uses on SK-1s/SK-5s. Pot: about 20-25k + 5k in series (the stock 1M gives too narrow a range).
   - **74HC4046 VCO (DIP-16):** pot plus a **CV input**, so the clock can be played from a sequencer or LFO.
3. **Back-to-stock without a separate switch:** keep the stock LC running on one 4069 gate (as in Jonas's mod), then a **74HC157 mux** picks stock vs. variable → pin 57. Drive the mux select from a **pot with a built-in switch**: fully CCW = click = stock clock.
4. **Wiring:**
   - Cut the traces from the tank to pins 57/58 (Jonas cuts both).
   - Mux output → pin 57; leave 58 open.
5. **POWER GOTCHA (negative logic):** the SK-1 labels rails upside down. **Add-on board GND → SK-1 negative rail; add-on +5 V → SK-1 GND** (Jonas Karlsson's README).

## First test, no build
Clip the LTC1799 kit on with test leads, sweep up from stock, and note the frequency where it glitches. That's the real "fly" ceiling.

## Sources
- Jonas Karlsson SK-1 octave mod (4069 + flip-flops + mux, cut traces, negative-logic power): https://github.com/jonaspaulkarlsson/sk-1-octave
- Hackaday write-up: https://hackaday.com/tag/casio-sk-1/
- Circuitbenders SK-1 reclock knob (slow clock = "massively" longer samples, bitcrush): https://circuitbenders.co.uk/synthmod/SK1.html
- getlofi LTC1799 kit (Spunky Toofers SK-1/SK-5, SA-39 pot values, dead zones): https://getlofi.com/?p=1383
