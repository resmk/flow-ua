#3D 
# edges are movabe 
#info about edges and nodes
#reset node btn 
#node 100 should be aim
#doubleclick on background => first state 
#change selected edges and nodes color 
#capacity 5-50
#1-100 nodes

"""
| Feature                         | Status | Description                                                                 |
|---------------------------------|--------|-----------------------------------------------------------------------------|
| 3D Graph                        | ✔      | Rendered with `3d-force-graph` and `three.js` in the browser.              |
| Movable Nodes (drag support)    | ✔      | Node positions can be adjusted and fixed manually by dragging.            |
| Node and Edge Info Display      | ✔      | Clicking nodes/edges shows their info in a side info box.                 |
| Target Node Highlight (N100)    | ✔      | Node N100 is styled with a pink sprite to indicate the goal/target.       |
| Reset Node Positions Button     | ✔      | A button clears fixed positions and reheats the graph layout.             |
| Double-Click to Reset View      | ✔      | Double-click resets camera view, clears colors, and info box content.     |
| Highlight Selected Nodes/Edges  | ✔      | Selected node turns red, selected edge turns orange.                      |
| Edge Capacities (5-50)          | ✔      | Capacities are assigned randomly between 5 and 50.                        |
| 100 Nodes (N1 to N100)          | ✔      | Graph consists of 100 nodes with backbone and additional random edges.    |


- Dash (for the interactive web app interface)
- Dash Extensions (for enhanced callback support via `DashProxy`)
- NetworkX (to generate and manage the graph structure)
- three.js + 3d-force-graph (for client-side 3D rendering and interaction)

"""

import dash
from dash import html
from dash_extensions.enrich import DashProxy, TriggerTransform, MultiplexerTransform
from dash.dependencies import Output, Input
import networkx as nx
import random
import json

# ----------- Build NetworkX Graph -----------
nodes = [f"N{i}" for i in range(1, 101)]
backbone_edges = [(f"N{i}", f"N{i+1}", random.randint(5, 15)) for i in range(1, 100)]

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

graph_data = {
    "nodes": [{"id": node, "name": node} for node in G.nodes()],
    "links": [{"source": u, "target": v, "capacity": G[u][v]['capacity']} for u, v in G.edges()]
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

app = DashProxy(
    __name__,
    external_scripts=external_scripts,
    transforms=[TriggerTransform(), MultiplexerTransform()]
)
server = app.server

app.layout = html.Div([
    html.Div([
        html.Button("Reset Node", id="reset-btn", n_clicks=0,
                    style={"position": "absolute", "top": "20px", "left": "20px", "zIndex": 11}),
        html.Div(id="3d-graph", style={"height": "95vh", "width": "100%"}),
        html.Div(id="info-box", style={
            "position": "absolute", "top": "60px", "right": "20px",
            "width": "280px", "padding": "15px",
            "backgroundColor": "#E6E6FA", "border": "1px solid #999",
            "borderRadius": "10px", "boxShadow": "2px 2px 6px rgba(75, 0, 130)",
            "overflowY": "auto", "maxHeight": "80vh", "zIndex": 10
        })
    ], style={"position": "relative", "height": "100vh", "width": "100vw"})
])

# ----------- Clientside Callback -----------
app.clientside_callback(
    f"""
    function(n_clicks) {{
        const graphData = {graph_data_json};
        const nodeInfo = {node_info_json};
        const edgeInfo = {edge_info_json};

        const interval = setInterval(() => {{
            if (!window.ForceGraph3D || !window.THREE) return;

            clearInterval(interval);

            const Graph = ForceGraph3D();
            const graphContainer = document.getElementById("3d-graph");
            const infoBox = document.getElementById("info-box");
            const THREE = window.THREE;

            const fg = Graph(graphContainer)
                .graphData(graphData)
                .nodeLabel('name')
                .nodeAutoColorBy('id')
                .linkDirectionalParticles(2)
                .linkWidth(link => link.capacity / 15)
                .linkDirectionalParticleSpeed(0.005)
                .backgroundColor('#000')

                .nodeThreeObject(node => {{
                    if (node.id === "N100") {{
                        const sprite = new THREE.Sprite(
                            new THREE.SpriteMaterial({{ color: 'deeppink' }})
                        );
                        sprite.scale.set(20, 20, 1);
                        return sprite;
                    }}
                    return null;
                }})

                .onNodeClick(function(node) {{
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

                .onLinkClick(function(link) {{
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

            // Handle reset button
            const resetBtn = document.getElementById("reset-btn");
            resetBtn.addEventListener("click", () => {{
                fg.graphData().nodes.forEach(node => {{
                    delete node.fx;
                    delete node.fy;
                    delete node.fz;
                }});
                fg.d3ReheatSimulation();
            }});

            // Handle double click to reset visuals
            graphContainer.addEventListener("dblclick", function(event) {{
                fg.cameraPosition(
                    {{ x: 0, y: 0, z: 500 }},
                    {{ x: 0, y: 0, z: 0 }},
                    1000
                );
                fg.graphData().nodes.forEach(n => delete n.color);
                fg.graphData().links.forEach(l => delete l.color);
                fg.nodeAutoColorBy('id');
                infoBox.innerHTML = '';
                fg.refresh();
            }});
        }}, 100);

        return '';
    }}
    """,
    Output("info-box", "children"),
    Input("reset-btn", "n_clicks")
)

# ----------- Run App -----------
if __name__ == '__main__':
    app.run(debug=True)
