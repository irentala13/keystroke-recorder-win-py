"""Synthetic event source for --demo mode.

Feeds fabricated keyboard/mouse events through the same callback the real
pynput listeners use, so the full pipeline — buffering, flushing, JSON output,
and the live TUI — runs and animates without any OS permission or real input.
Useful for previewing the rich UI and as a CI smoke test.

Exposes the same start()/stop() surface as the real listeners so app.py can
treat it interchangeably.
"""

from __future__ import annotations

import random
import threading
import time
from typing import Callable

_DEMO_WINDOW = "DemoApp exe -:- synthetic input"
_SENTENCE = "the quick brown fox jumps over 3 lazy dogs "


class DemoSource:
    def __init__(self, signal_type: str, start_monotonic: float,
                 callback: Callable[[list], None]) -> None:
        self._signal = signal_type
        self._start = start_monotonic
        self._callback = callback
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=1.0)

    # -- internals --
    def _elapsed(self) -> float:
        return time.monotonic() - self._start

    def _emit_key(self, char: str) -> None:
        if char == " ":
            label = "SimKey:vk49;49"
        elif char.isalnum():
            label = f"SimKey:{char.lower()};{ord(char)}"
        else:
            label = "SimKey:vk36;36"
        self._callback(["press", label, self._elapsed(), _DEMO_WINDOW,
                        {"autorepeat": False}])
        time.sleep(random.uniform(0.02, 0.06))
        self._callback(["release", label, self._elapsed(), _DEMO_WINDOW,
                        {"autorepeat": False}])

    def _emit_mouse(self, x: float, y: float) -> None:
        roll = random.random()
        if roll < 0.7:
            self._callback(["move", [x, y], self._elapsed(), _DEMO_WINDOW])
        elif roll < 0.9:
            button = random.choice(["Button.left", "Button.right"])
            self._callback(["click", [x, y, button], self._elapsed(), _DEMO_WINDOW])
            self._callback(["release", [x, y, button], self._elapsed(), _DEMO_WINDOW])
        else:
            self._callback(["scroll", [x, y, 0, random.choice([-1, 1])],
                            self._elapsed(), _DEMO_WINDOW])

    def _run(self) -> None:
        if self._signal == "keyboard":
            while not self._stop.is_set():
                for char in _SENTENCE:
                    if self._stop.is_set():
                        return
                    self._emit_key(char)
                    time.sleep(random.uniform(0.05, 0.18))
        else:
            x, y = 400.0, 300.0
            while not self._stop.is_set():
                x += random.uniform(-40, 40)
                y += random.uniform(-40, 40)
                self._emit_mouse(round(x, 1), round(y, 1))
                time.sleep(random.uniform(0.05, 0.15))
