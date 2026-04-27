import { useState } from "react";
import { EDGE_STYLES } from "./edgeStyles";
import type { EdgeType } from "../api/types";

export function Legend() {
  const [tip, setTip] = useState<{
    type: EdgeType;
    x: number;
    y: number;
  } | null>(null);

  return (
    <>
      <div
        style={{
          position: "absolute",
          top: 16,
          right: 16,
          background: "#1e293bdd",
          border: "1px solid #334155",
          borderRadius: 8,
          padding: 12,
          color: "#f1f5f9",
          fontSize: 12,
          minWidth: 220,
          backdropFilter: "blur(4px)",
        }}
      >
        <div style={{ fontWeight: 600, marginBottom: 8 }}>Edge types</div>
        {(Object.keys(EDGE_STYLES) as EdgeType[]).map((type) => {
          const s = EDGE_STYLES[type];
          return (
            <div
              key={type}
              onMouseEnter={(e) =>
                setTip({
                  type,
                  x: e.currentTarget.getBoundingClientRect().left,
                  y: e.currentTarget.getBoundingClientRect().bottom,
                })
              }
              onMouseLeave={() => setTip(null)}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                padding: "4px 0",
                cursor: "default",
              }}
            >
              <svg width="32" height="12">
                <line
                  x1="2"
                  y1="6"
                  x2={s.directed ? "22" : "30"}
                  y2="6"
                  stroke={s.color}
                  strokeWidth="2.5"
                  strokeDasharray={s.dashed ? "4 3" : undefined}
                />
                {s.directed && <polygon points="22,2 30,6 22,10" fill={s.color} />}
              </svg>
              <span>{s.label}</span>
            </div>
          );
        })}
      </div>

      {tip && (
        <div
          style={{
            position: "fixed",
            top: tip.y + 6,
            left: tip.x,
            maxWidth: 280,
            background: "#0b1220",
            border: "1px solid #334155",
            borderRadius: 6,
            padding: "8px 10px",
            color: "#cbd5e1",
            fontSize: 12,
            lineHeight: 1.4,
            zIndex: 50,
            pointerEvents: "none",
            boxShadow: "0 6px 16px rgba(0,0,0,0.5)",
          }}
        >
          {EDGE_STYLES[tip.type].description}
        </div>
      )}
    </>
  );
}
