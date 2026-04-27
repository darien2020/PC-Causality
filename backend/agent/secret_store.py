"""In-memory holder for the user's Anthropic API key.

Single-local-user app. Key lives in process memory only; lost on restart.
At startup, attempts to load from the ANTHROPIC_API_KEY env var.

When the user enters a key via the UI, we also write `export ANTHROPIC_API_KEY=...`
to their shell rc file (~/.zshrc or ~/.bashrc, picked from $SHELL) so it survives
backend restarts on subsequent shell sessions.

Tracks the source so the UI can distinguish env-derived from user-entered keys.
"""
from __future__ import annotations

import os
import re
import threading
from pathlib import Path
from typing import Literal

Source = Literal["env", "user"]

EXPORT_PATTERN = re.compile(
    r"^[ \t]*export[ \t]+ANTHROPIC_API_KEY[ \t]*=.*$",
    re.MULTILINE,
)
EXPORT_MARKER = "# Causality app — Anthropic API key"

_lock = threading.Lock()
_env = os.environ.get("ANTHROPIC_API_KEY") or None
_key: str | None = _env
_source: Source | None = "env" if _env else None


def get_key() -> str | None:
    with _lock:
        return _key


def get_source() -> Source | None:
    with _lock:
        return _source


def set_key(value: str) -> None:
    global _key, _source
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("key is empty")
    with _lock:
        _key = cleaned
        _source = "user"


def clear_key() -> None:
    global _key, _source
    with _lock:
        _key = None
        _source = None


def is_set() -> bool:
    return get_key() is not None


# ---------- Shell rc persistence ----------

def _shell_rc_path() -> Path:
    """Pick the rc file based on $SHELL; create directory if needed."""
    shell = os.environ.get("SHELL", "")
    home = Path(os.path.expanduser("~"))
    if shell.endswith("zsh"):
        return home / ".zshrc"
    if shell.endswith("bash"):
        # Prefer .bashrc on Linux, .bash_profile on macOS where login shells run it.
        if (home / ".bash_profile").exists():
            return home / ".bash_profile"
        return home / ".bashrc"
    # Sensible default
    return home / ".zshrc"


def _strip_existing(content: str) -> str:
    """Remove any prior export ANTHROPIC_API_KEY line + our marker comment."""
    cleaned = EXPORT_PATTERN.sub("", content)
    # Remove a marker comment immediately followed by a blank line, if present
    cleaned = re.sub(rf"^{re.escape(EXPORT_MARKER)}\s*\n", "", cleaned, flags=re.MULTILINE)
    # Collapse triple blank lines
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned


def persist_to_shell_rc(key: str) -> Path:
    """Append (or replace) `export ANTHROPIC_API_KEY=...` in the shell rc file."""
    path = _shell_rc_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    content = path.read_text() if path.exists() else ""
    cleaned = _strip_existing(content)
    if cleaned and not cleaned.endswith("\n"):
        cleaned += "\n"
    block = f"\n{EXPORT_MARKER}\nexport ANTHROPIC_API_KEY={_shell_quote(key)}\n"
    path.write_text(cleaned + block)
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path


def remove_from_shell_rc() -> Path | None:
    """Remove our export line from the shell rc file. Returns the path if anything changed."""
    path = _shell_rc_path()
    if not path.exists():
        return None
    content = path.read_text()
    cleaned = _strip_existing(content)
    if cleaned == content:
        return None
    path.write_text(cleaned)
    return path


def _shell_quote(s: str) -> str:
    """Wrap s in single quotes, escaping any single quotes inside."""
    return "'" + s.replace("'", "'\\''") + "'"
