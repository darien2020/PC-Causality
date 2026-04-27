import { useCallback, useEffect, useState } from "react";
import {
  clearOverride,
  fetchAppState,
  fetchSyntheticGraph,
  graphFromSource,
  setOverride,
} from "./api/client";
import type { DataSource, Graph, GraphEdge } from "./api/types";
import { DagView } from "./graph/DagView";
import {
  EdgeContextMenu,
  type MenuTarget,
} from "./graph/EdgeContextMenu";
import { Legend } from "./graph/Legend";
import { AdminPanel } from "./panels/AdminPanel";
import { ApiKeyBadge } from "./panels/ApiKeyBadge";
import { ChatPanel } from "./panels/ChatPanel";
import { InferencePanel } from "./panels/InferencePanel";

interface ActiveSource {
  id: string;
  label: string;
  rows: number;
  columns: string[]; // for refetch via from-source
  kind: "synthetic" | "csv";
}

export default function App() {
  const [graph, setGraph] = useState<Graph | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedEdge, setSelectedEdge] = useState<GraphEdge | null>(null);
  const [adminOpen, setAdminOpen] = useState(false);
  const [menu, setMenu] = useState<MenuTarget | null>(null);
  const [activeSource, setActiveSource] = useState<ActiveSource>({
    id: "__synthetic__",
    label: "synthetic NDR",
    rows: 2000,
    columns: [],
    kind: "synthetic",
  });
  const [restored, setRestored] = useState(false);

  // Restore the last-viewed source on mount so the graph view survives
  // backend restarts and browser reloads.
  useEffect(() => {
    let cancelled = false;
    fetchAppState()
      .then((s) => {
        if (cancelled) return;
        if (s.active_source && s.active_source.kind !== "synthetic") {
          setActiveSource({
            id: s.active_source.id,
            label: s.active_source.label,
            rows: s.active_source.rows,
            columns: s.active_source.columns,
            kind: "csv",
          });
        }
      })
      .catch(() => {
        // ignore — fall through to synthetic default
      })
      .finally(() => {
        if (!cancelled) setRestored(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const refetch = useCallback(async () => {
    try {
      if (activeSource.kind === "synthetic") {
        const r = await fetchSyntheticGraph();
        setGraph(r.graph);
      } else {
        const r = await graphFromSource(activeSource.id, activeSource.columns);
        setGraph(r.graph);
      }
    } catch (e) {
      // If the restored source is gone (deleted or backend reset), fall back.
      setError(String(e));
      if (activeSource.kind !== "synthetic") {
        setActiveSource({
          id: "__synthetic__",
          label: "synthetic NDR",
          rows: 2000,
          columns: [],
          kind: "synthetic",
        });
      }
    }
  }, [activeSource]);

  useEffect(() => {
    if (!restored) return;
    refetch();
  }, [restored, refetch]);

  function handleGraphFromSource(
    g: Graph,
    src: DataSource,
    used: number,
    selectedColumns: string[],
  ) {
    setGraph(g);
    setSelectedEdge(null);
    setActiveSource({
      id: src.id,
      label: src.name,
      rows: used,
      // Persist the user's actual selection so subsequent refetches (after an
      // edge override, etc.) use the same column subset. Otherwise the next
      // refetch widens to all numeric columns and clobbers the rendered graph.
      columns: selectedColumns,
      kind: "csv",
    });
  }

  async function applyOverride(directionFrom: string | null) {
    if (!menu) return;
    const { edge } = menu;
    setMenu(null);
    try {
      await setOverride(activeSource.id, edge.source, edge.target, directionFrom);
      await refetch();
    } catch (e) {
      setError(String(e));
    }
  }

  async function applyClear() {
    if (!menu) return;
    const { edge } = menu;
    setMenu(null);
    try {
      await clearOverride(activeSource.id, edge.source, edge.target);
      await refetch();
    } catch (e) {
      setError(String(e));
    }
  }

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100vh",
        width: "100vw",
        background: "#0f172a",
      }}
    >
      <header
        style={{
          padding: "8px 16px",
          borderBottom: "1px solid #334155",
          color: "#f1f5f9",
          fontWeight: 600,
          fontSize: 14,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 12,
        }}
      >
        <div style={{ display: "flex", alignItems: "baseline", gap: 12, flex: 1, minWidth: 0 }}>
          <span style={{ flexShrink: 0 }}>Causality — NDR causal graph</span>
          <span
            style={{
              fontSize: 11,
              fontWeight: 400,
              color: "#94a3b8",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            source: {activeSource.label} · {activeSource.rows} rows · right-click
            an edge to override
            {graph?.dropped_columns && graph.dropped_columns.length > 0 && (
              <span
                style={{ color: "#fbbf24", marginLeft: 8 }}
                title={`Auto-dropped: ${graph.dropped_columns.join(", ")}`}
              >
                · {graph.dropped_columns.length} col
                {graph.dropped_columns.length === 1 ? "" : "s"} auto-dropped
              </span>
            )}
          </span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <button
            onClick={() => setAdminOpen(true)}
            style={{
              background: "#1e293b",
              border: "1px solid #334155",
              color: "#f1f5f9",
              padding: "4px 10px",
              borderRadius: 6,
              fontSize: 12,
              cursor: "pointer",
            }}
          >
            ⚙ Data sources
          </button>
          <ApiKeyBadge />
        </div>
      </header>
      <div style={{ display: "flex", flex: 1, minHeight: 0 }}>
        <div style={{ width: 340, minWidth: 340, height: "100%" }}>
          <ChatPanel
            graph={graph}
            sourceLabel={`${activeSource.label} (${activeSource.rows} rows)`}
            onSourceIngested={(info) => {
              console.log(
                `Agent ingested ${info.name} (${info.n_rows} rows, ${info.numeric_columns.length} numeric cols)`,
              );
            }}
            onGraphBuilt={(info) => {
              setGraph(info.graph);
              setSelectedEdge(null);
              setActiveSource({
                id: info.source_id,
                label: info.source_label,
                rows: info.n_rows,
                columns: info.graph.nodes.map((n) => n.id),
                kind: "csv",
              });
            }}
          />
        </div>
        <div
          style={{
            flex: 1,
            display: "flex",
            flexDirection: "column",
            minWidth: 0,
          }}
        >
          <div style={{ flex: 1, position: "relative", minHeight: 0 }}>
            {error && (
              <div style={{ color: "#fca5a5", padding: 16 }}>Error: {error}</div>
            )}
            {!graph && !error && (
              <div style={{ color: "#94a3b8", padding: 16 }}>Loading graph…</div>
            )}
            {graph && (
              <DagView
                graph={graph}
                onEdgeClick={setSelectedEdge}
                onEdgeContextMenu={(edge, position) => setMenu({ edge, position })}
              />
            )}
            {graph && <Legend />}
          </div>
          <InferencePanel
            edge={selectedEdge}
            allColumns={graph?.nodes.map((n) => n.id) ?? []}
          />
        </div>
      </div>
      <AdminPanel
        open={adminOpen}
        onClose={() => setAdminOpen(false)}
        onGraphReady={handleGraphFromSource}
      />
      {menu && (
        <EdgeContextMenu
          target={menu}
          onSetDirection={(from) => applyOverride(from)}
          onSetNoLink={() => applyOverride(null)}
          onClear={applyClear}
          onClose={() => setMenu(null)}
        />
      )}
    </div>
  );
}
