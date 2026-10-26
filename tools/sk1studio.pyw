"""Rosetta OS // SK-1 Studio: put your own sounds into the Casio SK-1's preset ROM.

Five preset slots (the SK-1's 5 PCM presets), each fed from a WAV, a Roland S-760/S-770 sample CD or an Akai
S1000/S3000 sample CD.
Sounds are pitched to the stock sound of their slot, so they play in tune on the same keys; "own" keeps the
speed. The stock drum kit (0x0B00-0x0FFF) is always kept so the rhythms still work. One slot may loop: it goes
last, runs to the end of the ROM and gets a crossfaded loop that table entry 8 points at.
Builds a 64 KB image for a W27C512 (burned with minipro on a T48) or 512 KB for an SST39SF040 (Hex Wizard).

Run: pythonw sk1studio.pyw          (needs numpy, scipy; your own LSI2 dump as the base ROM)
"""
import json
import os
import queue
import re
import struct
import subprocess
import sys
import tempfile
import threading
import wave

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from sk1rom import RATE, TABLE, ROM_SIZE, END, fit, load_wav, to_pcm  # noqa: E402
import roland_presets as rp  # noqa: E402
from roland import Disc  # noqa: E402
import akai  # noqa: E402

SOUND_START = 0x1000            # after the stock drum kit
SILENT = 0x0FFE                 # a stock FF FF marker: an empty slot plays nothing
# table entry, pitch of the stock sound in that slot (Hz), what it held on the stock ROM (best guess)
SLOTS = [(0, 447.0, "piano?"), (1, 224.0, "brass ens.?"), (2, 447.0, "trumpet?"),
         (3, 144.0, "synth drums?"), (4, 447.0, "voice?")]
NOTES = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
SETTINGS = os.path.join(os.path.expanduser("~"), ".sk1studio.json")
BG, PANEL, BLUE, GREEN, TXT, DIM = "#05080c", "#0d141c", "#2ec4ff", "#39ff88", "#cfeee0", "#4f6b7a"


def parse_note(s):
    """'A4' / 'C#3' / 'Bb2' / '69' -> MIDI note; '' or 'own' -> None (keep the sound's own speed)"""
    s = (s or "").strip()
    if not s or s.lower() == "own":
        return None
    if s.isdigit():
        return int(s)
    m = re.fullmatch(r"([A-Ga-g])([#b_]?)(-?\d)", s)
    if not m:
        raise ValueError(f"note '{s}' (use A4, C#3, Bb2, a MIDI number or own)")
    n = NOTES[m.group(1).upper()] + {"#": 1, "b": -1}.get(m.group(2), 0)
    return 12 * (int(m.group(3)) + 1) + n


def note_in_name(name):
    """the note many sample names carry ('VOX:TrnChrA_4', 'POLYSYNTC3'), or ''"""
    m = re.search(r"([A-G])([#_]?)(\d)(?!.*[A-G][#_]?\d)", name)
    return f"{m.group(1)}{'#' if m.group(2) == '#' else ''}{m.group(3)}" if m else ""


def disc_list(kind, path):
    """every sample on a Roland or Akai CD image: [(label, key)]; key finds it again in load_source"""
    if kind == "roland":
        d = Disc(path)
        try:
            return [(n, n) for _, n in d.entries(0x44)]
        finally:
            d.close()
    img = akai.Image(path)
    try:
        return [(f"{v.name} / {n}", f"{v.name}\t{n}") for v in img.volumes for n in v.samples]
    finally:
        img.close()


def load_akai(path, key):
    vol, name = key.split("\t")
    img = akai.Image(path)
    try:
        for v in img.volumes:
            if v.name == vol and name in v.samples:
                s = v.sample(name)
                return s["pcm"].astype(np.float64), s["rate"]
    finally:
        img.close()
    raise ValueError(f"{name} not found on {os.path.basename(path)}")


def load_source(slot, roland_dir=None):
    """slot dict -> float audio at RATE, pitched for its table entry"""
    note, hz = parse_note(slot.get("note")), dict((e, h) for e, h, _ in SLOTS)[slot["entry"]]
    if slot["src"] in ("roland", "akai"):
        if slot["src"] == "roland":
            x, rate = rp.load_roland(Disc, os.path.dirname(slot["path"]), os.path.basename(slot["path"]),
                                     slot["name"])
        else:
            x, rate = load_akai(slot["path"], slot["key"])
        y = rp.to_slot(x, rate, note, hz if note is not None else None)
    else:
        y = load_wav(slot["path"])
        if note is not None:
            y = rp.to_slot(y, RATE, note, hz)
    return y[::-1].copy() if slot.get("reverse") else y


def capacity(n_filled, long_mode):
    """bytes the looping slot can use: everything after the other slots' shares"""
    room = ROM_SIZE - SOUND_START
    if long_mode or n_filled <= 1:
        return room
    share = room // n_filled
    share -= share & 1
    return room - share * (n_filled - 1)


def loop_points(slot, y, n):
    """(end, start, xfade) in SK-1 samples for a looping slot: the user's points, clamped, or a default loop
    (24 periods of the slot pitch for pitched sounds, the last quarter otherwise)"""
    end = min(slot.get("loop_end") or n, len(y), n)
    end -= end & 1
    if slot.get("loop_start") is not None:
        start = slot["loop_start"]
    elif parse_note(slot.get("note")) is not None:
        start = end - int(round(24 * RATE / dict((e, h) for e, h, _ in SLOTS)[slot["entry"]]))
    else:
        start = end - end // 4
    start = max(1, min(start, end - 8))
    xf = slot.get("xfade")
    xf = (end - start) // 2 if xf is None else xf
    return end, start, max(0, min(xf, start, end - start))


def make_loop(y, end, start, xf):
    """y[:end] with its last xf samples crossfaded into the audio just before the loop start, so the jump from
    end back to start is seamless"""
    seg = y[:end].copy()
    if xf:
        w = np.linspace(0, 1, xf)
        seg[end - xf:end] = seg[end - xf:end] * (1 - w) + y[start - xf:start] * w
    return seg


def build_image(base, slots, roland_dir, long_mode=False, log=print):
    """-> 32 KB ROM image with the filled slots packed after the drum kit"""
    rom = bytearray(base[:ROM_SIZE])
    rom[SOUND_START:] = b"\x80" * (ROM_SIZE - SOUND_START)
    filled = [s for s in slots if s.get("src")]
    if not filled:
        raise ValueError("no sounds loaded")
    if long_mode:
        filled = filled[:1]
    looped = [s for s in filled if s.get("loop")][:1]
    order = [s for s in filled if s not in looped] + looped
    room = ROM_SIZE - SOUND_START
    share = room // len(order)
    share -= share & 1                           # even slot starts keep every FF FF marker on an even address
    ptr = {e: SILENT for e, _, _ in SLOTS}
    a = SOUND_START
    for i, s in enumerate(order):
        log(f"  slot {s['entry'] + 1}: {s['name']}")
        y = load_source(s, roland_dir)
        last = i == len(order) - 1
        if s in looped:
            # the CPU jumps from 0x7FFF back to table entry 8, so the sound is placed to end exactly there
            end, ls, xf = loop_points(s, y, ROM_SIZE - a)
            start = ROM_SIZE - end
            rom[start:] = to_pcm(0.95 * make_loop(y, end, ls, xf))
            struct.pack_into("<H", rom, TABLE + 16, start + ls)
            ptr[s["entry"]] = start
            log(f"    0x{start:04X}, {end / RATE:.2f} s, loops 0x{start + ls:04X}-0x7FFF "
                f"({(end - ls) / RATE * 1000:.0f} ms, xfade {xf / RATE * 1000:.0f} ms)")
            a += share
            continue
        else:
            size = (ROM_SIZE - a if last else share) - len(END)
            size -= size & 1                     # markers sit on even addresses, like every stock one
            pcm = to_pcm(0.95 * fit(y, size))
            rom[a:a + len(pcm)] = pcm
            rom[a + len(pcm):a + len(pcm) + 2] = END
            log(f"    0x{a:04X}, {len(pcm) / RATE:.2f} s")
        ptr[s["entry"]] = a
        a += share
    if long_mode:
        ptr = {e: ptr[filled[0]["entry"]] for e in ptr}
    for e, p in ptr.items():
        struct.pack_into("<H", rom, TABLE + 2 * e, p)
    assert len(rom) == ROM_SIZE
    return bytes(rom)


def sound_area_wav(rom, path):
    """the sound area as an SK-1-rate WAV, markers turned into short gaps"""
    pcm = rom[SOUND_START:ROM_SIZE].replace(END, b"\x80" * 3000)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(1)
        w.setframerate(RATE)
        w.writeframes(pcm)


def gui():
    import tkinter as tk
    from tkinter import filedialog, messagebox, scrolledtext
    try:
        __import__("ctypes").windll.shell32.SetCurrentProcessExplicitAppUserModelID("Rosetta.SK1Studio")
        __import__("ctypes").windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    cfg = {"base": "", "minipro": "", "roland": "", "akai": "", "wavs": ""}
    try:
        cfg.update(json.load(open(SETTINGS, encoding="utf-8")))
    except (OSError, ValueError):
        pass
    slots = [{"entry": e} for e, _, _ in SLOTS]

    root = tk.Tk()
    root.title("Rosetta OS - SK-1 Studio")
    root.configure(bg=BG)                      # no fixed geometry: it sizes itself to the display scaling
    assets = os.path.join(getattr(sys, "_MEIPASS", os.path.join(HERE, "..")), "assets")
    try:
        root.iconbitmap(default=os.path.join(assets, "rosetta_sk1.ico"))
    except tk.TclError:
        pass
    lab = dict(bg=BG, fg=BLUE, font=("Consolas", 10))
    ent = dict(bg=PANEL, fg=TXT, insertbackground=GREEN, relief="flat", font=("Consolas", 10), highlightthickness=1,
               highlightbackground="#1b2a36", highlightcolor=BLUE)
    btn_s = dict(bg=PANEL, fg=GREEN, activebackground=BLUE, activeforeground=BG, relief="flat",
                 font=("Consolas", 10, "bold"))
    chk = dict(bg=BG, fg=BLUE, selectcolor=PANEL, activebackground=BG, activeforeground=GREEN, font=("Consolas", 10))

    head = tk.Frame(root, bg=BG)
    head.pack(fill="x", padx=10, pady=(10, 4))
    try:
        icon = tk.PhotoImage(file=os.path.join(assets, "hexgirl_icon.png")).subsample(4)
        tk.Label(head, image=icon, bg=BG).pack(side="left")
        root._icon = icon
    except tk.TclError:
        pass
    tk.Label(head, text="ROSETTA OS  //  SK-1 STUDIO", bg=BG, fg=GREEN, font=("Consolas", 15, "bold")).pack(
        side="left", padx=10)

    paths = tk.Frame(root, bg=BG)
    paths.pack(fill="x", padx=10)
    v_base, v_mini, v_roland, v_akai = (tk.StringVar(value=cfg[k]) for k in ("base", "minipro", "roland", "akai"))

    def path_row(r, label, var, pick):
        tk.Label(paths, text=label, anchor="w", **lab).grid(row=r, column=0, sticky="w", pady=3)
        tk.Entry(paths, textvariable=var, **ent).grid(row=r, column=1, sticky="we", padx=4, ipady=2)
        tk.Button(paths, text="...", command=pick, width=3, **btn_s).grid(row=r, column=2)
    path_row(0, "Base ROM (your LSI2 dump)", v_base, lambda: v_base.set(filedialog.askopenfilename(
        title="Your own SK-1 ROM dump (32 KB)", filetypes=[("ROM", "*.bin"), ("all", "*.*")]) or v_base.get()))
    path_row(1, "Roland CD folder", v_roland, lambda: v_roland.set(filedialog.askdirectory() or v_roland.get()))
    path_row(2, "Akai CD folder", v_akai, lambda: v_akai.set(filedialog.askdirectory() or v_akai.get()))
    path_row(3, "minipro.exe (T48)", v_mini, lambda: v_mini.set(filedialog.askopenfilename(
        title="minipro.exe", filetypes=[("minipro", "minipro*.exe"), ("all", "*.*")]) or v_mini.get()))
    paths.columnconfigure(1, weight=1)

    grid = tk.Frame(root, bg=BG)
    grid.pack(fill="x", padx=10, pady=8)
    for c, t in enumerate(("slot", "stock", "sound", "note", "rev", "loop", "")):
        tk.Label(grid, text=t, bg=BG, fg=DIM, font=("Consolas", 9)).grid(row=0, column=c, sticky="w", padx=3)
    v_name, v_note, v_rev = [], [], []
    v_loop = tk.IntVar(value=-1)

    def set_slot(i, **kw):
        if "path" in kw:                          # new sound: its old loop points mean nothing
            for k in ("loop_start", "loop_end", "xfade"):
                slots[i].pop(k, None)
        slots[i].update(kw)
        v_name[i].set(slots[i].get("name", "(empty)"))
        v_note[i].set(slots[i].get("note", "") or "own")

    def pick_wav(i):
        p = filedialog.askopenfilename(title="WAV for slot %d" % (i + 1), initialdir=cfg.get("wavs") or None,
                                       filetypes=[("WAV", "*.wav"), ("all", "*.*")])
        if p:
            cfg["wavs"] = os.path.dirname(p)
            set_slot(i, src="wav", path=p, name=os.path.basename(p), note=note_in_name(os.path.basename(p)))

    def clear(i):
        slots[i] = {"entry": SLOTS[i][0]}
        v_rev[i].set(False)
        set_slot(i)

    for i, (e, hz, stock) in enumerate(SLOTS):
        r = i + 1
        v_name.append(tk.StringVar(value="(empty)"))
        v_note.append(tk.StringVar(value="own"))
        v_rev.append(tk.BooleanVar(value=False))
        tk.Label(grid, text=f"{i + 1}", **lab).grid(row=r, column=0, sticky="w", padx=3)
        tk.Label(grid, text=stock, bg=BG, fg=DIM, font=("Consolas", 9)).grid(row=r, column=1, sticky="w", padx=3)
        tk.Label(grid, textvariable=v_name[i], width=30, anchor="w", bg=PANEL, fg=TXT,
                 font=("Consolas", 10)).grid(row=r, column=2, sticky="we", padx=3, pady=2, ipady=2)
        tk.Entry(grid, textvariable=v_note[i], width=5, **ent).grid(row=r, column=3, padx=3, ipady=2)
        tk.Checkbutton(grid, variable=v_rev[i], **chk).grid(row=r, column=4)
        tk.Radiobutton(grid, variable=v_loop, value=i, **chk).grid(row=r, column=5)
        bf = tk.Frame(grid, bg=BG)
        bf.grid(row=r, column=6, sticky="w")
        for t, f in (("WAV", pick_wav), ("ROLAND", lambda i: cd_picker(i, "roland")),
                     ("AKAI", lambda i: cd_picker(i, "akai")), ("PLAY", lambda i: preview(i)), ("X", clear)):
            tk.Button(bf, text=t, command=lambda f=f, i=i: f(i), **dict(btn_s, font=("Consolas", 9, "bold"))).pack(
                side="left", padx=1)
    lf = tk.Frame(grid, bg=BG)
    lf.grid(row=6, column=5, columnspan=2, sticky="w")
    tk.Radiobutton(lf, text="no loop", variable=v_loop, value=-1, **chk).pack(side="left")
    tk.Button(lf, text="EDIT LOOP", command=lambda: loop_editor(), **dict(btn_s, font=("Consolas", 9, "bold"))).pack(
        side="left", padx=8)
    grid.columnconfigure(2, weight=1)

    opt = tk.Frame(root, bg=BG)
    opt.pack(fill="x", padx=6)
    v_long = tk.BooleanVar(value=False)
    tk.Radiobutton(opt, text="5 presets", variable=v_long, value=False, **chk).pack(side="left")
    tk.Radiobutton(opt, text="1 long sound on every preset (slot 1, ~2.9 s)", variable=v_long, value=True,
                   **chk).pack(side="left")
    tk.Label(root, text="Pitched slots play in tune on the same keys as the stock sound. Drum kit is kept. "
             "Your ROM dump is not included.", bg=BG, fg=DIM, font=("Consolas", 9)).pack(anchor="w", padx=10)

    acts = tk.Frame(root, bg=BG)
    acts.pack(pady=6)
    logw = scrolledtext.ScrolledText(root, height=8, width=90, bg=PANEL, fg=GREEN, insertbackground=GREEN, relief="flat",
                                     font=("Consolas", 9), highlightthickness=1, highlightbackground="#1b2a36")
    logw.pack(fill="both", expand=True, padx=10, pady=(0, 10))
    q = queue.Queue()

    def log(s):
        q.put(s)

    def pump():
        while not q.empty():
            s = q.get()
            if callable(s):
                s()
                continue
            logw.insert("end", s + "\n")
            logw.see("end")
        root.after(100, pump)

    def current():
        """slot dicts with the GUI's note / reverse / loop applied"""
        out = []
        for i, s in enumerate(slots):
            s = dict(s, reverse=v_rev[i].get(), loop=v_loop.get() == i)
            if s.get("src"):
                parse_note(v_note[i].get())  # raises on a bad note before any work starts
                s["note"] = v_note[i].get()
            out.append(s)
        return out

    def base_rom():
        p = v_base.get()
        if not p or not os.path.exists(p):
            raise ValueError("pick your SK-1 ROM dump first (32 KB LSI2 read)")
        return open(p, "rb").read()

    def save_cfg():
        cfg.update(base=v_base.get(), minipro=v_mini.get(), roland=v_roland.get(), akai=v_akai.get())
        try:
            json.dump(cfg, open(SETTINGS, "w", encoding="utf-8"), indent=1)
        except OSError:
            pass

    def worker(job):
        def run():
            try:
                job()
            except Exception as ex:  # shown in the log, the GUI stays up
                log(f"ERROR: {ex}")
        save_cfg()
        threading.Thread(target=run, daemon=True).start()

    def play(path):
        import winsound
        winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)

    def preview(i):
        try:
            s = current()[i]
        except ValueError as ex:
            log(f"ERROR: {ex}")
            return
        if not s.get("src"):
            log(f"slot {i + 1} is empty")
            return
        n = (ROM_SIZE - SOUND_START) // max(1, sum(1 for x in slots if x.get("src")))  # Tk is read here, not in the thread

        def job():
            y = load_source(s)
            path = os.path.join(tempfile.gettempdir(), "sk1studio_slot.wav")
            with wave.open(path, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(1)
                w.setframerate(RATE)
                w.writeframes(to_pcm(0.95 * fit(y, n)))
            log(f"playing slot {i + 1} as the SK-1 hears it ({min(len(y), n) / RATE:.2f} s)")
            play(path)
        worker(job)

    def build(kind):
        try:
            sl, base = current(), base_rom()
        except ValueError as ex:
            log(f"ERROR: {ex}")
            return
        if kind != "preview":
            ext = ".sst.bin" if kind == "sst" else ".bin"
            out = filedialog.asksaveasfilename(defaultextension=ext, initialfile="sk1_custom" + ext,
                                               filetypes=[("ROM image", "*.bin")])
            if not out:
                return
        mp, long_mode = v_mini.get(), v_long.get()  # Tk is read here, not in the thread
        if kind == "burn" and not mp:
            log("ERROR: set minipro.exe first")
            return

        def job():
            log("building...")
            rom = build_image(base, sl, None, long_mode, log)
            if kind == "preview":
                path = os.path.join(tempfile.gettempdir(), "sk1studio_all.wav")
                sound_area_wav(rom, path)
                log("playing every slot back to back")
                play(path)
                return
            copies = 16 if kind == "sst" else 2
            open(out, "wb").write(rom * copies)
            log(f"wrote {out} ({len(rom) * copies // 1024} KB)")
            if kind == "burn":
                log("burning W27C512 on the T48...")
                r = subprocess.run([mp, "-p", "W27C512@DIP28", "-w", out], cwd=os.path.dirname(mp),
                                   capture_output=True, text=True, creationflags=0x08000000)
                for line in (r.stdout + r.stderr).splitlines():
                    if any(k in line for k in ("Chip ID", "Verification", "rror", "mismatch", "not found")):
                        log("  " + line.strip())
                log("done: put the chip back in the SK-1" if r.returncode == 0 else "burn FAILED")
        worker(job)

    for t, k in (("PREVIEW ALL", "preview"), ("SAVE W27C512 .BIN", "w27"), ("SAVE SST .BIN (HEX WIZARD)", "sst"),
                 ("BURN W27C512", "burn")):
        b = tk.Button(acts, text=t, command=lambda k=k: build(k), height=2, **btn_s)
        if k == "burn":
            b.config(fg=BG, bg=GREEN, activebackground=BLUE)
        b.pack(side="left", padx=4)

    def cd_picker(i, kind):
        folder = (v_roland if kind == "roland" else v_akai).get()
        if not folder or not os.path.isdir(folder):
            log(f"ERROR: set the {kind.capitalize()} CD folder first")
            return
        isos = sorted(f for f in os.listdir(folder) if f.lower().endswith((".iso", ".img", ".bin", ".nrg")))
        w = tk.Toplevel(root)
        w.title(f"{kind.capitalize()} CD sample for slot {i + 1}")
        w.geometry("760x480")
        w.configure(bg=BG)
        lb_kw = dict(bg=PANEL, fg=TXT, selectbackground=BLUE, selectforeground=BG, relief="flat",
                     font=("Consolas", 10), highlightthickness=0, exportselection=False)
        left = tk.Listbox(w, width=34, **lb_kw)
        left.pack(side="left", fill="y", padx=(10, 4), pady=10)
        right = tk.Frame(w, bg=BG)
        right.pack(side="left", fill="both", expand=True, padx=(4, 10), pady=10)
        v_f = tk.StringVar()
        tk.Entry(right, textvariable=v_f, **ent).pack(fill="x", ipady=2)
        names = tk.Listbox(right, **lb_kw)
        names.pack(fill="both", expand=True, pady=6)
        state = {"iso": None, "all": []}
        for f in isos:
            left.insert("end", f)

        def open_iso(_=None):
            sel = left.curselection()
            if not sel:
                return
            state["iso"] = os.path.join(folder, isos[sel[0]])
            try:
                state["all"] = disc_list(kind, state["iso"])
            except (OSError, ValueError, struct.error) as ex:
                state["all"] = []
                log(f"ERROR: {isos[sel[0]]}: {ex}")
            refilter()

        def refilter(*_):
            f = v_f.get().lower()
            state["shown"] = [(lab_, key) for lab_, key in state["all"] if f in lab_.lower()]
            names.delete(0, "end")
            for lab_, _ in state["shown"]:
                names.insert("end", lab_)

        def choose(_=None):
            sel = names.curselection()
            if not sel or not state["iso"]:
                return
            lab_, key = state["shown"][sel[0]]
            n = lab_.split(" / ")[-1]
            set_slot(i, src=kind, path=state["iso"], name=n, key=key, note=note_in_name(n))
            w.destroy()
        left.bind("<<ListboxSelect>>", open_iso)
        v_f.trace_add("write", refilter)
        names.bind("<Double-Button-1>", choose)
        tk.Button(right, text="USE THIS SAMPLE", command=choose, **btn_s).pack(fill="x")

    def loop_editor():
        i = v_loop.get()
        if i < 0:
            log("pick the loop slot first (loop column)")
            return
        try:
            s = current()[i]
        except ValueError as ex:
            log(f"ERROR: {ex}")
            return
        if not s.get("src"):
            log(f"slot {i + 1} is empty")
            return
        long_mode = v_long.get()
        n = capacity(1 if long_mode else sum(1 for x in slots if x.get("src")), long_mode)
        log(f"loading slot {i + 1} for the loop editor...")

        def job():
            y = load_source(s)
            q.put(lambda: open_loop_window(i, s, y, n))
        worker(job)

    def open_loop_window(i, s, y, n):
        end, start, xf = loop_points(s, y, n)
        st = {"end": end, "start": start, "drag": None}
        total = min(len(y), n)                    # the editor shows what fits in the slot
        w = tk.Toplevel(root)
        w.title(f"Loop: slot {i + 1}  {s['name']}")
        w.configure(bg=BG)
        W, H = 1100, 240
        cv = tk.Canvas(w, width=W, height=H, bg=PANEL, highlightthickness=0)
        cv.pack(padx=10, pady=(10, 4))
        v_info = tk.StringVar()
        tk.Label(w, textvariable=v_info, bg=BG, fg=TXT, font=("Consolas", 10)).pack(anchor="w", padx=10)
        v_xf = tk.DoubleVar(value=round(xf / RATE * 1000))
        row_ = tk.Frame(w, bg=BG)
        row_.pack(fill="x", padx=10, pady=6)
        tk.Label(row_, text="crossfade ms", **lab).pack(side="left")
        tk.Scale(row_, variable=v_xf, from_=0, to=300, orient="horizontal", length=300, bg=BG, fg=GREEN,
                 troughcolor=PANEL, highlightthickness=0, command=lambda _: draw()).pack(side="left", padx=6)

        cols = np.linspace(0, total, W + 1).astype(int)
        lo = [float(y[a:b].min()) if b > a else 0.0 for a, b in zip(cols[:-1], cols[1:])]
        hi = [float(y[a:b].max()) if b > a else 0.0 for a, b in zip(cols[:-1], cols[1:])]

        def x_of(k):
            return k * W / total

        def k_of(x):
            return int(max(0, min(total, x * total / W)))

        def xfade():
            return min(int(v_xf.get() * RATE / 1000), st["start"], st["end"] - st["start"])

        def draw():
            cv.delete("all")
            cv.create_rectangle(x_of(st["start"]), 0, x_of(st["end"]), H, fill="#123024", width=0)
            xs = x_of(st["end"] - xfade())
            cv.create_rectangle(xs, 0, x_of(st["end"]), H, fill="#173a52", width=0)
            xe = x_of(st["end"])
            for x in range(W):                    # past END is cut off in the ROM: drawn dim
                cv.create_line(x, H / 2 - hi[x] * H * 0.45, x, H / 2 - lo[x] * H * 0.45 + 1,
                               fill=GREEN if x <= xe else DIM)
            for k, col, t in ((st["start"], GREEN, "LOOP START"), (st["end"], BLUE, "END")):
                cv.create_line(x_of(k), 0, x_of(k), H, fill=col, width=2)
                cv.create_text(x_of(k) + (4 if t != "END" else -4), 10, text=t, fill=col,
                               anchor="w" if t != "END" else "e", font=("Consolas", 9, "bold"))
            ln = st["end"] - st["start"]
            v_info.set(f"start {st['start'] / RATE:.3f} s   end {st['end'] / RATE:.3f} s   loop {ln / RATE * 1000:.0f} ms"
                       f" ({ln} samples)   slot holds {n / RATE:.2f} s")

        def press(e):
            k = k_of(e.x)
            st["drag"] = "start" if abs(k - st["start"]) < abs(k - st["end"]) else "end"
            motion(e)

        def motion(e):
            k = k_of(e.x)
            if st["drag"] == "start":
                st["start"] = max(1, min(k, st["end"] - 8))
            elif st["drag"] == "end":
                st["end"] = max(st["start"] + 8, min(k, total))
            draw()

        def snap():
            """both points onto rising zero crossings: the cheapest way to a click-free loop"""
            def near(k):
                best = k
                for d in range(0, 400):
                    for c in (k - d, k + d):
                        if 1 <= c < len(y) and y[c - 1] < 0 <= y[c]:
                            return c
                return best
            st["start"] = near(st["start"])
            st["end"] = min(near(st["end"]), total)
            draw()

        def audition():
            end_, start_, xf_ = st["end"] - (st["end"] & 1), st["start"], xfade()
            seg = make_loop(y, end_, start_, xf_)
            reps = max(1, int(3.0 * RATE / max(1, end_ - start_)))
            out = np.concatenate([seg] + [seg[start_:end_]] * reps)
            path = os.path.join(tempfile.gettempdir(), "sk1studio_loop.wav")
            with wave.open(path, "wb") as f:
                f.setnchannels(1)
                f.setsampwidth(1)
                f.setframerate(RATE)
                f.writeframes(to_pcm(0.95 * out))
            play(path)

        def reset():
            st["end"], st["start"], x = loop_points({k: v for k, v in s.items()
                                                     if k not in ("loop_start", "loop_end", "xfade")}, y, n)
            v_xf.set(round(x / RATE * 1000))
            draw()

        def ok():
            slots[i].update(loop_start=st["start"], loop_end=st["end"], xfade=xfade())
            log(f"slot {i + 1} loop: {st['start'] / RATE:.3f}-{st['end'] / RATE:.3f} s, "
                f"crossfade {xfade() / RATE * 1000:.0f} ms")
            w.destroy()
        cv.bind("<Button-1>", press)
        cv.bind("<B1-Motion>", motion)
        cv.bind("<ButtonRelease-1>", lambda e: st.update(drag=None))
        bf = tk.Frame(w, bg=BG)
        bf.pack(pady=(0, 10))
        for t, f in (("SNAP TO ZERO", snap), ("PLAY LOOP", audition), ("RESET", reset), ("OK", ok)):
            b = tk.Button(bf, text=t, command=f, height=2, **btn_s)
            if t == "OK":
                b.config(fg=BG, bg=GREEN, activebackground=BLUE)
            b.pack(side="left", padx=4)
        w._loop = dict(st=st, snap=snap, audition=audition, ok=ok, draw=draw, v_xf=v_xf)  # for scripted tests
        draw()

    root.protocol("WM_DELETE_WINDOW", lambda: (save_cfg(), root.destroy()))
    root._studio = dict(slots=slots, set_slot=set_slot, v_base=v_base, v_roland=v_roland, v_akai=v_akai, v_loop=v_loop,
                        v_note=v_note, build=build, log=log)  # handles for scripted click tests
    pump()
    return root


if __name__ == "__main__":
    gui().mainloop()
