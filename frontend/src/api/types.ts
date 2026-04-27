export type EdgeType =
  | "causal_directed"
  | "causal_undirected"
  | "correlation"
  | "user_override";

export interface GraphNode {
  id: string;
}

export interface GraphEdge {
  source: string;
  target: string;
  type: EdgeType;
  strength: number;
  metadata: { pearson_r: number };
}

export interface Graph {
  nodes: GraphNode[];
  edges: GraphEdge[];
  dropped_columns?: string[];
}

export interface GraphResponse {
  graph: Graph;
  ground_truth_edges: { source: string; target: string }[];
}

export interface DataSource {
  id: string;
  name: string;
  kind: "csv" | "sigma";
  columns: string[];
  numeric_columns: string[];
  n_rows: number;
}
