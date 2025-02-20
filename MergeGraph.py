import networkx as nx
import itertools

class MergeGraph:
  def __init__(self):
    self.graph = nx.DiGraph()
    self._next_id = 0
    self.levels = []
    self.node_to_level = {}

    self.nodes_to_remove = set()
  
  def add_node(self):
    node_id = self._next_id
    self._next_id += 1

    self.graph.add_node(node_id)

    return node_id
  
  def add_edge(self, source, target):
    assert(isinstance(source, int))
    assert(isinstance(target, int))
    
    self.graph.add_edge(source, target)
    
  def add_edges(self, edges):
    for u, v in edges:
      assert(isinstance(u, int))
      assert(isinstance(v, int))
    self.graph.add_edges_from(edges)


  
  def get_node_successors(self, node):
    return self.graph.successors(node)
  
  def get_node_predecessors(self, node):
    return self.graph.predecessors(node)
  
  def merge_is_acyclic(self, nodes_to_merge):
    assert(len(self.levels) != 0)
    nodes_to_merge = set(nodes_to_merge)
    
    # From therom, Parts can be safely merged if and only if there is no external path in either direction between them
    # start traversing from min level ensures only 1 direction of search is necessary

    nodes_to_merge_max_level = max(nodes_to_merge, key = lambda n: self.node_to_level[n])

    node_to_merge_group_by_level = []
    for level, nodes in itertools.groupby(nodes_to_merge, key = lambda n: self.node_to_level[n]):
      node_to_merge_group_by_level.append((level, set(nodes)))
    node_to_merge_group_by_level.sort(key = lambda x: x[0])

    # print(node_to_merge_group_by_level)

    if len(node_to_merge_group_by_level) == 1:
      return True


    for source_level, source_nodes in node_to_merge_group_by_level:
      fringe = source_nodes.copy()
      fringe_next = set()

      current_level = source_level

      # + 1: extra safe guard
      while current_level <= nodes_to_merge_max_level + 1 and len(fringe) != 0:
        current_level_fringe = set(filter(lambda x: self.node_to_level[x] == current_level, fringe))

        fringe_next = fringe.difference(current_level_fringe)


        for vtx in current_level_fringe:
          for succ in self.graph.successors(vtx):
            if not (vtx in nodes_to_merge and succ in nodes_to_merge):
              # Not an internal edge
              fringe_next.add(succ)
        
        if not fringe_next.isdisjoint(nodes_to_merge):
          # has intersection, we encounter an external edge
          # this merge is cyclic
          return False
        
        fringe = fringe_next
        fringe_next = set()

        current_level += 1

    return True

  
  def merge_nodes(self, to, from_list):
    new_edges = []
    
    to_node_new_predecessors = set()
    to_node_new_sucessors = set()

    # 
    from_set = set(from_list)
    assert(to not in from_set)
    assert(len(from_set) == len(from_list))

    for n in from_set:
      to_node_new_predecessors.update(self.graph.predecessors(n))
      to_node_new_sucessors.update(self.graph.successors(n))

    to_node_new_predecessors.difference_update(self.graph.predecessors(to))
    to_node_new_sucessors.difference_update(self.graph.successors(to))

    to_node_new_predecessors.discard(to)
    to_node_new_sucessors.discard(to)

    for p in to_node_new_predecessors:
      new_edges.append((p, to))
    for s in to_node_new_sucessors:
      new_edges.append((to, s))

    self.graph.add_edges_from(new_edges)
    self.graph.remove_nodes_from(from_set)
    


  def graph_gc(self):
    # remove nodes together to speed up
    self.graph.remove_nodes_from(self.nodes_to_remove)
    self.nodes_to_remove.clear()

  def check_graph(self):
    assert(nx.is_directed_acyclic_graph(self.graph))


  def levelize(self):
    self.levels = []
    self.node_to_level.clear()

    for level_id, nodes in enumerate(nx.topological_generations(self.graph)):
      self.levels.append(list(nodes))
      for n in nodes:
        assert(n not in self.node_to_level)
        self.node_to_level[n] = level_id



  

