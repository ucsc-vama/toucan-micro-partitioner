import networkx as nx
import matplotlib.pyplot as plt

def hierarchical_layout(graph):
  """
  Create a hierarchical layout for a Directed Acyclic Graph (DAG).

  Parameters:
  - graph: A networkx DiGraph (must be a DAG).

  Returns:
  - A dictionary of node positions, where keys are nodes and values are (x, y) coordinates.
  """
  if not nx.is_directed_acyclic_graph(graph):
    raise ValueError("The graph must be a Directed Acyclic Graph (DAG).")

  # Step 1: Perform a topological sort
  topological_order = list(nx.topological_sort(graph))

  # Step 2: Assign levels to nodes
  levels = {}
  for node in topological_order:
    # The level of a node is the maximum level of its predecessors + 1
    if graph.in_degree(node) == 0:
      levels[node] = 0  # Root nodes are at level 0
    else:
      levels[node] = max(levels[pred] for pred in graph.predecessors(node)) + 1

  # Step 3: Position nodes in levels
  pos = {}
  level_groups = {}
  for node, level in levels.items():
    if level not in level_groups:
      level_groups[level] = []
    level_groups[level].append(node)

  # Arrange nodes in levels
  for level, nodes_in_level in level_groups.items():
    x_offset = 1.0 / (len(nodes_in_level) + 1)  # Evenly space nodes in the level
    for i, node in enumerate(nodes_in_level):
      pos[node] = ((i + 1) * x_offset, -level)  # y-coordinate decreases with level

  return pos

# # Example usage
# G = nx.DiGraph()
# G.add_edges_from([(1, 2), (1, 3), (2, 4), (3, 4), (4, 5), (5, 6)])

# # Compute the hierarchical layout
# pos = hierarchical_layout(G)

# # Draw the graph
# nx.draw(G, pos, with_labels=True, node_color='lightblue', edge_color='gray', node_size=500, font_size=10, arrows=True)
# plt.show()