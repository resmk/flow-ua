import dash
from dash import html, dcc
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
    v = f"N{random.randint(int(u[1:]) + 1, 100)}" if int(u[1:]) < 100 else "N100"
    if u != v:
        extra_edges.append((u, v, random.randint(5, 20)))

edges = backbone_edges + extra_edges

G = nx.DiGraph()
G.add_nodes_from(nodes)
for u, v, cap in edges:
    G.add_edge(u, v, capacity=cap)

# Prepare graph data
graph_data = {
    "nodes": [{"id": node, "name": node} for node in G.nodes()],
    "links": [{"source": u, "target": v, "capacity": G[u][v]['capacity']} for u, v in G.edges()]
}
graph_data_json = json.dumps(graph_data)

# Node and edge info for JavaScript
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
node_info_json = json.dumps(node_info)
edge_info_json = json.dumps(edge_info)

# ----------- Dash App Setup -----------
external_scripts = ["https://unpkg.com/3d-force-graph"]

app = DashProxy(
    __name__,
    external_scripts=external_scripts,
    transforms=[TriggerTransform(), MultiplexerTransform()]
)
server = app.server

app.layout = html.Div([
    html.Div([
        html.Div(id="3d-graph", style={"height": "95vh", "width": "100%"}),
        html.Div(id="info-box", style={
            "position": "absolute", "top": "20px", "right": "20px",
            "width": "280px", "padding": "15px",
            "backgroundColor": "#E6E6FA", "border": "1px solid #999",
            "borderRadius": "10px", "boxShadow": "2px 2px 6px rgba(75, 0, 130)",
            "overflowY": "auto", "maxHeight": "80vh", "zIndex": 10
        })
    ], style={"position": "relative", "height": "100vh", "width": "100vw"})
])


# ----------- Clientside Callback -----------
app.clientside_callback(
    """
    function(_) {
        const graphData = """ + graph_data_json + """;
        const nodeInfo = """ + node_info_json + """;
        const edgeInfo = """ + edge_info_json + """;

        const Graph = ForceGraph3D();
        const graphContainer = document.getElementById("3d-graph");
        const infoBox = document.getElementById("info-box");

        const fg = Graph(graphContainer)
            .graphData(graphData)
            .nodeLabel('name')
            .nodeAutoColorBy('id')
            .linkDirectionalParticles(2)
            .linkWidth(link => link.capacity / 15)
            .linkDirectionalParticleSpeed(0.005)
            .backgroundColor('#000')  // updated background color

            .onNodeClick(function(node) {
                // Reset all node colors
                fg.graphData().nodes.forEach(n => delete n.color);
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

            .onLinkClick(function(link) {
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
            });

        return '';
    }
    """,
    Output("info-box", "children"),
    Input("3d-graph", "id")
)

# ----------- Run App -----------
if __name__ == '__main__':
    app.run(debug=True)
