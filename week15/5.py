
import dash
from dash import html, dcc
from dash_extensions.enrich import DashProxy, TriggerTransform, MultiplexerTransform
from dash.dependencies import Output, Input, State
import networkx as nx
import re
import json
import copy

# ---------- GRAPH GENERATION ----------

def parse_adjacency_list(file_path, max_nodes=1036):
    """
    Reads an adjacency list from a file and returns a directed NetworkX graph (DiGraph).
    Only includes nodes with integer IDs in the range [0, max_nodes-1].

    File format example:
        0: (1, 10.0, 5.0, 1.0) (2, 8.0, 3.0, 0.0)
        1: (3, 7.0, 2.0, 1.0)
    Where each edge is represented as:
        (target_node, capacity, attack_cost, can_attack_flag)
    """

    G = nx.DiGraph()  # Create an empty directed graph

    # Regex pattern to extract the source node ID (e.g., "0:" or "12:")
    src_pat = re.compile(r'^(\d+):')

    # Regex pattern to extract edges and their attributes from each line
    # Matches: (target_id, capacity, attack_cost, attack_flag)
    edge_pat = re.compile(r'\((\d+),\s*([\d.]+),\s*([\d.]+),\s*([\d.]+)\)')

    # Open the adjacency list file
    with open(file_path, 'r') as f:
        for raw in f:
            line = raw.strip()  # Remove whitespace from start and end

            if not line:  # Skip empty lines
                continue

            # Match the source node at the start of the line
            m = src_pat.match(line)
            if not m:
                continue  # Skip lines without a valid source node

            src_id = int(m.group(1))
            if src_id >= max_nodes:
                continue  # Skip nodes outside the allowed range

            src = str(src_id)  # Convert to string for graph consistency
            G.add_node(src)    # Add the source node to the graph

            # Find all edges from this source node
            for tgt_s, cap_s, cost_s, att_s in edge_pat.findall(line):
                tgt_id = int(tgt_s)
                if tgt_id >= max_nodes:
                    continue  # Skip edges pointing to out-of-range nodes

                tgt = str(tgt_id)
                G.add_edge(
                    src, tgt,
                    capacity=float(cap_s),          # Capacity of the edge
                    attack_cost=float(cost_s),      # Cost to attack this edge
                    can_attack=(float(att_s) == 1.0) # Boolean flag for attack permission
                )

    return G


# Example usage: load graph from file
file_path = "/Users/miraki/Desktop/sem3/flowua/code/NEW GRAPH/graph.text"
G = parse_adjacency_list(file_path, max_nodes=1036)

# Keep an independent copy of the original graph for reset/analysis
ORIGINAL_GRAPH = copy.deepcopy(G)

# Define source and target nodes for analysis
source_node = "0"
target_node = "1035"


def create_graph_data(G):
    """
    Converts a NetworkX graph into a dictionary format suitable for visualization.
    Each node is marked as 'isRoot' (source) or 'isAim' (target).
    Capacities are normalized for rendering link thickness.
    """

    # Extract all capacities from edges
    caps = [data['capacity'] for _, _, data in G.edges(data=True)]
    max_capacity = max(caps) if caps else 1.0  # Avoid division by zero

    return {
        "nodes": [
            {
                "id": node,
                "name": node,
                "isRoot": node == source_node,
                "isAim": node == target_node
            }
            for node in G.nodes()
        ],
        "links": [
            {
                "source": u,
                "target": v,
                "capacity": G[u][v]['capacity'],
                "color": "black",  # Default color for edges
                "normCapacity": max(G[u][v]['capacity'] / max_capacity, 0.1)  # Min thickness 0.1
            }
            for u, v in G.edges()
        ]
    }

def budgeted_attack(G, source="source-node", sink="target-node", budget=300):
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
            html.Span("Source Node (source-node)", style={"fontSize": "14px"})
        ], style={"marginBottom": "6px"}),
        html.Div([
            html.Span("⬤", style={"color": "deeppink", "marginRight": "6px"}),
            html.Span("Target Node (target-node)", style={"fontSize": "14px"})
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
        html.Button("Jump to Source (source-node)", id="jump-source-btn", n_clicks=0, style=button_style),
        html.Button("Jump to Aim (target-node)", id="jump-aim-btn", n_clicks=0, style=button_style),
        
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
        path_from_source = nx.shortest_path(G, "source-node", u)
    except nx.NetworkXNoPath:
        path_from_source = []
    try:
        path_to_aim = nx.shortest_path(G, v, "target-node")
    except nx.NetworkXNoPath:
        path_to_aim = []
    return path_from_source, path_to_aim

# Clientside callback for dropdown toggle
app.clientside_callback(
    """
    function(n_clicks) {
        var options = document.getElementById("attack-options");
        if (n_clicks % 2 === 1) {
            options.style.display = "block";
        } else {
            options.style.display = "none";
        }
        return window.dash_clientside.no_update;
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
        return "jump-source-node", *([dash.no_update] * 9)
    elif trigger == "jump-aim-btn":
        return "jump-target-node", *([dash.no_update] * 9)
        
    elif trigger == "budgeted-attack-btn":
        pre_attack_data = current_graph_data
        total_capacity_before = calculate_total_capacity(G)
        flow_before, flow_after, affected_edges = budgeted_attack(G, "source-node", "target-node", budget=300)
        
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
        flow_before, flow_after, affected_edges = multi_step_attack(G, "source-node", "target-node", steps=3, edges_per_step=10)
        
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
        path_colors = ["green", "blue", "orange", "purple", "cyan", "brown", "magenta"]

        # Find all possible paths from source-node to target-node
        try:
            all_paths = list(nx.all_simple_paths(G, source="source-node", target="target-node", cutoff=20))
        except nx.NetworkXNoPath:
            return dash.no_update, *([dash.no_update] * 9)

        nodes_to_show = set()
        filtered_links = []
        colored_paths_info = []
        
        # For each attacked edge, find paths that contain it
        for idx, edge in enumerate(attacked_edges_data):
            u, v = edge["source"], edge["target"]
            color = path_colors[idx % len(path_colors)]
            
            # Find all paths containing this edge
            containing_paths = [path for path in all_paths 
                              if any((path[i], path[i+1]) == (u, v) 
                              for i in range(len(path)-1))]
            
            if not containing_paths:
                continue
                
            # Take the first path that contains this edge
            path = containing_paths[0]
            path_edges = list(zip(path, path[1:]))
            
            # Add nodes and edges to display
            for node in path:
                nodes_to_show.add(node)
                
            for a, b in path_edges:
                link_color = "red" if (a == u and b == v) else color
                filtered_links.append({"source": a, "target": b, "color": link_color})
            
            colored_paths_info.append((path_edges, (u, v), color))

        filtered_data = {
            "nodes": [node for node in current_data["nodes"] if node["id"] in nodes_to_show],
            "links": []
        }

        # Apply the colors to the links
        for link in current_data["links"]:
            for f_link in filtered_links:
                if (link["source"], link["target"]) == (f_link["source"], f_link["target"]):
                    new_link = link.copy()
                    new_link["color"] = f_link["color"]
                    filtered_data["links"].append(new_link)
                    break

        # Create info box showing affected paths
        path_info_children = [html.H4("Affected Paths")]
        for i, (path_edges, attacked_uv, color) in enumerate(colored_paths_info):
            full_path_nodes = [path_edges[0][0]] + [v for _, v in path_edges]
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