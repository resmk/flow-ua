import dash
from dash import dcc, html, Input, Output, State
import dash_cytoscape as cyto
import networkx as nx
import random

# ----------- Build Graph -----------

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

# ----------- Convert to Cytoscape Format -----------

cy_nodes = [{
    'data': {'id': node, 'label': node},
    'position': {'x': random.randint(0, 1000), 'y': random.randint(0, 1000)},
    'grabbable': True,
    'selectable': True
} for node in G.nodes()]

cy_edges = [{
    'data': {
        'id': f"{u}->{v}",
        'source': u,
        'target': v,
        'label': f"{u} → {v} ({G[u][v]['capacity']})",
        'capacity': G[u][v]['capacity']
    }
} for u, v in G.edges()]

elements = cy_nodes + cy_edges

# ----------- Dash App -----------

app = dash.Dash(__name__)
server = app.server

app.layout = html.Div([
    html.Div([
        cyto.Cytoscape(
            id='cytoscape-network',
            elements=elements,
            layout={'name': 'preset'},
            style={'width': '100%', 'height': '80vh'},
            stylesheet=[
                {'selector': 'node', 'style': {'label': 'data(label)', 'background-color': '#9370DB', 'width': 25, 'height': 25}},
                {'selector': 'edge', 'style': {'curve-style': 'bezier', 'target-arrow-shape': 'triangle', 'arrow-scale': 1.2, 'label': 'data(label)', 'font-size': 8}},
                {'selector': ':selected', 'style': {'background-color': '#FF1493', 'line-color': '#FF1493', 'target-arrow-color': '#FF1493'}}
            ],
            userZoomingEnabled=True,
            userPanningEnabled=True,
            boxSelectionEnabled=True,
            autoungrabify=False,
            autounselectify=False,
            minZoom=0.2,
            maxZoom=2
        ),
        html.Div(id='info-box', style={
            'marginTop': '10px',
            'padding': '10px',
            'border': '1px solid #999',
            'borderRadius': '5px',
            'width': '400px',
            'backgroundColor': '#f9f9f9',
            'boxShadow': '2px 2px 6px rgba(0,0,0,0.1)'
        })
    ])
])

# ----------- Callbacks -----------

@app.callback(
    Output('info-box', 'children'),
    Input('cytoscape-network', 'tapNodeData'),
    Input('cytoscape-network', 'tapEdgeData')
)
def show_info(node_data, edge_data):
    if node_data:
        node = node_data['id']
        out_edges = list(G.out_edges(node, data=True))
        in_edges = list(G.in_edges(node, data=True))

        return html.Div([
            html.H4(f"Node: {node}"),
            html.Div([
                html.Strong("Outgoing:"),
                html.Ul([
                    html.Li(f"{u} → {v} (Capacity: {data['capacity']})") for u, v, data in out_edges
                ]) if out_edges else html.P("None")
            ]),
            html.Div([
                html.Strong("Incoming:"),
                html.Ul([
                    html.Li(f"{u} → {v} (Capacity: {data['capacity']})") for u, v, data in in_edges
                ]) if in_edges else html.P("None")
            ])
        ])
    
    elif edge_data:
        return html.Div([
            html.H4("Edge Selected"),
            html.P(f"{edge_data['source']} → {edge_data['target']}"),
            html.P(f"Capacity: {edge_data['capacity']}")
        ])

    return "Click on a node or edge to see details."

# ----------- Run Server -----------

if __name__ == '__main__':
    app.run(debug=True)
