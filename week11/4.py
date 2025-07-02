#edges are visible and add network box
#budget attack
import dash
from dash import html, dcc
from dash_extensions.enrich import DashProxy, TriggerTransform, MultiplexerTransform
from dash.dependencies import Output, Input, State
import networkx as nx
import random
import json
import copy

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
for _ in range(100):
    u = f"N{random.randint(1, 99)}"
    v = f"N{random.randint(int(u[1:]) + 1, 100)}"
    if u != v and u != "N100":
        extra_edges.append((u, v, random.randint(5, 50)))

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

def budgeted_attack(G, source="N1", sink="N100", budget=50):
    G_copy = copy.deepcopy(G)
    flow_value_before, flow_dict = nx.maximum_flow(G_copy, source, sink,
                                                 flow_func=nx.algorithms.flow.edmonds_karp)

    # Select edges with flow, sorted by capacity
    flow_edges = [(u, v, G_copy[u][v]['capacity']) for u in flow_dict for v in flow_dict[u] if flow_dict[u][v] > 0]
    flow_edges.sort(key=lambda x: x[2], reverse=True)

    # Reduce capacities within budget
    total_reduced = 0
    affected_edges = []
    for u, v, cap in flow_edges:
        if total_reduced >= budget:
            break
        reduction = min(cap - 1, budget - total_reduced)
        G[u][v]['capacity'] = max(1, cap - reduction)
        total_reduced += reduction
        affected_edges.append((u, v, reduction))

    flow_value_after, _ = nx.maximum_flow(G, source, sink, flow_func=nx.algorithms.flow.edmonds_karp)
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

app = DashProxy(__name__, external_scripts=external_scripts,
                transforms=[TriggerTransform(), MultiplexerTransform()])
server = app.server
# [Previous imports and graph creation code remains the same until the app.layout section]

app.layout = html.Div([
    html.Button("Reset Node", id="reset-btn", n_clicks=0,
                style={"position": "absolute", "top": "20px", "left": "20px", "zIndex": 11}),
    html.Button("Jump to Source (N1)", id="jump-source-btn", n_clicks=0,
                style={"position": "absolute", "top": "60px", "left": "20px", "zIndex": 11}),
    html.Button("Jump to Aim (N100)", id="jump-aim-btn", n_clicks=0,
                style={"position": "absolute", "top": "100px", "left": "20px", "zIndex": 11}),
    html.Button("Run Budgeted Attack", id="attack-btn", n_clicks=0,
                style={"position": "absolute", "top": "180px", "left": "20px", "zIndex": 11}),
    dcc.Store(id="graph-data-store", data=graph_data_json),
    html.Div(id="3d-graph", style={"position": "absolute", "top": "0px", "left": "0px", "width": "100vw", "height": "100vh", "zIndex": "0", "overflow": "hidden"}),
    html.Div(id="info-box", style={
        "position": "absolute", 
        "top": "140px", 
        "right": "20px", 
        "width": "300px",
        "padding": "15px", 
        "backgroundColor": "#F8F9FA",
        "border": "1px solid #DEE2E6",
        "borderRadius": "8px",
        "boxShadow": "0 2px 8px rgba(0,0,0,0.1)",
        "overflowY": "auto",
        "maxHeight": "80vh",
        "zIndex": 10,
        "fontFamily": "Arial, sans-serif"
    }),
    html.Div(id="affected-edges-box", style={
        "position": "absolute",
        "top": "140px",
        "left": "20px",
        "width": "250px",
        "padding": "15px",
        "backgroundColor": "#FFF8F8",
        "border": "1px solid #FFD6D6",
        "borderRadius": "8px",
        "boxShadow": "0 2px 8px rgba(0,0,0,0.1)",
        "overflowY": "auto",
        "maxHeight": "80vh",
        "zIndex": 10,
        "fontFamily": "Arial, sans-serif",
        "display": "none"  # Initially hidden
    }),
    html.Div(id="capacity-box", style={
        "position": "absolute",
        "top": "500px",
        "right": "20px",
        "width": "300px",
        "padding": "15px",
        "backgroundColor": "#F0F8FF",
        "border": "1px solid #ADD8E6",
        "borderRadius": "8px",
        "boxShadow": "0 2px 8px rgba(0,0,0,0.1)",
        "overflowY": "auto",
        "maxHeight": "80vh",
        "zIndex": 10,
        "fontFamily": "Arial, sans-serif",
        "display": "none"
    }),
    html.Div(id="camera-action", style={"display": "none"})
])


def calculate_total_capacity(G):
    return sum(data['capacity'] for u, v, data in G.edges(data=True))

@app.callback(
    Output("camera-action", "children"),
    Output("info-box", "children"),
    Output("graph-data-store", "data"),
    Output("affected-edges-box", "children"),
    Output("affected-edges-box", "style"),
    Output("capacity-box", "children"),
    Output("capacity-box", "style"),
    Input("jump-source-btn", "n_clicks"),
    Input("jump-aim-btn", "n_clicks"),
    Input("reset-btn", "n_clicks"),
    Input("attack-btn", "n_clicks"),
    State("graph-data-store", "data"),
    prevent_initial_call=True
)
def unified_callback(jump_source, jump_aim, reset, attack, current_graph_data):
    triggered = dash.callback_context.triggered

    if not triggered:
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update

    trigger = triggered[0]["prop_id"].split(".")[0]

    if trigger == "jump-source-btn":
        return "jump-N1", dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update
    elif trigger == "jump-aim-btn":
        return "jump-N100", dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update
    elif trigger == "reset-btn": 
        updated_data = create_graph_data(G)
        return ("reset", dash.no_update, json.dumps(updated_data), dash.no_update, {"display": "none"}, dash.no_update, {"display": "none"})
    elif trigger == "attack-btn":
        # Calculate total capacity before attack
        total_capacity_before = calculate_total_capacity(G)
        
        flow_before, flow_after, affected_edges = budgeted_attack(G, "N1", "N100", budget=50)
        updated_data = create_graph_data(G)

        # Calculate total capacity after attack
        total_capacity_after = calculate_total_capacity(G)
        
        for u, v, _ in affected_edges:
            for link in updated_data["links"]:
                if link["source"] == u and link["target"] == v:
                    link["color"] = "red"

        # Calculate severity level
        severity = (flow_before - flow_after) / flow_before
        if severity < 0.1:
            severity_level = "Low"
            severity_color = "#006400"  # Dark green
        elif severity < 0.3:
            severity_level = "Moderate"
            severity_color = "#FF8C00"  # Dark orange
        else:
            severity_level = "High"
            severity_color = "#8B0000"  # Dark red

        attack_info = html.Div([
            html.Div([
                html.H4("Cyber Attack Report", style={
                    "color": "#8B0000", 
                    "marginBottom": "10px",
                    "borderBottom": "2px solid #8B0000",
                    "paddingBottom": "5px",
                    "textAlign": "center"
                }),
                html.Div([
                    html.Span("Attack Severity:", style={"fontWeight": "bold", "width": "120px", "display": "inline-block"}),
                    html.Span(severity_level, style={
                        "color": "white",
                        "backgroundColor": severity_color,
                        "padding": "2px 8px",
                        "borderRadius": "10px",
                        "fontWeight": "bold",
                        "float": "right"
                    })
                ], style={"marginBottom": "15px"})
            ], style={"marginBottom": "20px"}),
            
            html.Div([
                html.H5("Network Flow Impact", style={
                    "marginBottom": "10px",
                    "color": "#333",
                    "borderBottom": "1px solid #DEE2E6",
                    "paddingBottom": "5px"
                }),
                html.Div([
                    html.Div([
                        html.Span("Before Attack:", style={"fontWeight": "bold", "width": "120px", "display": "inline-block"}),
                        html.Span(f"{flow_before}", style={"color": "#006400", "float": "right"})
                    ], style={"marginBottom": "8px"}),
                    html.Div([
                        html.Span("After Attack:", style={"fontWeight": "bold", "width": "120px", "display": "inline-block"}),
                        html.Span(f"{flow_after}", style={"color": "#8B0000", "float": "right"})
                    ], style={"marginBottom": "8px"}),
                    html.Div([
                        html.Span("Reduction:", style={"fontWeight": "bold", "width": "120px", "display": "inline-block"}),
                        html.Span(f"{((flow_before - flow_after) / flow_before * 100):.1f}%", 
                                style={"color": severity_color, "float": "right", "fontWeight": "bold"})
                    ]),
                ], style={"padding": "10px", "backgroundColor": "#F0F8FF", "borderRadius": "5px"}),
            ], style={"marginBottom": "20px"}),
            
            html.Div([
                html.H5("Damage Assessment", style={
                    "marginBottom": "10px",
                    "color": "#333",
                    "borderBottom": "1px solid #DEE2E6",
                    "paddingBottom": "5px"
                }),
                html.Div([
                    html.Div([
                        html.Span("Edges Affected:", style={"fontWeight": "bold", "width": "150px", "display": "inline-block"}),
                        html.Span(f"{len(affected_edges)}", style={"color": "#8B0000", "float": "right"})
                    ], style={"marginBottom": "8px"}),
                    html.Div([
                        html.Span("Capacity Reduced:", style={"fontWeight": "bold", "width": "150px", "display": "inline-block"}),
                        html.Span(f"{sum(cap for _, _, cap in affected_edges)}", 
                                style={"color": "#8B0000", "float": "right"})
                    ]),
                ], style={"padding": "10px", "backgroundColor": "#FFF0F5", "borderRadius": "5px"}),
            ])
        ])

        # Create the affected edges box content
        affected_edges_content = html.Div([
            html.H4("Affected Edges", style={
                "color": "#8B0000",
                "marginBottom": "15px",
                "borderBottom": "2px solid #FF6B6B",
                "paddingBottom": "5px",
                "textAlign": "center"
            }),
            html.Div([
                html.Div([
                    html.Span("Total Affected:", style={"fontWeight": "bold"}),
                    html.Span(f" {len(affected_edges)}", style={"float": "right", "color": "#8B0000"})
                ], style={"marginBottom": "10px"}),
                html.Div([
                    html.Span("Total Reduction:", style={"fontWeight": "bold"}),
                    html.Span(f" {sum(cap for _, _, cap in affected_edges)}", style={"float": "right", "color": "#8B0000"})
                ], style={"marginBottom": "15px"}),
                html.Div([
                    html.H5("Edge Details", style={
                        "marginBottom": "10px",
                        "color": "#333",
                        "borderBottom": "1px solid #FFD6D6",
                        "paddingBottom": "5px"
                    }),
                    html.Ul([
                        html.Li([
                            html.Span(f"{u} → {v}", style={"fontWeight": "bold"}),
                            html.Span(f" -{cap}", style={"float": "right", "color": "#8B0000"})
                        ], style={
                            "padding": "8px",
                            "marginBottom": "5px",
                            "backgroundColor": "#FFEEEE",
                            "borderLeft": "3px solid #FF6B6B",
                            "listStyleType": "none"
                        }) for u, v, cap in affected_edges
                    ], style={"paddingLeft": "0", "marginTop": "10px"})
                ])
            ])
        ])
        
        # Create the capacity box content
        capacity_content = html.Div([
            html.H4("Network Capacity", style={
                "color": "#1E90FF",
                "marginBottom": "15px",
                "borderBottom": "2px solid #1E90FF",
                "paddingBottom": "5px",
                "textAlign": "center"
            }),
            html.Div([
                html.Div([
                    html.Span("Total Capacity Before:", style={"fontWeight": "bold"}),
                    html.Span(f" {total_capacity_before}", style={"float": "right", "color": "#006400"})
                ], style={"marginBottom": "10px"}),
                html.Div([
                    html.Span("Total Capacity After:", style={"fontWeight": "bold"}),
                    html.Span(f" {total_capacity_after}", style={"float": "right", "color": "#8B0000"})
                ], style={"marginBottom": "10px"}),
                html.Div([
                    html.Span("Total Reduction:", style={"fontWeight": "bold"}),
                    html.Span(f" {total_capacity_before - total_capacity_after}", 
                             style={"float": "right", "color": "#8B0000"})
                ], style={"marginBottom": "10px"}),
                html.Div([
                    html.Span("Percentage Reduction:", style={"fontWeight": "bold"}),
                    html.Span(f" {((total_capacity_before - total_capacity_after) / total_capacity_before * 100):.1f}%", 
                             style={"float": "right", "color": "#8B0000"})
                ])
            ], style={
                "padding": "15px",
                "backgroundColor": "#E6F7FF",
                "borderRadius": "8px"
            })
        ])

        return ("refresh", attack_info, json.dumps(updated_data), 
                affected_edges_content, 
                {"display": "block", "position": "absolute", "top": "230px", "left": "20px", 
                 "width": "250px", "padding": "15px", "backgroundColor": "#F0F8FF", 
                 "border": "1px solid #FFD6D6", "borderRadius": "8px", "boxShadow": "0 2px 8px rgba(0,0,0,0.1)",
                 "overflowY": "auto", "maxHeight": "70vh", "zIndex": 10, "fontFamily": "Arial, sans-serif"},
                capacity_content,
                {"display": "block", "position": "absolute", "top": "calc(230px + 290px)", "left": "20px", 
                 "width": "300px", "padding": "15px", "backgroundColor": "#F0F8FF", 
                 "border": "1px solid #ADD8E6", "borderRadius": "8px", "boxShadow": "0 2px 8px rgba(0,0,0,0.1)",
                 "overflowY": "auto", "maxHeight": "80vh", "zIndex": 10, "fontFamily": "Arial, sans-serif"})

    return "", dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update


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
        } else if (action === "refresh") {
            window.fgInstance.graphData(graphData);
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