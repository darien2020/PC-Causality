import { useEffect, useRef, useState } from "react";
import { streamChat, type ChatMessageWire } from "../api/client";
import type { Graph } from "../api/types";

interface ToolEvent {
  kind: "use" | "result";
  name: string;
  input?: Record<string, unknown>;
  ok?: boolean;
  summary?: string;
}

interface ChatTurn {
  role: "user" | "assistant";
  text: string;
  events?: ToolEvent[];
  pending?: boolean;
}

interface Props {
  graph: Graph | null;
  sourceLabel: string;
  onSourceIngested?: (info: {
    id: string;
    name: string;
    n_rows: number;
    numeric_columns: string[];
  }) => void;
  onGraphBuilt?: (info: {
    graph: Graph;
    source_id: string;
    source_label: string;
    n_rows: number;
    n_rows_total: number;
  }) => void;
}

export function ChatPanel({
  graph,
  sourceLabel,
  onSourceIngested,
  onGraphBuilt,
}: Props) {
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: 1e9, behavior: "smooth" });
  }, [turns]);

  function appendToLast(updater: (t: ChatTurn) => ChatTurn) {
    setTurns((prev) => {
      if (prev.length === 0) return prev;
      const idx = prev.length - 1;
      const next = prev.slice();
      next[idx] = updater(next[idx]);
      return next;
    });
  }

  async function send(text: string) {
    const trimmed = text.trim();
    if (!trimmed || busy) return;

    const newUser: ChatTurn = { role: "user", text: trimmed };
    const newAssistant: ChatTurn = {
      role: "assistant",
      text: "",
      events: [],
      pending: true,
    };
    const nextTurns = [...turns, newUser, newAssistant];
    setTurns(nextTurns);
    setInput("");
    setBusy(true);

    const wire: ChatMessageWire[] = nextTurns
      .filter((t) => !t.pending)
      .map((t) => ({ role: t.role, content: t.text }));

    const graphContext = graph
      ? {
          source_label: sourceLabel,
          nodes: graph.nodes.map((n) => n.id),
          edges: graph.edges.map((e) => {
            const r = e.metadata?.pearson_r;
            return {
              source: e.source,
              target: e.target,
              type: e.type,
              // pearson_r can be null/NaN if a column was constant after dropna;
              // coerce to 0 instead of letting `.toFixed` throw and kill send().
              r:
                typeof r === "number" && Number.isFinite(r)
                  ? Number(r.toFixed(3))
                  : 0,
            };
          }),
        }
      : null;

    const ctrl = new AbortController();
    abortRef.current = ctrl;

    try {
      await streamChat(wire, graphContext, {
      signal: ctrl.signal,
      onText: (chunk) => {
        appendToLast((t) => ({ ...t, text: t.text + chunk }));
      },
      onToolUse: (name, input) =>
        appendToLast((t) => ({
          ...t,
          events: [...(t.events ?? []), { kind: "use", name, input }],
        })),
      onToolResult: (name, ok, summary) =>
        appendToLast((t) => ({
          ...t,
          events: [...(t.events ?? []), { kind: "result", name, ok, summary }],
        })),
      onSourceIngested: (info) => onSourceIngested?.(info),
      onGraphBuilt: (info) => onGraphBuilt?.(info),
      onDone: () => {
        appendToLast((t) => ({ ...t, pending: false }));
        setBusy(false);
        abortRef.current = null;
      },
      onError: (msg) => {
        appendToLast((t) => ({
          ...t,
          text: t.text + (t.text ? "\n\n" : "") + `Error: ${msg}`,
          pending: false,
        }));
        setBusy(false);
        abortRef.current = null;
      },
      });
    } catch (e) {
      // Synchronous throw before/inside streamChat — make sure we don't strand
      // the busy flag and an empty pending bubble.
      appendToLast((t) => ({
        ...t,
        text:
          t.text + (t.text ? "\n\n" : "") + `Error: ${(e as Error).message ?? e}`,
        pending: false,
      }));
      setBusy(false);
      abortRef.current = null;
    }
  }

  function stop() {
    abortRef.current?.abort();
    abortRef.current = null;
    appendToLast((t) => ({ ...t, pending: false }));
    setBusy(false);
  }

  function clearChat() {
    abortRef.current?.abort();
    setTurns([]);
    setBusy(false);
  }

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        background: "#0b1220",
        borderRight: "1px solid #334155",
      }}
    >
      <div
        style={{
          padding: "10px 12px",
          borderBottom: "1px solid #334155",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          color: "#f1f5f9",
        }}
      >
        <div style={{ fontWeight: 600, fontSize: 13 }}>Causality Agent</div>
        {turns.length > 0 && (
          <button onClick={clearChat} style={btnGhost}>
            Clear
          </button>
        )}
      </div>

      <div
        ref={scrollRef}
        style={{
          flex: 1,
          overflow: "auto",
          padding: 12,
          display: "flex",
          flexDirection: "column",
          gap: 12,
        }}
      >
        {turns.length === 0 ? (
          <div style={{ color: "#94a3b8", fontSize: 12, lineHeight: 1.5 }}>
            Ask the Causality Agent to find Sigma objects (workbooks, data
            models, tables) or to interpret relationships between nodes in the
            graph.
          </div>
        ) : (
          turns.map((t, i) => <Bubble key={i} turn={t} />)
        )}
      </div>

      <div
        style={{
          padding: 10,
          borderTop: "1px solid #334155",
          display: "flex",
          gap: 6,
        }}
      >
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send(input);
            }
          }}
          placeholder="Find Sigma objects or interpret relationships…"
          rows={2}
          disabled={busy}
          style={{
            flex: 1,
            resize: "none",
            background: "#0f172a",
            color: "#f1f5f9",
            border: "1px solid #334155",
            borderRadius: 4,
            padding: "6px 8px",
            fontSize: 12,
            fontFamily: "inherit",
          }}
        />
        {busy ? (
          <button onClick={stop} style={btnSecondary}>
            Stop
          </button>
        ) : (
          <button
            onClick={() => send(input)}
            disabled={!input.trim()}
            style={btnPrimary}
          >
            Send
          </button>
        )}
      </div>
    </div>
  );
}

function Bubble({ turn }: { turn: ChatTurn }) {
  const isUser = turn.role === "user";
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: isUser ? "flex-end" : "flex-start",
        gap: 4,
      }}
    >
      <div
        style={{
          maxWidth: "92%",
          background: isUser ? "#1e293b" : "transparent",
          color: "#f1f5f9",
          padding: isUser ? "6px 10px" : "0",
          borderRadius: 8,
          fontSize: 12,
          lineHeight: 1.55,
          whiteSpace: "pre-wrap",
        }}
      >
        {turn.text || (turn.pending ? "" : null)}
        {turn.pending && <span style={{ opacity: 0.5 }}>▍</span>}
      </div>
      {turn.events && turn.events.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 3, width: "100%" }}>
          {turn.events.map((e, i) => (
            <ToolChip key={i} ev={e} />
          ))}
        </div>
      )}
    </div>
  );
}

function ToolChip({ ev }: { ev: ToolEvent }) {
  const isUse = ev.kind === "use";
  const color = isUse
    ? "#a78bfa"
    : ev.ok
      ? "#22c55e"
      : "#f87171";
  const inputPreview =
    ev.input && Object.keys(ev.input).length > 0
      ? Object.entries(ev.input)
          .map(([k, v]) => `${k}: ${jsonShort(v)}`)
          .join(", ")
      : "";
  return (
    <div
      style={{
        fontSize: 10.5,
        color,
        fontFamily: "ui-monospace, monospace",
        opacity: 0.85,
      }}
    >
      {isUse ? "→" : "✓"} {ev.name}
      {isUse && inputPreview && ` (${inputPreview})`}
      {!isUse && ev.summary && ` — ${ev.summary}`}
    </div>
  );
}

function jsonShort(v: unknown): string {
  if (typeof v === "string") return `"${v.length > 30 ? v.slice(0, 30) + "…" : v}"`;
  if (Array.isArray(v)) return `[${v.length}]`;
  return String(v);
}

const btnPrimary: React.CSSProperties = {
  background: "#2563eb",
  border: "1px solid #2563eb",
  color: "white",
  padding: "0 14px",
  borderRadius: 4,
  fontSize: 12,
  cursor: "pointer",
  height: 36,
  alignSelf: "stretch",
};

const btnSecondary: React.CSSProperties = {
  background: "transparent",
  border: "1px solid #334155",
  color: "#cbd5e1",
  padding: "0 14px",
  borderRadius: 4,
  fontSize: 12,
  cursor: "pointer",
  height: 36,
  alignSelf: "stretch",
};

const btnGhost: React.CSSProperties = {
  background: "transparent",
  border: "none",
  color: "#94a3b8",
  fontSize: 11,
  cursor: "pointer",
  padding: "2px 6px",
};

