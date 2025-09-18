# Dash + 3D Force Graph — Attack Simulator

An interactive Dash app for visualizing **directed graphs** in 3D and simulating **cyber-attacks** on network flows.

---

## Features
- 3D force-directed graph visualization  
- Source & destination relabeling (`0 → N1`, `1035 → N1036`)  
- Two attack modes:
  - **Budgeted Attack** (capacity reductions within a budget)  
  - **Multi-Step Attack** (iterative halving of capacities)  
- Highlights attacked edges in **red** + context paths in **green/purple**  
- Jump to Source/Aim, reset, and restore previous states  
- Clickable nodes and edges with info popups  

---

## Quick Start
1.Install dependencies:
```bash
pip install dash dash-extensions networkx
```
2.Prepare a graph file (graph.txt) with lines like:
```
0: (12, 10, 1.0, 1) (4, 5, 1.0, 1)
4: (1035, 20, 2.0, 1)
```
3.Run the app:
```
python Final1.py
```
4.Open: http://127.0.0.1:8050

