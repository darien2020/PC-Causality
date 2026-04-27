import { useEffect, useState } from "react";
import {
  clearApiKey,
  getApiKeyStatus,
  setApiKey,
  type ApiKeyStatus,
} from "../api/client";

interface Props {
  onChange?: (status: ApiKeyStatus) => void;
}

export function ApiKeyBadge({ onChange }: Props) {
  const [status, setStatus] = useState<ApiKeyStatus | null>(null);
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  useEffect(() => {
    getApiKeyStatus()
      .then((s) => {
        setStatus(s);
        onChange?.(s);
      })
      .catch(() => setStatus({ set: false, source: null }));
  }, [onChange]);

  async function save() {
    setBusy(true);
    setErr(null);
    setInfo(null);
    try {
      const result = await setApiKey(value);
      const next: ApiKeyStatus = { set: true, source: result.source };
      setStatus(next);
      setValue("");
      onChange?.(next);

      if (!result.validated) {
        setErr(
          `Saved, but key validation failed: ${
            result.validation_error ?? "unknown error"
          }. Chat & edge explanations will probably 401 — fix or clear the key.`,
        );
        return;
      }

      // Success → close the dropdown
      setOpen(false);
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function clear() {
    setBusy(true);
    setInfo(null);
    try {
      const result = await clearApiKey();
      const next: ApiKeyStatus = { set: false, source: null };
      setStatus(next);
      onChange?.(next);
      if (result.removed_from) {
        setInfo(`Cleared · removed export line from ${result.removed_from}.`);
      }
    } finally {
      setBusy(false);
    }
  }

  const isSet = status?.set ?? false;
  const fromEnv = status?.source === "env";

  const buttonStyle: React.CSSProperties = fromEnv
    ? {
        background: "#16a34a",
        border: "1px solid #15803d",
        color: "#f0fdf4",
      }
    : {
        background: "#1e293b",
        border: "1px solid #334155",
        color: "#f1f5f9",
      };

  const dotColor = fromEnv ? "#bbf7d0" : isSet ? "#16a34a" : "#dc2626";

  const label = fromEnv
    ? "Anthropic API key · env"
    : isSet
      ? "Anthropic API key · set"
      : "Anthropic API key · not set";

  return (
    <div style={{ position: "relative" }}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        style={{
          ...buttonStyle,
          padding: "4px 10px",
          borderRadius: 6,
          fontSize: 12,
          display: "flex",
          alignItems: "center",
          gap: 6,
          cursor: "pointer",
        }}
      >
        <span
          style={{
            width: 8,
            height: 8,
            borderRadius: "50%",
            background: dotColor,
            display: "inline-block",
          }}
        />
        {label}
      </button>

      {open && (
        <div
          style={{
            position: "absolute",
            top: "calc(100% + 6px)",
            right: 0,
            background: "#1e293b",
            border: "1px solid #334155",
            borderRadius: 8,
            padding: 12,
            minWidth: 340,
            color: "#f1f5f9",
            fontSize: 12,
            zIndex: 20,
            boxShadow: "0 8px 24px rgba(0,0,0,0.4)",
          }}
        >
          <div style={{ marginBottom: 6, lineHeight: 1.4 }}>
            Saving also appends{" "}
            <code style={{ background: "#0f172a", padding: "1px 4px", borderRadius: 3 }}>
              export ANTHROPIC_API_KEY
            </code>{" "}
            to your shell rc (~/.zshrc) so it persists across backend restarts.
          </div>
          <input
            type="password"
            placeholder="sk-ant-..."
            value={value}
            onChange={(e) => setValue(e.target.value)}
            disabled={busy}
            style={{
              width: "100%",
              padding: "6px 8px",
              background: "#0f172a",
              border: "1px solid #334155",
              borderRadius: 4,
              color: "#f1f5f9",
              fontSize: 12,
              fontFamily: "ui-monospace, monospace",
            }}
          />
          {err && (
            <div style={{ color: "#fca5a5", marginTop: 6 }}>{err}</div>
          )}
          {info && !err && (
            <div style={{ color: "#86efac", marginTop: 6, lineHeight: 1.4 }}>
              {info}
            </div>
          )}
          <div
            style={{
              display: "flex",
              gap: 6,
              marginTop: 8,
              justifyContent: "flex-end",
            }}
          >
            {isSet && (
              <button
                type="button"
                onClick={clear}
                disabled={busy}
                style={btnSecondary}
              >
                Clear
              </button>
            )}
            <button
              type="button"
              onClick={() => setOpen(false)}
              disabled={busy}
              style={btnSecondary}
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={save}
              disabled={busy || !value.trim()}
              style={btnPrimary}
            >
              {busy ? "Saving…" : "Save"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

const btnSecondary: React.CSSProperties = {
  background: "transparent",
  border: "1px solid #334155",
  color: "#cbd5e1",
  padding: "4px 10px",
  borderRadius: 4,
  fontSize: 12,
  cursor: "pointer",
};

const btnPrimary: React.CSSProperties = {
  background: "#2563eb",
  border: "1px solid #2563eb",
  color: "white",
  padding: "4px 10px",
  borderRadius: 4,
  fontSize: 12,
  cursor: "pointer",
};
