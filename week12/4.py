import dash
from dash import html, dcc
from dash_extensions.enrich import DashProxy, TriggerTransform, MultiplexerTransform
from dash.dependencies import Output, Input, State
import networkx as nx
import random
import json
import copy

# ---------- GRAPH GENERATION ----------

# Create graph structure
backbone_edges = []
for i in range(1, 100):
    current = f"N{i}"
    possible_targets = range(i + 2, min(i + 20, 101))
    if possible_targets:
        target = f"N{random.choice(possible_targets)}"
        capacity = random.randint(5, 15)
        backbone_edges.append((current, target, capacity))

extra_edges = []
for _ in range(200):
    u = f"N{random.randint(1, 99)}"
    v = f"N{random.randint(int(u[1:]) + 1, 100)}"
    if u != v and u != "N100":
        extra_edges.append((u, v, random.randint(5, 30)))

edges = backbone_edges + extra_edges

G = nx.DiGraph()
G.add_nodes_from([f"N{i}" for i in range(1, 101)])
for u, v, cap in edges:
    if u != "N100":
        G.add_edge(u, v, capacity=cap)

if not nx.has_path(G, "N1", "N100"):
    fallback_path = [f"N{i}" for i in range(1, 101, 10)]
    fallback_path[-1] = "N100"
    for i in range(len(fallback_path) - 1):
        u = fallback_path[i]
        v = fallback_path[i + 1]
        if not G.has_edge(u, v):
            fallback_cap = random.randint(10, 20)
            G.add_edge(u, v, capacity=fallback_cap)
            edges.append((u, v, fallback_cap))

unreachable_nodes = [n for n in G.nodes if not nx.has_path(G, n, "N100") and n != "N100"]
for node in unreachable_nodes:
    bridge_candidates = [n for n in G.nodes if nx.has_path(G, n, "N100") and n != node]
    if bridge_candidates:
        bridge = random.choice(bridge_candidates)
        if not G.has_edge(node, bridge):
            cap = random.randint(10, 20)
            G.add_edge(node, bridge, capacity=cap)
            edges.append((node, bridge, cap))

G.remove_edges_from([(u, v) for u, v in G.in_edges("N1")])
assert G.in_degree("N1") == 0

for node in G.nodes:
    if node != "N1" and G.in_degree(node) == 0:
        source_candidates = [n for n in G.nodes if n != node and n != "N100" and not G.has_edge(n, node)]
        if source_candidates:
            source = random.choice(source_candidates)
            cap = random.randint(10, 20)
            G.add_edge(source, node, capacity=cap)
            edges.append((source, node, cap))

source_candidates = [n for n in G.nodes if set(nx.descendants(G, n)) == set(G.nodes) - {n}]
root_node = source_candidates[0] if source_candidates else "N1"

max_capacity = max([cap for _, _, cap in edges])

def create_graph_data(G):
    return {
        "nodes": [
            {"id": node, "name": node, "isRoot": node == root_node, "isAim": node == "N100"}
            for node in G.nodes()
        ],
        "links": [
            {
                "source": u,
                "target": v,
                "capacity": G[u][v]['capacity'],
                "color": "black",
                "normCapacity": max(G[u][v]['capacity'] / max_capacity, 0.1)
            }
            for u, v in G.edges()
        ]
    }

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

app.layout = html.Div([
    html.Div([
        html.Button("Reset Graph", id="reset-btn", n_clicks=0, style=button_style),
        html.Button("Back to Main Graph", id="back-main-btn", n_clicks=0, style=button_style),
        html.Button("Jump to Source (N1)", id="jump-source-btn", n_clicks=0, style=button_style),
        html.Button("Jump to Aim (N100)", id="jump-aim-btn", n_clicks=0, style=button_style),
        html.Button("Run Budgeted Attack", id="attack-btn", n_clicks=0, style=button_style),
        html.Button("Run Multi-Step Attack", id="multi-step-attack-btn", n_clicks=0, style=button_style),
        html.Button("Show Attacked Edges", id="show-attack-btn", n_clicks=0, style=button_style),
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
    Input("reset-btn", "n_clicks"),
    Input("attack-btn", "n_clicks"),
    Input("show-attack-btn", "n_clicks"),
    Input("back-main-btn", "n_clicks"),
    Input("multi-step-attack-btn", "n_clicks"),
    State("graph-data-store", "data"),
    State("attacked-edges-store", "data"),
    State("original-graph-store", "data"),
    State("pre-attack-graph-store", "data"),
    prevent_initial_call=True
)
def unified_callback(jump_source, jump_aim, reset, attack, show_attack, back_main, multi_step_attack_click,
                     current_graph_data, attacked_edges_data, original_graph_data, pre_attack_graph_data):

    triggered = dash.callback_context.triggered
    if not triggered:
        return dash.no_update, *([dash.no_update] * 9)

    trigger = triggered[0]["prop_id"].split(".")[0]

    if trigger == "jump-source-btn":
        return "jump-N1", *([dash.no_update] * 9)
    elif trigger == "jump-aim-btn":
        return "jump-N100", *([dash.no_update] * 9)
    elif trigger == "reset-btn":
        global G
        G = nx.DiGraph()
        G.add_nodes_from([f"N{i}" for i in range(1, 101)])
        for u, v, cap in edges:
            if u != "N100":
                G.add_edge(u, v, capacity=cap)
        return ("reset", dash.no_update, original_graph_data,
                dash.no_update, {"display": "none"},
                dash.no_update, {"display": "none"},
                [], original_graph_data, original_graph_data)

    elif trigger == "attack-btn":
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
            affected_edges_content, {"display": "block", **affected_edges_style},  # Apply affected edges style
            capacity_content, {"display": "block", **capacity_box_style},  # Apply capacity box style
            affected_edges_list,
            json.dumps(original_graph_data),
            pre_attack_data
        )

    elif trigger == "multi-step-attack-btn":
        pre_attack_data = current_graph_data
        flow_before, flow_after, affected_edges = multi_step_attack(G, "N1", "N100", steps=3, edges_per_step=10)
        
        # Create updated graph data
        updated_data = create_graph_data(G)
        
        # Mark attacked edges as red
        attacked_edge_pairs = [(u, v) for u, v, _ in affected_edges]
        for link in updated_data["links"]:
            if (link["source"], link["target"]) in attacked_edge_pairs:
                link["color"] = "red"  # <-- Set attacked edges to red
        
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
        
        affected_edges_list = [{"source": u, "target": v, "reduction": cap} for u, v, cap in affected_edges]
        
        return (
            "refresh", attack_info, json.dumps(updated_data),
            affected_edges_content, {"display": "block"},
            dash.no_update, {"display": "none"},
            affected_edges_list,
            json.dumps(original_graph_data),
            pre_attack_data
        )
    elif trigger == "show-attack-btn":
        if not attacked_edges_data:
            return dash.no_update, *([dash.no_update] * 9)
        current_data = json.loads(current_graph_data)
        attacked_edges = [(e["source"], e["target"]) for e in attacked_edges_data]
        for link in current_data["links"]:
            if (link["source"], link["target"]) in attacked_edges:
                link["color"] = "red"
            else:
                link["color"] = "black"

        nodes_to_show = set()
        links_to_show = []
        for u, v in attacked_edges:
            nodes_to_show.add(u)
            nodes_to_show.add(v)
            path_from_source, path_to_aim = find_paths_to_source_and_aim(G, u, v)
            for i in range(len(path_from_source) - 1):
                nodes_to_show.add(path_from_source[i])
                nodes_to_show.add(path_from_source[i + 1])
                links_to_show.append((path_from_source[i], path_from_source[i + 1]))
            for i in range(len(path_to_aim) - 1):
                nodes_to_show.add(path_to_aim[i])
                nodes_to_show.add(path_to_aim[i + 1])
                links_to_show.append((path_to_aim[i], path_to_aim[i + 1]))
        filtered_data = {
            "nodes": [
                node
                for node in current_data["nodes"]
                if node["id"] in nodes_to_show
            ],
            "links": []
        }
        all_links_to_show = attacked_edges + list(set(links_to_show))
        for link in current_data["links"]:
            if (link["source"], link["target"]) in all_links_to_show:
                new_link = link.copy()
                if (link["source"], link["target"]) in attacked_edges:
                    new_link["color"] = "red"
                else:
                    new_link["color"] = "blue"
                filtered_data["links"].append(new_link)
        return ("show-attacked", dash.no_update, json.dumps(filtered_data),
                dash.no_update, {"display": "block"},
                dash.no_update, {"display": "none"},
                dash.no_update,
                dash.no_update, dash.no_update)

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
