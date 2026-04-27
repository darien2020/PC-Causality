import { useEffect, useRef, useState } from "react";
import {
  deleteSource,
  graphFromSource,
  listSources,
  uploadCsv,
} from "../api/client";
import type { DataSource, Graph } from "../api/types";
import { SigmaSection } from "./SigmaSection";

interface Props {
  open: boolean;
  onClose: () => void;
  onGraphReady: (
    g: Graph,
    source: DataSource,
    used: number,
    selectedColumns: string[],
  ) => void;
}

export function AdminPanel({ open, onClose, onGraphReady }: Props) {
  const [sources, setSources] = useState<DataSource[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedCols, setSelectedCols] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  async function refresh() {
    try {
      setSources(await listSources());
    } catch (e) {
      setErr(String(e));
    }
  }

  useEffect(() => {
    if (open) refresh();
  }, [open]);

  const selected = sources.find((s) => s.id === selectedId) ?? null;

  function pickSource(s: DataSource) {
    setSelectedId(s.id);
    setSelectedCols(new Set(s.numeric_columns));
    setErr(null);
  }

  function toggleCol(col: string) {
    const next = new Set(selectedCols);
    if (next.has(col)) next.delete(col);
    else next.add(col);
    setSelectedCols(next);
  }

  async function handleUpload(file: File) {
    setBusy(true);
    setErr(null);
    try {
      const src = await uploadCsv(file);
      await refresh();
      pickSource(src);
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function handleDelete(id: string) {
    setBusy(true);
    try {
      await deleteSource(id);
      if (selectedId === id) {
        setSelectedId(null);
        setSelectedCols(new Set());
      }
      await refresh();
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function runPC() {
    if (!selected) return;
    if (selectedCols.size < 2) {
      setErr("Select at least 2 columns");
      return;
    }
    setBusy(true);
    setErr(null);
    const cols = [...selectedCols];
    try {
      const result = await graphFromSource(selected.id, cols);
      onGraphReady(result.graph, selected, result.n_rows_used, cols);
      onClose();
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  }

  if (!open) return null;

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.5)",
        zIndex: 30,
        display: "flex",
        justifyContent: "flex-end",
      }}
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: 480,
          maxWidth: "100%",
          background: "#0f172a",
          borderLeft: "1px solid #334155",
          color: "#f1f5f9",
          padding: 20,
          overflow: "auto",
          fontSize: 13,
        }}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: 16,
          }}
        >
          <div style={{ fontSize: 16, fontWeight: 600 }}>Data sources</div>
          <button onClick={onClose} style={btnSecondary}>
            Close
          </button>
        </div>

        <Section title="Upload CSV">
          <div
            style={{
              color: "#94a3b8",
              marginBottom: 8,
              fontSize: 12,
              lineHeight: 1.4,
            }}
          >
            Each upload becomes a Parquet-backed local data source (up to ~5M
            rows). Numeric columns are available to the PC algorithm.
          </div>
          <input
            ref={fileRef}
            type="file"
            accept=".csv,text/csv"
            disabled={busy}
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) handleUpload(f);
            }}
            style={{ color: "#cbd5e1", fontSize: 12 }}
          />
        </Section>

        <Section title="Sigma Computing">
          <SigmaSection
            onIngested={(src) => {
              refresh();
              pickSource(src);
            }}
          />
        </Section>

        <Section title={`Data sources (${sources.length})`}>
          {sources.length === 0 && (
            <div style={{ color: "#64748b", fontSize: 12 }}>
              No sources yet. Upload a CSV above.
            </div>
          )}
          {sources.map((s) => (
            <SourceCard
              key={s.id}
              source={s}
              selected={selectedId === s.id}
              busy={busy}
              onPick={() => pickSource(s)}
              onDelete={() => handleDelete(s.id)}
            />
          ))}
        </Section>

        {selected && (
          <Section title={`Columns for ${selected.name}`}>
            <div
              style={{
                color: "#94a3b8",
                fontSize: 12,
                marginBottom: 8,
              }}
            >
              Pick which numeric columns to feed into the PC algorithm.
            </div>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 1fr",
                gap: 4,
              }}
            >
              {selected.columns.map((c) => {
                const numeric = selected.numeric_columns.includes(c);
                return (
                  <label
                    key={c}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 6,
                      padding: "4px 6px",
                      borderRadius: 4,
                      color: numeric ? "#f1f5f9" : "#64748b",
                      cursor: numeric ? "pointer" : "not-allowed",
                      fontSize: 12,
                    }}
                  >
                    <input
                      type="checkbox"
                      disabled={!numeric}
                      checked={selectedCols.has(c)}
                      onChange={() => toggleCol(c)}
                    />
                    {c}
                    {!numeric && (
                      <span style={{ fontSize: 10, color: "#64748b" }}>
                        (non-numeric)
                      </span>
                    )}
                  </label>
                );
              })}
            </div>
            <div
              style={{
                marginTop: 12,
                display: "flex",
                gap: 8,
                alignItems: "center",
              }}
            >
              <button
                onClick={runPC}
                disabled={busy || selectedCols.size < 2}
                style={btnPrimary}
              >
                {busy ? "Running…" : `Run PC on ${selectedCols.size} columns`}
              </button>
              <button
                onClick={() => setSelectedCols(new Set(selected.numeric_columns))}
                style={btnSecondary}
              >
                Select all numeric
              </button>
              <button
                onClick={() => setSelectedCols(new Set())}
                style={btnSecondary}
              >
                Clear
              </button>
            </div>
          </Section>
        )}

        {err && (
          <div
            style={{
              color: "#fca5a5",
              marginTop: 16,
              padding: 8,
              border: "1px solid #7f1d1d",
              borderRadius: 4,
              fontSize: 12,
            }}
          >
            {err}
          </div>
        )}
      </div>
    </div>
  );
}

function SourceCard({
  source,
  selected,
  busy,
  onPick,
  onDelete,
}: {
  source: DataSource;
  selected: boolean;
  busy: boolean;
  onPick: () => void;
  onDelete: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div
      onClick={onPick}
      style={{
        padding: 8,
        marginBottom: 6,
        borderRadius: 6,
        border: `1px solid ${selected ? "#2563eb" : "#334155"}`,
        background: selected ? "#1e3a8a33" : "transparent",
        cursor: "pointer",
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
        }}
      >
        <div style={{ minWidth: 0, flex: 1 }}>
          <div
            style={{
              fontWeight: 500,
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {source.name}
          </div>
          <div style={{ color: "#94a3b8", fontSize: 11, marginTop: 2 }}>
            {source.n_rows.toLocaleString()} rows · {source.columns.length}{" "}
            cols ({source.numeric_columns.length} numeric)
          </div>
        </div>
        <button
          onClick={(e) => {
            e.stopPropagation();
            setExpanded((x) => !x);
          }}
          style={{ ...btnGhost }}
        >
          {expanded ? "Hide cols" : "Show cols"}
        </button>
        <button
          onClick={(e) => {
            e.stopPropagation();
            onDelete();
          }}
          disabled={busy}
          style={{ ...btnSecondary, color: "#fca5a5", marginLeft: 6 }}
        >
          Delete
        </button>
      </div>
      {expanded && (
        <div
          style={{
            marginTop: 8,
            padding: "6px 8px",
            background: "#0b1220",
            border: "1px solid #334155",
            borderRadius: 4,
            fontSize: 11,
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: "2px 12px",
            fontFamily: "ui-monospace, monospace",
            maxHeight: 220,
            overflow: "auto",
          }}
          onClick={(e) => e.stopPropagation()}
        >
          {source.columns.map((c) => {
            const isNumeric = source.numeric_columns.includes(c);
            return (
              <span
                key={c}
                style={{ color: isNumeric ? "#cbd5e1" : "#64748b" }}
              >
                {c}
                {!isNumeric && (
                  <span style={{ fontSize: 9, marginLeft: 4 }}>(text)</span>
                )}
              </span>
            );
          })}
        </div>
      )}
    </div>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div style={{ marginBottom: 20 }}>
      <div
        style={{
          fontSize: 12,
          fontWeight: 600,
          color: "#94a3b8",
          textTransform: "uppercase",
          letterSpacing: 0.5,
          marginBottom: 8,
        }}
      >
        {title}
      </div>
      {children}
    </div>
  );
}

const btnPrimary: React.CSSProperties = {
  background: "#2563eb",
  border: "1px solid #2563eb",
  color: "white",
  padding: "6px 12px",
  borderRadius: 4,
  fontSize: 12,
  cursor: "pointer",
};

const btnSecondary: React.CSSProperties = {
  background: "transparent",
  border: "1px solid #334155",
  color: "#cbd5e1",
  padding: "4px 10px",
  borderRadius: 4,
  fontSize: 12,
  cursor: "pointer",
};

const btnGhost: React.CSSProperties = {
  background: "transparent",
  border: "1px solid #334155",
  color: "#94a3b8",
  padding: "2px 8px",
  borderRadius: 4,
  fontSize: 11,
  cursor: "pointer",
};
