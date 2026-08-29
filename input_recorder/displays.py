"""Display enumeration — Win32 analog of EnumerateMonitors() (mouse only).

Populated into metadata.monitor_info for mouse recordings via EnumDisplayMonitors
+ GetMonitorInfoW. width_mm/height_mm/name are always null, matching the
reference samples (no physical-size lookup). ctypes-only, no pywin32.
"""

from __future__ import annotations

import ctypes
from dataclasses import dataclass

try:
    from ctypes import wintypes
    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _IS_WINDOWS = True
except Exception:  # pragma: no cover
    _IS_WINDOWS = False


@dataclass
class MonitorInfo:
    x: int
    y: int
    width: int
    height: int
    is_primary: bool


_MONITORINFOF_PRIMARY = 0x1


if _IS_WINDOWS:
    class _RECT(ctypes.Structure):
        _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                    ("right", wintypes.LONG), ("bottom", wintypes.LONG)]

    class _MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", _RECT),
                    ("rcWork", _RECT), ("dwFlags", wintypes.DWORD)]

    _MONITORENUMPROC = ctypes.WINFUNCTYPE(
        wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC,
        ctypes.POINTER(_RECT), wintypes.LPARAM)


def enumerate_monitors() -> list[MonitorInfo]:
    if not _IS_WINDOWS:
        return []
    monitors: list[MonitorInfo] = []

    def _callback(hmonitor, hdc, lprect, lparam):
        mi = _MONITORINFO()
        mi.cbSize = ctypes.sizeof(_MONITORINFO)
        if _user32.GetMonitorInfoW(hmonitor, ctypes.byref(mi)):
            r = mi.rcMonitor
            monitors.append(MonitorInfo(
                x=r.left, y=r.top,
                width=r.right - r.left, height=r.bottom - r.top,
                is_primary=bool(mi.dwFlags & _MONITORINFOF_PRIMARY)))
        return True

    try:
        _user32.EnumDisplayMonitors(None, None, _MONITORENUMPROC(_callback), 0)
    except Exception:
        return monitors
    return monitors
