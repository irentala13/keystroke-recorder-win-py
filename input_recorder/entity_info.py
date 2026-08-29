"""entity block construction — the Python analog of entity_info.cpp.

machine_id / tenant / tuid are placeholders for the test pipeline, matching the
Windows tool's FAKE_* defaults. user_id / machine_name come from the local host.
"""

from __future__ import annotations

import getpass
import socket
from dataclasses import dataclass


@dataclass
class EntityInfo:
    machine_id: str
    machine_name: str
    tenant: str
    tuid: str
    user_id: str


def _current_username() -> str:
    try:
        return getpass.getuser()
    except Exception:
        return "unknown"


def _local_machine_name() -> str:
    name = socket.gethostname()
    return name or "unknown"


def build_entity_info(username_override: str,
                      machine_id_override: str,
                      tenant_override: str,
                      tuid_override: str) -> EntityInfo:
    return EntityInfo(
        machine_id=machine_id_override or "FAKE_MACHINE_ID",
        machine_name=_local_machine_name(),
        tenant=tenant_override or "FAKE_TENANT",
        tuid=tuid_override or "FAKE_TUID",
        user_id=username_override or _current_username(),
    )
