"""Keyboard capture via pynput — the macOS analog of keyboard_hook.cpp.

Emits payload entries of the form:
    [action, "SimKey:<label>;<vk>", elapsed_seconds, window_context]

Key-labeling rule (adapted from the Windows tool): a single alphanumeric
character -> its literal lowercase form (``a``, ``3``); everything else -> the
macOS virtual key code as ``vk<code>``. macOS virtual key codes differ from
Windows VK codes (this is the intended macOS adaptation), but the label shape is
identical so downstream parsing is unchanged.
"""

from __future__ import annotations

import time
from typing import Callable

from pynput import keyboard

from .window_context import get_frontmost_window_context


def _key_vk(key) -> int | None:
    vk = getattr(key, "vk", None)
    if vk is None:
        value = getattr(key, "value", None)  # special Key -> Key.value is a KeyCode
        vk = getattr(value, "vk", None)
    return vk


def _key_char(key) -> str | None:
    char = getattr(key, "char", None)
    if char is None:
        value = getattr(key, "value", None)
        char = getattr(value, "char", None)
    return char


def build_key_label(key) -> str:
    char = _key_char(key)
    vk = _key_vk(key)
    if char and len(char) == 1 and char.isalnum():
        label = char.lower()
    elif vk is not None:
        label = f"vk{vk}"
    else:
        label = str(key)
    vk_suffix = vk if vk is not None else ""
    return f"SimKey:{label};{vk_suffix}"


class KeyboardListener:
    """Wraps a pynput keyboard.Listener, forwarding normalized events."""

    def __init__(self, start_monotonic: float,
                 callback: Callable[[list], None]) -> None:
        self._start = start_monotonic
        self._callback = callback
        self._listener: keyboard.Listener | None = None

    def _emit(self, action: str, key) -> None:
        elapsed = time.monotonic() - self._start
        entry = [
            action,
            build_key_label(key),
            elapsed,
            get_frontmost_window_context(),
            # pynput can't distinguish OS auto-repeat -> unknown.
            {"autorepeat": None},
        ]
        self._callback(entry)

    def start(self) -> None:
        self._listener = keyboard.Listener(
            on_press=lambda key: self._emit("press", key),
            on_release=lambda key: self._emit("release", key),
        )
        self._listener.start()

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None
