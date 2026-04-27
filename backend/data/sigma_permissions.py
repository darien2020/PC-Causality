"""Per-tool permission policy for Sigma MCP tools.

Persisted alongside the OAuth tokens so the policy survives backend restarts.
Two policies:
  "allow_always" — agent runs the tool without asking
  "ask_always"   — agent must request user approval before each call

Tools without an explicit entry default to "allow_always" so an empty policy
file means "agent has full access" (matches existing behavior).
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Literal

Policy = Literal["allow_always", "ask_always"]
DEFAULT_POLICY: Policy = "allow_always"

PERMS_PATH = Path.home() / ".config" / "causality" / "sigma_permissions.json"

_lock = threading.Lock()


def _read() -> dict[str, Policy]:
    try:
        data = json.loads(PERMS_PATH.read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {
        str(k): v for k, v in data.items() if v in ("allow_always", "ask_always")
    }


def _write(policies: dict[str, Policy]) -> None:
    try:
        PERMS_PATH.parent.mkdir(parents=True, exist_ok=True)
        PERMS_PATH.write_text(json.dumps(policies, indent=2))
        try:
            PERMS_PATH.chmod(0o600)
        except OSError:
            pass
    except OSError:
        pass


def get_all() -> dict[str, Policy]:
    with _lock:
        return _read()


def get_for(tool_name: str) -> Policy:
    with _lock:
        return _read().get(tool_name, DEFAULT_POLICY)


def set_for(tool_name: str, policy: Policy) -> None:
    with _lock:
        policies = _read()
        policies[tool_name] = policy
        _write(policies)


def set_many(updates: dict[str, Policy]) -> dict[str, Policy]:
    with _lock:
        policies = _read()
        for name, policy in updates.items():
            if policy in ("allow_always", "ask_always"):
                policies[name] = policy
        _write(policies)
        return policies


def clear_all() -> None:
    with _lock:
        try:
            PERMS_PATH.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            pass
