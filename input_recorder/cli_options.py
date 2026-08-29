"""Command-line parsing — mirrors the flags of the Windows input_recorder."""

from __future__ import annotations

import argparse
from dataclasses import dataclass


@dataclass
class CliOptions:
    data_dir: str
    username: str = ""          # empty -> current user
    runtime_seconds: int = 60
    interval_seconds: int = 60
    signal_type: str = "keyboard"   # "keyboard" | "mouse"
    machine_id: str = ""        # empty -> FAKE_MACHINE_ID
    tenant: str = ""            # empty -> FAKE_TENANT
    tuid: str = ""              # empty -> FAKE_TUID
    skip_permission_check: bool = False
    plain: bool = False         # force the plain reporter (no rich TUI)
    mask_keys: bool = False     # hide typed characters in the live feed
    demo: bool = False          # feed synthetic events (no OS capture)
    session_id: str = ""        # empty -> generated UUID
    task_type: str = ""         # e.g. free-text | fixed-text | free-mouse
    prompt_id: str = ""         # id of the prompt/stimulus, if any
    backend: str = "auto"       # auto | winhook | pynput


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def parse_cli_options(argv: list[str]) -> CliOptions:
    """Parse argv (excluding program name is handled by argparse via argv[1:])."""
    parser = argparse.ArgumentParser(
        prog="input_recorder",
        description="Record Windows keyboard or mouse input to JSON for a "
                    "behavioral-biometrics test pipeline.",
    )
    parser.add_argument(
        "-d", "--data-dir", required=True, dest="data_dir",
        help="Output directory. Files go to <dir>\\KBD_JSON\\ or <dir>\\MOUSE_JSON\\",
    )
    parser.add_argument(
        "-u", "--username", default="", dest="username",
        help="Username prefix for filenames and entity.user_id (default: current user)",
    )
    parser.add_argument(
        "-r", "--runtime", type=_positive_int, default=60, dest="runtime_seconds",
        help="Recording duration in seconds (default: 60)",
    )
    parser.add_argument(
        "-i", "--interval", type=_positive_int, default=60, dest="interval_seconds",
        help="File flush interval in seconds (default: 60)",
    )
    parser.add_argument(
        "-t", "--type", choices=("keyboard", "mouse"), default="keyboard",
        dest="signal_type", help="Signal type: keyboard or mouse (default: keyboard)",
    )
    parser.add_argument(
        "--machine-id", default="", dest="machine_id",
        help="Placeholder entity.machine_id (default: FAKE_MACHINE_ID)",
    )
    parser.add_argument(
        "--tenant", default="", dest="tenant",
        help="Placeholder entity.tenant (default: FAKE_TENANT)",
    )
    parser.add_argument(
        "--tuid", default="", dest="tuid",
        help="Placeholder entity.tuid (default: FAKE_TUID)",
    )
    parser.add_argument(
        "--skip-permission-check", action="store_true", dest="skip_permission_check",
        help="No-op on Windows (kept for parity); low-level hooks need no permission",
    )
    parser.add_argument(
        "--plain", action="store_true", dest="plain",
        help="Use the plain text reporter instead of the rich live TUI",
    )
    parser.add_argument(
        "--mask-keys", action="store_true", dest="mask_keys",
        help="Hide typed characters in the live event feed (shows SimKey:•;<vk>)",
    )
    parser.add_argument(
        "--demo", action="store_true", dest="demo",
        help="Feed synthetic events instead of capturing real input (previews "
             "the UI; no permission needed)",
    )
    parser.add_argument(
        "--session-id", default="", dest="session_id",
        help="Recording session id recorded in metadata (default: generated UUID)",
    )
    parser.add_argument(
        "--task-type", default="", dest="task_type",
        help="Collection protocol / task (e.g. free-text, fixed-text, free-mouse)",
    )
    parser.add_argument(
        "--prompt-id", default="", dest="prompt_id",
        help="Identifier of the prompt/stimulus shown to the subject, if any",
    )
    parser.add_argument(
        "--backend", choices=("auto", "winhook", "pynput"), default="auto",
        dest="backend",
        help="Capture backend: winhook (low-level hooks + QPC, best for CA), "
             "pynput, or auto (winhook then pynput fallback). Default: auto",
    )

    ns = parser.parse_args(argv[1:])
    return CliOptions(
        data_dir=ns.data_dir,
        username=ns.username,
        runtime_seconds=ns.runtime_seconds,
        interval_seconds=ns.interval_seconds,
        signal_type=ns.signal_type,
        machine_id=ns.machine_id,
        tenant=ns.tenant,
        tuid=ns.tuid,
        skip_permission_check=ns.skip_permission_check,
        plain=ns.plain,
        mask_keys=ns.mask_keys,
        demo=ns.demo,
        session_id=ns.session_id,
        task_type=ns.task_type,
        prompt_id=ns.prompt_id,
        backend=ns.backend,
    )
