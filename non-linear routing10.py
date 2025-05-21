import dash
from dash import dcc, html, Input, Output, State
import plotly.graph_objs as go
import networkx as nx
import numpy as np
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

pos = nx.spring_layout(G, dim=3, seed=42)
pos = {node: list(coord) for node, coord in pos.items()}

# ----------- Dash App -----------

app = dash.Dash(__name__)
server = app.server

app.layout = html.Div([
    dcc.Graph(id='network-graph', style={'height': '80vh'}),
    dcc.Store(id='clicked-edges-store', data=[]),
    dcc.Store(id='selected-node-store', data=None),
    dcc.Store(id='camera-store', data=None),  # 👈 Store for camera
    html.Div(id='selected-node', style={'marginTop': '10px'}),
])

# ----------- Figure Builder -----------

def create_figure(selected_node=None, highlighted_edges=None, camera=None):
    if highlighted_edges is None:
        highlighted_edges = []

    fig = go.Figure()

    for (u, v, data) in G.edges(data=True):
        x0, y0, z0 = pos[u]
        x1, y1, z1 = pos[v]
        is_highlighted = [u, v] in highlighted_edges
        edge_color = 'darkslateblue' if is_highlighted else 'lightskyblue'

        fig.add_trace(go.Scatter3d(
            x=[x0, x1, None],
            y=[y0, y1, None],
            z=[z0, z1, None],
            mode='lines',
            line=dict(width=4 if is_highlighted else 2, color=edge_color),
            hoverinfo='text',
            text=[f"{u} → {v}<br>Capacity: {data['capacity']}"] * 3,
            customdata=[[u, v]] * 3,
            showlegend=False
        ))

    node_x, node_y, node_z, node_text, marker_colors, marker_sizes = [], [], [], [], [], []
    for node in G.nodes:
        x, y, z = pos[node]
        node_x.append(x)
        node_y.append(y)
        node_z.append(z)
        node_text.append(node)

        if node == 'N100':
            marker_colors.append('darkviolet')
            marker_sizes.append(15)
        elif node == selected_node:
            marker_colors.append('magenta')
            marker_sizes.append(10)
        else:
            marker_colors.append('mediumpurple')
            marker_sizes.append(7)

    fig.add_trace(go.Scatter3d(
        x=node_x,
        y=node_y,
        z=node_z,
        mode='markers+text',
        marker=dict(size=marker_sizes, color=marker_colors, line=dict(width=0.8, color='darkviolet')),
        text=node_text,
        textposition="top center",
        hoverinfo='text',
        showlegend=False
    ))

    fig.update_layout(
        title="3D Directed Flow UA Network ",
        scene=dict(
            xaxis=dict(visible=False),
            yaxis=dict(visible=False),
            zaxis=dict(visible=False),
            camera=camera if camera else dict()
        ),
        margin=dict(l=0, r=0, b=0, t=40),
        showlegend=False
    )

    return fig

# ----------- Callbacks -----------

@app.callback(
    Output('camera-store', 'data'),
    Input('network-graph', 'relayoutData'),
    State('camera-store', 'data'),
    prevent_initial_call=True
)
def store_camera(relayout_data, current_camera):
    if relayout_data and "scene.camera" in relayout_data:
        return relayout_data["scene.camera"]
    return current_camera

@app.callback(
    Output('network-graph', 'figure'),
    Input('clicked-edges-store', 'data'),
    Input('selected-node-store', 'data'),
    Input('camera-store', 'data')
)
def update_figure(clicked_edges, selected_node, camera):
    return create_figure(selected_node, clicked_edges, camera)

@app.callback(
    Output('clicked-edges-store', 'data'),
    Output('selected-node-store', 'data'),
    Output('selected-node', 'children'),
    Input('network-graph', 'clickData'),
    State('clicked-edges-store', 'data'),
    State('selected-node-store', 'data'),
    prevent_initial_call=True
)
def handle_click(clickData, clicked_edges, selected_node):
    if not clickData:
        return clicked_edges, selected_node, dash.no_update

    point = clickData['points'][0]

    if 'customdata' in point and isinstance(point['customdata'], list) and len(point['customdata']) == 2:
        u, v = point['customdata']
        edge = [u, v]
        if clicked_edges == [edge]:
            clicked_edges = []
        else:
            clicked_edges = [edge]
        return clicked_edges, selected_node, f"Selected edge: {u} → {v}"

    if 'text' in point:
        node = point['text']
        return clicked_edges, node, f"Selected node: {node}"

    return clicked_edges, selected_node, dash.no_update

# ----------- Run Server -----------
if __name__ == '__main__':
    app.run(debug=True)

