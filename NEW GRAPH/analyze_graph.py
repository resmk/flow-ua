#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import csv
from collections import defaultdict, Counter

# ------------------------------
# Config (defaults; no flags)
# ------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_FILE = os.path.join(SCRIPT_DIR, "graph.text")      # auto-read from same folder
OUT_CSV    = os.path.join(SCRIPT_DIR, "edges.csv")       # auto-write every run
OUT_GML    = os.path.join(SCRIPT_DIR, "graph.graphml")   # auto-write every run

TUPLE_RE = re.compile(r"\(([^)]*)\)")

def parse_line(line):
    """
    Example line:
      946:(180, 8.0, 443.0, 1.0);(496, 2.0, 18.0, 1.0)
    Returns: src_id (int), list of (dst, v1, v2, v3)
    """
    line = line.strip()
    if not line or ":" not in line:
        return None, []
    left, right = line.split(":", 1)
    try:
        src = int(left.strip())
    except ValueError:
        return None, []

    edges = []
    for m in TUPLE_RE.finditer(right):
        raw = m.group(1)
        parts = [p.strip() for p in raw.split(",")]
        if len(parts) != 4:
            # skip malformed tuples safely
            continue
        try:
            dst = int(parts[0])
            v1 = float(parts[1])
            v2 = float(parts[2])
            v3 = float(parts[3])
            edges.append((dst, v1, v2, v3))
        except ValueError:
            # skip tuples we can't parse
            continue
    return src, edges

def parse_graph(path):
    nodes = set()
    edges = []  # list of dicts: {src,dst,v1,v2,v3}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            src, tuples = parse_line(line)
            if src is None:
                continue
            nodes.add(src)
            for (dst, v1, v2, v3) in tuples:
                nodes.add(dst)
                edges.append({
                    "src": src,
                    "dst": dst,
                    "v1": v1,
                    "v2": v2,
                    "v3": v3
                })
    return nodes, edges

def write_csv(edges, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["src", "dst", "v1", "v2", "v3"])
        w.writeheader()
        w.writerows(edges)

def write_graphml(nodes, edges, path, directed=True):
    """
    Minimal GraphML writer (no external deps).
    Node IDs are written as-is; edge attributes: v1, v2, v3 (floats).
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as g:
        g.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        g.write('<graphml xmlns="http://graphml.graphdrawing.org/xmlns"\n')
        g.write('         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"\n')
        g.write('         xsi:schemaLocation="http://graphml.graphdrawing.org/xmlns '
                'http://graphml.graphdrawing.org/xmlns/1.0/graphml.xsd">\n')

        # Edge attribute keys
        g.write('  <key id="v1" for="edge" attr.name="v1" attr.type="double"/>\n')
        g.write('  <key id="v2" for="edge" attr.name="v2" attr.type="double"/>\n')
        g.write('  <key id="v3" for="edge" attr.name="v3" attr.type="double"/>\n')

        g.write(f'  <graph id="G" edgedefault="{"directed" if directed else "undirected"}">\n')

        # Nodes
        for n in sorted(nodes):
            g.write(f'    <node id="{n}"/>\n')

        # Edges
        eid = 0
        for e in edges:
            g.write(f'    <edge id="e{eid}" source="{e["src"]}" target="{e["dst"]}">\n')
            g.write(f'      <data key="v1">{e["v1"]}</data>\n')
            g.write(f'      <data key="v2">{e["v2"]}</data>\n')
            g.write(f'      <data key="v3">{e["v3"]}</data>\n')
            g.write('    </edge>\n')
            eid += 1

        g.write('  </graph>\n')
        g.write('</graphml>\n')

def summarize(nodes, edges, top_k=10):
    indeg = Counter()
    outdeg = Counter()
    for e in edges:
        outdeg[e["src"]] += 1
        indeg[e["dst"]] += 1
    deg = Counter()
    for n in nodes:
        deg[n] = indeg[n] + outdeg[n]

    print("=== Summary ===")
    print(f"Nodes: {len(nodes)}")
    print(f"Edges: {len(edges)}")
    print("\nTop out-degree:")
    for n, d in outdeg.most_common(top_k):
        print(f"  {n}: {d}")
    print("\nTop in-degree:")
    for n, d in indeg.most_common(top_k):
        print(f"  {n}: {d}")
    print("\nTop total degree:")
    for n, d in deg.most_common(top_k):
        print(f"  {n}: {d}")

def main():
    if not os.path.isfile(INPUT_FILE):
        print(f"[ERROR] Input file not found:\n  {INPUT_FILE}")
        return
    nodes, edges = parse_graph(INPUT_FILE)
    write_csv(edges, OUT_CSV)
    write_graphml(nodes, edges, OUT_GML, directed=True)
    summarize(nodes, edges)
    print("\nFiles written:")
    print(f"  CSV     -> {OUT_CSV}")
    print(f"  GraphML -> {OUT_GML}")

if __name__ == "__main__":
    main()
