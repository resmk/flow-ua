#show attack edges works
#show attack button hide and show

import dash
from dash import html, dcc
from dash_extensions.enrich import DashProxy, TriggerTransform, MultiplexerTransform
from dash.dependencies import Output, Input, State
import networkx as nx
import re
import json
import copy

# ---------- GRAPH GENERATION ----------
# App-wide contract constants (do not change elsewhere)
SRC_LABEL = "N1"
DST_LABEL = "N100"

# --- your parser (unchanged) ---
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
                G.add_edge(
                    src, tgt,
                    capacity=float(cap_s),
                    attack_cost=float(cost_s),
                    can_attack=(float(att_s) == 1.0)
                )
    return G

# --- adapter helpers ---
def _ensure_capacity(G, min_cap=1):
    for u, v, d in G.edges(data=True):
        if "capacity" not in d or d["capacity"] is None:
            d["capacity"] = min_cap
        else:
            try:
                d["capacity"] = max(int(d["capacity"]), min_cap)
            except Exception:
                d["capacity"] = min_cap

def _relabel_numeric_to_contract(G, src_numeric: str, dst_numeric: str):
    """
    Map numeric node id strings to N*-style ids while keeping the original numeric
    id visible in 'name'. Guarantees src->N1 and dst->N100.
    """
    # Stable ordering of all nodes (numeric ascending where possible)
    def _numkey(x):
        try:
            return (0, int(x))
        except ValueError:
            return (1, x)
    nodes_sorted = sorted(G.nodes(), key=_numkey)

    mapping = {}
    next_label_index = 1

    # Reserve N1 for source
    mapping[src_numeric] = SRC_LABEL

    # Reserve N100 for sink
    if dst_numeric == src_numeric:
        raise ValueError("Source and target cannot be the same.")
    mapping[dst_numeric] = DST_LABEL

    # Assign N2..N* to remaining nodes in stable order, skipping 1 and 100
    def _next_free_label():
        nonlocal next_label_index
        while True:
            next_label_index += 1
            if next_label_index not in (1, 100):
                return f"N{next_label_index}"

    for n in nodes_sorted:
        if n in (src_numeric, dst_numeric):
            continue
        if n not in mapping:
            mapping[n] = _next_free_label()

    G2 = nx.DiGraph()
    for old in G.nodes():
        G2.add_node(mapping[old], name=old)  # keep original numeric id in 'name'
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
                "name": G.nodes[node].get("name", node),  # show original numeric if present
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

def build_info_dicts(G):
    node_info = {
        node: {
            "incoming": [(u, v, G[u][v]["capacity"]) for u, v in G.in_edges(node)],
            "outgoing": [(u, v, G[u][v]["capacity"]) for u, v in G.out_edges(node)],
        }
        for node in G.nodes()
    }
    edge_info = {
        f"{u}->{v}": {"source": u, "target": v, "capacity": G[u][v]["capacity"]}
        for u, v in G.edges()
    }
    return node_info, edge_info

# --- load your file graph and adapt it to the app contract ---
file_path = "/Users/miraki/Desktop/sem3/flowua/code/NEW GRAPH/graph.text"
RAW_SOURCE = "0"
RAW_TARGET = "1035"

G_raw = parse_adjacency_list(file_path, max_nodes=1036)
_ensure_capacity(G_raw, min_cap=1)
G = _relabel_numeric_to_contract(G_raw, RAW_SOURCE, RAW_TARGET)

# Make sure source has no incoming edges (the app assumes this)
G.remove_edges_from(list(G.in_edges(SRC_LABEL)))

# (Optional) if there is no path to sink, you can either raise or add a simple chain.
# Here we just leave it; your app handles no-path cases in certain views.

ORIGINAL_GRAPH = copy.deepcopy(G)
root_node = SRC_LABEL  # the green node in your UI

# Build the JSON payloads the rest of the app expects
graph_data = create_graph_data(G)
node_info, edge_info = build_info_dicts(G)
graph_data_json = json.dumps(graph_data)
node_info_json = json.dumps(node_info)
edge_info_json = json.dumps(edge_info)


def budgeted_attack(G, source="N1", sink="N100", budget=300):
    G_copy = copy.deepcopy(G)
    flow_value_before, flow_dict = nx.maximum_flow(
        G_copy, source, sink,
        flow_func=nx.algorithms.flow.edmonds_karp
    )

    flow_edges = [(u, v, G_copy[u][v]['capacity']) for u in flow_dict for v in flow_dict[u] if flow_dict[u][v] > 0]
    flow_edges.sort(key=lambda x: x[2], reverse=True)

    total_reduced = 0
    affected_edges = []
    for u, v, cap in flow_edges:
        if total_reduced >= budget:
            break
        reduction = min(cap - 1, budget - total_reduced)
        G[u][v]['capacity'] = max(1, cap - reduction)
        total_reduced += reduction
        affected_edges.append((u, v, reduction))

    flow_value_after, _ = nx.maximum_flow(
        G, source, sink,
        flow_func=nx.algorithms.flow.edmonds_karp
    )
    return flow_value_before, flow_value_after, affected_edges

def multi_step_attack(G, source, sink, information='capacity', steps=3, edges_per_step=30):
    G_copy = copy.deepcopy(G)
    flow_value_before, flow_dict = nx.maximum_flow(G_copy, source, sink)
    affected_edges = []

    for step in range(steps):
        flow_value, flow_dict = nx.maximum_flow(G_copy, source, sink)
        edges_to_reduce = []
        
        if information == 'flow':
            flow_edges = [(u, v, flow_dict[u][v]) for u in flow_dict for v in flow_dict[u]]
            flow_edges.sort(key=lambda x: x[2], reverse=True)
            edges_to_reduce = flow_edges[:edges_per_step]
        else:
            cap_edges = [(u, v, G_copy[u][v]['capacity']) for u, v in G_copy.edges()]
            cap_edges.sort(key=lambda x: x[2], reverse=True)
            edges_to_reduce = cap_edges[:edges_per_step]

        for u, v, _ in edges_to_reduce:
            if G_copy.has_edge(u, v):
                old_cap = G_copy[u][v]['capacity']
                G_copy[u][v]['capacity'] = max(1, old_cap // 2)
                affected_edges.append((u, v, old_cap - G_copy[u][v]['capacity']))

    flow_value_after, _ = nx.maximum_flow(G_copy, source, sink)
    for u, v, _ in affected_edges:
        if G.has_edge(u, v):
            G[u][v]['capacity'] = G_copy[u][v]['capacity']
    return flow_value_before, flow_value_after, affected_edges

def build_info_dicts(G):
    node_info = {
        node: {
            "incoming": [(u, v, G[u][v]['capacity']) for u, v in G.in_edges(node)],
            "outgoing": [(u, v, G[u][v]['capacity']) for u, v in G.out_edges(node)]
        }
        for node in G.nodes()
    }
    edge_info = {
        f"{u}->{v}": {"source": u, "target": v, "capacity": G[u][v]['capacity']}
        for u, v in G.edges()
    }
    return node_info, edge_info


def create_color_legend():
    return html.Div([
        html.H4("Color Legend", style={"marginBottom": "10px"}),
        html.Div([
            html.Span("⬤", style={"color": "red", "marginRight": "6px"}),
            html.Span("Attacked Edge", style={"fontSize": "14px"})
        ], style={"marginBottom": "6px"}),
        html.Div([
            html.Span("⬤", style={"color": "green", "marginRight": "6px"}),
            html.Span("Path 1", style={"fontSize": "14px"})
        ], style={"marginBottom": "6px"}),
        html.Div([
            html.Span("⬤", style={"color": "blue", "marginRight": "6px"}),
            html.Span("Path 2", style={"fontSize": "14px"})
        ], style={"marginBottom": "6px"}),
        html.Div([
            html.Span("⬤", style={"color": "orange", "marginRight": "6px"}),
            html.Span("Path 3", style={"fontSize": "14px"})
        ], style={"marginBottom": "6px"}),
        html.Div([
            html.Span("⬤", style={"color": "purple", "marginRight": "6px"}),
            html.Span("Path 4", style={"fontSize": "14px"})
        ], style={"marginBottom": "6px"}),
        html.Div([
            html.Span("⬤", style={"color": "cyan", "marginRight": "6px"}),
            html.Span("Path 5", style={"fontSize": "14px"})
        ], style={"marginBottom": "6px"}),
        html.Div([
            html.Span("⬤", style={"color": "brown", "marginRight": "6px"}),
            html.Span("Path 6", style={"fontSize": "14px"})
        ], style={"marginBottom": "6px"}),
        html.Div([
            html.Span("⬤", style={"color": "magenta", "marginRight": "6px"}),
            html.Span("Path 7", style={"fontSize": "14px"})
        ]),
        html.Hr(style={"margin": "10px 0"}),
        html.Div([
            html.Span("⬤", style={"color": "green", "marginRight": "6px"}),
            html.Span("Source Node ", style={"fontSize": "14px"})
        ], style={"marginBottom": "6px"}),
        html.Div([
            html.Span("⬤", style={"color": "deeppink", "marginRight": "6px"}),
            html.Span("Target Node ", style={"fontSize": "14px"})
        ])
    ], style={
        "backgroundColor": "#f8f9fa",
        "padding": "15px",
        "borderRadius": "8px",
        "border": "1px solid #dee2e6",
        "marginBottom": "20px"
    })

graph_data = create_graph_data(G)
node_info, edge_info = build_info_dicts(G)
graph_data_json = json.dumps(graph_data)
node_info_json = json.dumps(node_info)
edge_info_json = json.dumps(edge_info)

external_scripts = [
    "https://unpkg.com/three@0.150.1/build/three.min.js",
    "https://unpkg.com/3d-force-graph"
]

external_stylesheets = [
    "https://fonts.googleapis.com/css2?family=Roboto:wght@400;700&display=swap"
]

app = DashProxy(__name__,
                external_scripts=external_scripts,
                external_stylesheets=external_stylesheets,
                transforms=[TriggerTransform(), MultiplexerTransform()])

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

restore_button_style = {
    **button_style,
    "backgroundColor": "#2dc00f",  # Gray color to differentiate
    "marginTop": "10px"  # Extra spacing
}

sidebar_style = {
    "position": "absolute",
    "top": "20px",
    "left": "20px",
    "width": "320px",
    "maxHeight": "90vh",
    "overflowY": "auto",
    "display": "flex",
    "flexDirection": "column",
    "gap": "20px",
    "zIndex": 11,
}

box_style = {
    "width": "100%",
    "padding": "15px",
    "borderRadius": "8px",
    "boxShadow": "0 2px 8px rgba(0,0,0,0.1)",
    "backgroundColor": "#FFFFFF",
    "border": "1px solid #E0E0E0",
    "fontFamily": "Roboto, sans-serif",
}

info_box_style = {**box_style}
affected_edges_style = {**box_style, "backgroundColor": "#FFF8F8", "border": "1px solid #FFCCCC"}
capacity_box_style = {**box_style, "backgroundColor": "#F0F8FF", "border": "1px solid #ADD8E6"}

dropdown_container_style = {
    "position": "relative",
    "width": "100%"
}

dropdown_content_style = {
    "display": "none",
    "position": "absolute",
    "width": "100%",
    "zIndex": 100
}

dropdown_button_style = {
    **button_style,
    "backgroundColor": "#0069D9",
    "marginBottom": "0",
    "borderRadius": "0"
}

app.layout = html.Div([
    html.Div([
        html.Button("RESTORE PREVIOUS", id="restore-btn", n_clicks=0, style=restore_button_style),
        html.Button("Jump to Source ", id="jump-source-btn", n_clicks=0, style=button_style),
        html.Button("Jump to Aim ", id="jump-aim-btn", n_clicks=0, style=button_style),
        
        # New dropdown attack button
        html.Div([
            html.Button("Run Attack", id="attack-dropdown-btn", n_clicks=0, style=button_style),
            html.Div([
                html.Button("Budgeted Attack", id="budgeted-attack-btn", n_clicks=0, style=dropdown_button_style),
                html.Button("Multi-Step Attack", id="multi-step-attack-btn", n_clicks=0, 
                          style={**dropdown_button_style, "borderBottomLeftRadius": "6px", "borderBottomRightRadius": "6px"})
            ], id="attack-options", style=dropdown_content_style)
        ], style=dropdown_container_style),
        
        html.Button("Show Attacked Edges", id="show-attack-btn", n_clicks=0, style=button_style),
        html.Div(id="color-legend-box", style={"display": "none"}, children=create_color_legend()),
        html.Div(id="info-box", style=info_box_style),
        html.Div(id="affected-edges-box", style={**affected_edges_style, "display": "none"}),
        html.Div(id="capacity-box", style={**capacity_box_style, "display": "none"}),
    ], style=sidebar_style),

    html.Div(id="3d-graph", style={
        "position": "absolute",
        "top": "0px",
        "left": "0px",
        "width": "100vw",
        "height": "100vh",
        "zIndex": "0",
        "overflow": "hidden",
    }),

    html.Div(id="camera-action", style={"display": "none"}),

    dcc.Store(id="graph-data-store", data=graph_data_json),
    dcc.Store(id="attacked-edges-store", data=[]),
    dcc.Store(id="original-graph-store", data=graph_data_json),
    dcc.Store(id="pre-attack-graph-store", data=graph_data_json),
])

@app.callback(
    Output("color-legend-box", "style"),
    Input("show-attack-btn", "n_clicks"),
    State("color-legend-box", "style"),
    prevent_initial_call=True
)
def toggle_color_legend(n_clicks, current_style):
    if n_clicks % 2 == 1:  # Odd clicks show, even clicks hide
        return {**current_style, "display": "block"}
    else:
        return {**current_style, "display": "none"}

def calculate_total_capacity(G):
    return sum(data['capacity'] for u, v, data in G.edges(data=True))

def find_paths_to_source_and_aim(G, u, v):
    try:
        path_from_source = nx.shortest_path(G, "N1", u)
    except nx.NetworkXNoPath:
        path_from_source = []
    try:
        path_to_aim = nx.shortest_path(G, v, "N100")
    except nx.NetworkXNoPath:
        path_to_aim = []
    return path_from_source, path_to_aim

# Clientside callback for dropdown toggle
# Toggle open/close with "Run Attack" and auto-close after choosing an attack
app.clientside_callback(
    """
    function(runClicks, budgetClicks, multiClicks) {
        const options = document.getElementById("attack-options");

        // If either attack-type button was clicked → close menu
        if ((budgetClicks && budgetClicks > 0) || (multiClicks && multiClicks > 0)) {
            return {"display": "none"};
        }

        // Otherwise toggle open/close with Run Attack button
        if (runClicks % 2 === 1) {
            return {"display": "block"};
        } else {
            return {"display": "none"};
        }
    }
    """,
    Output("attack-options", "style"),
    Input("attack-dropdown-btn", "n_clicks"),
    Input("budgeted-attack-btn", "n_clicks"),
    Input("multi-step-attack-btn", "n_clicks")
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

    if trigger == "restore-btn":
        # If there's a pre-attack state, restore to that
        if pre_attack_graph_data:
            return (
                "refresh",
                html.Div([html.H4("Graph Restored"), html.P("Restored to previous state")]),
                pre_attack_graph_data,
                dash.no_update,
                {"display": "none"},
                dash.no_update,
                {"display": "none"},
                [],  # Clear attacked edges store
                original_graph_data,
                pre_attack_graph_data
            )
        # If no pre-attack state, restore to original
        else:
            global G
            G = copy.deepcopy(ORIGINAL_GRAPH)
            updated_data = create_graph_data(G)
            return (
                "reset",
                html.Div([html.H4("Graph Reset"), html.P("Restored to original state")]),
                json.dumps(updated_data),
                dash.no_update,
                {"display": "none"},
                dash.no_update,
                {"display": "none"},
                [],
                json.dumps(updated_data),
                json.dumps(updated_data)
            )
    elif trigger == "jump-source-btn":
        return "jump-N1", *([dash.no_update] * 9)
    elif trigger == "jump-aim-btn":
        return "jump-N100", *([dash.no_update] * 9)
        
    elif trigger == "budgeted-attack-btn":
        pre_attack_data = current_graph_data
        total_capacity_before = calculate_total_capacity(G)
        flow_before, flow_after, affected_edges = budgeted_attack(G, "N1", "N100", budget=300)
        
        updated_data = create_graph_data(G)
        attacked_edge_pairs = [(u, v) for u, v, _ in affected_edges]
        for link in updated_data["links"]:
            if (link["source"], link["target"]) in attacked_edge_pairs:
                link["color"] = "red"  # Set attacked edges to red
        
        total_capacity_after = calculate_total_capacity(G)
        severity = (flow_before - flow_after) / flow_before
        severity_level = "Low" if severity < 0.1 else "Moderate" if severity < 0.3 else "High"
        
        attack_info = html.Div([
            html.H4("Cyber Attack Report"),
            html.P(f"Severity: {severity_level}"),
            html.P(f"Flow Before: {flow_before}"),
            html.P(f"Flow After: {flow_after}")
        ])
        
        affected_edges_content = html.Div([
            html.H4("Affected Edges"),
            html.Ul([html.Li(f"{u} → {v}: -{cap}") for u, v, cap in affected_edges])
        ])
        
        capacity_content = html.Div([
            html.H4("Network Capacity"),
            html.P(f"Total Before: {total_capacity_before}"),
            html.P(f"Total After: {total_capacity_after}"),
            html.P(f"Reduction: {total_capacity_before - total_capacity_after}"),
            html.P(f"Percentage: {((total_capacity_before - total_capacity_after) / total_capacity_before * 100):.1f}%"),
        ])
        
        affected_edges_list = [{"source": u, "target": v, "reduction": cap} for u, v, cap in affected_edges]
        
        return (
            "refresh", attack_info, json.dumps(updated_data),
            affected_edges_content, {"display": "block", **affected_edges_style},
            capacity_content, {"display": "block", **capacity_box_style},
            affected_edges_list,
            json.dumps(original_graph_data),
            pre_attack_data
        )

    elif trigger == "multi-step-attack-btn":
        pre_attack_data = current_graph_data
        flow_before, flow_after, affected_edges = multi_step_attack(G, "N1", "N100", steps=3, edges_per_step=10)
        
        updated_data = create_graph_data(G)
        attacked_edge_pairs = [(u, v) for u, v, _ in affected_edges]
        for link in updated_data["links"]:
            if (link["source"], link["target"]) in attacked_edge_pairs:
                link["color"] = "red"
        
        severity = (flow_before - flow_after) / flow_before
        severity_level = "Low" if severity < 0.1 else "Moderate" if severity < 0.3 else "High"
        
        attack_info = html.Div([
            html.H4("Multi-Step Attack Report"),
            html.P(f"Severity: {severity_level}"),
            html.P(f"Flow Before: {flow_before}"),
            html.P(f"Flow After: {flow_after}")
        ])
        
        affected_edges_content = html.Div([
            html.H4("Affected Edges"),
            html.Ul([html.Li(f"{u} → {v}: -{cap}") for u, v, cap in affected_edges])
        ])
        
        capacity_content = html.Div([
            html.H4("Network Capacity"),
            html.P(f"Flow Before: {flow_before}"),
            html.P(f"Flow After: {flow_after}"),
            html.P(f"Reduction: {flow_before - flow_after}"),
            html.P(f"Percentage: {((flow_before - flow_after) / flow_before * 100):.1f}%"),
        ])
        
        affected_edges_list = [{"source": u, "target": v, "reduction": cap} for u, v, cap in affected_edges]
        
        return (
            "refresh", attack_info, json.dumps(updated_data),
            affected_edges_content, {"display": "block", **affected_edges_style},
            capacity_content, {"display": "block", **capacity_box_style},
            affected_edges_list,
            json.dumps(original_graph_data),
            pre_attack_data
        )
        
    elif trigger == "show-attack-btn":
        if not attacked_edges_data:
            return dash.no_update, *([dash.no_update] * 9)

        current_data = json.loads(current_graph_data)
        path_colors = ["green", "blue", "purple", "cyan", "brown", "magenta"]

        nodes_to_show = set()
        filtered_links = []
        colored_paths_info = []

        # helper: safe shortest path
        def _sp(a, b):
            try:
                return nx.shortest_path(G, a, b)
            except nx.NetworkXNoPath:
                return []

        # cap how many attacked edges to visualize to keep UI snappy
        MAX_EDGES_TO_SHOW = 6
        attacked_subset = attacked_edges_data[:MAX_EDGES_TO_SHOW]

        for idx, edge in enumerate(attacked_subset):
            u, v = edge["source"], edge["target"]
            color = path_colors[idx % len(path_colors)]

            # build a single representative path that passes through (u, v)
            left = _sp("N1", u)
            right = _sp(v, "N100")
            if not left or not right:
                continue  # skip if no connection

            full_nodes = left + right  # left already ends at u; right starts at v (u -> v is implicit here)
            # insert the edge u->v if it is not consecutive (rare if left[-1] == u and right[0] == v)
            if left and right and (left[-1] != u or right[0] != v):
                full_nodes = left + [v] + right[1:]

            # collect nodes and edges for display
            for n in full_nodes:
                nodes_to_show.add(n)

            path_edges = list(zip(full_nodes, full_nodes[1:]))

            for a, b in path_edges:
                link_color = "red" if (a == u and b == v) else color
                filtered_links.append({"source": a, "target": b, "color": link_color})

            colored_paths_info.append((path_edges, (u, v), color))

        # build filtered graph
        filtered_data = {
            "nodes": [node for node in current_data["nodes"] if node["id"] in nodes_to_show],
            "links": []
        }

        # apply colors to the links we keep (O(E) not O(P*E))
        link_index = {(l["source"], l["target"]): l for l in current_data["links"]}
        for f in filtered_links:
            if (f["source"], f["target"]) in link_index:
                new_link = link_index[(f["source"], f["target"])].copy()
                new_link["color"] = f["color"]
                filtered_data["links"].append(new_link)

        # info box content
        path_info_children = [html.H4("Affected Paths")]
        for i, (path_edges, attacked_uv, color) in enumerate(colored_paths_info):
            if not path_edges:
                continue
            full_path_nodes = [path_edges[0][0]] + [vv for _, vv in path_edges]
            color_dot = html.Span("⬤", style={"color": color, "marginRight": "6px"})
            path_text = " → ".join(full_path_nodes)
            attacked_text = f"{attacked_uv[0]} → {attacked_uv[1]}"
            path_info_children.append(
                html.Div([
                    html.Strong([color_dot, f" Path {i+1} (Attacked: {attacked_text})"]),
                    html.P(path_text, style={"fontSize": "13px", "marginLeft": "12px"})
                ])
            )
        info_box_content = html.Div(path_info_children)

        return (
            "show-attacked",
            info_box_content,
            json.dumps(filtered_data),
            dash.no_update, dash.no_update,
            dash.no_update, dash.no_update,
            dash.no_update, dash.no_update, dash.no_update
        )


app.clientside_callback(
    """
    function(action, updatedGraphData) {
        const graphData = JSON.parse(updatedGraphData || '{}');
        const nodeInfo = %s;
        const edgeInfo = %s;
        if (!window.fgInstance) {
            const interval = setInterval(() => {
                if (!window.ForceGraph3D || !window.THREE) return;
                clearInterval(interval);
                const Graph = ForceGraph3D();
                const graphContainer = document.getElementById("3d-graph");
                const infoBox = document.getElementById("info-box");

                const fg = Graph(graphContainer)
                fg.d3Force('charge').strength(-350);
                fg.d3Force('center', null);
                
                fg.graphData(graphData)
                    .nodeLabel('name')
                    .nodeRelSize(8)
                    .nodeAutoColorBy('id')
                    .linkColor(link => {
                     return link.color || (link.capacity > 40 ? '#000' : '#aaa');
                })
                    .linkWidth(link => Math.max(0.5, Math.min(link.capacity / 10, 3)))
                    .linkOpacity(link => {
                     return link.color === "red" ? 1 :
                            link.color === "orange" ? 0.8 :
                            Math.max(0.1, link.capacity / 50);
                 })
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
                        fg.graphData().nodes.forEach(n => {
                            if (!n.isRoot && !n.isAim) {
                                delete n.color;
                            }
                        });
                        
                        node.color = 'red';
                        
                        const info = nodeInfo[node.id];
                        const html = `
                            <h4>Selected Node: ${node.id}</h4>
                            <strong>Outgoing Edges (${info.outgoing.length}):</strong>
                            <ul>${info.outgoing.map(e => `<li>${e[0]} → ${e[1]} (Capacity: ${e[2]})</li>`).join('')}</ul>
                            <strong>Incoming Edges (${info.incoming.length}):</strong>
                            <ul>${info.incoming.map(e => `<li>${e[0]} → ${e[1]} (Capacity: ${e[2]})</li>`).join('')}</ul>
                        `;
                        infoBox.innerHTML = html;
                        
                        fg.refresh();
                    })
                    .onLinkClick(link => {
                        fg.graphData().links.forEach(l => delete l.color);
                        link.color = 'orange';
                        const key = link.source.id + "->" + link.target.id;
                        const edge = edgeInfo[key];
                        const html = `
                            <h4>Selected Edge</h4>
                            <p><strong>${edge.source} → ${edge.target}</strong></p>
                            <p>Capacity: ${edge.capacity}</p>
                        `;
                        infoBox.innerHTML = html;
                        fg.refresh();
                    })
                    .onNodeDragEnd(node => {
                        node.fx = node.x;
                        node.fy = node.y;
                        node.fz = node.z;
                    });

                window.fgInstance = fg;
                
                graphContainer.addEventListener("dblclick", function(event) {
                    fg.cameraPosition({ x: 0, y: 0, z: 500 }, { x: 0, y: 0, z: 0 }, 1000);
                    fg.graphData().nodes.forEach(n => {
                        if (!n.isRoot && !n.isAim) {
                            delete n.color;
                        }
                    });
                    fg.graphData().links.forEach(l => delete l.color);
                    fg.nodeAutoColorBy('id');
                    infoBox.innerHTML = '';
                    fg.refresh();
                });
            }, 100);
            return '';
        }

        if (typeof action === 'string' && action.startsWith("jump-")) {
            const nodeId = action.split("-")[1];
            const node = window.fgInstance.graphData().nodes.find(n => n.id === nodeId);
            if (node) {
                window.fgInstance.cameraPosition({ x: node.x, y: node.y, z: node.z + 150 }, node, 1000);
            }
        } 
        
        else if (action === "back-to-main") {
            const newGraph = JSON.parse(updatedGraphData || '{}');
            window.fgInstance.graphData(newGraph);
            window.fgInstance.refresh();
            return '';
            
        } 
        
        else if (action === "refresh" || action === "show-attacked") {
            const newGraph = JSON.parse(updatedGraphData || '{}');
            window.fgInstance.graphData(newGraph);
            window.fgInstance.refresh();
            return '';


        } else if (action === "reset") {
            const newGraph = JSON.parse(updatedGraphData || '{}');
            window.fgInstance.graphData(newGraph);
            window.fgInstance.cameraPosition({ x: 0, y: 0, z: 500 }, { x: 0, y: 0, z: 0 }, 1000);
            window.fgInstance.graphData().nodes.forEach(n => {
                delete n.color;
                delete n.fx;
                delete n.fy;
                delete n.fz;
            });
            window.fgInstance.graphData().links.forEach(l => delete l.color);
            window.fgInstance.nodeAutoColorBy('id');
            document.getElementById("info-box").innerHTML = '';
            window.fgInstance.refresh();
            window.fgInstance.d3ReheatSimulation();
        }

        return "Action complete.";
    }
    """ % (node_info_json, edge_info_json),
    Output("info-box", "children"),
    Input("camera-action", "children"),
    State("graph-data-store", "data")
)

if __name__ == '__main__':
    app.run(debug=True)