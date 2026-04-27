"""User edge-direction overrides.

Stored in a small SQLite file. Keyed by (source_id, var_a, var_b) where
var_a < var_b alphabetically — so we identify an edge by the unordered pair
and store the user's chosen direction separately.

direction values:
    "a_to_b" — user asserts var_a causes var_b
    "b_to_a" — user asserts var_b causes var_a
    "none"   — user asserts no causal link between this pair
"""
from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

DB_PATH = Path("overrides.sqlite3")
Direction = Literal["a_to_b", "b_to_a", "none"]

_lock = threading.Lock()
_initialized = False


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def _init() -> None:
    global _initialized
    if _initialized:
        return
    with _lock, _conn() as c:
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS overrides (
                source_id TEXT NOT NULL,
                var_a TEXT NOT NULL,
                var_b TEXT NOT NULL,
                direction TEXT NOT NULL CHECK (direction IN ('a_to_b','b_to_a','none')),
                PRIMARY KEY (source_id, var_a, var_b)
            )
            """
        )
        _initialized = True


def _normalize(x: str, y: str) -> tuple[str, str]:
    return (x, y) if x < y else (y, x)


@dataclass
class Override:
    source_id: str
    var_a: str
    var_b: str
    direction: Direction


def set_override(source_id: str, x: str, y: str, want_directed_from: str | None) -> Override:
    """Record an override. If `want_directed_from` is one of x/y, that variable
    becomes the cause. If None, the edge is marked as no causal link."""
    _init()
    a, b = _normalize(x, y)
    if want_directed_from is None:
        direction: Direction = "none"
    elif want_directed_from == a:
        direction = "a_to_b"
    elif want_directed_from == b:
        direction = "b_to_a"
    else:
        raise ValueError(f"want_directed_from {want_directed_from!r} not in pair ({x},{y})")
    with _lock, _conn() as c:
        c.execute(
            """INSERT INTO overrides (source_id, var_a, var_b, direction)
               VALUES (?,?,?,?)
               ON CONFLICT(source_id, var_a, var_b) DO UPDATE SET direction=excluded.direction""",
            (source_id, a, b, direction),
        )
    return Override(source_id, a, b, direction)


def clear_override(source_id: str, x: str, y: str) -> bool:
    _init()
    a, b = _normalize(x, y)
    with _lock, _conn() as c:
        cur = c.execute(
            "DELETE FROM overrides WHERE source_id=? AND var_a=? AND var_b=?",
            (source_id, a, b),
        )
        return cur.rowcount > 0


def list_overrides(source_id: str) -> list[Override]:
    _init()
    with _lock, _conn() as c:
        rows = c.execute(
            "SELECT source_id, var_a, var_b, direction FROM overrides WHERE source_id=?",
            (source_id,),
        ).fetchall()
    return [Override(r["source_id"], r["var_a"], r["var_b"], r["direction"]) for r in rows]


def apply_to_graph(source_id: str, graph: dict) -> dict:
    """Mutate-and-return: apply user overrides to a graph dict (from Graph.to_dict())."""
    overrides = {(_normalize(o.var_a, o.var_b), o.direction) for o in list_overrides(source_id)}
    if not overrides:
        return graph

    overrides_by_pair = {
        (a, b): direction for ((a, b), direction) in overrides
    }
    pairs_with_override = set(overrides_by_pair.keys())

    new_edges = []
    seen_pairs: set[tuple[str, str]] = set()
    for e in graph["edges"]:
        pair = _normalize(e["source"], e["target"])
        if pair in pairs_with_override:
            seen_pairs.add(pair)
            direction = overrides_by_pair[pair]
            if direction == "none":
                continue
            a, b = pair
            src, tgt = (a, b) if direction == "a_to_b" else (b, a)
            new_edges.append({
                **e,
                "source": src,
                "target": tgt,
                "type": "user_override",
                "metadata": {**e.get("metadata", {}), "overridden_from": e["type"]},
            })
        else:
            new_edges.append(e)

    # Add overrides for pairs that PC found no edge for at all (e.g., user
    # adding a causal claim where PC was silent).
    node_ids = {n["id"] for n in graph["nodes"]}
    for (a, b), direction in overrides_by_pair.items():
        if (a, b) in seen_pairs:
            continue
        if direction == "none":
            continue
        if a not in node_ids or b not in node_ids:
            continue
        src, tgt = (a, b) if direction == "a_to_b" else (b, a)
        new_edges.append({
            "source": src,
            "target": tgt,
            "type": "user_override",
            "strength": 0.0,
            "metadata": {"overridden_from": "none"},
        })

    return {**graph, "edges": new_edges}
