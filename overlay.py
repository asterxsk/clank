#!/usr/bin/env python3
"""Overlay GUI: small sharp agent cursor + short pill message underneath.

Same blue for cursor and pill. Follows overlay-state.json {x,y,pill} in the OS temp dir.
Heartbeat: touches overlay-state.json.alive every tick so clank.py knows it runs.
Cross-platform: transparency degrades gracefully where Tk lacks -transparentcolor.
"""
import json
import math
import os
import tempfile
import time
import tkinter as tk
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
try:
    _STATEDIR = Path(tempfile.gettempdir()) / "clank"
    _STATEDIR.mkdir(exist_ok=True)
except OSError:
    _STATEDIR = Path(HERE)
STATE = os.path.join(str(_STATEDIR), "overlay-state.json")
ALIVE = STATE + ".alive"
COLOR = "#2563eb"  # always blue — pill uses same color
SIZE = 20  # small sharp cursor, px
CY = 34  # cursor sits lower so pill rides above it
PX = 46  # side padding so tilt + 80px ripple never clip at window edge
FONTS = ("Segoe UI", "SF Pro Text", "Helvetica Neue", "DejaVu Sans")

try:
    _other_alive = time.time() - os.path.getmtime(ALIVE) < 5
except OSError:
    _other_alive = False
if _other_alive:
    raise SystemExit(0)

root = tk.Tk()
root.overrideredirect(True)
root.attributes("-topmost", True)
try:
    root.attributes("-transparentcolor", "magenta")
    root.config(bg="magenta")
    CANVAS_BG = "magenta"
except tk.TclError:  # macOS / some Linux Tk builds lack -transparentcolor
    CANVAS_BG = root.cget("bg")
root.geometry("320x380+100+100")

canvas = tk.Canvas(root, width=320, height=380, bg=CANVAS_BG, highlightthickness=0)
canvas.pack()

import tkinter.font as _tkfont
_avail = set(_tkfont.families())
PILL_FONT = _tkfont.Font(family=next((f for f in FONTS if f in _avail), "TkDefaultFont"),
                         size=9, weight="bold")

pill_until = [0]
last_pill = [""]
last_click = [0]
shown = [200.0, 200.0]  # eased display position — glides toward target

# simple triangle cursor, local coords around tip pivot
TRI = [(3, 2), (3, 23), (22, 12)]
SPIN = [0.0]  # spinner angle while busy
IDLE_S = 60  # quit after this long with no state writes
last_mtime = [0.0]
last_active = [time.time()]


def read_state():
    try:
        return json.loads(Path(STATE).read_text())
    except (OSError, ValueError):
        return {}


def tick():
    st = read_state()
    try:
        mt = os.path.getmtime(STATE)
    except OSError:
        mt = 0.0
    if mt != last_mtime[0]:
        last_mtime[0] = mt
        last_active[0] = time.time()
    if time.time() - last_active[0] > IDLE_S:
        try:
            os.remove(ALIVE)
        except OSError:
            pass
        root.destroy()
        return
    tx, ty = int(st.get("x", 200)), int(st.get("y", 200))
    # smooth glide: ease 25% of remaining gap per frame
    shown[0] += (tx - shown[0]) * 0.25
    shown[1] += (ty - shown[1]) * 0.25
    if abs(tx - shown[0]) < 0.5:
        shown[0] = float(tx)
    if abs(ty - shown[1]) < 0.5:
        shown[1] = float(ty)
    root.geometry(f"+{int(shown[0]) + 14 - PX}+{int(shown[1]) + 16}")
    try:
        Path(ALIVE).write_text("1")
    except OSError:
        pass
    canvas.delete("all")
    now = time.time() * 1000
    # click: cursor tilts forward + one small blue ripple fading out (max 80px)
    cat = int(st.get("click_at", 0))
    if cat and cat != last_click[0]:
        last_click[0] = cat
    age = now - last_click[0] if last_click[0] else 9999
    clicking = age < 600
    if clicking:
        t = age / 600.0
        r = 6 + t * 34  # 12px → 80px diameter
        canvas.create_oval(8 + PX - r, CY + 8 - r, 8 + PX + r, CY + 8 + r,
                           outline=COLOR, width=max(1, int(3 * (1 - t) + 1)))
    # busy (model thinking/responding): loading spinner instead of cursor
    if st.get("busy"):
        SPIN[0] = (SPIN[0] + 12) % 360
        canvas.create_arc(PX - 2, CY - 2, PX + 24, CY + 24,
                          start=SPIN[0], extent=300,
                          outline=COLOR, width=4, style="arc")
        canvas.create_oval(PX + 9, CY + 9, PX + 13, CY + 13, fill=COLOR, outline=COLOR)
    # simple triangle cursor, upright; quick forward tilt while clicking
    else:
        th = math.radians(18 * math.sin(math.pi * min(1.0, age / 600.0))) if clicking else 0.0
        px, py = TRI[0]
        pts = []
        for (qx, qy) in TRI:
            dx, dy = qx - px, (qy + CY) - (py + CY)
            pts += [px + PX + dx * math.cos(th) - dy * math.sin(th),
                    py + CY + dx * math.sin(th) + dy * math.cos(th)]
        canvas.create_polygon(*pts, fill=COLOR, outline=COLOR, width=2,
                              joinstyle="round")
    pill = str(st.get("pill", ""))
    ms = int(st.get("pill_ms", 2500))
    now = time.time() * 1000
    if pill and pill != last_pill[0]:
        last_pill[0] = pill
        pill_until[0] = now + ms
    # typewriter: reveal typed text letter by letter at 100wpm (~8.3 chars/sec), hold 2s
    tw = str(st.get("type_text", ""))
    tat = int(st.get("type_at", 0))
    if tw and tat:
        n = int((now - tat) / 120)
        if 0 <= n <= len(tw) + 16 and now - tat < len(tw) * 120 + 2000:
            shown_tw = tw[:max(0, min(len(tw), n))] + "▍"
            pill, pill_until[0] = shown_tw, now + 100000
            last_pill[0] = shown_tw
    if pill and now < pill_until[0]:
        fnt = PILL_FONT
        MAXW, MAXH, LH = 200, 300, 20
        # word-wrap to MAXW
        words, lines, cur = str(pill).split(), [], ""
        for wd in words:
            t = (cur + " " + wd).strip()
            if fnt.measure(t) <= MAXW - 24 or not cur:
                cur = t
            else:
                lines.append(cur)
                cur = wd
        if cur:
            lines.append(cur)
        if not lines:
            lines = [""]
        # rebalance: pull words forward so last line isn't a runt
        for _ in range(3):
            if len(lines) < 2:
                break
            widths = [fnt.measure(l) for l in lines]
            if widths[-1] >= 0.6 * max(widths[:-1]):
                break
            prev = lines[-2].split()
            if len(prev) < 2:
                break
            lines[-2] = " ".join(prev[:-1])
            lines[-1] = prev[-1] + " " + lines[-1]
        # cap vertical, truncate with ellipsis
        while len(lines) * LH + 16 > MAXH and len(lines) > 1:
            lines.pop()
            lines[-1] = lines[-1][:20] + "…"
        w = max(min(MAXW, max(fnt.measure(l) for l in lines) + 24), 40)
        h = len(lines) * LH + 16
        x0, y0 = PX + 26, CY + SIZE + 6  # bottom-right of cursor
        x1 = x0 + w
        # squircle pill: small corner radius, dark shadow offset, blue body
        cr = 12
        for dx, dy, col in ((2, 2, "#0f172a"), (0, 0, COLOR)):
            canvas.create_arc(x0 + dx, y0 + dy, x0 + dx + 2 * cr, y0 + dy + 2 * cr,
                              start=90, extent=90, fill=col, outline=col)
            canvas.create_arc(x1 - 2 * cr + dx, y0 + dy, x1 + dx, y0 + dy + 2 * cr,
                              start=0, extent=90, fill=col, outline=col)
            canvas.create_arc(x0 + dx, y0 + dy + h - 2 * cr, x0 + dx + 2 * cr, y0 + dy + h,
                              start=180, extent=90, fill=col, outline=col)
            canvas.create_arc(x1 - 2 * cr + dx, y0 + dy + h - 2 * cr, x1 + dx, y0 + dy + h,
                              start=270, extent=90, fill=col, outline=col)
            canvas.create_rectangle(x0 + cr + dx, y0 + dy, x1 - cr + dx, y0 + dy + h,
                                    fill=col, outline=col)
            canvas.create_rectangle(x0 + dx, y0 + dy + cr, x1 + dx, y0 + dy + h - cr,
                                    fill=col, outline=col)
        cy0 = y0 + 8
        for l in lines:
            canvas.create_text(x0 + 13, cy0 + LH / 2 + 1, anchor="w", text=l,
                               fill="#0f172a", font=fnt)
            canvas.create_text(x0 + 12, cy0 + LH / 2, anchor="w", text=l,
                               fill="white", font=fnt)
            cy0 += LH
        root.geometry("320x380")
    root.after(50, tick)


root.after(50, tick)
root.mainloop()
