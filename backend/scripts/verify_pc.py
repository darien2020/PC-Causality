"""Smoke test: run PC on synthetic NDR data, compare to ground truth."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from causal.pc import run_pc
from causal.synthetic import generate, GROUND_TRUTH_EDGES


def main() -> None:
    df = generate(n=2000, seed=42)
    g = run_pc(df, alpha=0.05, corr_threshold=0.3, include_correlations=True)

    print(f"nodes: {len(g.nodes)}")
    print(f"edges: {len(g.edges)}")
    by_type: dict[str, int] = {}
    for e in g.edges:
        by_type[e.type] = by_type.get(e.type, 0) + 1
    print(f"  by type: {by_type}")

    print("\nground truth edges (undirected skeleton):")
    gt_skeleton = {tuple(sorted(e)) for e in GROUND_TRUTH_EDGES}
    for a, b in sorted(gt_skeleton):
        print(f"  {a} -- {b}")

    found_skeleton = {
        tuple(sorted((e.source, e.target)))
        for e in g.edges
        if e.type in {"causal_directed", "causal_undirected"}
    }

    recall = len(gt_skeleton & found_skeleton) / len(gt_skeleton)
    precision = (
        len(gt_skeleton & found_skeleton) / len(found_skeleton)
        if found_skeleton
        else 0
    )
    print(f"\nskeleton recall:    {recall:.2f}")
    print(f"skeleton precision: {precision:.2f}")

    print("\npc-inferred edges:")
    for e in g.edges:
        arrow = "->" if e.type == "causal_directed" else (
            "--" if e.type == "causal_undirected" else ".."
        )
        tag = e.type.ljust(18)
        print(f"  {tag} {e.source:>20} {arrow} {e.target:<20}  r={e.metadata['pearson_r']:+.2f}")

    print("\nsample edge JSON:")
    print(json.dumps(g.edges[0].to_dict(), indent=2))


if __name__ == "__main__":
    main()
