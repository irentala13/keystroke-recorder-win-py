"""Capture-permission pre-flight (Windows).

Unlike macOS (which gates event taps behind Input Monitoring), Windows
low-level hooks (WH_KEYBOARD_LL / WH_MOUSE_LL) install in a normal interactive
session with **no special permission and no admin elevation**. This module
exists to keep parity with the macOS package's app.py interface; the check is a
no-op that always succeeds.

The one practical caveat: a low-level hook cannot observe input directed at a
window running elevated (as Administrator) unless this process is *also*
elevated — a Windows UIPI restriction, not a grantable permission.
"""

from __future__ import annotations


def ensure_input_monitoring() -> bool:
    """Always True on Windows — low-level hooks need no granted permission."""
    return True
