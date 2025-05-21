
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

"""
==================================================================================
| Library               | Used For                                               |
==================================================================================
| dash                 | Creating the web app interface with interactive layout  |
| dash_extensions      | Advanced callback control using DashProxy and transforms|
| networkx             | Generating and managing the directed graph (nodes/edges)|
| json                 | Converting graph data to JSON for clientside JS usage   |
| 3d-force-graph       | Rendering the interactive 3D force-directed graph in JS |
| three.js             | Custom 3D rendering, including the N100 target sprite   |
==================================================================================


"""

