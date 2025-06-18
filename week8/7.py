import dash
from dash import html, dcc, callback_context as ctx
from dash_extensions.enrich import DashProxy, TriggerTransform, MultiplexerTransform
from dash.dependencies import Output, Input
import networkx as nx
import random
import json

# ----------- Build NetworkX Graph -----------
nodes = [f"N{i}" for i in range(1, 101)]

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
G.add_nodes_from(nodes)
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
        source_candidates = [n for n in G.nodes if n != node and n != "N100"]
        source = random.choice(source_candidates)
        cap = random.randint(10, 20)
        G.add_edge(source, node, capacity=cap)
        edges.append((source, node, cap))


source_candidates = [n for n in G.nodes if set(nx.descendants(G, n)) == set(G.nodes) - {n}]
root_node = source_candidates[0] if source_candidates else "N1"

max_capacity = max([cap for _, _, cap in edges])

graph_data = {
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

node_info = {
    node: {
        "incoming": [(u, v, G[u][v]['capacity']) for u, v in G.in_edges(node)],
        "outgoing": [(u, v, G[u][v]['capacity']) for u, v in G.out_edges(node)],
    }
    for node in G.nodes
}

edge_info = {
    f"{u}->{v}": {"source": u, "target": v, "capacity": G[u][v]['capacity']}
    for u, v in G.edges
}

graph_data_json = json.dumps(graph_data)
node_info_json = json.dumps(node_info)
edge_info_json = json.dumps(edge_info)

# ----------- Dash App Setup -----------
external_scripts = [
    "https://unpkg.com/three@0.150.1/build/three.min.js",
    "https://unpkg.com/3d-force-graph"
]

app = DashProxy(__name__, external_scripts=external_scripts,
                transforms=[TriggerTransform(), MultiplexerTransform()])
server = app.server

app.layout = html.Div([
    html.Div([
        html.Label("Source Node"),
        dcc.Dropdown(id="source-node-dropdown",
                     options=[{"label": n, "value": n} for n in G.nodes], value="N1"),
        html.Label("Target Node"),
        dcc.Dropdown(id="target-node-dropdown",
                     options=[{"label": n, "value": n} for n in G.nodes], value="N100"),
        html.Button("Run Shortest Path", id="shortest-path-btn", n_clicks=0)
    ], style={"position": "absolute", "top": "20px", "left": "180px", "zIndex": 12,
              "backgroundColor": "white", "padding": "10px", "borderRadius": "8px",
              "boxShadow": "2px 2px 6px rgba(0,0,0,0.3)"}),

    html.Button("Reset Node", id="reset-btn", n_clicks=0,
                style={"position": "absolute", "top": "20px", "left": "20px", "zIndex": 11}),
    html.Button("Jump to Source (N1)", id="jump-source-btn", n_clicks=0,
                style={"position": "absolute", "top": "60px", "left": "20px", "zIndex": 11}),
    html.Button("Jump to Aim (N100)", id="jump-aim-btn", n_clicks=0,
                style={"position": "absolute", "top": "100px", "left": "20px", "zIndex": 11}),

    html.Div(id="3d-graph", style={"height": "95vh", "width": "100%"}),
    html.Div(id="info-box", style={
        "position": "absolute", "top": "140px", "right": "20px",
        "width": "280px", "padding": "15px",
        "backgroundColor": "#E6E6FA", "border": "1px solid #999",
        "borderRadius": "10px", "boxShadow": "2px 2px 6px rgba(75, 0, 130)",
        "overflowY": "auto", "maxHeight": "80vh", "zIndex": 10
    }),
    html.Div(id="camera-action", style={"display": "none"})
])

@app.callback(
    Output("camera-action", "children"),
    [Input("jump-source-btn", "n_clicks"),
     Input("jump-aim-btn", "n_clicks"),
     Input("reset-btn", "n_clicks")]
)
def determine_action(source_clicks, aim_clicks, reset_clicks):
    trigger = ctx.triggered_id
    if trigger == "jump-source-btn":
        return "jump-N1"
    elif trigger == "jump-aim-btn":
        return "jump-N100"
    elif trigger == "reset-btn":
        return "reset"
    return ""

@app.callback(
    Output("camera-action", "children"),
    Output("info-box", "children"),
    Input("shortest-path-btn", "n_clicks"),
    Input("source-node-dropdown", "value"),
    Input("target-node-dropdown", "value"),
    prevent_initial_call=True
)
def compute_shortest_path(_, source, target):
    try:
        path = nx.shortest_path(G, source=source, target=target)
        total_capacity = sum(G[path[i]][path[i+1]]['capacity'] for i in range(len(path)-1))
        path_edges = [(path[i], path[i+1]) for i in range(len(path)-1)]
        js_command = {
            "action": "highlight-path",
            "nodes": path,
            "edges": [f"{u}->{v}" for u, v in path_edges]
        }
        return json.dumps(js_command), f"""
            <h4>Shortest Path from {source} to {target}</h4>
            <p>Nodes in path: {len(path)}</p>
            <p>Total capacity: {total_capacity}</p>"""
    except nx.NetworkXNoPath:
        return "", f"<h4>No path found from {source} to {target}</h4>"

app.clientside_callback(
    f"""
    function(action) {{
        const graphData = {graph_data_json};
        const nodeInfo = {node_info_json};
        const edgeInfo = {edge_info_json};

        if (typeof action === 'string') {{
            try {{ action = JSON.parse(action); }} catch (e) {{}}
        }}

        if (!window.fgInstance) {{
            const interval = setInterval(() => {{
                if (!window.ForceGraph3D || !window.THREE) return;
                clearInterval(interval);
                const Graph = ForceGraph3D();
                const graphContainer = document.getElementById("3d-graph");
                const infoBox = document.getElementById("info-box");

                const fg = Graph(graphContainer)
                    .graphData(graphData)
                    .nodeLabel('name')
                    .nodeRelSize(8)
                    .nodeAutoColorBy('id')
                    .linkColor(link => link.color || 'black')
                    .linkWidth(link => Math.min(link.capacity / 2, 1))
                    .backgroundColor('gray')
                    .nodeThreeObject(node => {{
                        const THREE = window.THREE;
                        if (node.isRoot) {{
                            const sprite = new THREE.Sprite(new THREE.SpriteMaterial({{ color: 'green' }}));
                            sprite.scale.set(40, 40, 1);
                            return sprite;
                        }} else if (node.isAim) {{
                            const sprite = new THREE.Sprite(new THREE.SpriteMaterial({{ color: 'deeppink' }}));
                            sprite.scale.set(40, 40, 1);
                            return sprite;
                        }}
                        return null;
                    }})
                    .onNodeClick(node => {{
                        fg.graphData().nodes.forEach(n => delete n.color);
                        node.color = 'red';
                        const info = nodeInfo[node.id];
                        const html = `
                            <h4>Selected Node: ${{node.id}}</h4>
                            <strong>Outgoing Edges (${{info.outgoing.length}}):</strong>
                            <ul>${{info.outgoing.map(e => `<li>${{e[0]}} → ${{e[1]}} (Capacity: ${{e[2]}})</li>`).join('')}}</ul>
                            <strong>Incoming Edges (${{info.incoming.length}}):</strong>
                            <ul>${{info.incoming.map(e => `<li>${{e[0]}} → ${{e[1]}} (Capacity: ${{e[2]}})</li>`).join('')}}</ul>
                        `;
                        infoBox.innerHTML = html;
                        fg.refresh();
                    }})
                    .onLinkClick(link => {{
                        fg.graphData().links.forEach(l => delete l.color);
                        link.color = 'orange';
                        const key = link.source.id + "->" + link.target.id;
                        const edge = edgeInfo[key];
                        const html = `
                            <h4>Selected Edge</h4>
                            <p><strong>${{edge.source}} → ${{edge.target}}</strong></p>
                            <p>Capacity: ${{edge.capacity}}</p>
                        `;
                        infoBox.innerHTML = html;
                        fg.refresh();
                    }})
                    .onNodeDragEnd(node => {{
                        node.fx = node.x;
                        node.fy = node.y;
                        node.fz = node.z;
                    }});

                window.fgInstance = fg;

                graphContainer.addEventListener("dblclick", function(event) {{
                    fg.cameraPosition({{ x: 0, y: 0, z: 500 }}, {{ x: 0, y: 0, z: 0 }}, 1000);
                    fg.graphData().nodes.forEach(n => delete n.color);
                    fg.graphData().links.forEach(l => delete l.color);
                    fg.nodeAutoColorBy('id');
                    infoBox.innerHTML = '';
                    fg.refresh();
                }});
            }}, 100);
            return '';
        }}

        if (action && action.action === "highlight-path") {{
            const nodesToHighlight = new Set(action.nodes);
            const edgesToHighlight = new Set(action.edges);
            window.fgInstance.graphData().nodes.forEach(n => n.color = nodesToHighlight.has(n.id) ? 'yellow' : undefined);
            window.fgInstance.graphData().links.forEach(l => {{
                const key = `${{l.source.id}}->${{l.target.id}}`;
                l.color = edgesToHighlight.has(key) ? 'red' : 'black';
            }});
            window.fgInstance.refresh();
        }}
        return '';
    }}
    """,
    Output("info-box", "children"),
    Input("camera-action", "children")
)

if __name__ == '__main__':
    app.run(debug=True)
