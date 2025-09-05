# Dash + 3D Force Graph app (strict edge consistency + matched labels)
# Fixes:
# - Attack dropdown can be used repeatedly (no permanent hide)
# - Preserve red attacked links on link clicks
# - File-path guard with friendly initial info
# - Robust label helper + SP cache in Show Attacked
# - Minor type/label safety, pinned 3d-force-graph version

import os
import dash
from dash import html, dcc
from dash_extensions.enrich import DashProxy, TriggerTransform, MultiplexerTransform
from dash.dependencies import Output, Input, State
import networkx as nx
import re
import json
import copy

# ---------- GRAPH GENERATION ----------

SRC_LABEL = "N1"
DST_LABEL = "N1036"

def parse_adjacency_list(file_path, max_nodes=1036):
    G = nx.DiGraph()
    src_pat = re.compile(r'^(\d+):')
    edge_pat = re.compile(r'\((\d+),\s*([\d.]+),\s*([\d.]+),\s*([\d.]+)\)')
    with open(file_path, 'r') as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            m = src_pat.match(line)
            if not m:
                continue
            src_id = int(m.group(1))
            if src_id >= max_nodes:
                continue
            src = str(src_id)
            G.add_node(src)
            for tgt_s, cap_s, cost_s, att_s in edge_pat.findall(line):
                tgt_id = int(tgt_s)
                if tgt_id >= max_nodes:
                    continue
                tgt = str(tgt_id)
                # Cast once to ints if capacities are integral in your model
                G.add_edge(
                    src, tgt,
                    capacity=int(float(cap_s)),
                    attack_cost=float(cost_s),
                    can_attack=(float(att_s) == 1.0)
                )
    return G

def _ensure_capacity(G, min_cap=1):
    for _, _, d in G.edges(data=True):
        if "capacity" not in d or d["capacity"] is None:
            d["capacity"] = min_cap
        else:
            try:
                d["capacity"] = max(int(d["capacity"]), min_cap)
            except Exception:
                d["capacity"] = min_cap

def _relabel_numeric_to_contract(G, src_numeric: str, dst_numeric: str):
    def _numkey(x):
        try:
            return (0, int(x))
        except ValueError:
            return (1, x)
    nodes_sorted = sorted(G.nodes(), key=_numkey)

    mapping = {}
    next_label_index = 1

    mapping[src_numeric] = SRC_LABEL
    if dst_numeric == src_numeric:
        raise ValueError("Source and target cannot be the same.")
    mapping[dst_numeric] = DST_LABEL

    def _next_free_label():
        nonlocal next_label_index
        while True:
            next_label_index += 1
            candidate = f"N{next_label_index}"
            if candidate not in mapping.values():
                return candidate

    for n in nodes_sorted:
        if n in (src_numeric, dst_numeric):
            continue
        if n not in mapping:
            mapping[n] = _next_free_label()

    G2 = nx.DiGraph()
    for old in G.nodes():
        G2.add_node(mapping[old], name=old)  # keep original numeric in 'name'
    for u, v, d in G.edges(data=True):
        G2.add_edge(mapping[u], mapping[v], **d)
    return G2

def _max_capacity(G):
    try:
        return max(d.get("capacity", 1) for _, _, d in G.edges(data=True)) or 1
    except ValueError:
        return 1

def _base_color_by_capacity(cap):
    if cap >= 25: return "#222"
    if cap >= 15: return "#555"
    return "#999"

def create_graph_data(G):
    max_cap = _max_capacity(G)
    return {
        "nodes": [
            {
                "id": node,
                "name": G.nodes[node].get("name", node),  # original numeric shown in tooltip
                "isRoot": node == SRC_LABEL,
                "isAim": node == DST_LABEL,
            }
            for node in G.nodes()
        ],
        "links": [
            {
                "source": u,
                "target": v,
                "capacity": G[u][v]["capacity"],
                "color": _base_color_by_capacity(G[u][v]["capacity"]),
                "normCapacity": max(G[u][v]["capacity"] / max_cap, 0.1),
            }
            for u, v in G.edges()
        ],
    }

def create_color_legend():
    return html.Div([
        html.H4("Color Legend", style={"marginBottom": "10px"}),
        html.Div([html.Span("⬤", style={"color": "red", "marginRight": "6px"}),
                  html.Span("Attacked Edge", style={"fontSize": "14px"})], style={"marginBottom": "6px"}),
        html.Div([html.Span("⬤", style={"color": "green", "marginRight": "6px"}),
                  html.Span("Path from Source to Attacked Edge", style={"fontSize": "14px"})], style={"marginBottom": "6px"}),
        html.Div([html.Span("⬤", style={"color": "blue", "marginRight": "6px"}),
                  html.Span("Not currently used in this version", style={"fontSize": "14px"})], style={"marginBottom": "6px"}),
        html.Div([html.Span("⬤", style={"color": "orange", "marginRight": "6px"}),
                  html.Span("Not currently used in this version", style={"fontSize": "14px"})], style={"marginBottom": "6px"}),
        html.Div([html.Span("⬤", style={"color": "purple", "marginRight": "6px"}),
                  html.Span("Shortest path from the target of the attacked edge to the destination node (N1036)", style={"fontSize": "14px"})], style={"marginBottom": "6px"}),
        html.Hr(style={"margin": "10px 0"}),
        html.Div([html.Span("⬤", style={"color": "green", "marginRight": "6px"}),
                  html.Span("Source Node ", style={"fontSize": "14px"})], style={"marginBottom": "6px"}),
        html.Div([html.Span("⬤", style={"color": "deeppink", "marginRight": "6px"}),
                  html.Span("Target Node ", style={"fontSize": "14px"})])
    ], style={
        "backgroundColor": "#f8f9fa",
        "padding": "15px",
        "borderRadius": "8px",
        "border": "1px solid #dee2e6",
        "marginBottom": "20px"
    })

# ---------- ATTACK / METRICS HELPERS ----------

def calculate_total_capacity(G):
    return sum(data['capacity'] for _, _, data in G.edges(data=True))

def snapshot_caps(G):
    return {(u, v): G[u][v]['capacity'] for u, v in G.edges()}

def edge_diffs(caps_before, G_after):
    rows = []
    for (u, v), before in caps_before.items():
        if G_after.has_edge(u, v):
            after = G_after[u][v]['capacity']
            if after != before:
                rows.append({
                    "source": u, "target": v,
                    "before": before, "after": after,
                    "reduction": before - after
                })
    rows.sort(key=lambda r: r["reduction"], reverse=True)
    return rows

def rows_from_red_links(updated_data_links, caps_before, G_after):
    """Build rows from the exact links we colored red in updated_data."""
    rows = []
    for l in updated_data_links:
        if l.get("color") != "red":
            continue
        u, v = l["source"], l["target"]
        if not G_after.has_edge(u, v):
            continue
        before = caps_before.get((u, v))
        if before is None:
            continue
        after = G_after[u][v]["capacity"]
        if after != before:
            rows.append({
                "source": u, "target": v,
                "before": before, "after": after,
                "reduction": before - after
            })
    rows.sort(key=lambda r: r['reduction'], reverse=True)
    return rows

def budgeted_attack(G, source="N1", sink="N1036", budget=150):
    G_copy = copy.deepcopy(G)
    flow_value_before, flow_dict = nx.maximum_flow(
        G_copy, source, sink, flow_func=nx.algorithms.flow.edmonds_karp
    )

    flow_edges = []
    for u, v in G_copy.edges():
        if not G_copy[u][v].get('can_attack', True):
            continue
        flow_amount = flow_dict.get(u, {}).get(v, 0)
        cap = G_copy[u][v].get('capacity', 1)
        if flow_amount > 0:
            flow_edges.append((u, v, cap, flow_amount))

    flow_edges.sort(key=lambda x: (x[3], x[2]), reverse=True)

    total_reduced = 0
    for u, v, cap, _flow_amt in flow_edges:
        if total_reduced >= budget:
            break
        reducible = cap - 1
        if reducible <= 0:
            continue
        reduction = min(reducible, budget - total_reduced)
        before = G[u][v].get('capacity', 1)
        G[u][v]['capacity'] = max(1, int(before - reduction))
        total_reduced += reduction

    flow_value_after, _ = nx.maximum_flow(
        G, source, sink, flow_func=nx.algorithms.flow.edmonds_karp
    )

    return flow_value_before, flow_value_after

def multi_step_attack(G, source, sink, information='flow', steps=3, edges_per_step=30):
    """
    Iteratively reduce capacities on a working copy, then apply cumulative reductions to G.
    Defaults to targeting edges carrying positive flow per step.
    """
    caps_before = snapshot_caps(G)
    G_pristine = copy.deepcopy(G)
    G_copy = copy.deepcopy(G)

    cumulative_reduction = {}

    for _ in range(steps):
        _, flow_dict = nx.maximum_flow(G_copy, source, sink)

        if information == 'flow':
            edges_with_metric = []
            for u, v in G_copy.edges():
                if not G_copy[u][v].get('can_attack', True):
                    continue
                f = flow_dict.get(u, {}).get(v, 0)
                if f > 0:
                    edges_with_metric.append((u, v, f))
            edges_sorted = sorted(edges_with_metric, key=lambda x: x[2], reverse=True)
        else:
            edges_with_metric = []
            for u, v in G_copy.edges():
                if not G_copy[u][v].get('can_attack', True):
                    continue
                edges_with_metric.append((u, v, G_copy[u][v]['capacity']))
            edges_sorted = sorted(edges_with_metric, key=lambda x: x[2], reverse=True)

        top_edges = edges_sorted[:edges_per_step]

        for u, v, _metric in top_edges:
            old_cap = G_copy[u][v]['capacity']
            new_cap = max(1, int(old_cap // 2))
            reduction = old_cap - new_cap
            if reduction <= 0:
                continue
            G_copy[u][v]['capacity'] = new_cap
            cumulative_reduction[(u, v)] = cumulative_reduction.get((u, v), 0) + reduction

    # Apply cumulative reductions to the actual G
    for (u, v), total_reduction in cumulative_reduction.items():
        G[u][v]['capacity'] = max(1, caps_before[(u, v)] - total_reduction)

    flow_before, _ = nx.maximum_flow(G_pristine, source, sink)
    flow_after, _  = nx.maximum_flow(G,         source, sink)

    return flow_before, flow_after

# --- load your file graph and adapt it to the app contract ---
file_path = os.getenv("GRAPH_FILE") or "/Users/miraki/Desktop/sem3/flowua/code/NEW GRAPH/graph.text"
RAW_SOURCE = "0"
RAW_TARGET = "1035"

file_warning = ""
if not os.path.exists(file_path):
    # Fallback so app boots
    G_raw = nx.DiGraph()
    G_raw.add_edge("0", "1035", capacity=10, attack_cost=1, can_attack=True)
    file_warning = f"⚠️ Graph file not found at: {file_path}. Loaded a tiny fallback graph."
else:
    G_raw = parse_adjacency_list(file_path, max_nodes=1036)

_ensure_capacity(G_raw, min_cap=1)
G = _relabel_numeric_to_contract(G_raw, RAW_SOURCE, RAW_TARGET)
G.remove_edges_from(list(G.in_edges(SRC_LABEL)))

ORIGINAL_GRAPH = copy.deepcopy(G)

graph_data_json = json.dumps(create_graph_data(G))

external_scripts = [
    "https://unpkg.com/three@0.150.1/build/three.min.js",
    "https://unpkg.com/3d-force-graph@1.73.3"
]
external_stylesheets = [
    "https://fonts.googleapis.com/css2?family=Roboto:wght@400;700&display=swap"
]

app = DashProxy(
    __name__,
    external_scripts=external_scripts,
    external_stylesheets=external_stylesheets,
    transforms=[TriggerTransform(), MultiplexerTransform()]
)

server = app.server

button_style = {
    "backgroundColor": "#007BFF",
    "color": "white",
    "border": "none",
    "padding": "10px 16px",
    "marginBottom": "10px",
    "borderRadius": "6px",
    "cursor": "pointer",
    "fontWeight": "bold",
    "fontFamily": "Roboto, sans-serif",
    "fontSize": "14px",
    "boxShadow": "0 2px 4px rgba(0,0,0,0.2)",
    "width": "100%",
}
restore_button_style = {**button_style, "backgroundColor": "#2dc00f", "marginTop": "10px"}

sidebar_style = {
    "position": "absolute", "top": "20px", "left": "20px", "width": "320px",
    "maxHeight": "90vh", "overflowY": "auto", "display": "flex",
    "flexDirection": "column", "gap": "20px", "zIndex": 11,
}

box_style = {
    "width": "100%", "padding": "15px", "borderRadius": "8px",
    "boxShadow": "0 2px 8px rgba(0,0,0,0.1)", "backgroundColor": "#FFFFFF",
    "border": "1px solid #E0E0E0", "fontFamily": "Roboto, sans-serif",
}
affected_edges_style = {**box_style, "backgroundColor": "#FFF8F8", "border": "1px solid #FFCCCC"}
capacity_box_style = {**box_style, "backgroundColor": "#F0F8FF", "border": "1px solid #ADD8E6"}

dropdown_container_style = {"position": "relative", "width": "100%"}
dropdown_content_style = {"display": "none", "position": "absolute", "width": "100%", "zIndex": 100}
dropdown_button_style = {**button_style, "backgroundColor": "#0069D9", "marginBottom": "0", "borderRadius": "0"}

# ---- label helper so text matches graph tooltip exactly ----
def display_node_label(nid: str) -> str:
    try:
        return str(G.nodes[nid].get("name", nid))
    except Exception:
        return str(nid)

# Initial info box
initial_info_children = [
    html.H4("Ready"),
    html.P("Use ‘Run Attack’ to simulate, ‘Show Attacked Edges’ for a focused view, double-click to reset camera.")
]
if file_warning:
    initial_info_children.append(html.P(file_warning))
initial_info = html.Div(initial_info_children)

app.layout = html.Div([
    html.Div([
        html.Button("RESTORE PREVIOUS", id="restore-btn", n_clicks=0, style=restore_button_style),
        html.Button("Jump to Source ", id="jump-source-btn", n_clicks=0, style=button_style),
        html.Button("Jump to Aim ", id="jump-aim-btn", n_clicks=0, style=button_style),

        html.Div([
            html.Button("Run Attack", id="attack-dropdown-btn", n_clicks=0, style=button_style),
            html.Div([
                html.Button("Budgeted Attack", id="budgeted-attack-btn", n_clicks=0, style=dropdown_button_style),
                html.Button("Multi-Step Attack", id="multi-step-attack-btn", n_clicks=0,
                            style={**dropdown_button_style, "borderBottomLeftRadius": "6px",
                                   "borderBottomRightRadius": "6px"})
            ], id="attack-options", style=dropdown_content_style)
        ], style=dropdown_container_style),

        html.Button("Show Attacked Edges", id="show-attack-btn", n_clicks=0, style=button_style),
        html.Button("Legend", id="toggle-legend-btn", n_clicks=0, style=button_style),

        html.Div(id="color-legend-box", style={"display": "none"}, children=create_color_legend()),
        html.Div(id="info-box", style=box_style, children=initial_info),
        html.Div(id="affected-edges-box", style={**affected_edges_style, "display": "none"}),
        html.Div(id="capacity-box", style={**capacity_box_style, "display": "none"}),
    ], style=sidebar_style),

    html.Div(id="3d-graph", style={
        "position": "absolute", "top": "0px", "left": "0px", "width": "100vw",
        "height": "100vh", "zIndex": "0", "overflow": "hidden",
    }),

    html.Div(id="camera-action", style={"display": "none"}),

    dcc.Store(id="graph-data-store", data=graph_data_json),
    dcc.Store(id="attacked-edges-store", data=[]),            # authoritative list used by "Show Attacked"
    dcc.Store(id="original-graph-store", data=graph_data_json),
    dcc.Store(id="pre-attack-graph-store", data=graph_data_json),
])

@app.callback(
    Output("color-legend-box", "style"),
    Input("toggle-legend-btn", "n_clicks"),
    State("color-legend-box", "style"),
    prevent_initial_call=True
)
def toggle_color_legend(n_clicks, current_style):
    if (n_clicks or 0) % 2 == 1:
        return {**current_style, "display": "block"}
    else:
        return {**current_style, "display": "none"}

# Dropdown open/close — simple, toggle only by the parent button
app.clientside_callback(
    """
    function(runClicks) {
        const open = (runClicks || 0) % 2 === 1;
        return { display: open ? "block" : "none" };
    }
    """,
    Output("attack-options", "style"),
    Input("attack-dropdown-btn", "n_clicks")
)

@app.callback(
    Output("camera-action", "children"),
    Output("info-box", "children"),
    Output("graph-data-store", "data"),
    Output("affected-edges-box", "children"),
    Output("affected-edges-box", "style"),
    Output("capacity-box", "children"),
    Output("capacity-box", "style"),
    Output("attacked-edges-store", "data"),
    Output("original-graph-store", "data"),
    Output("pre-attack-graph-store", "data"),
    Input("jump-source-btn", "n_clicks"),
    Input("jump-aim-btn", "n_clicks"),
    Input("restore-btn", "n_clicks"),
    Input("budgeted-attack-btn", "n_clicks"),
    Input("show-attack-btn", "n_clicks"),
    Input("multi-step-attack-btn", "n_clicks"),
    State("graph-data-store", "data"),
    State("attacked-edges-store", "data"),
    State("original-graph-store", "data"),
    State("pre-attack-graph-store", "data"),
    prevent_initial_call=True
)
def unified_callback(jump_source, jump_aim, restore, budgeted_attack_clicks, show_attack, multi_step_attack_click,
                     current_graph_data, attacked_edges_data, original_graph_data, pre_attack_graph_data):

    triggered = dash.callback_context.triggered
    if not triggered:
        return dash.no_update, *([dash.no_update] * 9)

    trigger = triggered[0]["prop_id"].split(".")[0]

    # RESTORE
    if trigger == "restore-btn":
        if pre_attack_graph_data:
            return (
                "refresh",
                html.Div([html.H4("Graph Restored"), html.P("Restored to previous state")]),
                pre_attack_graph_data,
                dash.no_update, {"display": "none"},
                dash.no_update, {"display": "none"},
                [],
                original_graph_data,
                pre_attack_graph_data
            )
        else:
            global G
            G = copy.deepcopy(ORIGINAL_GRAPH)
            updated_json = json.dumps(create_graph_data(G))
            msg = [html.H4("Graph Reset"), html.P("Restored to original state")]
            if file_warning:
                msg.append(html.P(file_warning))
            return (
                "reset",
                html.Div(msg),
                updated_json,
                dash.no_update, {"display": "none"},
                dash.no_update, {"display": "none"},
                [],
                updated_json,
                updated_json
            )

    elif trigger == "jump-source-btn":
        return "jump-N1", *([dash.no_update] * 9)
    elif trigger == "jump-aim-btn":
        return "jump-N1036", *([dash.no_update] * 9)

    # ---------- BUDGETED ATTACK ----------
    elif trigger == "budgeted-attack-btn":
        pre_attack_data = current_graph_data

        caps_before = snapshot_caps(G)
        total_capacity_before = calculate_total_capacity(G)

        flow_before, flow_after = budgeted_attack(G, "N1", "N1036", budget=150)

        attacked_rows_true = edge_diffs(caps_before, G)
        attacked_edge_pairs = {(r["source"], r["target"]) for r in attacked_rows_true}

        updated_data = create_graph_data(G)
        for link in updated_data["links"]:
            if (link["source"], link["target"]) in attacked_edge_pairs:
                link["color"] = "red"

        rows = rows_from_red_links(updated_data["links"], caps_before, G)
        affected_edges_content = html.Div([
            html.H4("Affected Edges"),
            html.Ul([
                html.Li(f"{display_node_label(r['source'])} → {display_node_label(r['target'])}: "
                        f"{r['before']} → {r['after']} (−{r['reduction']})")
                for r in rows
            ])
        ])

        total_capacity_after = calculate_total_capacity(G)
        severity = (flow_before - flow_after) / flow_before if flow_before else 0
        severity_level = "Low" if severity < 0.1 else "Moderate" if severity < 0.3 else "High"

        attack_info = html.Div([
            html.H4("Cyber Attack Report"),
            html.P(f"Severity: {severity_level}"),
            html.P(f"Flow Before: {flow_before}"),
            html.P(f"Flow After: {flow_after}")
        ])

        reduction = total_capacity_before - total_capacity_after
        percent = (reduction / total_capacity_before * 100) if total_capacity_before else 0

        capacity_content = html.Div([
            html.H4("Network Capacity"),
            html.P(f"Total capacity before attack: {total_capacity_before}"),
            html.P(f"Total capacity after attack: {total_capacity_after}"),
            html.P(f"Capacity reduced by: {reduction} ({percent:.1f}%)")
        ])

        attacked_edges_list = rows

        return (
            "refresh",
            attack_info,
            json.dumps(updated_data),
            affected_edges_content, {"display": "block", **affected_edges_style},
            capacity_content, {"display": "block", **capacity_box_style},
            attacked_edges_list,
            original_graph_data,
            pre_attack_data
        )

    # ---------- MULTI-STEP ATTACK ----------
    elif trigger == "multi-step-attack-btn":
        pre_attack_data = current_graph_data

        caps_before = snapshot_caps(G)
        total_capacity_before = calculate_total_capacity(G)

        flow_before, flow_after = multi_step_attack(
            G, "N1", "N1036", information='flow', steps=3, edges_per_step=10
        )

        attacked_rows_true = edge_diffs(caps_before, G)
        attacked_edge_pairs = {(r["source"], r["target"]) for r in attacked_rows_true}

        updated_data = create_graph_data(G)
        for link in updated_data["links"]:
            if (link["source"], link["target"]) in attacked_edge_pairs:
                link["color"] = "red"

        rows = rows_from_red_links(updated_data["links"], caps_before, G)
        affected_edges_content = html.Div([
            html.H4("Affected Edges"),
            html.Ul([
                html.Li(f"{display_node_label(r['source'])} → {display_node_label(r['target'])}: "
                        f"{r['before']} → {r['after']} (−{r['reduction']})")
                for r in rows
            ])
        ])

        total_capacity_after = calculate_total_capacity(G)

        flow_reduction = max(0, flow_before - flow_after)
        flow_pct = (flow_reduction / flow_before * 100) if flow_before else 0.0
        severity = flow_pct / 100.0
        severity_level = "Low" if severity < 0.1 else "Moderate" if severity < 0.3 else "High"

        attack_info = html.Div([
            html.H4("Multi-Step Attack Report"),
            html.P(f"Severity (by flow drop): {severity_level}"),
            html.P(f"Flow Before: {flow_before}"),
            html.P(f"Flow After: {flow_after}")
        ])

        cap_reduction = total_capacity_before - total_capacity_after
        cap_pct = (cap_reduction / total_capacity_before * 100) if total_capacity_before else 0.0

        capacity_content = html.Div([
            html.H4("Network Capacity"),
            html.P(f"Total capacity before attack: {total_capacity_before}"),
            html.P(f"Total capacity after attack: {total_capacity_after}"),
            html.P(f"Capacity reduced by: {cap_reduction} ({cap_pct:.1f}%)"),
            html.Hr(),
            html.H4("Max Flow"),
            html.P(f"Flow before: {flow_before}"),
            html.P(f"Flow after: {flow_after}"),
            html.P(f"Reduction: {flow_reduction} ({flow_pct:.1f}%)"),
        ])

        attacked_edges_list = rows

        return (
            "refresh",
            attack_info,
            json.dumps(updated_data),
            affected_edges_content, {"display": "block", **affected_edges_style},
            capacity_content, {"display": "block", **capacity_box_style},
            attacked_edges_list,
            original_graph_data,
            pre_attack_data
        )

    # ---------- SHOW ATTACKED EDGES ----------
    elif trigger == "show-attack-btn":
        if not attacked_edges_data:
            return dash.no_update, *([dash.no_update] * 9)

        base_data = create_graph_data(G)
        attacked_pairs = {(row["source"], row["target"]) for row in attacked_edges_data}
        node_index = {n["id"]: n for n in base_data["nodes"]}
        link_index = {(l["source"], l["target"]): l for l in base_data["links"]}

        nodes_to_show = set()
        links_to_show = {}

        def _add_link(u, v, color):
            if (u, v) not in link_index:
                return
            base = link_index[(u, v)].copy()
            prev = links_to_show.get((u, v))
            if prev and prev.get("color") == "red":
                return
            if color == "red":
                base["color"] = "red"
            else:
                base["color"] = prev.get("color") if (prev and prev.get("color") == "red") else color
            links_to_show[(u, v)] = base
            nodes_to_show.add(u); nodes_to_show.add(v)

        for (u, v) in attacked_pairs:
            _add_link(u, v, "red")

        # Shortest path cache
        _sp_cache = {}
        def _sp(a, b):
            key = (a, b)
            if key in _sp_cache:
                return _sp_cache[key]
            try:
                p = nx.shortest_path(G, a, b)
            except nx.NetworkXNoPath:
                p = []
            _sp_cache[key] = p
            return p

        for (u, v) in attacked_pairs:
            left = _sp("N1", u)
            if left and len(left) > 1:
                for a, b in zip(left, left[1:]):
                    _add_link(a, b, "green")
            right = _sp(v, "N1036")
            if right and len(right) > 1:
                for a, b in zip(right, right[1:]):
                    _add_link(a, b, "purple")

        attacked_nodes = [node_index[nid] for nid in nodes_to_show if nid in node_index]
        attacked_links = list(links_to_show.values())

        filtered_data = {
            "nodes": attacked_nodes,
            "links": attacked_links
        }

        def _numlabel(nid: str) -> str:
            return str(node_index.get(nid, {}).get("name", nid))

        info_children = [
            html.H4("Attacked Edges (All) + Context"),
            html.P(f"Total attacked edges: {len(attacked_pairs)}"),
            html.P("Colors: red = attacked edge, green = N1→edge-source, purple = edge-target→N1036."),
            html.Ul([
                html.Li(f"{_numlabel(u)} → {_numlabel(v)}")
                for (u, v) in sorted(attacked_pairs)
            ], style={"maxHeight": "260px", "overflowY": "auto", "margin": 0, "paddingLeft": "18px"})
        ]
        info_box_content = html.Div(info_children)

        return (
            "show-attacked",
            info_box_content,
            json.dumps(filtered_data),
            dash.no_update, dash.no_update,
            dash.no_update, dash.no_update,
            dash.no_update, dash.no_update, dash.no_update
        )

    return dash.no_update, *([dash.no_update] * 9)

# ---- Client-side renderer (reads live graphData; safe source/target id handling)
app.clientside_callback(
    """
    function(action, updatedGraphData) {
        const graphData = JSON.parse(updatedGraphData || '{}');

        if (!window.fgInstance) {
            const interval = setInterval(() => {
                if (!window.ForceGraph3D || !window.THREE) return;
                clearInterval(interval);

                const Graph = ForceGraph3D();
                const graphContainer = document.getElementById("3d-graph");
                const infoBox = document.getElementById("info-box");

                const fg = Graph(graphContainer);
                fg.d3Force('charge').strength(-350);
                fg.d3Force('center', null);

                fg.graphData(graphData)
                  .nodeLabel(node => `<span style="color: black;">${node.name}</span>`)
                  .nodeRelSize(8)
                  .nodeAutoColorBy('id')
                  .linkColor(link => link.color || (link.capacity > 40 ? '#000' : '#aaa'))
                  .linkWidth(link => Math.max(0.5, Math.min(link.capacity / 10, 3)))
                  .linkOpacity(link => link.color ? 1 : Math.max(0.1, Math.min(link.capacity / 50, 0.9)))
                  .backgroundColor('white')
                  .nodeThreeObject(node => {
                      const THREE = window.THREE;
                      let color = 'blue';
                      if (node.isRoot) color = 'green';
                      else if (node.isAim) color = 'deeppink';
                      else if (node.color === 'red') color = 'red';
                      const geometry = new THREE.CircleGeometry(12, 44);
                      const material = new THREE.MeshBasicMaterial({ color: color, side: THREE.DoubleSide });
                      const circle = new THREE.Mesh(geometry, material);
                      return circle;
                  })
                  .onNodeClick(node => {
                      const gd = fg.graphData();
                      const outgoing = gd.links
                        .filter(l => (l.source.id || l.source) === node.id)
                        .map(l => [ (l.source.id || l.source), (l.target.id || l.target), l.capacity ]);
                      const incoming = gd.links
                        .filter(l => (l.target.id || l.target) === node.id)
                        .map(l => [ (l.source.id || l.source), (l.target.id || l.target), l.capacity ]);

                      // Render info via direct DOM write (kept from original pattern)
                      infoBox.innerHTML = `
                          <h4>Selected Node: ${node.name ?? node.id}</h4>
                          <strong>Outgoing Edges (${outgoing.length}):</strong>
                          <ul>${outgoing.map(e => `<li>${gd.nodes.find(n=>n.id===e[0]).name ?? e[0]} → ${gd.nodes.find(n=>n.id===e[1]).name ?? e[1]} (Capacity: ${e[2]})</li>`).join('')}</ul>
                          <strong>Incoming Edges (${incoming.length}):</strong>
                          <ul>${incoming.map(e => `<li>${gd.nodes.find(n=>n.id===e[0]).name ?? e[0]} → ${gd.nodes.find(n=>n.id===e[1]).name ?? e[1]} (Capacity: ${e[2]})</li>`).join('')}</ul>
                      `;

                      gd.nodes.forEach(n => { if (!n.isRoot && !n.isAim) delete n.color; });
                      node.color = 'red';
                      fg.refresh();
                  })
                  .onLinkClick(link => {
                      const gd = fg.graphData();
                      const src = (link.source.id || link.source);
                      const dst = (link.target.id || link.target);
                      const srcName = gd.nodes.find(n=>n.id===src)?.name ?? src;
                      const dstName = gd.nodes.find(n=>n.id===dst)?.name ?? dst;

                      // Preserve red (attacked) links; clear only non-red highlight colors
                      gd.links.forEach(l => { if (l.color && l.color !== 'red') delete l.color; });
                      if (link.color !== 'red') link.color = 'orange';

                      // Info panel
                      const infoBox = document.getElementById("info-box");
                      infoBox.innerHTML = `
                          <h4>Selected Edge</h4>
                          <p><strong>${srcName} → ${dstName}</strong></p>
                          <p>Capacity: ${link.capacity}</p>
                      `;
                      fg.refresh();
                  })
                  .onNodeDragEnd(node => {
                      node.fx = node.x; node.fy = node.y; node.fz = node.z;
                  });

                window.fgInstance = fg;

                graphContainer.addEventListener("dblclick", function() {
                    fg.cameraPosition({ x: 0, y: 0, z: 500 }, { x: 0, y: 0, z: 0 }, 1000);
                    const gd = fg.graphData();
                    gd.nodes.forEach(n => { if (!n.isRoot && !n.isAim) { delete n.color; delete n.fx; delete n.fy; delete n.fz; } });
                    gd.links.forEach(l => { if (l.color && l.color !== 'red') delete l.color; }); // keep attacked red
                    fg.nodeAutoColorBy('id');
                    const infoBox = document.getElementById("info-box");
                    infoBox.innerHTML = '';
                    fg.refresh();
                    fg.d3ReheatSimulation();
                });
            }, 100);
            return '';
        }

        // Existing instance: respond to actions
        if (typeof action === 'string' && action.startsWith("jump-")) {
            const nodeId = action.split("-")[1];
            const node = window.fgInstance.graphData().nodes.find(n => n.id === nodeId);
            if (node) {
                window.fgInstance.cameraPosition({ x: node.x, y: node.y, z: node.z + 150 }, node, 1000);
            }
        } else if (action === "back-to-main" || action === "refresh" || action === "show-attacked" || action === "reset") {
            const newGraph = JSON.parse(updatedGraphData || '{}');
            window.fgInstance.graphData(newGraph);
            if (action === "reset") {
                window.fgInstance.cameraPosition({ x: 0, y: 0, z: 500 }, { x: 0, y: 0, z: 0 }, 1000);
                const gd = window.fgInstance.graphData();
                gd.nodes.forEach(n => { delete n.color; delete n.fx; delete n.fy; delete n.fz; });
                gd.links.forEach(l => { if (l.color && l.color !== 'red') delete l.color; });
                window.fgInstance.nodeAutoColorBy('id');
                const infoBox = document.getElementById("info-box");
                infoBox.innerHTML = '';
                window.fgInstance.d3ReheatSimulation();
            }
            window.fgInstance.refresh();
            return '';
        }

        return "Action complete.";
    }
    """,
    Output("info-box", "children"),
    Input("camera-action", "children"),
    State("graph-data-store", "data")
)

if __name__ == '__main__':
    app.run(debug=True)
