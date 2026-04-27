"""PC algorithm wrapper → typed-edge graph.

Edge types in the output:
    causal_directed    — PC oriented the edge A→B
    causal_undirected  — in CPDAG equivalence class, direction ambiguous
    correlation        — pair not in PC skeleton but |Pearson r| >= corr_threshold
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Literal

import numpy as np
import pandas as pd
from causallearn.search.ConstraintBased.PC import pc
from causallearn.utils.cit import fisherz

EdgeType = Literal["causal_directed", "causal_undirected", "correlation"]


@dataclass
class Edge:
    source: str
    target: str
    type: EdgeType
    strength: float  # |r| for correlation; |r| for causal edges as weight proxy
    metadata: dict

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Node:
    id: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Graph:
    nodes: list[Node]
    edges: list[Edge]
    dropped_columns: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "dropped_columns": list(self.dropped_columns),
        }


class CollinearColumnsError(ValueError):
    """Raised when the correlation matrix is too rank-deficient to run PC even
    after attempting to drop the most-redundant columns."""


class InsufficientDataError(ValueError):
    """Raised when there aren't enough complete rows to run PC."""


def _impute_missing(df: pd.DataFrame, fill_value: float = 0.0) -> pd.DataFrame:
    """Replace NaN with `fill_value` (default 0).

    For typical SaaS engagement signals (calls, events, chat counts), NaN
    means "no activity" and 0 is the right semantic. This avoids both the
    "dropna kills all rows" failure mode and the "drop sparse columns wipes
    out the user's selection" failure mode.
    """
    return df.fillna(fill_value)


def _drop_collinear(
    df: pd.DataFrame, columns: list[str], threshold: float = 0.999
) -> tuple[list[str], list[str]]:
    """Greedy drop of columns whose abs Pearson r ≥ threshold with a kept column.

    Also drops constant columns (zero variance). Returns (kept, dropped).
    """
    kept: list[str] = []
    dropped: list[str] = []
    for col in columns:
        col_var = df[col].var()
        if not np.isfinite(col_var) or col_var == 0:
            dropped.append(col)
            continue
        is_redundant = False
        for k in kept:
            r = df[col].corr(df[k])
            if np.isfinite(r) and abs(r) >= threshold:
                is_redundant = True
                break
        if is_redundant:
            dropped.append(col)
        else:
            kept.append(col)
    return kept, dropped


MIN_ROWS_FOR_PC = 30


def run_pc(
    df: pd.DataFrame,
    alpha: float = 0.05,
    corr_threshold: float = 0.3,
    include_correlations: bool = True,
    subsample: int | None = 200_000,
    seed: int = 42,
) -> Graph:
    """Run PC on df's numeric columns and return a typed-edge graph.

    Pre-processing pipeline:
      1. Subsample to `subsample` rows if df is huge.
      2. Zero-impute NaN values — for the SaaS engagement metrics this app
         targets, missing usually means "no activity," and 0 is the right
         semantic. This keeps every column the user selected and every row.
      3. Drop near-perfectly-collinear columns (PC's Fisher's Z crashes on a
         singular correlation matrix).
      4. Run PC.
    """
    if subsample is not None and len(df) > subsample:
        df = df.sample(n=subsample, random_state=seed)

    numeric_cols = list(df.select_dtypes(include=[np.number]).columns)
    df = df[numeric_cols]

    # 2. Zero-impute instead of dropna so a sparsely-populated column doesn't
    #    nuke all the rows or force the user to manually unselect it.
    df = _impute_missing(df, fill_value=0.0)

    if len(df) < MIN_ROWS_FOR_PC:
        raise InsufficientDataError(
            f"Only {len(df)} rows; PC needs at least {MIN_ROWS_FOR_PC}."
        )

    # 3. Drop collinear columns (kept columns AFTER imputation; constant cols
    #    introduced by zero-imputation get dropped here too).
    kept, dropped_collinear = _drop_collinear(df, numeric_cols)
    if dropped_collinear:
        df = df[kept]

    data = df.to_numpy()
    columns = list(df.columns)
    n = len(columns)
    if n < 2:
        raise CollinearColumnsError(
            "After dropping collinear/constant columns, fewer than 2 remain. "
            f"Dropped: {dropped_collinear}"
        )

    dropped = dropped_collinear

    cg = pc(data, alpha=alpha, indep_test=fisherz, show_progress=False)
    adj = cg.G.graph  # (n,n) matrix. causal-learn convention:
    # adj[i,j] == 1  and  adj[j,i] == -1  ⇒  j → i
    # adj[i,j] == -1 and  adj[j,i] == -1  ⇒  undirected i — j

    corr = df[columns].corr().to_numpy()

    seen: set[tuple[int, int]] = set()
    edges: list[Edge] = []

    def _safe_r(i: int, j: int) -> tuple[float, float]:
        """Return (r, strength) coercing NaN/inf to 0 — keeps JSON serializable."""
        v = float(corr[i, j])
        if not np.isfinite(v):
            return 0.0, 0.0
        return v, abs(v)

    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            key = tuple(sorted((i, j)))
            if key in seen:
                continue
            a, b = adj[i, j], adj[j, i]
            r, strength = _safe_r(i, j)

            if a == 1 and b == -1:
                edges.append(Edge(columns[j], columns[i], "causal_directed",
                                  strength, {"pearson_r": r}))
                seen.add(key)
            elif a == -1 and b == 1:
                edges.append(Edge(columns[i], columns[j], "causal_directed",
                                  strength, {"pearson_r": r}))
                seen.add(key)
            elif a == -1 and b == -1:
                s, t = sorted((columns[i], columns[j]))
                edges.append(Edge(s, t, "causal_undirected", strength,
                                  {"pearson_r": r}))
                seen.add(key)

    if include_correlations:
        for i in range(n):
            for j in range(i + 1, n):
                if (i, j) in seen:
                    continue
                r, strength = _safe_r(i, j)
                if strength >= corr_threshold:
                    edges.append(Edge(columns[i], columns[j], "correlation",
                                      strength, {"pearson_r": r}))

    nodes = [Node(c) for c in columns]
    return Graph(nodes, edges, dropped_columns=dropped)
