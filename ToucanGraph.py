import Utils

import networkx as nx

class ToucanGraph:
  def __init__(self, graph=None):
    if graph is None:
      self.graph = nx.DiGraph()  # Use directed graph, change to Graph() for undirected
    elif isinstance(graph, nx.DiGraph):
      self.graph = graph.copy()
    else:
      raise TypeError("graph must be an instance of networkx.DiGraph")

    self.levels = []  # List of lists to store nodes at each level

  def load(self, file_path: str) -> None:
    """Load a graph from a text file in the described format."""
    with open(file_path, 'r') as file:
      # Read the first line for number of edges and nodes
      first_line = file.readline().strip()
      num_edges, num_nodes = map(int, first_line.split())

      nodes_to_add = []
      edges_to_add = []

      for node_id, line in enumerate(file):
        node_id = int(node_id)
        parts = line.strip().split()
        if len(parts) < 2:
          raise ValueError(f"Node {node_id} is missing weight or neighbors.")

        label = parts[0]
        if not label:
          raise ValueError(f"Node {node_id} has an empty label, which is illegal.")

        weight = int(parts[1])

        # Skip invalid nodes
        if weight < 0:
          continue

        # Parse label into OpName, LUTName, and MulId/AddId
        label_parts = label.split('-')
        if len(label_parts) > 3:
          raise ValueError(f"Node {node_id} has an invalid label format: {label}")
        assert(len(label_parts) > 0)

        op_name = label_parts[0]
        lut_name = label_parts[1] if len(label_parts) > 1 else None
        id_part = label_parts[2] if len(label_parts) > 2 else None
        mul_id = id_part if id_part and id_part.startswith('m') else None
        add_id = id_part if id_part and id_part.startswith('a') else None

        if mul_id is not None:
          assert(mul_id[0] == 'm')
          mul_id = int(mul_id[1:])

        if add_id is not None:
          assert(add_id[0] == 'a')
          add_id = int(add_id[1:])

        # Collect node information
        nodes_to_add.append((node_id, {
          "label": label,
          "weight": weight,
          "op_name": op_name,
          "lut_name": lut_name,
          "mul_id": mul_id,
          "add_id": add_id
        }))

        # Collect edges information
        if len(parts) > 2:
          neighbors = map(int, parts[2:])
          for neighbor in neighbors:
            edges_to_add.append((node_id, neighbor))

      # Add all nodes to the graph
      self.graph.add_nodes_from(nodes_to_add)

      # Add all edges to the graph
      edge_count = 0
      for source, target in edges_to_add:
        if not self.graph.has_node(source) or not self.graph.has_node(target):
          raise ValueError(f"Edge from {source} to {target} refers to non-existent node.")
        self.graph.add_edge(source, target)
        edge_count += 1

      # Assert the number of nodes and edges
      assert self.graph.number_of_nodes() == num_nodes, f"Expected {num_nodes} nodes, found {self.graph.number_of_nodes()}"
      assert edge_count == num_edges, f"Expected {num_edges} edges, found {edge_count}"

  def create_subgraph(self, node_list):
    """Create a subgraph containing only the specified nodes."""
    subgraph = self.graph.subgraph(node_list).copy()
    return ToucanGraph(subgraph)

  def levelize(self):
    """Legalize the graph by assigning level IDs to each node and updating levels list."""
    if not nx.is_directed_acyclic_graph(self.graph):
      raise ValueError("The graph must be a Directed Acyclic Graph (DAG) to levelize.")

    # Compute the levels using topological sorting
    level_mapping = {}
    self.levels = []  # Reset levels
    for level_id, nodes in enumerate(nx.topological_generations(self.graph)):
      self.levels.append(list(nodes))
      for node in nodes:
        level_mapping[node] = level_id

    # Assign level IDs to node attributes
    for node, level_id in level_mapping.items():
      self.graph.nodes[node]["level_id"] = level_id

  def is_levelized(self) -> bool:
    """Check if the graph is levelized by verifying if levels is empty."""
    return bool(self.levels)

  def __str__(self):
    """Return a string representation of the graph."""
    level_info = f" and {len(self.levels)} levels" if self.levels else ""
    return f"Graph with {self.graph.number_of_nodes()} nodes and {self.graph.number_of_edges()} edges{level_info}."

  def findAllNodesWithTag(self, tagName):
    """Find all nodes with a specific tagName and return a dict with tagValue as the key."""
    result = {}
    for node, attrs in self.graph.nodes(data=True):
      tagValue = attrs.get(tagName)
      if tagValue != None:
        if tagValue not in result:
          result[tagValue] = []
        result[tagValue].append(node)
    return result
  
  def is_acyclic(self) -> bool:
    """Check if the graph is acyclic."""
    return nx.is_directed_acyclic_graph(self.graph)
  
  # def merge_nodes(self, nodes_to_merge, new_node_attributes=None):
  #   """Merge multiple nodes into a single node.

  #   Args:
  #     nodes_to_merge: List of node IDs to be merged.
  #     new_node_attributes: Attributes for the new node (optional).

  #   Returns:
  #     new_node_id: The ID of the newly created node.
  #   """
  #   if not all(node in self.graph for node in nodes_to_merge):
  #     raise ValueError("All nodes to merge must exist in the graph.")

  #   # Generate a new node ID
  #   new_node_id = max(self.graph.nodes) + 1

  #   # Collect edges for the new node
  #   incoming_edges = set()
  #   outgoing_edges = set()

  #   for node in nodes_to_merge:
  #     incoming_edges.update((pred, new_node_id) for pred in self.graph.predecessors(node) if pred not in nodes_to_merge)
  #     outgoing_edges.update((new_node_id, succ) for succ in self.graph.successors(node) if succ not in nodes_to_merge)

  #   # Remove the old nodes
  #   self.graph.remove_nodes_from(nodes_to_merge)

  #   # Add the new merged node
  #   self.graph.add_node(new_node_id, **(new_node_attributes or {}))

  #   # Add the collected edges
  #   self.graph.add_edges_from(incoming_edges)
  #   self.graph.add_edges_from(outgoing_edges)

  #   return new_node_id
  
  # def dropAllConstDecls

if __name__ == "__main__":
  # test
  fileName = "design_before_cut.graph"


  g = ToucanGraph()
  g.load(fileName)
  g.levelize()
  assert(g.is_acyclic())

  print(g)

  print(len(g.levels))
  for node in g.levels[-1]:
    print(g.graph.nodes[node].get('label'))

  Utils.print_memory_usage()