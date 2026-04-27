"""Sigma MCP client.

Uses the official MCP Python SDK over Streamable HTTP. OAuth (with dynamic
client registration + PKCE) is handled by the SDK's OAuthClientProvider; we
supply storage, a browser-launching redirect handler, and a callback handler
that waits on an asyncio future fulfilled by FastAPI's /sigma/oauth-callback
endpoint.

Tokens persist to disk so the connection survives backend restarts. The MCP
SDK refreshes expired access tokens automatically using the stored refresh
token — so a normal restart needs no user interaction.
"""
from __future__ import annotations

import asyncio
import json
import threading
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from mcp import ClientSession
from mcp.client.auth import OAuthClientProvider, TokenStorage
from mcp.client.streamable_http import streamablehttp_client
from mcp.shared.auth import OAuthClientInformationFull, OAuthClientMetadata, OAuthToken

SIGMA_MCP_URL = "https://api.staging.sigmacomputing.io/mcp/v2"
REDIRECT_URI = "http://127.0.0.1:8765/sigma/oauth-callback"
TOKEN_PATH = Path.home() / ".config" / "causality" / "sigma_tokens.json"


class _FileTokenStorage(TokenStorage):
    """OAuth tokens + dynamic-client-registration info persisted to one JSON file.

    Re-reads the file on every get to pick up out-of-band changes (e.g. user
    completing OAuth in another process, or a manual edit). Writes update an
    in-memory cache too so the SDK's tight call sequence sees consistent state.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._tokens: OAuthToken | None = None
        self._client: OAuthClientInformationFull | None = None
        self._lock = threading.Lock()

    def _read(self) -> dict:
        try:
            return json.loads(self._path.read_text())
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}

    def _save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            payload: dict = {}
            if self._tokens is not None:
                payload["tokens"] = json.loads(self._tokens.model_dump_json())
            if self._client is not None:
                payload["client_info"] = json.loads(self._client.model_dump_json())
            self._path.write_text(json.dumps(payload, indent=2))
            try:
                self._path.chmod(0o600)
            except OSError:
                pass
        except OSError:
            pass

    async def get_tokens(self) -> OAuthToken | None:
        with self._lock:
            data = self._read()
            try:
                if isinstance(data.get("tokens"), dict):
                    self._tokens = OAuthToken.model_validate(data["tokens"])
                else:
                    self._tokens = None
            except Exception:
                self._tokens = None
            return self._tokens

    async def set_tokens(self, tokens: OAuthToken) -> None:
        with self._lock:
            self._tokens = tokens
            self._save()

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        with self._lock:
            data = self._read()
            try:
                if isinstance(data.get("client_info"), dict):
                    self._client = OAuthClientInformationFull.model_validate(
                        data["client_info"]
                    )
                else:
                    self._client = None
            except Exception:
                self._client = None
            return self._client

    async def set_client_info(
        self, client_info: OAuthClientInformationFull
    ) -> None:
        with self._lock:
            self._client = client_info
            self._save()

    def clear(self) -> None:
        with self._lock:
            self._tokens = None
            self._client = None
            try:
                self._path.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                pass


_storage = _FileTokenStorage(TOKEN_PATH)
_callback_future: asyncio.Future[tuple[str, str]] | None = None
_callback_lock = threading.Lock()


async def _redirect_handler(authorization_url: str) -> None:
    webbrowser.open(authorization_url, new=1, autoraise=True)


async def _callback_handler() -> tuple[str, str]:
    """Block until /sigma/oauth-callback resolves the future."""
    global _callback_future
    loop = asyncio.get_running_loop()
    with _callback_lock:
        _callback_future = loop.create_future()
        fut = _callback_future
    try:
        return await asyncio.wait_for(fut, timeout=300)
    finally:
        with _callback_lock:
            _callback_future = None


def resolve_callback(code: str, state: str) -> bool:
    """Called by the FastAPI callback endpoint to deliver the auth code."""
    with _callback_lock:
        fut = _callback_future
    if fut is None or fut.done():
        return False
    fut.get_loop().call_soon_threadsafe(fut.set_result, (code, state))
    return True


def _oauth_provider() -> OAuthClientProvider:
    return OAuthClientProvider(
        server_url=SIGMA_MCP_URL,
        client_metadata=OAuthClientMetadata(
            client_name="Causality (local)",
            redirect_uris=[REDIRECT_URI],
            grant_types=["authorization_code", "refresh_token"],
            response_types=["code"],
            # Public client doing PKCE — no client secret.
            token_endpoint_auth_method="none",
        ),
        storage=_storage,
        redirect_handler=_redirect_handler,
        callback_handler=_callback_handler,
    )


@asynccontextmanager
async def session():
    """Open an authenticated MCP session. Triggers OAuth on first call."""
    auth = _oauth_provider()
    async with streamablehttp_client(SIGMA_MCP_URL, auth=auth) as (read, write, _):
        async with ClientSession(read, write) as s:
            await s.initialize()
            yield s


async def is_connected() -> bool:
    return (await _storage.get_tokens()) is not None


async def disconnect() -> None:
    _storage.clear()


def _unwrap_tool_result(result: Any) -> Any:
    """Convert MCP CallToolResult into a plain Python value."""
    if not getattr(result, "content", None):
        return None
    block = result.content[0]
    text = getattr(block, "text", None)
    if text is None:
        return None
    import json
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return text


async def call_tool(name: str, args: dict | None = None) -> Any:
    """Call a Sigma MCP tool.

    Sigma documents `begin_session` as REQUIRED before any other tool in a
    conversation. Each call here opens a fresh Streamable HTTP session, so we
    invoke `begin_session` first within the same session for non-init calls.
    """
    async with session() as s:
        if name != "begin_session":
            try:
                await s.call_tool("begin_session", {})
            except Exception:
                # If begin_session fails, fall through and let the actual call
                # surface the real error rather than masking it.
                pass
        result = await s.call_tool(name, args or {})
        return _unwrap_tool_result(result)


async def list_available_tools() -> list[dict]:
    """Ask the Sigma MCP server what tools it exposes."""
    async with session() as s:
        result = await s.list_tools()
        out: list[dict] = []
        for t in result.tools:
            out.append(
                {
                    "name": t.name,
                    "description": (t.description or "").strip(),
                    "input_schema": getattr(t, "inputSchema", None) or {},
                }
            )
        return out


# Convenience wrappers for the Sigma tools we use ----------------------

async def begin_session() -> Any:
    return await call_tool("begin_session", {})


async def list_documents(collection: str, limit: int = 20) -> Any:
    return await call_tool("list_documents", {"collection": collection, "limit": limit})


async def search(query: str, entity_types: list[str] | None = None, limit: int = 10) -> Any:
    # Sigma's MCP requires `entityTypes` to be a non-empty array even though
    # the docs say "omit to search across all types" — default to everything.
    types = entity_types if entity_types else [
        "workbook",
        "dataModel",
        "dataModelElement",
        "table",
    ]
    args: dict[str, Any] = {"query": query, "entityTypes": types, "limit": limit}
    return await call_tool("search", args)


async def describe(obj: dict) -> Any:
    return await call_tool("describe", {"object": obj})


async def query(payload: dict) -> Any:
    return await call_tool("query", {"query": payload})


async def query_paginated(
    base_payload: dict,
    base_sql: str,
    page_size: int = 50_000,
    max_rows: int = 1_000_000,
) -> list:
    """Run a SQL query repeatedly with LIMIT/OFFSET, accumulating rows.

    `base_payload` is `{type, dataModelId/workbookId/connectionId}` (no `sql`).
    `base_sql` should NOT contain LIMIT/OFFSET — we append them.
    Returns a list of row dicts (or list of CSV strings if Sigma returns CSV).

    Stops early when a page returns fewer than `page_size` rows or when
    `max_rows` is reached.
    """
    import io
    import pandas as pd  # local import keeps cold-start light

    base_sql = base_sql.rstrip().rstrip(";")
    offset = 0
    chunks: list = []
    total = 0

    while total < max_rows:
        remaining = max_rows - total
        page = min(page_size, remaining)
        sql = f"{base_sql} LIMIT {page} OFFSET {offset}"
        payload = {**base_payload, "sql": sql}
        result = await query(payload)
        df = _result_to_dataframe(result)
        if df.empty:
            break
        chunks.append(df)
        total += len(df)
        offset += len(df)
        if len(df) < page:
            break  # short page = end of data
    return chunks


def _result_to_dataframe(result) -> "pd.DataFrame":
    """Normalize a Sigma `query` tool result into a DataFrame.

    Sigma's MCP returns one of:
      - {columns: [str], rows: [[val]]}  — positional rows + separate header
      - {rows: [{col: val}]}             — list of dicts
      - {csv: "..."} or a CSV string     — CSV text
      - [[...]] / [{...}]                — bare list
    Most importantly, when the response has a `columns` array, those names
    must be applied to the rows — otherwise pandas falls back to integer
    column indices and the parquet ends up with columns named "0", "1", ...
    """
    import io
    import pandas as pd
    if result is None:
        return pd.DataFrame()
    if isinstance(result, str):
        try:
            return pd.read_csv(io.StringIO(result))
        except Exception:
            return pd.DataFrame()
    if isinstance(result, dict):
        cols = result.get("columns")
        # Preferred: explicit columns + positional rows
        for key in ("rows", "data", "results"):
            v = result.get(key)
            if isinstance(v, list):
                if v and isinstance(v[0], dict):
                    return pd.DataFrame(v)  # list of dicts already named
                if isinstance(cols, list) and cols:
                    return pd.DataFrame(v, columns=list(cols))
                return pd.DataFrame(v)
        if isinstance(result.get("csv"), str):
            try:
                return pd.read_csv(io.StringIO(result["csv"]))
            except Exception:
                return pd.DataFrame()
    if isinstance(result, list):
        return pd.DataFrame(result)
    return pd.DataFrame()
