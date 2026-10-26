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

## Space
- ROM is full. Cutting demo song + rhythms only frees ~1.3 KB = 0.14 s of sound.
- Real space = the W27C512's second 32 KB (pin 1 switch) = a full second set.
- Slot sizes are set by the start table + tone records → resizing slots = edit both (needs test burns).
