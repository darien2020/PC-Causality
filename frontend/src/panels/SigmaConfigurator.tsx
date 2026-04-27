import { useEffect, useState } from "react";
import {
  sigmaSetPermissions,
  sigmaTools,
  type SigmaPolicy,
  type SigmaTool,
} from "../api/client";

interface Props {
  open: boolean;
  onClose: () => void;
  connected: boolean;
}

export function SigmaConfigurator({ open, onClose, connected }: Props) {
  const [tools, setTools] = useState<SigmaTool[] | null>(null);
  const [policies, setPolicies] = useState<Record<string, SigmaPolicy>>({});
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<number | null>(null);

  useEffect(() => {
    if (!open) return;
    if (!connected) {
      setTools(null);
      setErr("Connect to Sigma to see capabilities.");
      return;
    }
    setBusy(true);
    setErr(null);
    sigmaTools()
      .then((r) => {
        setTools(r.tools);
        const initial: Record<string, SigmaPolicy> = {};
        for (const t of r.tools) initial[t.name] = t.policy;
        setPolicies(initial);
      })
      .catch((e) => setErr(String(e)))
      .finally(() => setBusy(false));
  }, [open, connected]);

  function setPolicy(name: string, policy: SigmaPolicy) {
    setPolicies((p) => ({ ...p, [name]: policy }));
  }

  function setAll(policy: SigmaPolicy) {
    if (!tools) return;
    const next: Record<string, SigmaPolicy> = {};
    for (const t of tools) next[t.name] = policy;
    setPolicies(next);
  }

  async function save() {
    setBusy(true);
    setErr(null);
    try {
      await sigmaSetPermissions(policies);
      setSavedAt(Date.now());
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
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.6)",
        zIndex: 40,
        display: "flex",
        justifyContent: "center",
        alignItems: "center",
        padding: 24,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "#0f172a",
          border: "1px solid #334155",
          borderRadius: 8,
          width: 720,
          maxWidth: "100%",
          maxHeight: "90vh",
          display: "flex",
          flexDirection: "column",
          color: "#f1f5f9",
          fontSize: 13,
          boxShadow: "0 16px 48px rgba(0,0,0,0.6)",
        }}
      >
        <div
          style={{
            padding: "14px 18px",
            borderBottom: "1px solid #334155",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <div>
            <div style={{ fontSize: 15, fontWeight: 600 }}>
              Sigma MCP server
            </div>
            <div style={{ fontSize: 11, color: "#94a3b8", marginTop: 2 }}>
              api.staging.sigmacomputing.io/mcp/v2 ·{" "}
              <span style={{ color: connected ? "#22c55e" : "#dc2626" }}>
                {connected ? "● connected" : "● not connected"}
              </span>
            </div>
          </div>
          <button onClick={onClose} style={btnSecondary}>
            Close
          </button>
        </div>

        <div style={{ padding: 18, overflow: "auto", flex: 1 }}>
          {!tools && !err && (
            <div style={{ color: "#94a3b8" }}>
              {busy ? "Loading capabilities…" : ""}
            </div>
          )}
          {err && (
            <div style={{ color: "#fca5a5" }}>{err}</div>
          )}
          {tools && tools.length === 0 && (
            <div style={{ color: "#94a3b8" }}>
              The MCP server didn't return any tools.
            </div>
          )}
          {tools && tools.length > 0 && (
            <>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  marginBottom: 12,
                  color: "#94a3b8",
                  fontSize: 12,
                }}
              >
                <span>{tools.length} capabilities</span>
                <span style={{ display: "flex", gap: 6 }}>
                  <button
                    onClick={() => setAll("allow_always")}
                    style={btnGhost}
                    disabled={busy}
                  >
                    All allow always
                  </button>
                  <button
                    onClick={() => setAll("ask_always")}
                    style={btnGhost}
                    disabled={busy}
                  >
                    All ask always
                  </button>
                </span>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {tools.map((t) => (
                  <div
                    key={t.name}
                    style={{
                      padding: 10,
                      border: "1px solid #334155",
                      borderRadius: 6,
                      background: "#0b1220",
                    }}
                  >
                    <div
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "flex-start",
                        gap: 12,
                      }}
                    >
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div
                          style={{
                            fontFamily: "ui-monospace, monospace",
                            fontWeight: 600,
                          }}
                        >
                          {t.name}
                        </div>
                        {t.description && (
                          <div
                            style={{
                              color: "#94a3b8",
                              fontSize: 11.5,
                              marginTop: 4,
                              lineHeight: 1.4,
                              whiteSpace: "pre-wrap",
                              overflow: "hidden",
                              display: "-webkit-box",
                              WebkitLineClamp: 3,
                              WebkitBoxOrient: "vertical",
                            }}
                          >
                            {t.description}
                          </div>
                        )}
                      </div>
                      <PolicyToggle
                        value={policies[t.name] ?? "allow_always"}
                        onChange={(p) => setPolicy(t.name, p)}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>

        <div
          style={{
            padding: "10px 18px",
            borderTop: "1px solid #334155",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <span style={{ fontSize: 11, color: "#94a3b8" }}>
            {savedAt
              ? `Saved at ${new Date(savedAt).toLocaleTimeString()}`
              : "Permissions persist across backend restarts."}
          </span>
          <div style={{ display: "flex", gap: 6 }}>
            <button onClick={onClose} style={btnSecondary}>
              Cancel
            </button>
            <button onClick={save} disabled={busy || !tools} style={btnPrimary}>
              {busy ? "Saving…" : "Save permissions"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function PolicyToggle({
  value,
  onChange,
}: {
  value: SigmaPolicy;
  onChange: (p: SigmaPolicy) => void;
}) {
  const opts: { v: SigmaPolicy; label: string }[] = [
    { v: "allow_always", label: "Allow always" },
    { v: "ask_always", label: "Ask always" },
  ];
  return (
    <div
      style={{
        display: "inline-flex",
        border: "1px solid #334155",
        borderRadius: 4,
        overflow: "hidden",
        flexShrink: 0,
      }}
    >
      {opts.map((o, i) => {
        const active = value === o.v;
        return (
          <button
            key={o.v}
            onClick={() => onChange(o.v)}
            style={{
              padding: "4px 10px",
              fontSize: 11,
              border: "none",
              borderLeft: i === 0 ? "none" : "1px solid #334155",
              background: active
                ? o.v === "allow_always"
                  ? "#16a34a"
                  : "#ca8a04"
                : "transparent",
              color: active ? "#0b1220" : "#cbd5e1",
              fontWeight: active ? 600 : 400,
              cursor: "pointer",
            }}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

const btnPrimary: React.CSSProperties = {
  background: "#2563eb",
  border: "1px solid #2563eb",
  color: "white",
  padding: "6px 14px",
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
  color: "#cbd5e1",
  padding: "2px 8px",
  borderRadius: 4,
  fontSize: 11,
  cursor: "pointer",
};
