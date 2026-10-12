"""Маленький индикатор у курсора: запись / распознавание / результат."""
from __future__ import annotations

import ctypes
import math
import tkinter as tk

from .winutil import cursor_pos, make_click_through

_BG = "#1f2329"
_FG = "#f2f4f7"
_MUTED = "#9aa3ad"
_RED = "#ff4d5e"
_BLUE = "#4da3ff"
_GREEN = "#3ecf8e"
_W, _H = 230, 46


class Overlay:
    def __init__(self, root: tk.Misc):
        self.win = tk.Toplevel(root)
        self.win.withdraw()
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.attributes("-alpha", 0.97)
        self.win.configure(bg=_BG)
        self.k = k = max(1.0, root.winfo_fpixels("1i") / 96)
        self.w, self.h = int(_W * k), int(_H * k)
        self.canvas = tk.Canvas(self.win, width=self.w, height=self.h, bg=_BG, highlightthickness=0, bd=0)
        self.canvas.pack()
        self.win.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(self.win.winfo_id()) or self.win.winfo_id()
        make_click_through(hwnd)

        self.mode = "hidden"
        self.text = ""
        self.level_fn = lambda: 0.0
        self.seconds_fn = lambda: 0.0
        self._phase = 0.0
        self._hide_job = None
        self._anchor: tuple[int, int] | None = None
        self._tick()

    # --- публичные методы (вызывать из UI-потока) ---
    def recording(self, level_fn, seconds_fn):
        self._set("recording", "Говорите…")
        self.level_fn, self.seconds_fn = level_fn, seconds_fn

    def processing(self, text: str = "Распознаю…"):
        self._set("processing", text)

    def done(self, text: str):
        self._set("done", text)
        self._schedule_hide(1300)

    def error(self, text: str):
        self._set("error", text)
        self._schedule_hide(3500)

    def hide(self):
        self.mode = "hidden"
        self._anchor = None
        self.win.withdraw()

    # --- внутреннее ---
    def _set(self, mode: str, text: str):
        if self._hide_job:
            self.win.after_cancel(self._hide_job)
            self._hide_job = None
        if self.mode == "hidden":
            self._anchor = None
        self.mode, self.text = mode, text
        self._place()
        self.win.deiconify()
        self.win.attributes("-topmost", True)
        self._draw()

    def _schedule_hide(self, ms: int):
        self._hide_job = self.win.after(ms, self.hide)

    def _place(self):
        x, y = cursor_pos() if self.mode == "recording" or self._anchor is None else self._anchor
        self._anchor = (x, y)
        sw, sh = self.win.winfo_screenwidth(), self.win.winfo_screenheight()
        k = self.k
        px, py = x + int(20 * k), y + int(24 * k)
        if px + self.w > sw:
            px = x - self.w - int(12 * k)
        if py + self.h > sh:
            py = y - self.h - int(12 * k)
        self.win.geometry(f"{self.w}x{self.h}+{px}+{py}")

    def _tick(self):
        if self.mode != "hidden":
            self._phase += 0.25
            if self.mode == "recording":
                self._place()
            self._draw()
        self.win.after(50, self._tick)

    def _draw(self):
        c, k = self.canvas, self.k
        c.delete("all")
        c.create_rectangle(0, 0, self.w - 1, self.h - 1, outline="#353b44", width=1)
        cy = self.h / 2
        if self.mode == "recording":
            pulse = 0.5 + 0.5 * math.sin(self._phase)
            r = (6 + 2 * pulse) * k
            c.create_oval(20 * k - r, cy - r, 20 * k + r, cy + r, fill=_RED, outline="")
            secs = int(self.seconds_fn())
            c.create_text(38 * k, 14 * k, text=self.text, fill=_FG, anchor="w", font=("Segoe UI", 10, "bold"))
            c.create_text(self.w - 12 * k, 14 * k, text=f"{secs // 60}:{secs % 60:02d}", fill=_MUTED,
                          anchor="e", font=("Segoe UI", 9))
            x0, x1, y0, y1 = 38 * k, self.w - 12 * k, 30 * k, 35 * k
            c.create_rectangle(x0, y0, x1, y1, fill="#2c323a", outline="")
            lvl = max(0.0, min(1.0, self.level_fn()))
            if lvl > 0.01:
                c.create_rectangle(x0, y0, x0 + (x1 - x0) * lvl, y1, fill=_GREEN if lvl < 0.85 else _RED,
                                   outline="")
        else:
            color = {"processing": _BLUE, "done": _GREEN, "error": _RED}.get(self.mode, _MUTED)
            if self.mode == "processing":
                for i in range(3):
                    a = self._phase * 1.6 + i * 0.9
                    rr = (2.5 + 1.8 * (0.5 + 0.5 * math.sin(a))) * k
                    cx = (14 + i * 9) * k
                    c.create_oval(cx - rr, cy - rr, cx + rr, cy + rr, fill=color, outline="")
                tx = 46 * k
            else:
                c.create_oval(14 * k, cy - 6 * k, 26 * k, cy + 6 * k, fill=color, outline="")
                tx = 36 * k
            text = self.text if len(self.text) <= 30 else self.text[:29] + "…"
            c.create_text(tx, cy, text=text, fill=_FG, anchor="w", font=("Segoe UI", 10))
