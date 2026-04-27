import { useEffect, useState } from "react";
import { streamEdgeExplanation } from "../api/client";
import type { GraphEdge } from "../api/types";
import { EDGE_STYLES } from "../graph/edgeStyles";

interface Props {
  edge: GraphEdge | null;
  allColumns: string[];
}

export function InferencePanel({ edge, allColumns }: Props) {
  const [text, setText] = useState("");
  const [status, setStatus] = useState<"idle" | "streaming" | "done" | "error">(
    "idle",
  );
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!edge) {
      setText("");
      setStatus("idle");
      setError(null);
      return;
    }
    const ctrl = new AbortController();
    setText("");
    setError(null);
    setStatus("streaming");
    streamEdgeExplanation(edge, allColumns, {
      signal: ctrl.signal,
      onText: (c) => setText((t) => t + c),
      onDone: () => setStatus("done"),
      onError: (m) => {
        setError(m);
        setStatus("error");
      },
    });
    return () => ctrl.abort();
  }, [edge, allColumns]);

  return (
    <div
      style={{
        height: 220,
        borderTop: "1px solid #334155",
        background: "#0f172a",
        color: "#f1f5f9",
        padding: 16,
        overflow: "auto",
        fontSize: 13,
      }}
    >
      {!edge ? (
        <div style={{ color: "#64748b" }}>
          Click an edge to see correlation and causal inference details.
        </div>
      ) : (
        <div>
          <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 6 }}>
            <span style={{ color: EDGE_STYLES[edge.type].color }}>
              {edge.source}
            </span>{" "}
            {EDGE_STYLES[edge.type].directed ? "→" : "—"}{" "}
            <span style={{ color: EDGE_STYLES[edge.type].color }}>
              {edge.target}
            </span>
            <span
              style={{
                marginLeft: 10,
                fontSize: 11,
                color: "#94a3b8",
                fontWeight: 400,
              }}
            >
              {EDGE_STYLES[edge.type].label} · r ={" "}
              {edge.metadata.pearson_r.toFixed(3)}
              {status === "streaming" && " · thinking…"}
            </span>
          </div>
          {error ? (
            <div style={{ color: "#fca5a5" }}>Error: {error}</div>
          ) : (
            <div
              style={{
                lineHeight: 1.55,
                color: "#cbd5e1",
                whiteSpace: "pre-wrap",
              }}
            >
              {text}
              {status === "streaming" && (
                <span style={{ opacity: 0.5 }}>▍</span>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
