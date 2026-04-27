"""Local tabular data store backed by Parquet files.

Replaces the prior ChromaDB-based store. Each ingested data source is a
single Parquet file under `backend/.tabular/<id>.parquet`, with metadata
maintained in a JSON catalog. Built for analytical workloads up to ~1M rows:
column-pruned reads via PyArrow are millisecond-fast, writes are streaming
chunked, and the file format is the same one the rest of the data stack
already speaks.

API surface is intentionally minimal so callers (`main.py`, `agent/chat.py`)
can swap the storage backend later without touching anything else.
"""
from __future__ import annotations

import json
import re
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator, Literal

import pandas as pd
import pyarrow as pa
import pyarrow.csv as pacsv
import pyarrow.parquet as pq

ROOT = Path(".tabular")
CATALOG_PATH = ROOT / "catalog.json"
ID_PREFIX = "src_"
MAX_ROWS = 5_000_000  # hard upper bound to keep things sane

SourceKind = Literal["csv", "sigma", "synthetic"]


@dataclass
class TabularSource:
    id: str
    name: str
    columns: list[str]
    numeric_columns: list[str]
    n_rows: int
    kind: SourceKind = "csv"
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "columns": self.columns,
            "numeric_columns": self.numeric_columns,
            "n_rows": self.n_rows,
            "kind": self.kind,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TabularSource":
        return cls(
            id=d["id"],
            name=d["name"],
            columns=list(d.get("columns", [])),
            numeric_columns=list(d.get("numeric_columns", [])),
            n_rows=int(d.get("n_rows", 0) or 0),
            kind=d.get("kind", "csv"),
            created_at=d.get("created_at", datetime.now(timezone.utc).isoformat()),
        )


_lock = threading.Lock()


# ---------- Catalog helpers ----------

def _ensure_root() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)


def _read_catalog() -> dict[str, dict]:
    if not CATALOG_PATH.exists():
        return {}
    try:
        return json.loads(CATALOG_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _write_catalog(catalog: dict[str, dict]) -> None:
    _ensure_root()
    CATALOG_PATH.write_text(json.dumps(catalog, indent=2))


def _parquet_path(source_id: str) -> Path:
    return ROOT / f"{source_id}.parquet"


def _slugify(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", name).strip("_").lower()
    return s or "src"


def _new_id(name: str) -> str:
    return f"{ID_PREFIX}{_slugify(name)}_{uuid.uuid4().hex[:8]}"


def _is_numeric_arrow(t: pa.DataType) -> bool:
    return (
        pa.types.is_floating(t)
        or pa.types.is_integer(t)
        or pa.types.is_decimal(t)
    )


def _columns_from_schema(schema: pa.Schema) -> tuple[list[str], list[str]]:
    columns = [f.name for f in schema]
    numeric = [f.name for f in schema if _is_numeric_arrow(f.type)]
    return columns, numeric


# ---------- Public API ----------

def ingest_csv(file_bytes: bytes, filename: str) -> TabularSource:
    """In-memory CSV ingest (small files). For large files use ingest_csv_path."""
    import io
    return _ingest_table(pacsv.read_csv(io.BytesIO(file_bytes)), filename, kind="csv")


def ingest_csv_path(path: str | Path, filename: str) -> TabularSource:
    """Stream a CSV from disk via PyArrow, write to Parquet."""
    table = pacsv.read_csv(str(path))
    return _ingest_table(table, filename, kind="csv")


def _ingest_table(table: pa.Table, name: str, kind: SourceKind) -> TabularSource:
    if table.num_rows == 0:
        raise ValueError("table has 0 rows")
    if table.num_rows > MAX_ROWS:
        raise ValueError(
            f"table exceeds {MAX_ROWS:,} rows (got {table.num_rows:,})"
        )
    source_id = _new_id(name)
    parquet_path = _parquet_path(source_id)
    _ensure_root()
    pq.write_table(table, parquet_path, compression="zstd")
    columns, numeric = _columns_from_schema(table.schema)
    src = TabularSource(
        id=source_id,
        name=name,
        columns=columns,
        numeric_columns=numeric,
        n_rows=table.num_rows,
        kind=kind,
    )
    with _lock:
        catalog = _read_catalog()
        catalog[source_id] = src.to_dict()
        _write_catalog(catalog)
    return src


def ingest_dataframe(df: pd.DataFrame, name: str, kind: SourceKind = "csv") -> TabularSource:
    table = pa.Table.from_pandas(df, preserve_index=False)
    return _ingest_table(table, name, kind=kind)


def ingest_chunks(
    chunks: Iterable[pd.DataFrame], name: str, kind: SourceKind = "sigma"
) -> TabularSource:
    """Stream DataFrame chunks to a single Parquet file. Used by the Sigma
    paginated ingest. Raises ValueError if total rows exceed MAX_ROWS."""
    source_id = _new_id(name)
    parquet_path = _parquet_path(source_id)
    _ensure_root()

    writer: pq.ParquetWriter | None = None
    n_rows = 0
    columns: list[str] = []
    numeric: list[str] = []
    try:
        for df in chunks:
            if df.empty:
                continue
            table = pa.Table.from_pandas(df, preserve_index=False)
            if writer is None:
                columns, numeric = _columns_from_schema(table.schema)
                writer = pq.ParquetWriter(parquet_path, table.schema, compression="zstd")
            writer.write_table(table)
            n_rows += table.num_rows
            if n_rows > MAX_ROWS:
                raise ValueError(
                    f"ingest exceeded {MAX_ROWS:,} rows (got {n_rows:,}); aborted"
                )
    except BaseException:
        if writer is not None:
            writer.close()
        parquet_path.unlink(missing_ok=True)
        raise
    finally:
        if writer is not None:
            writer.close()

    if n_rows == 0:
        parquet_path.unlink(missing_ok=True)
        raise ValueError("no rows written")

    src = TabularSource(
        id=source_id,
        name=name,
        columns=columns,
        numeric_columns=numeric,
        n_rows=n_rows,
        kind=kind,
    )
    with _lock:
        catalog = _read_catalog()
        catalog[source_id] = src.to_dict()
        _write_catalog(catalog)
    return src


def list_sources() -> list[TabularSource]:
    with _lock:
        catalog = _read_catalog()
    out: list[TabularSource] = []
    for d in catalog.values():
        try:
            out.append(TabularSource.from_dict(d))
        except (KeyError, ValueError):
            continue
    out.sort(key=lambda s: s.created_at, reverse=True)
    return out


def get_source(source_id: str) -> TabularSource:
    with _lock:
        catalog = _read_catalog()
    d = catalog.get(source_id)
    if not d:
        raise KeyError(source_id)
    return TabularSource.from_dict(d)


def delete_source(source_id: str) -> None:
    with _lock:
        catalog = _read_catalog()
        if source_id in catalog:
            del catalog[source_id]
            _write_catalog(catalog)
    _parquet_path(source_id).unlink(missing_ok=True)


def read_dataframe(source_id: str, columns: list[str]) -> pd.DataFrame:
    """Read selected columns as a DataFrame, coerced to numeric (NaN where the
    cell is non-numeric). Caller is responsible for handling NaNs (e.g. PC
    runs `_drop_sparse` then `dropna` so a single mostly-null column doesn't
    wipe out the whole sample)."""
    path = _parquet_path(source_id)
    if not path.exists():
        raise FileNotFoundError(source_id)
    table = pq.read_table(path, columns=columns)
    df = table.to_pandas()
    for col in columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def iter_chunks_from_dataframes(dfs: Iterable[pd.DataFrame]) -> Iterator[pd.DataFrame]:
    """Helper to make `chunks` arg from any dataframe iterable."""
    for df in dfs:
        if df is not None and not df.empty:
            yield df
