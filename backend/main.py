"""FastAPI entry point. Step 1: just serve a PC graph over synthetic NDR data."""
from __future__ import annotations

import json

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agent import secret_store
from agent.chat import stream_chat
from agent.explain import EdgeExplainRequest, stream_explanation
from agent.validate import validate_anthropic_key
from causal.pc import CollinearColumnsError, InsufficientDataError, run_pc
from causal.synthetic import generate, GROUND_TRUTH_EDGES
import asyncio
import io
import re

import pandas as pd
from fastapi.responses import HTMLResponse

from data import app_state, overrides, sigma_client, sigma_permissions, tabular_store

SYNTHETIC_SOURCE_ID = "__synthetic__"

app = FastAPI(title="Causality API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://[::1]:5173",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


class GraphRequest(BaseModel):
    alpha: float = 0.05
    corr_threshold: float = 0.3
    include_correlations: bool = True
    n_samples: int = 2000
    seed: int = 42


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.get("/state")
def get_state() -> dict:
    """Persisted UI session state. Currently just the last active data source."""
    active = app_state.get_active_source()
    return {"active_source": active.to_dict() if active else None}


class ApiKeyRequest(BaseModel):
    key: str


@app.get("/api-key")
def api_key_status() -> dict:
    return {"set": secret_store.is_set(), "source": secret_store.get_source()}


@app.post("/api-key")
async def set_api_key(req: ApiKeyRequest) -> dict:
    try:
        secret_store.set_key(req.key)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    persisted_path: str | None = None
    persist_error: str | None = None
    try:
        persisted_path = str(secret_store.persist_to_shell_rc(req.key))
    except Exception as e:
        persist_error = str(e)

    # Validate the key so the agent can fail fast if it's wrong, with no restart.
    validated, validation_error = await validate_anthropic_key(req.key)

    return {
        "set": True,
        "source": secret_store.get_source(),
        "persisted_path": persisted_path,
        "persist_error": persist_error,
        "validated": validated,
        "validation_error": validation_error,
    }


@app.delete("/api-key")
def clear_api_key() -> dict:
    secret_store.clear_key()
    removed_path: str | None = None
    try:
        path = secret_store.remove_from_shell_rc()
        removed_path = str(path) if path else None
    except Exception:
        pass
    return {"set": False, "source": None, "removed_from": removed_path}




@app.post("/graph/synthetic")
def graph_synthetic(req: GraphRequest) -> dict:
    df = generate(n=req.n_samples, seed=req.seed)
    g = run_pc(
        df,
        alpha=req.alpha,
        corr_threshold=req.corr_threshold,
        include_correlations=req.include_correlations,
    )
    graph = overrides.apply_to_graph(SYNTHETIC_SOURCE_ID, g.to_dict())
    app_state.set_active_source(
        app_state.ActiveSource(
            id=SYNTHETIC_SOURCE_ID,
            label="synthetic NDR",
            kind="synthetic",
            columns=[n["id"] for n in graph["nodes"]],
            rows=req.n_samples,
        )
    )
    return {
        "source_id": SYNTHETIC_SOURCE_ID,
        "graph": graph,
        "ground_truth_edges": [
            {"source": s, "target": t} for s, t in GROUND_TRUTH_EDGES
        ],
    }


def _source_to_dict(s: tabular_store.TabularSource) -> dict:
    return {
        "id": s.id,
        "name": s.name,
        "kind": s.kind,
        "columns": s.columns,
        "numeric_columns": s.numeric_columns,
        "n_rows": s.n_rows,
    }


@app.get("/sources")
def list_sources() -> dict:
    return {"sources": [_source_to_dict(s) for s in tabular_store.list_sources()]}


@app.post("/sources/csv/upload")
async def upload_csv(file: UploadFile = File(...)) -> dict:
    """Stream the upload to a temp file, then ingest via PyArrow.

    Avoids loading the entire CSV into memory; supports up to ~5M rows.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="missing filename")
    import tempfile
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".csv")
    try:
        chunk_size = 1024 * 1024  # 1MB chunks
        while True:
            chunk = await file.read(chunk_size)
            if not chunk:
                break
            tmp.write(chunk)
        tmp.close()
        try:
            src = tabular_store.ingest_csv_path(tmp.name, file.filename)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"failed to ingest CSV: {e}")
    finally:
        try:
            import os
            os.unlink(tmp.name)
        except OSError:
            pass
    return _source_to_dict(src)


@app.get("/sigma/status")
async def sigma_status() -> dict:
    return {"connected": await sigma_client.is_connected()}


def _flatten_exc(e: BaseException) -> str:
    """Walk into BaseExceptionGroup so we surface the real cause, not 'TaskGroup'."""
    parts: list[str] = []
    seen: set[int] = set()

    def visit(x: BaseException, depth: int = 0) -> None:
        if id(x) in seen or depth > 6:
            return
        seen.add(id(x))
        excs = getattr(x, "exceptions", None)
        if excs:
            for sub in excs:
                visit(sub, depth + 1)
        else:
            parts.append(f"{type(x).__name__}: {x}")
        if x.__cause__:
            visit(x.__cause__, depth + 1)

    visit(e)
    return "; ".join(parts) or f"{type(e).__name__}: {e}"


@app.post("/sigma/connect")
async def sigma_connect() -> dict:
    """Trigger OAuth (or no-op if already connected) by making one MCP call."""
    import traceback
    try:
        info = await asyncio.wait_for(sigma_client.begin_session(), timeout=300)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Sigma OAuth timed out")
    except BaseException as e:
        # Print full traceback to backend log so we can see the wire-level cause
        print("--- /sigma/connect failed ---", flush=True)
        traceback.print_exception(e)
        raise HTTPException(
            status_code=502, detail=f"Sigma connect failed: {_flatten_exc(e)}"
        )
    user = (info or {}).get("user", {}) if isinstance(info, dict) else {}
    return {"connected": True, "user": user}


@app.get("/sigma/oauth-callback")
async def sigma_oauth_callback(code: str | None = None, state: str | None = None,
                                error: str | None = None) -> HTMLResponse:
    if error:
        body = f"<h1>Sigma authorization failed</h1><p>{error}</p>"
        return HTMLResponse(body, status_code=400)
    if not code or not state:
        return HTMLResponse("<h1>Missing code/state</h1>", status_code=400)
    delivered = sigma_client.resolve_callback(code, state)
    body = (
        "<h1>Sigma connected.</h1>"
        "<p>You can close this tab and return to the app.</p>"
        if delivered
        else "<h1>No pending Sigma connect request.</h1>"
    )
    return HTMLResponse(body)


@app.post("/sigma/disconnect")
async def sigma_disconnect() -> dict:
    await sigma_client.disconnect()
    return {"connected": False}


@app.get("/sigma/config")
async def sigma_get_config() -> dict:
    return {
        "mcp_url": sigma_client.get_mcp_url(),
        "connected": await sigma_client.is_connected(),
    }


class SigmaConfigUpdate(BaseModel):
    mcp_url: str


@app.post("/sigma/config")
async def sigma_set_config(req: SigmaConfigUpdate) -> dict:
    """Update the MCP URL. Switching servers wipes the OAuth tokens since
    they're scoped to the previous server — the user will need to reconnect.
    """
    try:
        new_url = await sigma_client.change_mcp_url(req.mcp_url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"mcp_url": new_url, "connected": False}


@app.get("/sigma/tools")
async def sigma_tools() -> dict:
    if not await sigma_client.is_connected():
        raise HTTPException(status_code=409, detail="Not connected to Sigma")
    try:
        tools = await sigma_client.list_available_tools()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to list tools: {e}")
    policies = sigma_permissions.get_all()
    enriched = []
    for t in tools:
        enriched.append(
            {
                **t,
                "policy": policies.get(t["name"], sigma_permissions.DEFAULT_POLICY),
            }
        )
    return {"tools": enriched, "default_policy": sigma_permissions.DEFAULT_POLICY}


@app.get("/sigma/permissions")
def sigma_get_permissions() -> dict:
    return {
        "policies": sigma_permissions.get_all(),
        "default_policy": sigma_permissions.DEFAULT_POLICY,
    }


class SigmaPermissionsUpdate(BaseModel):
    policies: dict[str, str]


@app.post("/sigma/permissions")
def sigma_set_permissions(req: SigmaPermissionsUpdate) -> dict:
    valid: dict[str, sigma_permissions.Policy] = {}
    for k, v in req.policies.items():
        if v not in ("allow_always", "ask_always"):
            raise HTTPException(
                status_code=400, detail=f"unknown policy {v!r} for tool {k!r}"
            )
        valid[k] = v  # type: ignore[assignment]
    saved = sigma_permissions.set_many(valid)
    return {"policies": saved, "default_policy": sigma_permissions.DEFAULT_POLICY}


@app.get("/sigma/documents")
async def sigma_documents(collection: str = "recommendations", limit: int = 20) -> dict:
    try:
        result = await sigma_client.list_documents(collection, limit)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {"result": result}


class SigmaSearchRequest(BaseModel):
    query: str
    entity_types: list[str] | None = None
    limit: int = 10


@app.post("/sigma/search")
async def sigma_search(req: SigmaSearchRequest) -> dict:
    try:
        result = await sigma_client.search(req.query, req.entity_types, req.limit)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {"result": result}


class SigmaDescribeRequest(BaseModel):
    object: dict


@app.post("/sigma/describe")
async def sigma_describe(req: SigmaDescribeRequest) -> dict:
    try:
        result = await sigma_client.describe(req.object)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {"result": result}


class SigmaIngestRequest(BaseModel):
    data_model_id: str
    element_id: str
    columns: list[dict]  # [{id: str, label: str}]
    name: str  # human-readable, used as the data source display name
    limit: int = 1_000_000  # default cap; agent can lower
    page_size: int = 50_000


@app.post("/sigma/ingest")
async def sigma_ingest(req: SigmaIngestRequest) -> dict:
    """Run a SQL query against a data model element, paginated, and write rows
    to a Parquet-backed local data source. Supports up to 1M rows by default.
    """
    if not req.columns:
        raise HTTPException(status_code=400, detail="columns is empty")
    select_parts = [
        f'"{c["id"]}" AS "{_safe_label(c["label"])}"' for c in req.columns
    ]
    base_sql = (
        f"SELECT {', '.join(select_parts)} "
        f'FROM "datamodel"."{req.element_id}"'
    )
    payload = {"type": "datamodel", "dataModelId": req.data_model_id}
    try:
        chunks = await sigma_client.query_paginated(
            payload,
            base_sql,
            page_size=int(req.page_size),
            max_rows=int(req.limit),
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Sigma query failed: {e}")

    if not chunks:
        raise HTTPException(status_code=400, detail="Sigma query returned no rows")
    try:
        src = tabular_store.ingest_chunks(
            chunks, name=f"sigma:{req.name}", kind="sigma"
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _source_to_dict(src) | {"sigma_columns": len(req.columns)}


def _safe_label(label: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "_", label).strip("_")
    return s or "col"


@app.delete("/sources/{source_id}")
def delete_source(source_id: str) -> dict:
    try:
        tabular_store.delete_source(source_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"deleted": source_id}


class GraphFromSourceRequest(BaseModel):
    source_id: str
    columns: list[str]
    alpha: float = 0.05
    corr_threshold: float = 0.3
    include_correlations: bool = True


@app.post("/graph/from-source")
def graph_from_source(req: GraphFromSourceRequest) -> dict:
    if len(req.columns) < 2:
        raise HTTPException(status_code=400, detail="select at least 2 columns")
    try:
        df = tabular_store.read_dataframe(req.source_id, req.columns)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"source not found: {e}")
    n_total = len(df)
    try:
        g = run_pc(
            df,
            alpha=req.alpha,
            corr_threshold=req.corr_threshold,
            include_correlations=req.include_correlations,
        )
    except (CollinearColumnsError, InsufficientDataError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        # PC's Fisher's Z inverts a sub-correlation matrix and fails on
        # singular data even after we drop obvious collinearities.
        raise HTTPException(
            status_code=400,
            detail=(
                f"PC failed on this column set: {e}. "
                "Try dropping columns that are linear combinations of others "
                "(e.g., totals + their components, or current vs lagged values)."
            ),
        )
    graph = overrides.apply_to_graph(req.source_id, g.to_dict())
    try:
        src = tabular_store.get_source(req.source_id)
        label = src.name
    except KeyError:
        label = req.source_id
    app_state.set_active_source(
        app_state.ActiveSource(
            id=req.source_id,
            label=label,
            kind="csv",
            columns=req.columns,
            rows=n_total,
        )
    )
    return {"source_id": req.source_id, "graph": graph, "n_rows_used": n_total}


class SetOverrideRequest(BaseModel):
    source_id: str
    var_a: str
    var_b: str
    direction_from: str | None  # one of var_a/var_b, or null for "no link"


class ClearOverrideRequest(BaseModel):
    source_id: str
    var_a: str
    var_b: str


@app.get("/overrides")
def get_overrides(source_id: str) -> dict:
    return {
        "source_id": source_id,
        "overrides": [
            {"var_a": o.var_a, "var_b": o.var_b, "direction": o.direction}
            for o in overrides.list_overrides(source_id)
        ],
    }


@app.post("/overrides")
def post_override(req: SetOverrideRequest) -> dict:
    if req.var_a == req.var_b:
        raise HTTPException(status_code=400, detail="var_a and var_b must differ")
    try:
        o = overrides.set_override(
            req.source_id, req.var_a, req.var_b, req.direction_from
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"var_a": o.var_a, "var_b": o.var_b, "direction": o.direction}


@app.post("/overrides/clear")
def post_override_clear(req: ClearOverrideRequest) -> dict:
    return {"cleared": overrides.clear_override(req.source_id, req.var_a, req.var_b)}


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    graph_context: dict | None = None


@app.post("/chat")
async def chat(req: ChatRequest) -> StreamingResponse:
    if not secret_store.is_set():
        raise HTTPException(
            status_code=503,
            detail="Anthropic API key not set. Enter one in the app header, or export ANTHROPIC_API_KEY before starting the backend.",
        )
    convo: list[dict] = [{"role": m.role, "content": m.content} for m in req.messages]
    graph_ctx = req.graph_context

    async def event_stream():
        try:
            async for ev in stream_chat(convo, graph_ctx):
                yield f"data: {json.dumps(ev, default=str)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
            yield "data: {\"type\": \"done\"}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class ExplainEdgeRequest(BaseModel):
    source: str
    target: str
    type: str
    pearson_r: float
    all_columns: list[str]


@app.post("/explain-edge")
def explain_edge(req: ExplainEdgeRequest) -> StreamingResponse:
    try:
        chunks = stream_explanation(
            EdgeExplainRequest(
                source=req.source,
                target=req.target,
                type=req.type,
                pearson_r=req.pearson_r,
                all_columns=req.all_columns,
            )
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    def event_stream():
        try:
            for chunk in chunks:
                yield f"data: {json.dumps({'text': chunk})}\n\n"
            yield "data: {\"done\": true}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
