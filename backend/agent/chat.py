"""Causality chat agent.

Claude (Opus 4.7) with tool use. The tool surface wraps our Sigma MCP client +
local Chroma ingest, so the user can ask "find a workbook about NDR" or "load
the MRR data into the graph" in natural language.

Streamed via SSE — yields a sequence of typed events the frontend can render
into a chat bubble + inline tool-use chips.
"""
from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any, Literal

import anthropic
import pandas as pd

from agent.secret_store import get_key
from causal.pc import (
    CollinearColumnsError,
    InsufficientDataError,
    run_pc as _run_pc_algo,
)
from data import app_state, overrides, sigma_client, tabular_store

MODEL = "claude-opus-4-7"

SYSTEM_PROMPT = """You are the Causality Agent in an app that runs the PC causal-discovery algorithm on numeric data and renders the result as a typed-edge DAG. The app is focused on understanding drivers of Net Dollar Retention (NDR).

You have two distinct jobs:

(A) DATA DISCOVERY — find Sigma objects and load them into the app.
    Tools talk to the user's Sigma Computing workspace via MCP.
    Workflow:
    1. ANY time the user mentions a name, topic, or keyword that could correspond to a Sigma object (workbook, data model, table), call sigma_search. Default to broad searches across all entity types — do not restrict entity_types unless the user is specific (e.g. "find a workbook called…"). If the first search returns nothing, try a broader/shorter query before giving up. Do not say "I couldn't find it" without actually calling sigma_search at least once.
    2. Summarize what you found in 1–2 sentences. If multiple candidates exist, ask which to use.
    3. For data models: call sigma_describe_data_model to list elements, then sigma_describe_element to see columns.
    4. Pick a GENEROUS set of numeric columns — aim for 15–30 when the data model has many. PC works better with more variables. Always include the outcome (NDR/MRR/ARR), at least 2–3 categories of candidate drivers (engagement, financial, support, account context, time signals), and any "change" or "previous-period" variables. Skip ONLY: text columns, IDs/UUIDs, dates, free-text fields, and pure category labels (region, segment, etc.). Don't be conservative — when in doubt, include the column. Numeric flags (0/1) like `customer_is_churned` ARE useful and should be included.
    5. Call sigma_ingest_element to pull rows. The default cap is 1,000,000 rows — only lower it if the user asks. Capture the returned `collection_id`.
    6. IMMEDIATELY call run_pc with that `collection_id` so the DAG renders. Don't ask permission first — running PC is the whole point of ingesting. After it returns, summarize the most interesting causal_directed edges in 1–2 sentences.

(B) RELATIONSHIP INTERPRETATION — explain edges in the current graph.
    The current graph (nodes + typed edges + Pearson r) is given to you as a system reminder before the user's message. Edge types:
    - causal_directed: PC inferred a direction (source → target).
    - causal_undirected: PC found a causal link but cannot orient it (Markov equivalence). Both orientations are statistically consistent.
    - correlation: pair is associated but PC found a separating set; likely explained by other variables.
    - user_override: the user manually set the direction.
    When the user asks why two variables relate, what could confound, or what the data suggests, ground your answer in the actual node names and edge types currently in the graph. Discuss likely causal mechanisms in business terms (SaaS / NDR / customer success). Don't invent edges that aren't present.

Conventions:
- Be concise — short paragraphs, no bullet lists unless the user asks.
- Reference variable names from the actual schema or graph, not made-up ones.
- If the user has not connected Sigma yet, Sigma tool calls will fail; tell them to click "Connect to Sigma" in the ⚙ Data sources panel.
- For non-data, non-graph questions, answer briefly without calling tools."""


# ---------- Tool definitions ----------

TOOLS: list[dict] = [
    {
        "name": "sigma_search",
        "description": (
            "Search the user's Sigma workspace for workbooks, data models, "
            "data model elements, or tables matching a query string."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search term, e.g. 'MRR' or 'NDR causality'",
                },
                "entity_types": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": ["workbook", "dataModel", "dataModelElement", "table"],
                    },
                    "description": "Optional filter; omit to search all types",
                },
                "limit": {"type": "integer", "default": 10, "minimum": 1, "maximum": 20},
            },
            "required": ["query"],
        },
    },
    {
        "name": "sigma_list_data_models",
        "description": (
            "Browse data models in the workspace by collection. "
            "'recommendations' = AI-curated; 'recents' / 'favorites' / 'dataModels'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "collection": {
                    "type": "string",
                    "enum": ["recommendations", "favorites", "recents", "dataModels"],
                },
                "limit": {"type": "integer", "default": 20, "minimum": 1, "maximum": 50},
            },
            "required": ["collection"],
        },
    },
    {
        "name": "sigma_describe_data_model",
        "description": "List the elements (queryable datasets) inside a data model.",
        "input_schema": {
            "type": "object",
            "properties": {
                "data_model_id": {"type": "string"},
            },
            "required": ["data_model_id"],
        },
    },
    {
        "name": "sigma_describe_element",
        "description": (
            "Get the column-level schema (SQL DDL) for a specific element. "
            "Call this before sigma_ingest_element so you have the column IDs."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "data_model_id": {"type": "string"},
                "element_id": {"type": "string"},
            },
            "required": ["data_model_id", "element_id"],
        },
    },
    {
        "name": "sigma_ingest_element",
        "description": (
            "Pull rows from a Sigma data model element into a local data source "
            "(Parquet-backed). Pick numeric columns relevant to the user's question. "
            "Supports up to 1,000,000 rows by default with automatic pagination. "
            "Returns a `collection_id` you should pass directly to `run_pc`."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "data_model_id": {"type": "string"},
                "element_id": {"type": "string"},
                "name": {
                    "type": "string",
                    "description": "Human-readable name for the new data source",
                },
                "columns": {
                    "type": "array",
                    "minItems": 2,
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {
                                "type": "string",
                                "description": "Exact column ID from the DDL",
                            },
                            "label": {
                                "type": "string",
                                "description": "Human-readable label",
                            },
                        },
                        "required": ["id", "label"],
                    },
                },
                "limit": {
                    "type": "integer",
                    "default": 1_000_000,
                    "minimum": 100,
                    "maximum": 1_000_000,
                    "description": "Max rows to pull. Larger samples = better statistical power for PC.",
                },
            },
            "required": ["data_model_id", "element_id", "name", "columns"],
        },
    },
    {
        "name": "run_pc",
        "description": (
            "Run the PC causal-discovery algorithm on a local data source and "
            "render the resulting DAG in the main app view. Always call this "
            "right after sigma_ingest_element so the user sees the graph. "
            "If `columns` is omitted, all numeric columns of the source are used. "
            "Returns the typed-edge graph; the frontend updates automatically."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "source_id": {
                    "type": "string",
                    "description": "Data source ID returned by sigma_ingest_element or a CSV upload",
                },
                "columns": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional column names; defaults to all numeric columns",
                },
                "alpha": {
                    "type": "number",
                    "default": 0.05,
                    "description": "PC significance threshold for conditional independence tests",
                },
            },
            "required": ["source_id"],
        },
    },
]


# ---------- Tool execution ----------

async def _execute_tool(name: str, args: dict) -> Any:
    if name == "sigma_search":
        return await sigma_client.search(
            args["query"],
            args.get("entity_types"),
            args.get("limit", 10),
        )
    if name == "sigma_list_data_models":
        return await sigma_client.list_documents(
            args["collection"], args.get("limit", 20)
        )
    if name == "sigma_describe_data_model":
        return await sigma_client.describe(
            {"type": "datamodel", "dataModelId": args["data_model_id"]}
        )
    if name == "sigma_describe_element":
        return await sigma_client.describe(
            {
                "type": "datamodel-element",
                "dataModelId": args["data_model_id"],
                "elementId": args["element_id"],
            }
        )
    if name == "sigma_ingest_element":
        return await _ingest_element(args)
    if name == "run_pc":
        return _run_pc_tool(args)
    raise ValueError(f"unknown tool {name!r}")


async def _ingest_element(args: dict) -> dict:
    cols = args["columns"]
    if len(cols) < 2:
        raise ValueError("Need at least 2 columns")
    select = ", ".join(
        f'"{c["id"]}" AS "{_safe_label(c["label"])}"' for c in cols
    )
    base_sql = f"SELECT {select} FROM \"datamodel\".\"{args['element_id']}\""
    payload = {"type": "datamodel", "dataModelId": args["data_model_id"]}
    chunks = await sigma_client.query_paginated(
        payload,
        base_sql,
        page_size=50_000,
        max_rows=int(args.get("limit", 1_000_000)),
    )
    if not chunks:
        raise ValueError("query returned 0 rows")
    src = tabular_store.ingest_chunks(
        chunks, name=f"sigma:{args['name']}", kind="sigma"
    )
    return {
        "collection_id": src.id,
        "name": src.name,
        "n_rows": src.n_rows,
        "numeric_columns": src.numeric_columns,
    }


def _run_pc_tool(args: dict) -> dict:
    source_id = args["source_id"]
    try:
        src = tabular_store.get_source(source_id)
    except KeyError:
        raise ValueError(f"data source not found: {source_id}")
    columns = args.get("columns") or src.numeric_columns
    if len(columns) < 2:
        raise ValueError("need at least 2 numeric columns")
    df = tabular_store.read_dataframe(source_id, columns)
    n_total = len(df)
    try:
        g = _run_pc_algo(
            df,
            alpha=float(args.get("alpha", 0.05)),
            corr_threshold=0.3,
            include_correlations=True,
        )
    except (CollinearColumnsError, InsufficientDataError) as e:
        raise ValueError(str(e))
    except ValueError as e:
        raise ValueError(
            f"PC failed: {e}. Drop columns that are linear combinations of "
            "others (e.g., a total and its components)."
        )
    graph_dict = overrides.apply_to_graph(source_id, g.to_dict())
    app_state.set_active_source(
        app_state.ActiveSource(
            id=source_id,
            label=src.name,
            kind=src.kind,
            columns=list(columns),
            rows=n_total,
        )
    )
    return {
        "source_id": source_id,
        "source_name": src.name,
        "n_rows": src.n_rows,
        "n_rows_used": n_total,
        "n_edges": len(graph_dict["edges"]),
        "graph": graph_dict,
    }


def _safe_label(label: str) -> str:
    import re
    s = re.sub(r"[^A-Za-z0-9]+", "_", label).strip("_")
    return s or "col"


# ---------- Streaming agent loop ----------

EventType = Literal[
    "text",
    "tool_use",
    "tool_result",
    "source_ingested",
    "graph_built",
    "error",
    "done",
]


def _client() -> anthropic.AsyncAnthropic:
    key = get_key()
    if not key:
        raise RuntimeError(
            "Anthropic API key not set. Enter one in the app header, or export ANTHROPIC_API_KEY before starting the backend."
        )
    return anthropic.AsyncAnthropic(api_key=key)


async def stream_chat(
    messages: list[dict],
    graph_context: dict | None = None,
) -> AsyncIterator[dict]:
    """Run the agent loop and yield typed events.

    `messages` is a list of {role, content} where content is text or a list of
    content blocks (for assistant turns that include tool_use).
    `graph_context` describes the DAG currently shown — used so the agent can
    interpret relationships between specific nodes.
    """
    client = _client()
    convo = list(messages)

    system_blocks: list[dict] = [
        {
            "type": "text",
            "text": SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        }
    ]
    if graph_context:
        system_blocks.append(
            {
                "type": "text",
                "text": _format_graph_context(graph_context),
            }
        )

    for _iter in range(8):  # safety cap on tool-use rounds
        async with client.messages.stream(
            model=MODEL,
            max_tokens=4096,
            thinking={"type": "adaptive"},
            output_config={"effort": "medium"},
            system=system_blocks,
            tools=TOOLS,
            messages=convo,
        ) as stream:
            async for event in stream:
                if event.type == "content_block_delta":
                    delta = event.delta
                    if delta.type == "text_delta":
                        yield {"type": "text", "text": delta.text}
            final = await stream.get_final_message()

        if final.stop_reason != "tool_use":
            yield {"type": "done"}
            return

        # Echo full assistant turn (preserves tool_use blocks)
        convo.append({"role": "assistant", "content": final.content})

        tool_results: list[dict] = []
        for block in final.content:
            if block.type != "tool_use":
                continue
            yield {
                "type": "tool_use",
                "name": block.name,
                "input": _safe_input_preview(block.input),
            }
            try:
                result = await _execute_tool(block.name, dict(block.input))
            except Exception as e:
                yield {"type": "tool_result", "name": block.name, "ok": False, "summary": str(e)}
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": f"error: {e}",
                        "is_error": True,
                    }
                )
                continue

            yield {
                "type": "tool_result",
                "name": block.name,
                "ok": True,
                "summary": _summarize_result(block.name, result),
            }
            if block.name == "sigma_ingest_element" and isinstance(result, dict):
                yield {
                    "type": "source_ingested",
                    "id": result.get("collection_id"),
                    "name": result.get("name"),
                    "n_rows": result.get("n_rows"),
                    "numeric_columns": result.get("numeric_columns"),
                }
            elif block.name == "run_pc" and isinstance(result, dict):
                yield {
                    "type": "graph_built",
                    "source_id": result.get("source_id"),
                    "source_label": result.get("source_name"),
                    "n_rows": result.get("n_rows_used"),
                    "n_rows_total": result.get("n_rows"),
                    "graph": result.get("graph"),
                }
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": _to_text(result),
                }
            )
        convo.append({"role": "user", "content": tool_results})

    yield {
        "type": "error",
        "message": "Tool-use loop exceeded 8 iterations.",
    }
    yield {"type": "done"}


# ---------- Helpers ----------

def _format_graph_context(ctx: dict) -> str:
    nodes = ctx.get("nodes") or []
    edges = ctx.get("edges") or []
    label = ctx.get("source_label") or "current source"
    lines = [
        f"Current graph (source: {label}):",
        f"Nodes ({len(nodes)}): {', '.join(map(str, nodes))}",
        f"Edges ({len(edges)}):",
    ]
    for e in edges:
        et = e.get("type")
        arrow = (
            "->" if et == "causal_directed" or et == "user_override"
            else "--" if et == "causal_undirected"
            else ".."
        )
        lines.append(
            f"  {arrow}  {e.get('source')} {arrow} {e.get('target')}  "
            f"[{et}, r={e.get('r')}]"
        )
    return "\n".join(lines)


def _to_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, default=str)


def _safe_input_preview(inp: Any) -> dict:
    """Shorten tool inputs for display (don't ship 50-column lists to the UI)."""
    out: dict = {}
    if not isinstance(inp, dict):
        return {"_": str(inp)[:120]}
    for k, v in inp.items():
        if isinstance(v, list) and len(v) > 4:
            out[k] = f"[{len(v)} items]"
        elif isinstance(v, str) and len(v) > 120:
            out[k] = v[:120] + "…"
        else:
            out[k] = v
    return out


def _summarize_result(tool_name: str, result: Any) -> str:
    if tool_name == "sigma_search":
        if isinstance(result, dict):
            entries = result.get("entries") or result.get("results") or []
            if isinstance(entries, list):
                return f"{len(entries)} match{'es' if len(entries) != 1 else ''}"
        return "ok"
    if tool_name == "sigma_list_data_models":
        if isinstance(result, dict):
            entries = result.get("entries") or []
            if isinstance(entries, list):
                return f"{len(entries)} item{'s' if len(entries) != 1 else ''}"
        return "ok"
    if tool_name in ("sigma_describe_data_model", "sigma_describe_element"):
        return "schema received"
    if tool_name == "sigma_ingest_element":
        if isinstance(result, dict):
            return (
                f"{result.get('n_rows', '?')} rows, "
                f"{len(result.get('numeric_columns') or [])} numeric cols"
            )
        return "ok"
    return "ok"
