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
    self.vecdecl_to_nop = {} # Map of original VecDecl to new Vecdecl NOP
    self.max_node_id = 0

  def load(self, file_path: str) -> None:
    """Load a graph from a text file in the described format."""
    with open(file_path, 'r') as file:
      for lineno, line in enumerate(file):
        if lineno == 0:
          # Read the first line for number of edges and nodes
          first_line = line.strip()
          num_edges, num_nodes = map(int, first_line.split())

          nodes_to_add = []
          edges_to_add = []
          invalid_nodes = set()
          continue

        
        parts = line.strip().split()
        node_id = int(parts[0])
        self.max_node_id = max(node_id, self.max_node_id)
        if len(parts) < 3:
          raise ValueError(f"Node {node_id} is missing weight or neighbors.")

        label = parts[1]
        if not label:
          raise ValueError(f"Node {node_id} has an empty label, which is illegal.")

        weight = int(parts[2])

        # Skip invalid nodes
        if weight < 0:
          invalid_nodes.add(node_id)
          continue

        # Collect node information
        nodes_to_add.append((node_id, {
          "label": label,
          "weight": weight
        }))

        # Collect edges information
        if len(parts) > 3:
          neighbors = map(int, parts[3:])
          for neighbor in neighbors:
            edges_to_add.append((node_id, neighbor))

      # Add all nodes to the graph
      self.graph.add_nodes_from(nodes_to_add)

      # Add all edges to the graph
      edge_count = 0
      for source, target in edges_to_add:
        assert(source not in invalid_nodes)
        if target in invalid_nodes:
          continue
        if not self.graph.has_node(source) or not self.graph.has_node(target):
          source_existance = "Exist" if self.graph.has_node(source) else "NonExist"
          target_existance = "Exist" if self.graph.has_node(source) else "NonExist"
          raise ValueError(f"Line {lineno}: Edge from {source} ({source_existance}) to {target} ({target_existance}) refers to non-existent node.")
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

  # def findAllNodesWithTag(self, tagName):
  #   """Find all nodes with a specific tagName and return a dict with tagValue as the key."""
  #   result = {}
  #   for node, attrs in self.graph.nodes(data=True):
  #     tagValue = attrs.get(tagName)
  #     if tagValue != None:
  #       if tagValue not in result:
  #         result[tagValue] = []
  #       result[tagValue].append(node)
  #   return result
  
  def is_acyclic(self) -> bool:
    """Check if the graph is acyclic."""
    return nx.is_directed_acyclic_graph(self.graph)
  
  def expand_VecDecl(self, vecDeclElements: dict):
    vecDecl_node_ids = []
    nodes_to_remove = []

    for node, attrs in self.graph.nodes(data=True):
      tagValue = attrs.get("label")
      if tagValue == "VecDecl":
        node_weight = attrs.get("weight")
        vecDecl_node_ids.append((node, node_weight))
        nodes_to_remove.append(node)
    print(len(vecDecl_node_ids))

    for node, weight in vecDecl_node_ids:
      vec_input_nodes = list(self.graph.predecessors(node))
      vec_user_nodes = list(self.graph.successors(node))

      # Vec info file should be consistant with graph info
      assert(node in vecDeclElements)

      vec_element_op_ids = vecDeclElements[node]

      # At least one vecDecl element
      assert(weight > 0)
      # should also be consistant
      assert(weight == len(vec_element_op_ids))
      assert(len(vec_input_nodes) <= weight)

      nodes_to_add = []
      edges_to_add = []
      new_node_list = []
      for i in range(0, weight):
        # insert NOP
        self.max_node_id += 1
        node_id = self.max_node_id
        assert(node_id not in self.graph.nodes())

        nodes_to_add.append((node_id, {
          "label": "VecDecl_LUT_NOP",
          "weight": 1,
          "original_vec_decl": node
        }))
        new_node_list.append(node_id)

        edge_src = vec_element_op_ids[i]
        assert(edge_src in vec_input_nodes)
        for d in vec_user_nodes:
          edges_to_add.append((edge_src, node_id))
          edges_to_add.append((node_id, d))

      assert(node not in self.vecdecl_to_nop)
      self.vecdecl_to_nop[node] = new_node_list
      self.graph.add_nodes_from(nodes_to_add)
      self.graph.add_edges_from(edges_to_add)
    assert(len(nodes_to_remove) <= len(vecDeclElements))
    self.graph.remove_nodes_from(nodes_to_remove)

  def remove_ConstDecl(self):
    nodes_to_remove = []
    for node, attrs in self.graph.nodes(data=True):
      tagValue = attrs.get("label")
      if tagValue == "ConstDecl":
        nodes_to_remove.append(node)
    print(f"Remove {len(nodes_to_remove)} ConstDecl nodes")
    self.graph.remove_nodes_from(nodes_to_remove)

  def save_vector_def_info(self, filename: str):
    with open(filename, 'w') as out:
      for vecDecl_node, nop_list in self.vecdecl_to_nop.items():
        line = [vecDecl_node]
        line.extend(nop_list)
        assert(len(nop_list) != 0)
        out.write(' '.join(map(lambda x: str(x), line)))
        out.write("\n")




  
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