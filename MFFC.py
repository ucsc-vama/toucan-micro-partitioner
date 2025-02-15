

import MergeAddMul



import networkx as nx


def find_mffcs(G: nx.DiGraph):
  mffcs = []

  # sinks = [n for n in G.nodes() if G.out_degree(n) == 0]
  visited = set()
  topo_order = list(nx.topological_sort(G))

  # assert last node is a sink node
  assert(G.out_degree(topo_order[-1]) == 0)

  for seed in reversed(topo_order):
    if seed in visited:
      continue

    # unvisited. Grow mffc
    mffc = set()
    mffc.add(seed)
    fringe = set(G.predecessors(seed))
    fringe_next = set()

    while len(fringe) != 0:
      for eachVtx in fringe:
        if all((w in mffc) for w in G.successors(eachVtx)):
          # include this node
          mffc.add(eachVtx)

          for eachPredecessor in G.predecessors(eachVtx):
            fringe_next.add(eachPredecessor)
      fringe = fringe_next
      fringe_next = set()

    # done with one mffc
    mffcs.append(mffc)

    for v in mffc:
      visited.add(v)

  return mffcs


import statistics
from collections import Counter

def print_set_size_statistics(list_of_sets):
  # Compute sizes for each set
  sizes = [len(s) for s in list_of_sets]

  # Basic stats
  n = len(sizes)
  min_size = min(sizes) if sizes else 0
  max_size = max(sizes) if sizes else 0
  avg_size = sum(sizes) / n if n else 0
  # For population std dev use statistics.pstdev
  # For sample std dev use statistics.stdev
  std_dev = statistics.pstdev(sizes) if n > 1 else 0

  # Frequency distribution
  freq = Counter(sizes)  # size -> count

  print(f"Number of sets: {n}")
  print(f"Min size: {min_size}")
  print(f"Max size: {max_size}")
  print(f"Average size: {avg_size:.2f}")
  print(f"Std Dev (population): {std_dev:.2f}")
  print("\nDistribution of sizes:")
  for size, count in sorted(freq.items()):
    print(f"  Size {size}: {count} set(s)")





if __name__ == "__main__":
  # Example usage
  G = nx.DiGraph()
  G.add_edges_from([
    ("A", "B"),
    ("B", "C"),
    ("C", "D"),
    ("B", "E"),
    ("E", "F"),
    ("X", "Y"),  # A separate component
  ])

  # Ensure G is acyclic
  assert nx.is_directed_acyclic_graph(G), "Graph must be a DAG."

  result = find_mffcs(G)
  for mffc_set in result:
    print(f"{mffc_set}")




if __name__ == "__main__":
    
  g = MergeAddMul.test_graph()


  print("\nAll MFFCs:")
  result = find_mffcs(g.graph)
  print_set_size_statistics(result)
  # for mffc_set in result:
  #   print(f"{mffc_set}")
