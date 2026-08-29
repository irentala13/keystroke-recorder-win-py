"""input_recorder — Windows keystroke/mouse recorder.

A Windows-native (Python) recorder that captures low-level keyboard or mouse
input and writes it to JSON for a behavioral-biometrics pipeline. It mirrors the
architecture of the macOS ``keystroke-recorder-mac`` package (same CLI, schema,
rich TUI, demo mode, and metadata) and the Win32 semantics of the original C++
``keystroke-recorder-win`` tool (VK labeling, window context, wheel deltas).

Two capture backends: a native ``winhook`` backend (SetWindowsHookEx low-level
hooks with QueryPerformanceCounter timing and auto-repeat detection) and a
``pynput`` fallback.
"""

__version__ = "1.0.0"
