"""Persisted Sigma MCP URL.

Stored alongside the OAuth tokens so the URL the user picks survives
backend restarts. Defaults to the staging MCP endpoint when nothing has
been written yet.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from urllib.parse import urlparse

DEFAULT_URL = "https://api.staging.sigmacomputing.io/mcp/v2"
CONFIG_PATH = Path.home() / ".config" / "causality" / "sigma_config.json"

_lock = threading.Lock()


def _read() -> dict:
    try:
        return json.loads(CONFIG_PATH.read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _write(data: dict) -> None:
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps(data, indent=2))
        try:
            CONFIG_PATH.chmod(0o600)
        except OSError:
            pass
    except OSError:
        pass


def get_url() -> str:
    with _lock:
        data = _read()
    url = data.get("mcp_url")
    return url if isinstance(url, str) and url else DEFAULT_URL


def set_url(url: str) -> str:
    """Validate + persist a new MCP URL. Returns the stored URL.

    Raises ValueError if the URL is malformed.
    """
    cleaned = (url or "").strip().rstrip("/")
    if not cleaned:
        raise ValueError("URL is empty")
    parsed = urlparse(cleaned)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("URL must start with http:// or https://")
    if not parsed.netloc:
        raise ValueError("URL is missing a host")
    with _lock:
        data = _read()
        data["mcp_url"] = cleaned
        _write(data)
    return cleaned


def reset_to_default() -> str:
    return set_url(DEFAULT_URL)
