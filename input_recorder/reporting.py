"""Session reporting with two backends behind one interface.

- RichReporter: a live TUI — a header, a time progress bar, running stats, a
  flush/notes strip, and a scrolling event feed (rich).
- PlainReporter: the dependency-free carriage-return status line + log lines,
  used when rich isn't installed or stdout isn't a TTY (pipes / CI).

app.py talks only to the Reporter interface; make_reporter() picks the backend.
Both are context managers (``with reporter:``) so the live display — if any —
is started and torn down cleanly.
"""

from __future__ import annotations

import collections
import os
import sys
from typing import Deque, Optional

from .console import ConsoleReporter, format_mmss

_FEED_ROWS = 12       # scrolling event-feed length
_NOTES_ROWS = 4       # recent flush/info lines kept on screen


def _mask_label(label: str) -> str:
    """Replace a single alphanumeric key character with a bullet, so the feed
    doesn't display exactly what was typed. ``SimKey:a;0`` -> ``SimKey:•;0``.
    Non-character keys (``SimKey:vk49;49``) and mouse entries are unchanged."""
    if not isinstance(label, str) or not label.startswith("SimKey:"):
        return label
    try:
        body = label[len("SimKey:"):]
        key, _, vk = body.partition(";")
        if len(key) == 1 and key.isalnum():
            return f"SimKey:•;{vk}"
    except Exception:
        pass
    return label


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------

class Reporter:
    """No-op-ish base defining the interface app.py depends on."""

    def __enter__(self) -> "Reporter":
        return self

    def __exit__(self, *exc) -> None:
        pass

    def begin(self, signal_type: str, output_subdir: str,
              runtime: int, interval: int, username: str) -> None: ...

    def event(self, entry: list) -> None: ...

    def flush_written(self, result: Optional[tuple[str, int]]) -> None: ...

    def update(self, elapsed: float, total: float, events: int,
               files: int, next_flush_in: int) -> None: ...

    def note(self, message: str) -> None: ...

    def end(self, events: int, files: int, elapsed: float,
            output_subdir: str, stopped_early: bool) -> None: ...


# ---------------------------------------------------------------------------
# Plain backend
# ---------------------------------------------------------------------------

class PlainReporter(Reporter):
    def __init__(self) -> None:
        self._c = ConsoleReporter()

    def __exit__(self, *exc) -> None:
        self._c.clear()

    def begin(self, signal_type, output_subdir, runtime, interval, username) -> None:
        self._c.log(f"● Recording {signal_type}  →  {output_subdir}")
        self._c.log(f"  duration {runtime}s · flush every {interval}s · user '{username}'")
        self._c.log("  Press Ctrl+C to stop early.")

    def event(self, entry) -> None:
        pass  # plain mode reports aggregate counts, not individual events

    def flush_written(self, result) -> None:
        if result is not None:
            filename, count = result
            self._c.log(f"  ✓ wrote {os.path.basename(filename)} "
                        f"({count} action{'s' if count != 1 else ''})")

    def update(self, elapsed, total, events, files, next_flush_in) -> None:
        self._c.status(
            f"  ● {format_mmss(elapsed)} / {format_mmss(total)}  "
            f"│ events {events}  │ files {files}  "
            f"│ next flush {next_flush_in}s  │ Ctrl+C to stop")

    def note(self, message) -> None:
        self._c.log(message)

    def end(self, events, files, elapsed, output_subdir, stopped_early) -> None:
        self._c.clear()
        if stopped_early:
            self._c.log("  (stopped early)")
        self._c.log(f"✔ Recording complete — {events} events, "
                    f"{files} file{'s' if files != 1 else ''} "
                    f"in {format_mmss(elapsed)} → {output_subdir}")
        if events == 0:
            self._c.log(
                "  ⚠ No events were captured. If you expected input, try "
                "--backend pynput,\n"
                "    and run elevated if the target window is an Administrator "
                "process.")


# ---------------------------------------------------------------------------
# Rich backend
# ---------------------------------------------------------------------------

class RichReporter(Reporter):
    def __init__(self, mask_keys: bool = False, console=None) -> None:
        from rich.console import Console
        self._mask = mask_keys
        self._console = console or Console()
        self._live = None
        # Feeds are appended from the listener thread; deque append is atomic.
        self._events: Deque[list] = collections.deque(maxlen=_FEED_ROWS)
        self._notes: Deque[str] = collections.deque(maxlen=_NOTES_ROWS)
        # Session metadata / latest stats for rendering.
        self._signal = ""
        self._output = ""
        self._runtime = 0
        self._interval = 0
        self._username = ""
        self._elapsed = 0.0
        self._events_total = 0
        self._files = 0
        self._next_flush = 0

    # -- lifecycle --
    def __enter__(self) -> "RichReporter":
        from rich.live import Live
        self._live = Live(self._render(), console=self._console,
                          refresh_per_second=8, transient=False)
        self._live.__enter__()
        return self

    def __exit__(self, *exc) -> None:
        if self._live is not None:
            self._live.update(self._render())
            self._live.__exit__(*exc)
            self._live = None
        # Persist the summary below the (now static) final panel.
        summary = getattr(self, "_summary", None)
        if summary:
            self._console.print(summary, style="bold")
            if getattr(self, "_zero", False):
                self._console.print(
                    "  ⚠ No events were captured — try --backend pynput, or run "
                    "elevated for Administrator windows.", style="yellow")

    # -- interface --
    def begin(self, signal_type, output_subdir, runtime, interval, username) -> None:
        self._signal = signal_type
        self._output = output_subdir
        self._runtime = runtime
        self._interval = interval
        self._username = username
        self._refresh()

    def event(self, entry) -> None:
        self._events.append(entry)

    def flush_written(self, result) -> None:
        if result is not None:
            filename, count = result
            self._notes.append(f"✓ wrote {os.path.basename(filename)} "
                               f"({count} action{'s' if count != 1 else ''})")
            self._refresh()

    def update(self, elapsed, total, events, files, next_flush_in) -> None:
        self._elapsed = elapsed
        self._runtime = total
        self._events_total = events
        self._files = files
        self._next_flush = next_flush_in
        self._refresh()

    def note(self, message) -> None:
        self._notes.append(message)
        self._refresh()

    def end(self, events, files, elapsed, output_subdir, stopped_early) -> None:
        self._events_total = events
        self._files = files
        self._elapsed = elapsed
        if stopped_early:
            self._notes.append("(stopped early)")
        self._refresh()
        # Persist a summary line below the (now torn-down) live panel.
        exit_note = (f"✔ Recording complete — {events} events, "
                     f"{files} file{'s' if files != 1 else ''} "
                     f"in {format_mmss(elapsed)} → {output_subdir}")
        # Deferred: printed after __exit__ stops the Live region.
        self._summary = exit_note
        self._zero = (events == 0)

    # -- rendering --
    def _refresh(self) -> None:
        if self._live is not None:
            self._live.update(self._render())

    def _render(self):
        from rich.console import Group
        from rich.panel import Panel
        from rich.progress_bar import ProgressBar
        from rich.table import Table
        from rich.text import Text

        header = Text.assemble(
            ("● ", "bold red"),
            (f"{self._signal}", "bold"),
            ("  →  ", "dim"),
            (self._output, "cyan"),
            ("   user ", "dim"),
            (f"'{self._username}'", "green"),
        )

        total = max(self._runtime, 1)
        bar = ProgressBar(total=total, completed=min(self._elapsed, total), width=40)
        bar_row = Table.grid(padding=(0, 1))
        bar_row.add_column()
        bar_row.add_column()
        bar_row.add_row(
            bar,
            Text(f"{format_mmss(self._elapsed)} / {format_mmss(self._runtime)}",
                 style="bold"))

        stats = Text.assemble(
            ("events ", "dim"), (str(self._events_total), "bold yellow"),
            ("   files ", "dim"), (str(self._files), "bold yellow"),
            ("   next flush ", "dim"), (f"{self._next_flush}s", "bold"),
            ("   ·  Ctrl+C to stop", "dim"),
        )

        notes = Text("\n".join(self._notes) if self._notes else "—",
                     style="green")

        feed = Table(show_header=True, header_style="bold magenta",
                     box=None, expand=True, pad_edge=False)
        feed.add_column("time", width=7, justify="right", style="cyan", no_wrap=True)
        feed.add_column("action", width=8, no_wrap=True)
        feed.add_column("key / pos", ratio=2, overflow="fold")
        feed.add_column("window", ratio=3, overflow="ellipsis", style="dim")
        for entry in list(self._events):
            action, label, elapsed, window = entry[0], entry[1], entry[2], entry[3]
            if self._mask:
                label = _mask_label(label)
            action_style = {"press": "green", "release": "yellow",
                            "click": "green", "scroll": "blue",
                            "move": "dim"}.get(action, "white")
            feed.add_row(f"{elapsed:6.2f}", Text(action, style=action_style),
                         str(label), str(window))

        body = Group(
            header,
            Text(""),
            bar_row,
            stats,
            Text(""),
            Panel(notes, title="recent", title_align="left",
                  border_style="dim", padding=(0, 1)),
            Panel(feed, title=f"event feed (last {_FEED_ROWS})",
                  title_align="left", border_style="blue", padding=(0, 1)),
        )
        return Panel(body, title="input_recorder", border_style="red",
                     padding=(1, 2))


def make_reporter(force_plain: bool = False, mask_keys: bool = False) -> Reporter:
    """Pick the rich TUI when it's available and stdout is a real terminal;
    otherwise fall back to the plain line reporter."""
    if force_plain or not sys.stdout.isatty():
        return PlainReporter()
    try:
        return RichReporter(mask_keys=mask_keys)
    except Exception:
        return PlainReporter()
