"""RecordingWriter — buffers payload entries and flushes JSON files.

Structurally parallel to json_writer.cpp (same entity/payload layout, same
KBD_JSON / MOUSE_JSON subdirs, same <username><N>.json filenames, compact JSON),
with an extended `metadata` block for behavioral-biometrics data collection:
session identity, timing provenance, device/environment, collection protocol,
mouse sampling rate, and basic data-quality counters. Schema `version` is "2".
"""

from __future__ import annotations

import json
import os
import threading
import time

from .displays import MonitorInfo
from .entity_info import EntityInfo


class RecordingWriter:
    def __init__(self, output_dir: str, signal_type: str, entity: EntityInfo,
                 file_write_interval_seconds: int,
                 monitor_info: list[MonitorInfo] | None = None,
                 session_id: str = "",
                 session_start: float | None = None,
                 timing: dict | None = None,
                 device: dict | None = None,
                 collection: dict | None = None) -> None:
        self._output_dir = output_dir
        self._signal_type = signal_type
        self._entity = entity
        self._file_write_interval = file_write_interval_seconds
        self._monitor_info = monitor_info or []
        self._session_id = session_id
        self._session_start = session_start
        # Keep the caller's dict identity — app.py fills `timing` in after the
        # capture backend is known (an empty dict is falsy, so don't use `or`).
        self._timing = timing if timing is not None else {}
        self._device = device if device is not None else {}
        self._collection = collection if collection is not None else {}
        self._payload: list = []
        self._lock = threading.Lock()
        self._sequence = 0
        self._last_elapsed: float | None = None
        self.total_events = 0    # cumulative across the whole session
        self.files_written = 0
        self.out_of_order_events = 0

    def _subdirectory_name(self) -> str:
        return "MOUSE_JSON" if self._signal_type == "mouse" else "KBD_JSON"

    @property
    def output_subdir(self) -> str:
        return os.path.join(self._output_dir, self._subdirectory_name())

    def add_payload_entry(self, entry: list) -> None:
        # Called from the pynput listener thread; the main thread flushes.
        with self._lock:
            # entry = [action, key/pos, elapsed_seconds, window_context]
            elapsed = entry[2] if len(entry) > 2 else None
            if (isinstance(elapsed, (int, float)) and self._last_elapsed is not None
                    and elapsed < self._last_elapsed):
                self.out_of_order_events += 1
            if isinstance(elapsed, (int, float)):
                self._last_elapsed = elapsed
            self._payload.append(entry)
            self.total_events += 1

    def _sampling_rate_hz(self, payload: list) -> float | None:
        """Observed mouse sampling rate from 'move' events in this buffer.
        Kinematic features need a known Δt (Ahmed & Traore, IEEE TDSC 2007)."""
        times = [e[2] for e in payload
                 if e and e[0] == "move" and isinstance(e[2], (int, float))]
        if len(times) < 2:
            return None
        span = times[-1] - times[0]
        if span <= 0:
            return None
        return round((len(times) - 1) / span, 2)

    def flush(self, username_prefix: str) -> tuple[str, int] | None:
        """Write buffered events to the next file. Returns (path, count) on a
        write, or None if there was nothing to write / the write failed."""
        with self._lock:
            if not self._payload:
                return None
            payload = self._payload
            self._payload = []
            self._sequence += 1
            sequence = self._sequence
            out_of_order = self.out_of_order_events

        entity = {
            "machine_id": self._entity.machine_id,
            "machine_name": self._entity.machine_name,
            "tenant": self._entity.tenant,
            "tuid": self._entity.tuid,
            "user_id": self._entity.user_id,
        }

        metadata: dict = {
            "collection": self._collection,
            "device": self._device,
            "file_write_interval": self._file_write_interval,
        }
        if self._monitor_info:
            metadata["monitor_info"] = [
                {
                    "height": m.height,
                    "height_mm": None,
                    "is_primary": m.is_primary,
                    "name": None,
                    "width": m.width,
                    "width_mm": None,
                    "x": m.x,
                    "y": m.y,
                }
                for m in self._monitor_info
            ]
        metadata["number_of_actions"] = len(payload)
        metadata["quality"] = {"out_of_order_events": out_of_order}
        if self._signal_type == "mouse":
            metadata["sampling_rate_hz"] = self._sampling_rate_hz(payload)
        metadata["session_id"] = self._session_id
        metadata["session_start"] = self._session_start
        metadata["signal_type"] = self._signal_type
        metadata["timestamp"] = time.time()
        metadata["timing"] = self._timing
        metadata["version"] = "2"

        document = {"entity": entity, "metadata": metadata, "payload": payload}

        subdir = os.path.join(self._output_dir, self._subdirectory_name())
        try:
            os.makedirs(subdir, exist_ok=True)
        except OSError as exc:
            print(f"ERROR: could not create directory '{subdir}' ({exc})")
            return None

        filename = os.path.join(subdir, f"{username_prefix}{sequence}.json")
        try:
            with open(filename, "w", encoding="utf-8") as fh:
                json.dump(document, fh, separators=(",", ":"), ensure_ascii=False)
        except OSError as exc:
            print(f"ERROR: could not open '{filename}' for writing ({exc})")
            return None

        self.files_written += 1
        return (filename, len(payload))
