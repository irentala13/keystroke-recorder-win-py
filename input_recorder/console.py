"""Console reporting: a live in-place status line plus persistent log lines.

Keeps a single updating status line at the bottom (carriage-return based, no
dependencies) while letting flush/summary messages scroll above it. Falls back
to plain line output when stdout is not a TTY (pipes, CI, redirected logs).
"""

from __future__ import annotations

import sys


def format_mmss(seconds: float) -> str:
    total = int(seconds)
    return f"{total // 60:02d}:{total % 60:02d}"


class ConsoleReporter:
    def __init__(self) -> None:
        self._tty = sys.stdout.isatty()
        self._status_len = 0

    def _clear_status(self) -> None:
        if self._tty and self._status_len:
            sys.stdout.write("\r" + " " * self._status_len + "\r")
            self._status_len = 0

    def log(self, message: str) -> None:
        """Print a persistent line, without clobbering the live status line."""
        self._clear_status()
        sys.stdout.write(message + "\n")
        sys.stdout.flush()

    def status(self, message: str) -> None:
        """Update the in-place status line (no-op on non-TTY output)."""
        if not self._tty:
            return
        self._clear_status()
        sys.stdout.write(message)
        sys.stdout.flush()
        self._status_len = len(message)

    def clear(self) -> None:
        """Remove the live status line (call before final summary)."""
        self._clear_status()
