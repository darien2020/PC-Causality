import { useEffect, useRef } from "react";
import cytoscape, { type Core, type ElementDefinition } from "cytoscape";
import dagre from "cytoscape-dagre";
import type { Graph, GraphEdge } from "../api/types";
import { EDGE_STYLES } from "./edgeStyles";

cytoscape.use(dagre);

interface Props {
  graph: Graph;
  onEdgeClick?: (edge: GraphEdge) => void;
  onEdgeContextMenu?: (edge: GraphEdge, position: { x: number; y: number }) => void;
}

function edgeId(e: GraphEdge): string {
  return `${e.source}__${e.target}__${e.type}`;
}

export function DagView({ graph, onEdgeClick, onEdgeContextMenu }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    const elements: ElementDefinition[] = [
      ...graph.nodes.map((n) => ({
        data: { id: n.id, label: n.id.replace(/_/g, " ") },
      })),
      ...graph.edges.map((e) => ({
        data: {
          id: edgeId(e),
          source: e.source,
          target: e.target,
          type: e.type,
          weight: e.strength,
          r: e.metadata.pearson_r,
          edge: e,
        },
      })),
    ];

    const cy = cytoscape({
      container: containerRef.current,
      elements,
      style: [
        {
          selector: "node",
          style: {
            "background-color": "#1e293b",
            label: "data(label)",
            color: "#f1f5f9",
            "text-valign": "center",
            "text-halign": "center",
            "font-size": "11px",
            "font-weight": 500,
            width: "label",
            height: "label",
            padding: "12px",
            shape: "round-rectangle",
            "border-width": 1,
            "border-color": "#334155",
          },
        },
        {
          selector: "edge",
          style: {
            // Fallback width when `weight` (= |Pearson r|) isn't present.
            width: 1,
            "curve-style": "bezier",
            "line-color": "#94a3b8",
            "target-arrow-color": "#94a3b8",
            "target-arrow-shape": "triangle",
            "arrow-scale": 0.9,
            opacity: 0.9,
          },
        },
        {
          // Pearson r is in [-1, 1]; we store |r| as `weight` (already in
          // [0, 1]). Map across the full range so weak ties stay visibly
          // thin and strong ones (|r| → 1) read as much heavier.
          selector: "edge[weight]",
          style: {
            width: "mapData(weight, 0, 1, 0.8, 6)",
          },
        },
        ...(Object.entries(EDGE_STYLES).flatMap(([type, s]) => [
          {
            selector: `edge[type = "${type}"]`,
            style: {
              "line-color": s.color,
              "target-arrow-color": s.color,
              "line-style": s.dashed ? "dashed" : "solid",
              "target-arrow-shape": s.directed ? "triangle" : "none",
            },
          },
        ]) as cytoscape.Stylesheet[]),
        {
          selector: "edge:selected",
          style: {
            width: 6,
            "line-color": "#fbbf24",
            "target-arrow-color": "#fbbf24",
            "z-index": 10,
          },
        },
      ],
      layout: {
        name: "dagre",
        rankDir: "LR",
        nodeSep: 60,
        rankSep: 140,
        fit: true,
        padding: 40,
      } as cytoscape.LayoutOptions,
      wheelSensitivity: 0.2,
    });

    cy.on("tap", "edge", (evt) => {
      const data = evt.target.data();
      if (onEdgeClick && data.edge) onEdgeClick(data.edge as GraphEdge);
    });

    cy.on("cxttap", "edge", (evt) => {
      const data = evt.target.data();
      if (!onEdgeContextMenu || !data.edge) return;
      const orig = evt.originalEvent as MouseEvent | undefined;
      const pos = { x: orig?.clientX ?? 0, y: orig?.clientY ?? 0 };
      onEdgeContextMenu(data.edge as GraphEdge, pos);
    });

    if (containerRef.current) {
      containerRef.current.addEventListener("contextmenu", (e) =>
        e.preventDefault(),
      );
    }

    const ro = new ResizeObserver(() => cy.resize() && cy.fit(undefined, 40));
    ro.observe(containerRef.current);

    (window as unknown as { __cy?: Core }).__cy = cy;

    cyRef.current = cy;
    return () => {
      ro.disconnect();
      cy.destroy();
      cyRef.current = null;
    };
  }, [graph, onEdgeClick]);

  return (
    <div
      ref={containerRef}
      style={{ width: "100%", height: "100%", background: "#0f172a" }}
    />
  );
}
