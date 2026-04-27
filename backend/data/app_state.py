"""Persisted UI session state.

Today this only tracks which data source the user was last looking at, so the
graph view comes back the way they left it after a backend restart or page
reload. Stored as a tiny JSON file alongside the parquet catalog.
"""
from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

STATE_PATH = Path(".tabular") / "app_state.json"
SourceKind = Literal["synthetic", "csv", "sigma"]

_lock = threading.Lock()


@dataclass
class ActiveSource:
    id: str
    label: str
    kind: SourceKind
    columns: list[str] = field(default_factory=list)
    rows: int = 0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "kind": self.kind,
            "columns": self.columns,
            "rows": self.rows,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ActiveSource":
        return cls(
            id=str(d.get("id", "__synthetic__")),
            label=str(d.get("label", "synthetic NDR")),
            kind=d.get("kind", "synthetic"),
            columns=list(d.get("columns", [])),
            rows=int(d.get("rows", 0) or 0),
        )


def _read() -> dict:
    try:
        return json.loads(STATE_PATH.read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _write(data: dict) -> None:
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(data, indent=2))
    except OSError:
        pass


def get_active_source() -> ActiveSource | None:
    with _lock:
        data = _read()
    blob = data.get("active_source")
    if not isinstance(blob, dict):
        return None
    try:
        return ActiveSource.from_dict(blob)
    except (TypeError, ValueError):
        return None


def set_active_source(active: ActiveSource) -> None:
    with _lock:
        data = _read()
        data["active_source"] = active.to_dict()
        _write(data)


def clear_active_source() -> None:
    with _lock:
        data = _read()
        data.pop("active_source", None)
        _write(data)
