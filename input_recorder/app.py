"""Recording session driver — the Python analog of the C++ main.cpp.

The capture backend (WinHook low-level hooks, or pynput) runs on its own thread;
the main thread polls a monotonic clock to drive interval flushes and the
runtime cutoff. Ctrl+C flushes and exits.
"""

from __future__ import annotations

import sys
import time
import uuid

from .cli_options import parse_cli_options
from .demo import DemoSource
from .device_info import build_device_info, clock_resolution_ms
from .displays import enumerate_monitors
from .entity_info import build_entity_info
from .json_writer import RecordingWriter
from .keyboard_listener import KeyboardListener
from .mouse_listener import MouseListener
from .permissions import ensure_input_monitoring
from .reporting import make_reporter

_POLL_INTERVAL_SECONDS = 0.2


def _timing_for(backend: str) -> dict:
    # winhook samples QPC in the low-level hook (≈ event time); pynput/demo
    # time at the callback.
    source = "qpc_hook" if backend == "winhook" else "monotonic_callback"
    return {
        "backend": backend,
        "source": source,
        "unit": "s",
        "clock_resolution_ms": round(clock_resolution_ms(), 6),
    }


def _make_listener(name: str, signal_type: str, start: float, callback):
    if name == "winhook":
        from .winhook import WinHookListener
        return WinHookListener(signal_type, start, callback)
    if signal_type == "keyboard":
        return KeyboardListener(start, callback)
    return MouseListener(start, callback)


def _start_capture(preference: str, signal_type: str, start: float, callback):
    """Start the preferred backend, falling back per --backend. Returns
    (listener, backend_name). Raises if no backend could start."""
    order = {
        "auto": ["winhook", "pynput"],
        "winhook": ["winhook"],
        "pynput": ["pynput"],
    }[preference]
    last_exc: Exception | None = None
    for name in order:
        try:
            listener = _make_listener(name, signal_type, start, callback)
            listener.start()
            return listener, name
        except Exception as exc:  # tap-create failure, missing perms, etc.
            last_exc = exc
    raise last_exc or RuntimeError("no capture backend available")


def main(argv: list[str]) -> int:
    options = parse_cli_options(argv)

    # Kept for parity with the macOS package; on Windows low-level hooks need
    # no granted permission, so this always passes.
    if (not options.demo and not options.skip_permission_check
            and not ensure_input_monitoring()):
        return 1

    entity = build_entity_info(
        options.username, options.machine_id, options.tenant, options.tuid)
    username_prefix = entity.user_id

    monitor_info = []
    if options.signal_type == "mouse":
        monitor_info = enumerate_monitors()

    session_id = options.session_id or str(uuid.uuid4())
    session_start = time.time()
    collection = {
        "task_type": options.task_type or None,
        "prompt_id": options.prompt_id or None,
    }

    # Populated once the capture backend is known (writer reads it at flush).
    timing: dict = {}

    writer = RecordingWriter(
        options.data_dir, options.signal_type, entity,
        options.interval_seconds, monitor_info,
        session_id=session_id,
        session_start=session_start,
        timing=timing,
        device=build_device_info(),
        collection=collection)

    reporter = make_reporter(force_plain=options.plain, mask_keys=options.mask_keys)

    # Tap the capture callback so each event lands in both the JSON buffer and
    # the live feed. Called from the capture backend's thread.
    def on_entry(entry: list) -> None:
        writer.add_payload_entry(entry)
        reporter.event(entry)

    start = time.monotonic()
    runtime = options.runtime_seconds
    interval = options.interval_seconds

    with reporter:
        reporter.begin(options.signal_type, writer.output_subdir,
                       runtime, interval, username_prefix)

        try:
            if options.demo:
                listener = DemoSource(options.signal_type, start, on_entry)
                listener.start()
                backend = "demo"
            else:
                listener, backend = _start_capture(
                    options.backend, options.signal_type, start, on_entry)
        except Exception as exc:
            reporter.note(f"ERROR: failed to start capture ({exc})")
            reporter.note("Grant Input Monitoring to your terminal in System "
                          "Settings > Privacy & Security, then relaunch it.")
            return 1

        timing.update(_timing_for(backend))
        reporter.note(f"capture backend: {backend} "
                      f"(timing source: {timing['source']})")

        last_flush = 0.0
        stopped_early = False
        try:
            while True:
                now = time.monotonic() - start
                if now >= runtime:
                    break
                if now - last_flush >= interval:
                    reporter.flush_written(writer.flush(username_prefix))
                    last_flush = now
                next_flush_in = max(0, int(interval - (now - last_flush)))
                reporter.update(now, runtime, writer.total_events,
                                writer.files_written, next_flush_in)
                time.sleep(_POLL_INTERVAL_SECONDS)
        except KeyboardInterrupt:
            stopped_early = True
        finally:
            listener.stop()
            # Flush anything captured since the last interval boundary.
            reporter.flush_written(writer.flush(username_prefix))

        elapsed = time.monotonic() - start
        reporter.end(writer.total_events, writer.files_written, elapsed,
                     writer.output_subdir, stopped_early)

    return 0


def run() -> None:
    """Console-script entry point."""
    sys.exit(main(sys.argv))
