"""
Task Graph Visualizer

Generates a beautiful Mermaid.js interactive graph of the TaskGraph
and automatically opens it in the default web browser.

Usage:
    visualize_graph(task_graph)
"""

import os
import webbrowser
from core.graph.task_graph import TaskGraph

# Ensure the graphs directory exists
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
GRAPHS_DIR = os.path.join(BASE_DIR, "data", "graphs")
os.makedirs(GRAPHS_DIR, exist_ok=True)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Jarvis Task Graph: {graph_name}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: #1a1a2e;
            color: #e0e0e0;
            margin: 0;
            padding: 20px;
            display: flex;
            flex-direction: column;
            align-items: center;
        }}
        .header {{
            text-align: center;
            margin-bottom: 20px;
        }}
        h1 {{
            color: #7c3aed;
            margin: 0 0 10px 0;
        }}
        .summary {{
            color: #a0a0b0;
            font-size: 14px;
        }}
        .mermaid {{
            background-color: #2a2a40;
            padding: 30px;
            border-radius: 12px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
            width: 100%;
            max-width: 900px;
            display: flex;
            justify-content: center;
        }}
    </style>
    <!-- Include Mermaid.js -->
    <script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
    <script>
        mermaid.initialize({{ 
            startOnLoad: true,
            theme: 'dark',
            flowchart: {{
                useMaxWidth: true,
                htmlLabels: true,
                curve: 'basis'
            }}
        }});
    </script>
</head>
<body>
    <div class="header">
        <h1>🧠 Jarvis Execution Plan</h1>
        <div class="summary">Task: {graph_name} &nbsp;|&nbsp; Nodes: {node_count}</div>
    </div>
    
    <div class="mermaid">
        {mermaid_code}
    </div>
</body>
</html>
"""

def generate_mermaid_code(graph: TaskGraph) -> str:
    """Converts a TaskGraph into Mermaid.js syntax."""
    lines = ["graph TD", ""]
    
    # Add nodes
    for node_id, node in graph.nodes.items():
        # Escape quotes for safety
        desc = node.description.replace('"', "'")
        action = f"<i>{node.action}</i>"
        label = f'"{desc}<br/>{action}"'
        
        # Style based on status or type
        if node.agent == 'system':
            shape_start, shape_end = "((", "))"  # Circle
        elif node.agent == 'window':
            shape_start, shape_end = "[[", "]]"  # Subroutine
        else:
            shape_start, shape_end = "[", "]"    # Square
            
        lines.append(f"    {node_id}{shape_start}{label}{shape_end}")
        
    lines.append("")
    
    # Add dependencies (edges)
    has_edges = False
    for node_id, node in graph.nodes.items():
        for dep_id in node.depends_on:
            if dep_id in graph.nodes:
                lines.append(f"    {dep_id} --> {node_id}")
                has_edges = True
                
    if not has_edges and len(graph.nodes) > 1:
        # If no explicit edges exist but there are multiple nodes, 
        # they run in parallel.
        pass

    return "\n".join(lines)


def visualize_graph(graph: TaskGraph, auto_open: bool = True) -> str:
    """
    Generates an HTML visualization of the graph and optionally 
    opens it in the default web browser.
    
    Returns the file path.
    """
    if not graph or not graph.nodes:
        return ""
        
    mermaid_code = generate_mermaid_code(graph)
    
    html_content = HTML_TEMPLATE.format(
        graph_name=graph.name,
        node_count=len(graph.nodes),
        mermaid_code=mermaid_code
    )
    
    file_path = os.path.abspath(os.path.join(GRAPHS_DIR, f"graph_{graph.id}.html"))
    
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(html_content)
        
    if auto_open:
        try:
            webbrowser.open(f"file://{file_path}")
            print(f"Graph visualization opened in browser.")
        except Exception as e:
            print(f"Could not auto-open browser: {e}")
            
    return file_path
