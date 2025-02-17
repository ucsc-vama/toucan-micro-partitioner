import networkx as nx
import itertools

class DirectedHyperGraph:
  def __init__(self):
    self.graph = nx.DiGraph()
    self._next_id = 0
    self.levels = []
    self.node_to_level = {}

    self.nodes_to_remove = set()
  
  def add_node(self):
    node_id = self._next_id
    self._next_id += 1

    self.graph.add_node(node_id, type='node')

    return node_id
  
  def add_hyperedge(self, source, targets):
    
    if not isinstance(source, int) and source is not None:
      raise TypeError("source must be an integer")
    
    he_id = self._next_id
    self._next_id += 1
    
    self.graph.add_node(he_id, type='hyperedge')

    if source is not None:
      self.graph.add_edge(source, he_id)
      assert(source in self.graph.nodes())
      assert(self.graph.nodes[source]['type'] == 'node')

    if targets is not None:
      for tgt in targets:
        # if tgt not in self.graph.nodes():
        #   print(f" Target node {tgt} not in graph")
        assert(tgt in self.graph.nodes())
        assert(self.graph.nodes[tgt]['type'] == 'node')
        self.graph.add_edge(he_id, tgt)
    
    return he_id
  
  def get_hyperedge_sources(self, he_id):
    return [n for n in self.graph.predecessors(he_id)]
  
  def get_hyperedge_targets(self, he_id):
    return [n for n in self.graph.successors(he_id)]
  
  def get_output_hyperedges(self, node):
    assert(self.graph.nodes[node]['type'] == 'node')
    return [n for n in self.graph.successors(node) 
            if self.graph.nodes[n]['type'] == 'hyperedge']
  
  def get_input_hyperedges(self, node):
    assert(self.graph.nodes[node]['type'] == 'node')
    return [n for n in self.graph.predecessors(node)
            if self.graph.nodes[n]['type'] == 'hyperedge']
  
  def get_node_successors(self, node):
    hes = self.get_output_hyperedges(node)
    ret = []
    for he in hes:
      ret.extend(self.get_hyperedge_targets(he))
    return ret
  
  def get_node_predecessors(self, node):
    hes = self.get_input_hyperedges(node)
    ret = []
    for he in hes:
      ret.extend(self.get_hyperedge_sources(he))
    return set(ret)
  
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
          for he in self.get_output_hyperedges(vtx):
            for he_dst in self.get_hyperedge_targets(he):
              # dep from vtx -> he_dst
              if not (vtx in nodes_to_merge and he_dst in nodes_to_merge):
                # Not an internal edge
                fringe_next.add(he_dst)
        
        if not fringe_next.isdisjoint(nodes_to_merge):
          # has intersection, we encounter an external edge
          # this merge is cyclic
          return False
        
        fringe = fringe_next
        fringe_next = set()

        current_level += 1


    return True

  
  def merge_nodes(self, to, from_list):
    edges_to_remove = []
    # 
    all_nodes = set([to, *from_list])
    from_set = set(from_list)
    assert(to not in from_set)
    assert(len(from_set) == len(from_list))

    from_list_input_hes = set()
    # from_list_output_hes = []
    all_node_output_hes = []

    for n in from_list:
      from_list_input_hes.update(self.get_input_hyperedges(n))

    for n in all_nodes:
      assert(self.graph.nodes[n]['type'] == 'node')
      output_hes = self.get_output_hyperedges(n)
      if len(output_hes) > 1:
        print(f"Node has {len(output_hes)} output hes")
      all_node_output_hes.extend(self.get_output_hyperedges(n))
    assert(len(all_node_output_hes) == len(set(all_node_output_hes)))
    assert(len(all_node_output_hes) <= len(all_nodes))


    # move input edges
    for he_id in from_list_input_hes:
      he_out = self.get_hyperedge_targets(he_id)
      for each_target in he_out:
        if each_target in from_set:
          # this edge should be moved to new target
          self.graph.remove_edge(he_id, each_target)
          if not self.graph.has_edge(he_id, to):
            self.graph.add_edge(he_id, to)

      assert self.graph.out_degree(he_id) != 0



    # move output edges
    all_nodes_successors = set()
    all_nodes_output_hes = set()
    for he_id in all_node_output_hes:
      he_src = self.get_hyperedge_sources(he_id)
      assert(len(he_src) == 1)
      assert(he_src[0] in all_nodes)
      all_nodes_successors.update(self.get_hyperedge_targets(he_id))
      # delete all old hyper edges
      # self.graph.remove_node(he_id)
      all_nodes_output_hes.add(he_id)
      # self.nodes_to_remove.add(he_id)
    
    if len(all_node_output_hes) != 0:

      # collect all targets
      new_he_targets = set()
      for he_id in all_node_output_hes:
        for et in self.get_hyperedge_targets(he_id):
          if et not in all_nodes:
            new_he_targets.add(et)

      # Remove old hyper edges
      self.nodes_to_remove.update(all_node_output_hes)
      for he in all_node_output_hes:
        for src in self.get_hyperedge_sources(he):
          edges_to_remove.append((src, he))
          # self.graph.remove_edge(src, he)
        for dst in self.get_hyperedge_targets(he):
          # self.graph.remove_edge(he, dst)
          edges_to_remove.append((he, dst))
      self.graph.remove_edges_from(edges_to_remove)

      if len(new_he_targets) != 0:
        # Need merge output edge
        # part_out_he_id = all_node_output_hes.pop()
        new_out_he_id = self.add_hyperedge(None, None)

        # add to -> new_he_id
        self.graph.add_edge(to, new_out_he_id)

        # add edges that connect all deps
        for et in new_he_targets:
          self.graph.add_edge(new_out_he_id, et)
      



    # remove possible empty hes
    # : Question: will this be executed?
    for he in from_list_input_hes:
      if self.graph.out_degree(he) == 0:
        # self.graph.remove_node(he)
        self.nodes_to_remove.add(he)


    # remove no longer used nodes
    for n in from_list:
      assert(all(map(lambda x: x in self.nodes_to_remove, self.graph.predecessors(n))))
      assert(all(map(lambda x: x in self.nodes_to_remove, self.graph.successors(n))))
      # assert(self.graph.out_degree(n) == 0 or n in self.nodes_to_remove)
      # self.graph.remove_node(n)
      self.nodes_to_remove.add(n)

    # assert(nx.is_directed_acyclic_graph(self.graph))

    # self.levels = []
    # self.node_to_level.clear()

  def graph_gc(self):
    # remove nodes together to speed up
    self.graph.remove_nodes_from(self.nodes_to_remove)
    self.nodes_to_remove.clear()

  def check_graph(self):
    assert(nx.is_directed_acyclic_graph(self.graph))

    for he in self.all_hyperedges():
      assert(self.graph.in_degree(he) == 1)
      assert(self.graph.out_degree(he) >= 1)

  def levelize(self):
    self.levels = []
    self.node_to_level.clear()

    level_id = 0
    for topo_level_id, nodes in enumerate(nx.topological_generations(self.graph)):
      node_types = set()
      for n in nodes:
        node_types.add(self.graph.nodes[n]['type'])
      assert(len(node_types) == 1)
    
      if 'node' in node_types:
        assert(topo_level_id == level_id * 2)
        self.levels.append(nodes)
        for n in nodes:
          assert(n not in self.node_to_level)
          self.node_to_level[n] = level_id
        level_id += 1
  
  # @property
  def all_nodes(self):
    return [n for n in self.graph.nodes 
            if self.graph.nodes[n]['type'] == 'node']
  
  # @property
  def all_hyperedges(self):
    return [n for n in self.graph.nodes 
            if self.graph.nodes[n]['type'] == 'hyperedge']
  

