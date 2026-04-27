"""Claude-backed edge explanation.

Streams a short causal/correlational interpretation for a single edge in the
DAG. The system prompt and dataset summary form a cacheable prefix; only the
edge being explained varies between requests, so cache hits are typical.
"""
from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

import anthropic

from agent.secret_store import get_key

MODEL = "claude-opus-4-7"

SYSTEM_PROMPT = """You are a causal inference assistant helping a user explore the drivers of Net Dollar Retention (NDR) for a SaaS business. You explain edges in a graph produced by the PC causal discovery algorithm.

Edge types you must reason about:
- causal_directed: PC inferred a direction (source -> target) from conditional independence tests.
- causal_undirected: PC found a causal link but the direction is ambiguous (Markov equivalence class). Both orientations are statistically consistent.
- correlation: variables are associated (|Pearson r| above threshold) but PC found a separating set, so the link is likely explained by other variables in the graph (confounders or chains).
- user_override: the user has set the direction manually, overriding PC.

Your job, for each edge the user clicks:
1. State the relationship in plain language (one sentence).
2. Interpret the Pearson correlation strength and sign in business terms.
3. Discuss what the edge type means about causality here -- including what would need to be true for the inferred direction to be wrong, or which variables in the dataset could be confounders for a correlation-only edge.
4. Suggest one practical NDR-relevant takeaway (1 sentence).

Keep the entire response under 180 words. Use short paragraphs, no headings, no bullet lists, no markdown emphasis. Be concrete; refer to the actual variable names."""


@dataclass
class EdgeExplainRequest:
    source: str
    target: str
    type: str
    pearson_r: float
    all_columns: list[str]


def _client() -> anthropic.Anthropic:
    key = get_key()
    if not key:
        raise RuntimeError(
            "Anthropic API key not set. Enter one in the app header, or export ANTHROPIC_API_KEY before starting the backend."
        )
    return anthropic.Anthropic(api_key=key)


def _dataset_context(columns: list[str]) -> str:
    return (
        "The full variable set in the graph is: "
        + ", ".join(columns)
        + ". These are SaaS account-level metrics. NDR (net dollar retention) is the "
          "outcome variable; expansion_revenue and churn_risk are the proximate drivers."
    )


def stream_explanation(req: EdgeExplainRequest) -> Iterator[str]:
    """Yield text chunks of Claude's streaming explanation."""
    client = _client()

    user_message = (
        f"Explain this edge:\n"
        f"  source: {req.source}\n"
        f"  target: {req.target}\n"
        f"  type: {req.type}\n"
        f"  pearson_r: {req.pearson_r:+.3f}"
    )

    with client.messages.stream(
        model=MODEL,
        max_tokens=1024,
        thinking={"type": "adaptive"},
        output_config={"effort": "medium"},
        system=[
            {"type": "text", "text": SYSTEM_PROMPT},
            {
                "type": "text",
                "text": _dataset_context(req.all_columns),
                "cache_control": {"type": "ephemeral"},
            },
        ],
        messages=[{"role": "user", "content": user_message}],
    ) as stream:
        for text in stream.text_stream:
            yield text
