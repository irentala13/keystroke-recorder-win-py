"""Device / environment metadata for the recording session (Windows).

Behavioral-biometrics features are only comparable across recordings taken on a
consistent device (Shen et al., IEEE TIFS 2013; Ahmed & Traore, IEEE TDSC 2007).
This captures the environment so consumers can filter/segment by device, screen,
and keyboard layout. Every field is best-effort — anything unavailable is null.
"""

from __future__ import annotations

import ctypes
import platform
import time

try:
    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _IS_WINDOWS = True
except Exception:  # pragma: no cover
    _IS_WINDOWS = False

_SM_CXSCREEN = 0
_SM_CYSCREEN = 1
_SM_CXVIRTUALSCREEN = 78
_SM_CYVIRTUALSCREEN = 79


def _primary_screen() -> dict | None:
    if not _IS_WINDOWS:
        return None
    try:
        return {
            "width_px": int(_user32.GetSystemMetrics(_SM_CXSCREEN)),
            "height_px": int(_user32.GetSystemMetrics(_SM_CYSCREEN)),
            "virtual_width_px": int(_user32.GetSystemMetrics(_SM_CXVIRTUALSCREEN)),
            "virtual_height_px": int(_user32.GetSystemMetrics(_SM_CYVIRTUALSCREEN)),
        }
    except Exception:
        return None


def _keyboard_layout() -> str | None:
    """Active keyboard layout id (KLID hex string, e.g. 00000409 for US)."""
    if not _IS_WINDOWS:
        return None
    try:
        buf = ctypes.create_unicode_buffer(9)  # KL_NAMELENGTH
        if _user32.GetKeyboardLayoutNameW(buf):
            return buf.value or None
    except Exception:
        pass
    return None


def clock_resolution_ms() -> float:
    """Resolution of the monotonic clock, in milliseconds."""
    try:
        return time.get_clock_info("monotonic").resolution * 1000.0
    except Exception:
        return 0.0


def build_device_info() -> dict:
    return {
        "keyboard_layout": _keyboard_layout(),
        "os": platform.platform(),
        "os_version": platform.version() or None,
        "primary_screen": _primary_screen(),
        "python": platform.python_version(),
    }
