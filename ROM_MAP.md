# SK-1 ROM map (LSI2, 32 KB) — first pass 2026-10-26

Guesses are marked (?). Nothing decoded bit-exact yet.

| Range | Size | What it is |
|---|---|---|
| 0x0000-0x0017 | 24 B | header / init values (?) |
| 0x0060-0x00A3 | ~70 B | small parameter tables (?) |
| 0x0178-0x02EF | ~380 B | **tone records**: 13 blocks starting `F1 FF` + 2 starting `01 10`, 0x18-0x28 B each. Some hold words inside the PCM area (0x0EB0, 0x1000, 0x0300) → sample start/loop pointers + envelope per preset (?) |
| 0x02F8-0x0372 | 124 B | rising 16-bit curve, 62 steps (envelope or volume curve) |
| 0x037C-0x03EB | 112 B | second rising curve, 56 steps |
| 0x03EC-0x0413 | 40 B | small table (?) |
| 0x047C-0x04D3 | 88 B | `00 0C 10 13 18` x11 = semitone offsets 0/12/16/19/24 → chord voicing for auto-accompaniment, one copy per rhythm (?) |
| 0x04DC-0x081B | 832 B | **rhythm patterns**: 26 blocks of 32 B (16 steps x 2 B: bass/chord step + drum bit mask) (?) |
| 0x085C-0x086D | 18 B | **sample start table**, 8 words LE + 0x7EB2 |
| 0x089C-0x08B9 | 30 B | small table (?) |
| 0x08BC-0x0A62 | 423 B | **demo song** note stream (?) |
| 0x0B00-0x7FFF | 29.4 KB | **8 PCM sounds**, 8-bit unsigned, centre 0x80, 9387 Hz |
| free (FF) | 582 B | scattered gaps, biggest 197 B at 0x00A3 |

## PCM slots (start table order)

| Table # | Start | Size | Length | Guess |
|---|---|---|---|---|
| 0 | 0x2000 | 8192 B | 0.87 s | long melodic preset |
| 1 | 0x6000 | 8192 B (to 0x7FFF; 0x7EB2 = loop point?) | 0.87 s | long melodic preset |
| 2 | 0x1000 | 4096 B | 0.44 s | preset |
| 3 | 0x4000 | 4096 B | 0.44 s | preset |
| 4 | 0x5000 | 4096 B | 0.44 s | preset |
| 5 | 0x0F80 | 128 B | 14 ms | drum (hat?) |
| 6 | 0x0B00 | 768 B | 82 ms | drum (kick?) |
| 7 | 0x0E00 | 384 B | 41 ms | drum (snare?) |

WAVs of each: `rom/wav/` (gitignored, Casio audio).

## WORKS ON HW 2026-10-26: one 3.2 s sound
- `tools/sk1rom.py test-long`: all 8 table entries → 0x0B00, one sound 0x0B00-0x7FFD + FF FF. User heard the full 3 s on the SK-1.
- So a sound ends at FF FF, not at a fixed length; tone records didn't cut it. Envelope/"ring-mod" colour on some presets = tone records, not decoded yet.
- Ready next: `rom/test_count_w27c512.bin` (spoken "one two three") for a cleaner check.

## Pointer scan 2026-10-26
- Searched the whole header for 16-bit pointers (LE/BE, with and without +0x8000) to every block start.
- **Nothing points at the demo tracks (0x08BC / 0x0908 / 0x09E8), rhythms (0x04DC), tone records (0x0178), curves, chord table or the sample table (0x085C).** Those addresses are baked into the MSM6283's internal code. The ROM has no jump/call table we could redirect.
- Demo = 3 tracks: 0x08BC (3-byte events, ends ~0x0905), 0x0908 (packed bytes, ends `F1 00 00` at 0x09E5), 0x09E8 (ends `F1 FF` at 0x0A62).
- **Drums:** 0x085C entries 5-7 (0x0F80, 0x0B00, 0x0E00) are drum sounds, not presets, and 0x089E holds 3 more drum pointers (0x0C00, 0x0D00, 0x0D80). Drum sub-sounds end with FF FF at 0x0B00/0C00/0C80/0D00/0D80/0E00/0F00/0F80. The 5 melodic presets are table entries 0-4.
- So the 8-slot images replace the drums too → rhythms play the new sounds. Keep 0x0B00-0x0FFF + entries 5-7 to keep the drum kit.

## Decode pass 2 (2026-10-26, from spec page p3 + key matrix p7)
- Spec: 5 PCM presets (piano, brass ensemble, trumpet, synth drums, human voice), 3 harmonic-synthesis presets (flute, pipe organ, jazz organ; 9 drawbar harmonics 16'..1', 14 levels each), 13 selectable envelopes, loop set, vibrato, portamento.
- **0x0060-0x0077: 8 x 3-byte groups = one per preset** (00 20 BF, 00 20 AF, 04 00 CF, 08 00 EF, 10 00 BF, 10 00 BF, 10 00 CF, 10 00 EF), then 0x11. Meaning not known yet.
- **0x03EC-0x0412: 13 x 3-byte groups = the 13 envelopes** (00 00 00, 74 00 00, 73 02 00, A4 00 20, ...). The first byte looks like two rate nibbles.
- **0x037C: 56-step curve = 1 - e^(-0.0577 n)** (RC-style envelope curve). **0x02F8: 62-step curve** with the same k, starting at 0.36 (the upper part). Swapping these reshapes every envelope.
- Stock end markers sit on even, 128-aligned addresses. Odd FF FF pairs inside sounds (0x2183) don't stop playback.
- Loop theory: sounds without a marker run to 0x7FFF and the CPU jumps to table entry 8 (stock 0x7EB2). Probe 1 tests this.
- Harmonic levels for flute/organs: not found in the ROM yet (may be inside the CPU).

## Tone records = 16 x 24 B at 0x0178 (decode pass 3)
- Exact 24-byte grid 0x0178 + 0x18*k, k = 0..15, FF-padded → **indexable by one nibble**.
- Two kinds: `F1 FF ...` (13 records) and `01 xx ...` (records 3, 4, 10). Records 11-15 are short (`F1 FF FF 00 ...`), and 12/13/14 differ in one byte only (02 / 08 / 01).
- Most end with `00 00` and a tail `08 10 xx ..` → probably the release part.
- **0x3EC envelopes:** the first byte's nibbles are always 7-B (high) and 3-6 (low) → likely record indexes: envelope = record A + record B.
- **0x060 presets:** the third byte's high nibble is A/B/C/E → likely a record index too.

## Probes
- `probe12_w27c512.bin`, lower half (pin 1 GND) = **probe 1**: entries 0-4 say one..five, drums stock, "five" runs into a saw to 0x7FFF with the loop start at 0x7E00 → hold the key: endless buzz = loops work.
- Upper half (pin 1 5V) = **probe 2** = probe 1 plus:
  - 0x060: all 8 preset groups = group 0. Do all presets now behave alike (envelope / vibrato / octave)?
  - 0x3EC: all 13 envelopes = envelope 4. Sample something, then step Envelope Select: does every setting sound the same?
- `probe34_w27c512.bin`, lower half = **probe 3**: probe 1 with all 16 tone records = record 3. Does everything (presets, organs, sample envelopes) get the same envelope?
- Upper half = **probe 4**: probe 1 with both envelope curves made linear. Do fades sound more even / less "plucky"?

## Space
- ROM is full. Cutting demo song + rhythms only frees ~1.3 KB = 0.14 s of sound.
- Real space = the W27C512's second 32 KB (pin 1 switch) = a full second set.
- Slot sizes are set by the start table + tone records → resizing slots = edit both (needs test burns).
