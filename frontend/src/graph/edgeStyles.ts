import type { EdgeType } from "../api/types";

export interface EdgeStyle {
  label: string;
  color: string;
  description: string;
  directed: boolean;
  dashed: boolean;
}

export const EDGE_STYLES: Record<EdgeType, EdgeStyle> = {
  causal_directed: {
    label: "Causal (directed)",
    color: "#2563eb",
    description:
      "PC algorithm inferred a directional causal relationship from source to target.",
    directed: true,
    dashed: false,
  },
  causal_undirected: {
    label: "Causal (ambiguous)",
    color: "#9333ea",
    description:
      "PC found a causal link but cannot orient it (Markov equivalence). Use the override controls to set direction.",
    directed: false,
    dashed: false,
  },
  correlation: {
    label: "Correlation only",
    color: "#94a3b8",
    description:
      "Variables are correlated but PC found no direct causal link — likely explained by other variables in the graph.",
    directed: false,
    dashed: true,
  },
  user_override: {
    label: "User override",
    color: "#16a34a",
    description:
      "Direction set manually by the user, overriding the PC algorithm output.",
    directed: true,
    dashed: false,
  },
};
