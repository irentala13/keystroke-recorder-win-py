"""Foreground-window context — Win32 analog of the C++ window_context.cpp.

Produces "<process> exe -:- <sanitized title>", matching the original Windows
tool: the foreground process's base name with any ".exe" stripped, plus the
window title with every non-alphanumeric, non-space character replaced by a
space. Uses ctypes (user32/kernel32) so there's no pywin32 dependency.
"""

from __future__ import annotations

import ctypes
import os

try:
    from ctypes import wintypes
    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _IS_WINDOWS = True
except Exception:  # pragma: no cover - importing off-Windows
    _IS_WINDOWS = False


_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def _sanitize(text: str) -> str:
    """Non-alphanumeric, non-space characters -> space (matches real recordings)."""
    return "".join(c if (c.isalnum() or c.isspace()) else " " for c in text)


def _foreground_process_base_name(pid: int) -> str:
    if not pid:
        return "Unknown"
    handle = _kernel32.OpenProcess(
        _PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return "Unknown"
    try:
        buf = ctypes.create_unicode_buffer(32768)
        size = wintypes.DWORD(len(buf))
        if _kernel32.QueryFullProcessImageNameW(
                handle, 0, buf, ctypes.byref(size)) and size.value:
            name = os.path.basename(buf.value)
            if name.lower().endswith(".exe"):
                name = name[:-4]
            return name or "Unknown"
    finally:
        _kernel32.CloseHandle(handle)
    return "Unknown"


def _foreground_title(hwnd) -> str:
    length = _user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    _user32.GetWindowTextW(hwnd, buf, length + 1)
    return _sanitize(buf.value)


def get_frontmost_window_context() -> str:
    if not _IS_WINDOWS:
        return "Unknown exe -:- Unknown"
    try:
        hwnd = _user32.GetForegroundWindow()
        if not hwnd:
            return "Unknown exe -:- Unknown"
        pid = wintypes.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        process_name = _foreground_process_base_name(pid.value)
        title = _foreground_title(hwnd)
        return f"{process_name} exe -:- {title}"
    except Exception:
        return "Unknown exe -:- Unknown"
