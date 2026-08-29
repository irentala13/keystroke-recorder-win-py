"""Mouse capture via pynput — the pynput fallback (≈ mouse_hook.cpp).

Payload shapes match the Windows tool:
    ["move",    [x, y],                    elapsed, window_context]
    ["click",   [x, y, "Button.left"],     elapsed, window_context]
    ["release", [x, y, "Button.left"],     elapsed, window_context]
    ["scroll",  [x, y, dx, dy],            elapsed, window_context]
"""

from __future__ import annotations

import time
from typing import Callable

from pynput import mouse

from .window_context import get_frontmost_window_context


class MouseListener:
    def __init__(self, start_monotonic: float,
                 callback: Callable[[list], None]) -> None:
        self._start = start_monotonic
        self._callback = callback
        self._listener: mouse.Listener | None = None

    def _elapsed(self) -> float:
        return time.monotonic() - self._start

    def _on_move(self, x, y) -> None:
        self._callback(["move", [float(x), float(y)], self._elapsed(),
                        get_frontmost_window_context()])

    def _on_click(self, x, y, button, pressed) -> None:
        # pynput Button repr is already "Button.left" / "Button.right" / etc.
        action = "click" if pressed else "release"
        self._callback([action, [float(x), float(y), str(button)], self._elapsed(),
                        get_frontmost_window_context()])

    def _on_scroll(self, x, y, dx, dy) -> None:
        self._callback(["scroll", [float(x), float(y), dx, dy], self._elapsed(),
                        get_frontmost_window_context()])

    def start(self) -> None:
        self._listener = mouse.Listener(
            on_move=self._on_move,
            on_click=self._on_click,
            on_scroll=self._on_scroll,
        )
        self._listener.start()

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None
