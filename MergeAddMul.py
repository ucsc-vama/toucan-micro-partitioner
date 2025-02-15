
import ToucanGraph
import Utils
import NetworkUtils

import networkx as nx
import matplotlib.pyplot as plt


import networkx as nx

def longest_path_length_in_dag(graph):
  """
  Find the length of the longest path in a Directed Acyclic Graph (DAG),
  even if the graph has multiple disconnected components.

  Parameters:
  - graph: A networkx DiGraph (must be a DAG).

  Returns:
  - The length of the longest path.
  """
  if not nx.is_directed_acyclic_graph(graph):
    raise ValueError("The graph must be a Directed Acyclic Graph (DAG).")

  max_length = 0

  # Step 1: Find all weakly connected components
  for component in nx.weakly_connected_components(graph):
    # Create a subgraph for the current component
    subgraph = graph.subgraph(component)

    # Step 2: Perform a topological sort of the subgraph
    topological_order = list(nx.topological_sort(subgraph))

    # Step 3: Initialize distances
    distance = {node: float('-inf') for node in subgraph.nodes}

    # Set the distance of the first node in the topological order to 0
    distance[topological_order[0]] = 0

    # Step 4: Relax edges in topological order
    for node in topological_order:
      for neighbor in subgraph.successors(node):
        if distance[neighbor] < distance[node] + 1:  # Assuming unweighted edges
          distance[neighbor] = distance[node] + 1

    # Step 5: Update the maximum length
    max_length = max(max_length, max(distance.values()))

  return max_length + 1


def are_islands_disjoint_in_original_graph(original_graph, subgraph_nodes):
    """
    Check if the nodes in the subgraph are disconnected in the original graph.
    
    Parameters:
    - original_graph: The original directed acyclic graph (DAG).
    - subgraph_nodes: A list of nodes in the subgraph.
    
    Returns:
    - True if the nodes in the subgraph are disconnected in the original graph (no path connects different islands).
    - False otherwise.
    """
    # Create the subgraph induced by the given nodes
    subgraph = original_graph.subgraph(subgraph_nodes)
    
    # Find weakly connected components in the subgraph
    connected_components = list(nx.weakly_connected_components(subgraph))
    
    # If there's only one connected component, the nodes are already connected
    if len(connected_components) <= 1:
        return True
    
    # Check if any two connected components are connected in the original graph
    for i in range(len(connected_components)):
        for j in range(i + 1, len(connected_components)):
            # Pick any node from each component
            node_i = next(iter(connected_components[i]))  # First node in component i
            node_j = next(iter(connected_components[j]))  # First node in component j
            
            # Check if there's a path between node_i and node_j in the original graph
            if nx.has_path(original_graph, node_i, node_j) or nx.has_path(original_graph, node_j, node_i):
                return False  # There's a path connecting the components in the original graph
    
    # No paths connect any of the components in the original graph
    return True

def plot_sub_nodes(graph):
  pos = NetworkUtils.hierarchical_layout(graph)

  plt.figure(figsize=(4, 10))
  nx.draw(graph, pos, with_labels=True, node_color='lightblue', edge_color='gray', node_size=200, font_size=10)

  # Display the plot
  plt.show()



def replace_nodes_with_chain(G: nx.DiGraph, add_id, nodes, chain_length: int):
  nodes_set = set(nodes)

  # 1) Create the chain once
  chain_nodes = []
  for i in range(chain_length):

    new_node_id = max(G.nodes) + 1
    new_node = f"chain_{add_id}_{i}"
    G.add_node(new_node_id, label = new_node, op_name = "VecOp", weight = 1)
    chain_nodes.append(new_node_id)

  # Link up the chain internally
  for i in range(chain_length - 1):
    G.add_edge(chain_nodes[i], chain_nodes[i + 1])

  chain_start = chain_nodes[0]
  chain_end   = chain_nodes[-1]

  # 2) Replace each node in `nodes` with the existing chain
  for node in nodes:
    if node not in G:
      # Skip if the node was already removed or doesn't exist
      raise ValueError("Input node should in graph")

    # Gather incoming and outgoing edges
    in_edges = list(G.in_edges(node, data=True))
    out_edges = list(G.out_edges(node, data=True))

    # Remove the node
    G.remove_node(node)

    # Reroute incoming edges to the chain start
    for src, _, data in in_edges:
      # Ensure the source still exists after removals
      if src in G and src not in nodes_set:
        G.add_edge(src, chain_start, **data)

    # Reroute outgoing edges from the chain end
    for _, dst, data in out_edges:
      # Ensure the destination still exists after removals
      if dst in G and dst not in nodes_set:
        G.add_edge(chain_end, dst, **data)




def sim_replace_add(g, adds, add_width = 16):
  print("This is just a guess! may not accurate!")

  for add_id, add_nodes in adds.items():
    sub_g = g.graph.subgraph(add_nodes)

    longest_path_len = longest_path_length_in_dag(sub_g)

    new_chain_length = int(longest_path_len * 4 / add_width) + 1

    replace_nodes_with_chain(g.graph, add_id, add_nodes, new_chain_length)


def sim_replace_mul(g, muls, mul_width = 16):
  print("This is just a guess! may not accurate!")

  for mul_id, mul_nodes in muls.items():
    sub_g = g.graph.subgraph(mul_nodes)

    longest_path_len = longest_path_length_in_dag(sub_g)

    new_chain_length = int(longest_path_len * 4 / mul_width) + 1

    replace_nodes_with_chain(g.graph, mul_id, mul_nodes, new_chain_length)


def test_graph(fileName = "design_before_cut.graph"):

  g = ToucanGraph.ToucanGraph()
  g.load(fileName)

  # looking for add
  adds = g.findAllNodesWithTag('add_id')


  nodes_to_remove = []
  for n in g.graph.nodes():
    opName = g.graph.nodes[n]['op_name']
    if opName == "ConstDecl":
      nodes_to_remove.append(n)
  print(f"Remove {len(nodes_to_remove)} ConstDecl nodes")
  g.graph.remove_nodes_from(nodes_to_remove)


  total_add_nodes = 0
  total_path_len = 0
  max_path_len = 0
  for add_id, add_nodes in adds.items():
    total_add_nodes += len(add_nodes)
    sub_g = g.graph.subgraph(add_nodes)

    longest_path_len = longest_path_length_in_dag(sub_g)
    total_path_len += longest_path_len
    max_path_len = max(max_path_len, longest_path_len)

    # if (longest_path_len == 28):
    #   plot_sub_nodes(sub_g)
    #   exit()

    if not are_islands_disjoint_in_original_graph(g.graph, add_nodes):
      print(add_id)
      plot_sub_nodes(sub_g)
      exit(0)


  print(f"Graph has {len(adds)} add subgraphs, avg size {total_add_nodes / len(adds)}, avg path {total_path_len / len(adds)}, longest path {max_path_len}")

  


  # looking for mul
  muls = g.findAllNodesWithTag('mul_id')

  total_mul_nodes = 0
  max_path_len = 0
  total_path_len = 0
  for mul_id, mul_nodes in muls.items():
    total_mul_nodes += len(mul_nodes)

    longest_path_len = longest_path_length_in_dag(g.graph.subgraph(mul_nodes))
    total_path_len += longest_path_len
    max_path_len = max(max_path_len, longest_path_len)

    if not are_islands_disjoint_in_original_graph(g.graph, mul_nodes):
      print(mul_id)

      # # some bug here?
      # pos = nx.spring_layout(region_g.graph)  # Layout for positioning nodes
      # nx.draw(region_g.graph, pos, with_labels=True, node_color='lightblue', edge_color='gray', node_size=500, font_size=10)

      # # Display the plot
      # plt.show()
      
      # exit(0)

  print(f"Graph has {len(muls)} mul subgraphs, avg size {total_mul_nodes / len(muls)}, avg path {total_path_len / len(adds)}, longest path {max_path_len}")


  g.levelize()
  print(g)


  sim_replace_add(g, adds, 512)
  g.levelize()
  print(g)

  sim_replace_mul(g, muls, 512)
  g.levelize()
  print(g)





  return g

if __name__ == '__main__':
  test_graph()

  Utils.print_memory_usage()