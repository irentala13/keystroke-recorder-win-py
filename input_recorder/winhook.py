"""SetWindowsHookEx capture backend — CA-grade timing for Windows.

Native low-level hooks (WH_KEYBOARD_LL / WH_MOUSE_LL) installed via ctypes,
mirroring the original C++ tool's semantics (VK labeling, button names, wheel
delta, "<proc> exe -:- <title>" context) — the Windows analog of the macOS
CGEventTap backend.

Timing: a low-level hook callback fires synchronously with the input event, so
QueryPerformanceCounter sampled in the callback is effectively the event time at
sub-microsecond resolution — far finer than the ~15.6 ms GetTickCount() domain
of the hook struct's own `time` field, which we keep only as a coarse cross-check
(Killourhy & Maxion, IEEE/IFIP DSN 2009). timing.source = "qpc_hook".

Auto-repeat: WH_KEYBOARD_LL doesn't flag repeats, so we detect them by tracking
which VKs are currently down; a second key-down without an intervening key-up is
a repeat. Reported as a trailing {"autorepeat": bool} on each keyboard entry.

Low-level hooks require a message loop on the installing thread, so the hook
runs on a dedicated thread that pumps messages until asked to stop. Exposes
start()/stop() so it's interchangeable with the pynput listeners.
"""

from __future__ import annotations

import ctypes
import threading
import time
from typing import Callable

from .window_context import get_frontmost_window_context

try:
    from ctypes import wintypes
    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _IS_WINDOWS = True
except Exception:  # pragma: no cover - importing off-Windows
    _IS_WINDOWS = False


# --- constants -------------------------------------------------------------
_WH_KEYBOARD_LL = 13
_WH_MOUSE_LL = 14
_HC_ACTION = 0
_WM_QUIT = 0x0012

_WM_KEYDOWN, _WM_KEYUP = 0x0100, 0x0101
_WM_SYSKEYDOWN, _WM_SYSKEYUP = 0x0104, 0x0105

_WM_MOUSEMOVE = 0x0200
_WM_LBUTTONDOWN, _WM_LBUTTONUP = 0x0201, 0x0202
_WM_RBUTTONDOWN, _WM_RBUTTONUP = 0x0204, 0x0205
_WM_MBUTTONDOWN, _WM_MBUTTONUP = 0x0207, 0x0208
_WM_MOUSEWHEEL = 0x020A
_WM_XBUTTONDOWN, _WM_XBUTTONUP = 0x020B, 0x020C
_WM_MOUSEHWHEEL = 0x020E

_KEYDOWN_MSGS = (_WM_KEYDOWN, _WM_SYSKEYDOWN)
_KEYUP_MSGS = (_WM_KEYUP, _WM_SYSKEYUP)
_BUTTON_DOWN = (_WM_LBUTTONDOWN, _WM_RBUTTONDOWN, _WM_MBUTTONDOWN, _WM_XBUTTONDOWN)
_BUTTON_UP = (_WM_LBUTTONUP, _WM_RBUTTONUP, _WM_MBUTTONUP, _WM_XBUTTONUP)


if _IS_WINDOWS:
    _LRESULT = ctypes.c_ssize_t
    _HOOKPROC = ctypes.WINFUNCTYPE(
        _LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

    class _KBDLLHOOKSTRUCT(ctypes.Structure):
        _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD),
                    ("flags", wintypes.DWORD), ("time", wintypes.DWORD),
                    ("dwExtraInfo", ctypes.c_size_t)]

    class _POINT(ctypes.Structure):
        _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]

    class _MSLLHOOKSTRUCT(ctypes.Structure):
        _fields_ = [("pt", _POINT), ("mouseData", wintypes.DWORD),
                    ("flags", wintypes.DWORD), ("time", wintypes.DWORD),
                    ("dwExtraInfo", ctypes.c_size_t)]


def build_key_label(vk: int) -> str:
    # VK '0'-'9' and 'A'-'Z' equal their ASCII codes (shift-independent);
    # everything else -> vk<code>. Matches the C++ tool's rule.
    if 0x30 <= vk <= 0x39:
        label = chr(vk)
    elif 0x41 <= vk <= 0x5A:
        label = chr(vk).lower()
    else:
        label = f"vk{vk}"
    return f"SimKey:{label};{vk}"


def _button_name(msg: int, mouse_data: int) -> str:
    if msg in (_WM_LBUTTONDOWN, _WM_LBUTTONUP):
        return "Button.left"
    if msg in (_WM_RBUTTONDOWN, _WM_RBUTTONUP):
        return "Button.right"
    if msg in (_WM_MBUTTONDOWN, _WM_MBUTTONUP):
        return "Button.middle"
    xbutton = (mouse_data >> 16) & 0xFFFF
    return "Button.x1" if xbutton == 1 else "Button.x2"


def _signed_hiword(mouse_data: int) -> int:
    hi = (mouse_data >> 16) & 0xFFFF
    return hi - 0x10000 if hi >= 0x8000 else hi


class WinHookListener:
    def __init__(self, signal_type: str, start_monotonic: float,
                 callback: Callable[[list], None]) -> None:
        self._signal = signal_type
        self._callback = callback
        self._down: set[int] = set()

        self._hook = None
        self._proc = None            # keep the HOOKPROC alive
        self._thread_id = 0
        self._qpf = 1.0
        self._start_qpc = 0
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._ready = threading.Event()
        self._create_ok = False

    # -- lifecycle --
    def start(self) -> None:
        if not _IS_WINDOWS:
            raise RuntimeError("WinHook backend requires Windows")
        self._thread.start()
        self._ready.wait(timeout=2.0)
        if not self._create_ok:
            raise RuntimeError("SetWindowsHookEx failed")

    def stop(self) -> None:
        if self._thread_id:
            _user32.PostThreadMessageW(self._thread_id, _WM_QUIT, 0, 0)
        self._thread.join(timeout=1.0)

    # -- QPC timing --
    def _qpc(self) -> int:
        counter = ctypes.c_int64()
        _kernel32.QueryPerformanceCounter(ctypes.byref(counter))
        return counter.value

    def _elapsed(self) -> float:
        return (self._qpc() - self._start_qpc) / self._qpf

    # -- hook thread --
    def _run(self) -> None:
        _user32.SetWindowsHookExW.restype = ctypes.c_void_p
        _user32.SetWindowsHookExW.argtypes = [
            ctypes.c_int, _HOOKPROC, ctypes.c_void_p, wintypes.DWORD]
        _user32.CallNextHookEx.restype = _LRESULT
        _user32.CallNextHookEx.argtypes = [
            ctypes.c_void_p, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]

        freq = ctypes.c_int64()
        _kernel32.QueryPerformanceFrequency(ctypes.byref(freq))
        self._qpf = float(freq.value) or 1.0
        self._start_qpc = self._qpc()
        self._thread_id = _kernel32.GetCurrentThreadId()

        hook_id = _WH_KEYBOARD_LL if self._signal == "keyboard" else _WH_MOUSE_LL
        self._proc = _HOOKPROC(self._hook_proc)
        hmod = _kernel32.GetModuleHandleW(None)
        self._hook = _user32.SetWindowsHookExW(hook_id, self._proc, hmod, 0)
        if not self._hook:
            self._create_ok = False
            self._ready.set()
            return
        self._create_ok = True
        self._ready.set()

        msg = wintypes.MSG()
        while _user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            _user32.TranslateMessage(ctypes.byref(msg))
            _user32.DispatchMessageW(ctypes.byref(msg))

        _user32.UnhookWindowsHookEx(self._hook)
        self._hook = None

    def _hook_proc(self, n_code, w_param, l_param):
        if n_code == _HC_ACTION:
            try:
                if self._signal == "keyboard":
                    self._handle_key(w_param, l_param)
                else:
                    self._handle_mouse(w_param, l_param)
            except Exception:
                pass
        return _user32.CallNextHookEx(None, n_code, w_param, l_param)

    def _handle_key(self, msg, l_param) -> None:
        info = ctypes.cast(l_param, ctypes.POINTER(_KBDLLHOOKSTRUCT)).contents
        vk = info.vkCode
        label = build_key_label(vk)
        elapsed = self._elapsed()
        window = get_frontmost_window_context()

        if msg in _KEYDOWN_MSGS:
            autorepeat = vk in self._down
            self._down.add(vk)
            self._callback(["press", label, elapsed, window,
                            {"autorepeat": autorepeat}])
        elif msg in _KEYUP_MSGS:
            self._down.discard(vk)
            self._callback(["release", label, elapsed, window,
                            {"autorepeat": False}])

    def _handle_mouse(self, msg, l_param) -> None:
        info = ctypes.cast(l_param, ctypes.POINTER(_MSLLHOOKSTRUCT)).contents
        x, y = float(info.pt.x), float(info.pt.y)
        elapsed = self._elapsed()
        window = get_frontmost_window_context()

        if msg == _WM_MOUSEMOVE:
            self._callback(["move", [x, y], elapsed, window])
        elif msg in _BUTTON_DOWN:
            self._callback(["click", [x, y, _button_name(msg, info.mouseData)],
                            elapsed, window])
        elif msg in _BUTTON_UP:
            self._callback(["release", [x, y, _button_name(msg, info.mouseData)],
                            elapsed, window])
        elif msg == _WM_MOUSEWHEEL:
            self._callback(["scroll", [x, y, 0, _signed_hiword(info.mouseData) / 120.0],
                            elapsed, window])
        elif msg == _WM_MOUSEHWHEEL:
            self._callback(["scroll", [x, y, _signed_hiword(info.mouseData) / 120.0, 0],
                            elapsed, window])
