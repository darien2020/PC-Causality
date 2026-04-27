import { useEffect, useState } from "react";
import { sigmaConnect, sigmaDisconnect, sigmaStatus } from "../api/client";
import { SigmaConfigurator } from "./SigmaConfigurator";

export function SigmaSection() {
  const [connected, setConnected] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [configOpen, setConfigOpen] = useState(false);

  async function refresh() {
    try {
      const s = await sigmaStatus();
      setConnected(s.connected);
    } catch {
      setConnected(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function connect() {
    setBusy(true);
    setErr(null);
    try {
      await sigmaConnect();
      setConnected(true);
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function disconnect() {
    setBusy(true);
    setErr(null);
    try {
      await sigmaDisconnect();
      setConnected(false);
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  }

  if (connected === null) {
    return <div style={{ color: "#94a3b8", fontSize: 12 }}>Checking Sigma…</div>;
  }

  return (
    <div>
      <div
        style={{
          padding: "8px 10px",
          border: "1px solid #334155",
          borderRadius: 6,
          background: connected ? "#16a34a22" : "transparent",
          marginBottom: 8,
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 6,
            marginBottom: 8,
            minWidth: 0,
          }}
        >
          <span
            style={{
              width: 8,
              height: 8,
              borderRadius: "50%",
              background: connected ? "#16a34a" : "#dc2626",
              display: "inline-block",
              flexShrink: 0,
            }}
          />
          <span style={{ fontSize: 12, color: "#f1f5f9", flexShrink: 0 }}>
            {connected ? "Connected" : "Not connected"}
          </span>
          <span
            style={{
              fontSize: 10.5,
              color: "#94a3b8",
              fontFamily: "ui-monospace, monospace",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
              minWidth: 0,
            }}
            title="api.staging.sigmacomputing.io/mcp/v2"
          >
            api.staging.sigmacomputing.io/mcp/v2
          </span>
        </div>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          <button
            onClick={() => setConfigOpen(true)}
            style={btnSecondary}
            disabled={busy}
          >
            Configure
          </button>
          {connected ? (
            <button onClick={disconnect} disabled={busy} style={btnDanger}>
              Disconnect
            </button>
          ) : (
            <button onClick={connect} disabled={busy} style={btnPrimary}>
              {busy ? "Waiting for OAuth…" : "Connect"}
            </button>
          )}
        </div>
      </div>
      {!connected && (
        <div style={{ color: "#94a3b8", fontSize: 11.5, lineHeight: 1.5 }}>
          Connecting opens a browser tab for OAuth login. Token persists across
          backend restarts.
        </div>
      )}
      {err && (
        <div
          style={{
            color: "#fca5a5",
            marginTop: 8,
            padding: 6,
            border: "1px solid #7f1d1d",
            borderRadius: 4,
            fontSize: 11,
          }}
        >
          {err}
        </div>
      )}

      <SigmaConfigurator
        open={configOpen}
        onClose={() => setConfigOpen(false)}
        connected={connected}
      />
    </div>
  );
}

const btnPrimary: React.CSSProperties = {
  background: "#2563eb",
  border: "1px solid #2563eb",
  color: "white",
  padding: "4px 12px",
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

const btnDanger: React.CSSProperties = {
  background: "transparent",
  border: "1px solid #7f1d1d",
  color: "#fca5a5",
  padding: "4px 10px",
  borderRadius: 4,
  fontSize: 12,
  cursor: "pointer",
};
