import type { GraphEdge } from "../api/types";

export interface MenuPosition {
  x: number;
  y: number;
}

export interface MenuTarget {
  edge: GraphEdge;
  position: MenuPosition;
}

interface Props {
  target: MenuTarget;
  onSetDirection: (from: string) => void;
  onSetNoLink: () => void;
  onClear: () => void;
  onClose: () => void;
}

export function EdgeContextMenu({
  target,
  onSetDirection,
  onSetNoLink,
  onClear,
  onClose,
}: Props) {
  const { edge, position } = target;
  const isOverride = edge.type === "user_override";
  return (
    <>
      <div
        onClick={onClose}
        onContextMenu={(e) => {
          e.preventDefault();
          onClose();
        }}
        style={{
          position: "fixed",
          inset: 0,
          zIndex: 25,
        }}
      />
      <div
        style={{
          position: "fixed",
          left: position.x,
          top: position.y,
          zIndex: 26,
          background: "#1e293b",
          border: "1px solid #334155",
          borderRadius: 6,
          padding: 4,
          minWidth: 230,
          boxShadow: "0 8px 24px rgba(0,0,0,0.5)",
          fontSize: 12,
          color: "#f1f5f9",
        }}
      >
        <div
          style={{
            padding: "6px 8px",
            color: "#94a3b8",
            borderBottom: "1px solid #334155",
            marginBottom: 4,
          }}
        >
          Override edge {edge.source} ↔ {edge.target}
        </div>
        <MenuItem onClick={() => onSetDirection(edge.source)}>
          Set direction:{" "}
          <strong>
            {edge.source} → {edge.target}
          </strong>
        </MenuItem>
        <MenuItem onClick={() => onSetDirection(edge.target)}>
          Set direction:{" "}
          <strong>
            {edge.target} → {edge.source}
          </strong>
        </MenuItem>
        <MenuItem onClick={onSetNoLink}>Mark as no causal link</MenuItem>
        {isOverride && (
          <MenuItem onClick={onClear} danger>
            Clear override (revert to PC)
          </MenuItem>
        )}
      </div>
    </>
  );
}

function MenuItem({
  children,
  onClick,
  danger,
}: {
  children: React.ReactNode;
  onClick: () => void;
  danger?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      style={{
        display: "block",
        width: "100%",
        textAlign: "left",
        background: "transparent",
        border: "none",
        color: danger ? "#fca5a5" : "#f1f5f9",
        padding: "6px 8px",
        borderRadius: 4,
        fontSize: 12,
        cursor: "pointer",
      }}
      onMouseEnter={(e) => (e.currentTarget.style.background = "#334155")}
      onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
    >
      {children}
    </button>
  );
}
