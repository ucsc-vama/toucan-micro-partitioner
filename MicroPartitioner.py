import argparse

import ToucanGraph
import Utils

import MergeGraph
import statistics


import networkx as nx

DEBUG = True


valid_node_tags = set([
  "ConstDecl",
  "RegRead",
  "MemRead",
  "VecDecl",
  "VecDecl_LUT_NOP",
  "VecRead",
  "LUT",
  "VecArith",
  "VecLogic",
  "Print",
  "Stop",
  "RegWrite",
  "MemWrite"
])

exclude_node_tags = set([
  "ConstDecl",
  "RegRead",
  "MemRead",
  "VecDecl",
  # "VecDecl_LUT_NOP",
  "VecRead",
  # "LUT",
  "VecArith",
  "VecLogic",
  "Print",
  "Stop",
  "RegWrite",
  "MemWrite"
])
# exclude_node_tags = ['VecRead', 'VecOp', 'VecDecl', "MemRead", "MemWrite"]

group_node_tags = []

def find_exclude_nodes(g: nx.DiGraph):

  ret = []
  for node, attrs in g.nodes(data=True):
    tagValue = attrs.get("label")

    # Note: tagValue could be None for inserted dummy nodes
    # assert(tagValue is not None)

    if tagValue in exclude_node_tags:
      ret.append(node)

    if tagValue not in valid_node_tags:
      print(tagValue)
    assert(tagValue in valid_node_tags)
  return set(ret)
  
 
def print_part_and_level(g, part):
  p = {}
  for n in part:
    level = g.nodes[n]['level_id']
    assert level is not None
    if level not in p.keys():
      p[level] = []
    p[level].append(n)

  for k in sorted(p.keys()):
    v = map(lambda x: str(x), p[k])
    print(f"Level {k}: {" ".join(v)}")
  

def report_part_info(parts):
  ret = {}

  for p in parts:
    part_size = len(p.nodes)

    if part_size in ret.keys():
      ret[part_size] += 1
    else:
      ret[part_size] = 1

  for k in sorted(ret.keys()):
    print(f"Part size {k}: {ret[k]}")

  ret = {}

  for p in parts:

    part_depth = len(p.levels)

    if part_depth in ret.keys():
      ret[part_depth] += 1
    else:
      ret[part_depth] = 1

  for k in sorted(ret.keys()):
    print(f"Part depth {k}: {ret[k]}")

  avg_depth = sum([k * v for k, v in ret.items()]) / len(parts)
  print(f"Avg depth {avg_depth} of {len(parts)} parts")










GPU_WARP_SIZE = 32
PART_MAX_LEVEL = 9999






class MicroPartition:
  def __init__(self, G, excluded_nodes=None):
    self.G = G

    self.excluded_nodes = excluded_nodes if excluded_nodes else set()
    self.nodes = set()
    self.levels = []
    self.node_levels = {}

    self.var_life_cycle = {}

    self.max_live_vars = None
    self.num_input_vars = None
    self.num_output_vars = None

    # self.input_nodes = set()
    # self.output_nodes = set()
    # self.input_edges_src = set()
    # self.output_edges_src = set()

  def copy(self):
    new_part = MicroPartition(self.G, self.excluded_nodes)
    new_part.nodes = self.nodes.copy()
    new_part.levels = self.levels.copy()
    new_part.node_levels = self.node_levels.copy()

    new_part.var_life_cycle = self.var_life_cycle.copy()

    new_part.max_live_vars = self.max_live_vars

    # new_part.input_nodes = self.input_nodes.copy()
    # new_part.input_edges = self.input_edges
    # new_part.output_nodes = self.output_nodes.copy()
    # new_part.output_edges = self.output_edges
    return new_part

  def _calculate_node_level(self):
    for p in self.nodes:
      assert(p not in self.excluded_nodes)
      assert(p in self.g.nodes())


    if not nx.is_directed_acyclic_graph(self.g):
      raise ValueError("The graph must be a Directed Acyclic Graph (DAG) to levelize.")

    # Compute the levels using topological sorting
    self.levels = []
    self.node_levels = {}
    for level_id, ns in enumerate(nx.topological_generations(self.g)):
      assert(level_id < PART_MAX_LEVEL)
      self.levels.append(list(ns))
      for n in ns:
        self.node_levels[n] = level_id


  def _collect_variable_liveness(self):
    # Must run after levelize
    assert(len(self.levels) != 0)

    # variable: [life_start, life_end)
    self.var_life_cycle = {}


    for node in self.nodes:
      life_start = self.node_levels[node]
      life_end = life_start

      for s in self.G.successors(node):
        if s not in self.nodes:
          # this edge points to outside of the part
          life_end = PART_MAX_LEVEL
        else:
          assert(self.node_levels[s] > life_start)
          life_end = max(life_end, self.node_levels[s])
      
      if life_start != life_end:
        if node not in self.var_life_cycle:
          self.var_life_cycle[node] = (life_start, life_end)
        else:
          # an existing var
          old_start, old_end = self.var_life_cycle[node]
          assert(old_start == life_start)
          self.var_life_cycle[node] = (life_start, max(old_end, life_end))
      else:
        # a sink node. Doesn't produce value. ignore
        pass
    
    # some input might coming from outside
    for node in self.nodes:

      for p in self.G.predecessors(node):
        if p in self.nodes:
          assert(p in self.var_life_cycle)
        else:
          # an external edge
          life_start = -1
          life_end = self.node_levels[node]

          # save
          if p in self.var_life_cycle:
            # used some where
            old_life_end = self.var_life_cycle[p][1]
            self.var_life_cycle[p] = (life_start, max(life_end, old_life_end))
          else:
            self.var_life_cycle[p] = (life_start, life_end)


  def _check_liveness_constraint(self):
    # At any time, live values should not exceed GPU_WARP_SIZE
    assert(len(self.var_life_cycle) != 0)
    # if len(self.var_life_cycle) == 0:
    #   # It's possible that node have either no input and no output
    #   for n in self.nodes:
    #     print(self.G.nodes[n])
    #     assert(self.G.in_degree(n) == 0 and self.G.out_degree(n) == 0)
    #   self.max_live_vars = 1
    #   return True
    


    level_var_acive = {}
    level_var_deactive = {}

    for v, (life_start, life_end) in self.var_life_cycle.items():
      if life_start not in level_var_acive:
        level_var_acive[life_start] = set()
      assert(v not in level_var_acive[life_start])
      level_var_acive[life_start].add(v)


      if life_end not in level_var_deactive:
        level_var_deactive[life_end] = set()
      assert(v not in level_var_deactive[life_end])
      level_var_deactive[life_end].add(v)



    # external vars
    current_live_vars = set()
    if -1 in level_var_acive:
      current_live_vars.update(level_var_acive[-1])
      assert(len(current_live_vars) != 0)

    # print(f"checking liveness\nexternal input edge source: {str(current_live_vars)}")
    self.max_live_vars = len(current_live_vars)
    self.num_input_vars = len(current_live_vars)

    for level in range(0, len(self.levels)):

      # print(f"Level {level}")

      self.max_live_vars = max(len(current_live_vars), self.max_live_vars)

      if len(current_live_vars) > GPU_WARP_SIZE:
        # print("Hit contraint. Stop")
        return False
      
      if level in level_var_deactive:
        # those variables will die during this level
        # print(f"deactive var {str(level_var_deactive[level])}")
        for e in level_var_deactive[level]:
          assert(e in current_live_vars)
          current_live_vars.remove(e)
      if level in level_var_acive:
        # new result vales
        # print(f"activate var {str(level_var_acive[level])}")
        for e in level_var_acive[level]:
          assert(e not in current_live_vars)
          current_live_vars.add(e)
    
    if PART_MAX_LEVEL in level_var_deactive:
      for e in level_var_deactive[PART_MAX_LEVEL]:
        assert(e in current_live_vars)
      assert(len(current_live_vars) == len(level_var_deactive[PART_MAX_LEVEL]))
    else:
      assert(len(current_live_vars) == 0)

    self.num_output_vars = len(current_live_vars)    
    self.max_live_vars = max(len(current_live_vars), self.max_live_vars)
    if len(current_live_vars) > GPU_WARP_SIZE:
      return False
    
    return True

  def check_correctness(self):
    self.g = self.G.subgraph(self.nodes)
    self._calculate_node_level()
    self._collect_variable_liveness()
    good = self._check_liveness_constraint()

    return good

  def try_add_nodes(self, new_nodes):
    # return success or not
    # will destroy if failed!

    for n in new_nodes:
      assert(n not in self.excluded_nodes)

    self.nodes.update(new_nodes)

    return self.check_correctness()

    

def partitioner2(G, excluded_nodes: set):

  G.levelize()
  g = G.graph

  partitions = []
  visited = set()

  visited.update(exclude_nodes)

  # sinks = [n for n in G.nodes 
  #         if G.out_degree(n) == 0 
  #         and n not in excluded_nodes]
  # seeds = sorted(sinks, key=lambda x: G.nodes[x].get("level_id", 0), reverse=True)

  topo_order = list(nx.topological_sort(g))

  for seed in reversed(topo_order):
    if seed in visited:
      continue

    seed_in_degree = len(g.in_edges(seed))
    seed_opname = g.nodes[seed]['label']
    node_should_exclude = seed_in_degree > 3
    if node_should_exclude:
      print(f"Node {seed} has more than 3 inputs. This node is a {seed_opname}")
    assert(not node_should_exclude)


    part = MicroPartition(g, excluded_nodes)

    succ = part.try_add_nodes(set({seed}))
    assert(succ)



    mffc_fringe = set(g.predecessors(seed))
    mffc_fringe_next = set()

    last_level = g.nodes[seed]['level_id']
    assert(last_level is not None)



    while (len(mffc_fringe) != 0):

      mffc_nodes = []
      for eachVtx in mffc_fringe:
        if all((w in part.nodes) for w in g.successors(eachVtx)) and eachVtx not in visited:
          mffc_nodes.append(eachVtx)
      assert(len(mffc_nodes) == len(set(mffc_nodes)))
      # print(f"Found {len(mffc_nodes)} MFFC nodes for next iter")

      if len(mffc_nodes) == 0:
        break

      # find all nodes that has level distance of 1. they are noew nodes to be added into this part
      part_candidates = set()
      mffc_max_level = max(map(lambda x: g.nodes[x]['level_id'], mffc_nodes))
      if mffc_max_level + 1 != last_level:
        # in this case, next fringe depends on values that are also shared with other cones.
        # simply stop
        # print("Done")
        break
      for eachVtx in mffc_nodes:
        level = g.nodes[eachVtx]['level_id']
        assert(level < last_level)
        if level + 1 == last_level:
          part_candidates.add(eachVtx)
      # print(f"Found {len(part_candidates)} part candidates in level {last_level - 1}")


      # assert(len(part_candidates) != 0)
      if len(part_candidates) == 0:
        # does it means completed?
        assert(len(mffc_nodes) == 0)
        # print("Done since no predecessors")
        break

      part_backup = part.copy()

      good_to_add = part.try_add_nodes(part_candidates)

      if not good_to_add:
        # stop
        part = part_backup
        break


      mffc_fringe_next = mffc_fringe.difference(part_candidates)

      # mffc_fringe_next = mffc_fringe.difference(part)
      for eachVtx in part_candidates:
        for es in g.predecessors(eachVtx):
          mffc_fringe_next.add(es)
      mffc_fringe = mffc_fringe_next

      assert(last_level != 0)
      last_level -= 1

    assert(part.check_correctness())
    assert(part.max_live_vars is not None)
    partitions.append(part)

    visited.update(part.nodes)

  return partitions









class PartitionMerger:
  def __init__(self, G, exclude_nodes):
    self.mg = None
    self.G = G
    self.g = G.graph
    self.exclude_nodes = exclude_nodes

    self.exclude_part_ids = set()
    self.node_id_to_part = {}



  def build_part_mg(self, parts):
    mg = MergeGraph.MergeGraph()

    # add nodes for all parts
    for i, p in enumerate(parts):
      part_id = mg.add_node()
      assert(part_id == i)
      self.node_id_to_part[part_id] = p

    # add exclude parts
    for n in self.exclude_nodes:
      part_id = mg.add_node()

      self.exclude_part_ids.add(part_id)
      self.node_id_to_part[part_id] = set({n})



    # map from node_id to part_id. exclude_nodes are considered as a single part and cannot be merged for now

    node_id_to_part_id = {}
    for part_id, part in self.node_id_to_part.items():
      if isinstance(part, MicroPartition):
        # a regular part
        assert(part_id not in self.exclude_part_ids)

        for n in part.nodes:
          assert(n not in node_id_to_part_id)
          node_id_to_part_id[n] = part_id
      else:
        assert(isinstance(part, set))
        assert(part_id in self.exclude_part_ids)
        assert(len(part) == 1)

        for n in part:
          assert(n not in node_id_to_part_id)
          node_id_to_part_id[n] = part_id
    
    # build edges
    for part_id, part in self.node_id_to_part.items():
      part_output_edges = []

      if isinstance(part, MicroPartition):
        for n in part.nodes:
          for out_edge in self.g.out_edges(n):
            src, dst = out_edge
            if dst not in part.nodes:
              # an edge that points to outside current part
              part_output_edges.append(out_edge)
      else:
        for n in part:
          for out_edge in self.g.out_edges(n):
            src, dst = out_edge
            if dst not in part:
              # an edge that points to outside current part
              part_output_edges.append(out_edge)

      new_edges = []
      for eachEdge in part_output_edges:
        src, dst = eachEdge
        src_part_id = node_id_to_part_id[src]
        dst_part_id = node_id_to_part_id[dst]
        assert(src_part_id == part_id)
        new_edges.append((src_part_id, dst_part_id))

      mg.add_edges(new_edges)


    self.mg = mg


  def print_part_stat(self):
    self.mg.levelize()

    max_levels = len(self.mg.levels)
    
    norm_part_size = []
    norm_part_depth = []
    norm_part_inputs = []
    norm_part_outputs = []
    norm_part_active_vars = []
    special_part_size = []
    special_part_depth = []

    for pid, part in self.node_id_to_part.items():
      if pid in self.exclude_part_ids:
        special_part_size.append(len(part))
        special_part_depth.append(1)
      else:
        norm_part_size.append(len(part.nodes))
        norm_part_depth.append(len(part.levels))
        norm_part_inputs.append(part.num_input_vars)
        norm_part_outputs.append(part.num_output_vars)
        norm_part_active_vars.append(part.max_live_vars)

    print(f"Part graph has {max_levels} levels")
    print(f"Has {len(norm_part_size)} normal parts:")
    print(f"size: mean {statistics.mean(norm_part_size):.2f}, min {min(norm_part_size)}, max {max(norm_part_size)}, median {statistics.median(norm_part_size)}")
    print(f"depth: mean {statistics.mean(norm_part_depth):.2f}, min {min(norm_part_depth)}, max {max(norm_part_depth)}, median {statistics.median(norm_part_depth)}")
    print(f"input vars: mean {statistics.mean(norm_part_inputs):.2f}, min {min(norm_part_inputs)}, max {max(norm_part_inputs)}, median {statistics.median(norm_part_inputs)}")
    print(f"output vars: mean {statistics.mean(norm_part_outputs):.2f}, min {min(norm_part_outputs)}, max {max(norm_part_outputs)}, median {statistics.median(norm_part_outputs)}")
    print(f"max live vars: mean {statistics.mean(norm_part_active_vars):.2f}, min {min(norm_part_active_vars)}, max {max(norm_part_active_vars)}, median {statistics.median(norm_part_active_vars)}")

    print(f"Has {len(special_part_size)} special (vector) parts, size: mean {statistics.mean(special_part_size):.2f}, min {min(special_part_size)}, max {max(special_part_size)}, median {statistics.median(special_part_size)}, depth: mean {statistics.mean(special_part_depth):.2f}, min {min(special_part_depth)}, max {max(special_part_depth)}, median {statistics.median(special_part_depth)}")


  def try_merge_upart_nodes(self, to, from_nodes, check_acyclic = False):
    all_nodes = set([to, *from_nodes])

    if check_acyclic:
      is_acyclic = self.mg.merge_is_acyclic(all_nodes)
      if not is_acyclic:
        return False
    else:
      assert(self.mg.merge_is_acyclic(all_nodes))

    for n in all_nodes:
      assert(n in self.node_id_to_part)
      assert(n in self.mg.graph.nodes())
      assert(n not in self.exclude_part_ids)
      assert(isinstance(self.node_id_to_part[n], MicroPartition))

    new_part = self.node_id_to_part[to].copy()
    new_nodes = set()
    for n in from_nodes:
      from_part = self.node_id_to_part[n]
      new_nodes.update(from_part.nodes)

    assert(len(new_nodes) != 0)
    good_to_merge = new_part.try_add_nodes(new_nodes)

    if not good_to_merge:
      return False
    

    # ok to merge
    self.node_id_to_part[to] = new_part


    self.mg.merge_nodes(to, from_nodes)

    for n in from_nodes:
      del self.node_id_to_part[n]
      # assert(n not in self.mg.graph.nodes())

    return True


  def check_mg(self):
    for n in self.mg.graph.nodes():
      if isinstance(self.node_id_to_part[n], MicroPartition):
        assert(self.node_id_to_part[n].max_live_vars is not None)

    self.mg.check_graph()

  def merge_direct_child(self):

    self.check_mg()

    merge_cnt = 0

    merge_queue = []

    # for he in self.mg.all_hyperedges():
    for n in self.mg.graph.nodes():
      merge_to = n
      merge_froms = list(self.mg.get_node_successors(n))


      if merge_to in self.exclude_part_ids:
        continue

      # TODO: Remove this?
      if len(merge_froms) != 1:
        continue


      if len(merge_froms) == 0:
        continue


      merge_from = merge_froms[0]
      merge_to_level = self.mg.node_to_level[merge_to]
      merge_from_level = self.mg.node_to_level[merge_from]

      if merge_from in self.exclude_part_ids:
        continue

      if merge_from_level != merge_to_level + 1:
        # unnecessary and may cause cycle
        continue

      # can be considered to merge
      merge_queue.append((merge_to, merge_from))

    # merge parts from small child to large
    merge_queue.sort(key = lambda pids: len(self.node_id_to_part[pids[1]].nodes))
    # merge parts from longest path
    merge_queue.sort(key = lambda pids: self.mg.node_to_level[pids[1]], reverse=True)

    print(f" {len(merge_queue)} pending merges")
    for pa, pb in merge_queue:
      # merge if both part has not been merged
      if pa in self.node_id_to_part and pb in self.node_id_to_part:
        # merge or fail. No partial merge
        merge_ok = self.try_merge_upart_nodes(pa, [pb])
        if merge_ok:
          merge_cnt += 1
    self.mg.graph_gc()


    assert(len(self.node_id_to_part) == len(self.mg.graph.nodes()))
    self.mg.check_graph()

    return merge_cnt


  def merge_adjacent_group(self):
    self.check_mg()

    total_merge_cnt = 0


    iter_start_level = 0

    while len(self.mg.levels) > iter_start_level + 1:
      merge_cnt = 0


      level_id = iter_start_level
      level_nodes = self.mg.levels[level_id]



      nodes_visited = set()
      merge_queue = []

      for each_node in level_nodes:
        if each_node in nodes_visited or each_node in self.exclude_part_ids:
          continue

        childs = self.mg.get_node_successors(each_node)
        childs_next_level = set(filter(lambda x: self.mg.node_to_level[x] == level_id + 1, childs))

        if len(childs_next_level) == 0:
          continue

        child_all_predecessors = set()
        for c in childs_next_level:
          child_all_predecessors.update(self.mg.get_node_predecessors(c))
        
        child_all_predecessors_this_level = set(filter(lambda x: self.mg.node_to_level[x] == level_id, child_all_predecessors))
        
        assert(len(child_all_predecessors_this_level) != 0)
        assert(each_node in child_all_predecessors_this_level)

        # nodes if merge. Even they cannot be merged, they don't need to be visited again
        new_part_vtxes = set()
        new_part_vtxes.update(childs_next_level)
        new_part_vtxes.update(child_all_predecessors_this_level)
        nodes_visited.update(new_part_vtxes)


        if not new_part_vtxes.isdisjoint(self.exclude_part_ids):
          continue

        new_part_vtxes.remove(each_node)
        merge_queue.append((each_node, new_part_vtxes))

      # print(len(merge_queue))

      for pa, pbs in merge_queue:
        # merge if all parts has not been merged
        if pa in self.node_id_to_part and all(map(lambda x: x in self.node_id_to_part, pbs)):
          # assert(self.exclude_part_ids == exclude_part_ids_old)
          assert(pa not in self.exclude_part_ids)
          assert(pbs.isdisjoint(self.exclude_part_ids))
          # Note: This merge is acyclic
          merge_ok = self.try_merge_upart_nodes(pa, pbs, False)
          if merge_ok:
            merge_cnt += 1

      self.mg.graph_gc()
      self.mg.levelize()


      if merge_cnt == 0:
        # nothing to do for this level. go to next
        iter_start_level += 1
        # print(f"Go to level {iter_start_level}")
      else:
        # stay in this level
        total_merge_cnt += merge_cnt
        # print(f"Merged {merge_cnt} times. Keep working on level {iter_start_level}")
    return total_merge_cnt


  def merge_siblings(self):

    self.check_mg()


    merge_queue = []

    total_merge_cnt = 0

    current_level = 0

    nodes_no_feasible_merge = set()

    while len(self.mg.levels) > current_level + 1:
      merge_cnt = 0

      for n in self.mg.levels[current_level]:
        if n in nodes_no_feasible_merge:
          continue

        successors = list(filter(lambda x: x not in self.exclude_part_ids and self.mg.node_to_level[x] == current_level + 1, self.mg.get_node_successors(n)))

        successors.sort(key = lambda x: self.node_id_to_part[x].max_live_vars)


        if len(successors) < 2:
          nodes_no_feasible_merge.add(n)
          continue

        successors_live_vars = list(map(lambda x: self.node_id_to_part[x].max_live_vars, successors))
        while len(successors) > 1:
          # pop largest parts until it's possible to merge
          total_live_vars = sum(successors_live_vars)
          if total_live_vars <= 32:
            break
          else:
            #unlikely mergeable
            successors.pop()
            successors_live_vars.pop()

        if len(successors) <= 2:
          nodes_no_feasible_merge.add(n)
          continue

        while len(successors) >= 2:
          to = successors[0]
          from_nodes = set(successors[1:])
          succ = self.try_merge_upart_nodes(to, from_nodes, True)

          if succ:
            # self.mg.graph_gc()
            # self.mg.levelize()
            # self.mg.check_graph()
            # print(f"Succesfully merge {len(successors)} nodes")
            merge_cnt += 1
            break
          else:
            successors.pop()
      
      if merge_cnt != 0:
        # print(f"Level {current_level} merged {merge_cnt} groups")
        total_merge_cnt += merge_cnt
      else:
        current_level += 1
        nodes_no_feasible_merge.clear()
        # print(f"Move to level {current_level}")

        self.mg.graph_gc()
        self.mg.levelize()
    return total_merge_cnt
  

  def merge_same_level(self):
    self.check_mg()


    total_merge_cnt = 0

    current_level = 0

    # nodes_no_feasible_merge = set()

    while len(self.mg.levels) > current_level + 1:
      merge_cnt = 0


      nodes_valid = list(filter(lambda x: x in self.node_id_to_part and x not in self.exclude_part_ids, self.mg.levels[current_level]))

      for n in nodes_valid:
        if not isinstance(self.node_id_to_part[n], MicroPartition):
          print(self.node_id_to_part[n].__class__.__name__)
          assert(False)

      nodes_to_consider = list(filter(lambda x: self.node_id_to_part[x].max_live_vars < 32, nodes_valid))

      nodes_to_consider.sort(key = lambda x: self.node_id_to_part[x].max_live_vars)


      while len(nodes_to_consider) > 1:
        # pick largest
        largest_node_id = nodes_to_consider[-1]
        smallest_node_id = nodes_to_consider[0]

        succ = self.try_merge_upart_nodes(largest_node_id, [smallest_node_id], False)
        if succ:
          merge_cnt += 1
          nodes_to_consider.remove(smallest_node_id)
        else:
          nodes_to_consider.pop()
        
      
      if merge_cnt != 0:
        # print(f"Level {current_level} merged {merge_cnt} groups")
        total_merge_cnt += merge_cnt
      else:
        current_level += 1
        # print(f"Move to level {current_level}")

        self.mg.graph_gc()
        self.mg.levelize()
    return total_merge_cnt
  
  def save(self, filename: str):
    self.mg.levelize()

    with open(filename, 'w') as out:
      for level_id, level_nodes in enumerate(self.mg.levels):
        # L: level
        out.write(f"L {level_id}\n")

        current_level_exclude_nodes = []

        for pid in level_nodes:
          part = self.node_id_to_part[pid]
          if pid in self.exclude_part_ids:
            # part is a set
            assert(len(part) == 1)
            # e: exclude part
            current_level_exclude_nodes.append(part.pop())
          else:
            # n: normal part
            assert(len(part.nodes) > 0)
            assert(len(part.levels) > 0)
            assert(sum(map(lambda x: len(x), part.levels)) == len(part.nodes))
            # new normal part
            out.write('n')
            for eachLevel in part.levels:
              assert(len(eachLevel) > 0)
              # Use letter 'l' as seperator for each level
              out.write(' l ' + ' '.join(map(lambda x: str(x), eachLevel)))
            out.write(f"\n")
        # save exclude nodes if exists
        if len(current_level_exclude_nodes) > 0:
          out.write(f"e {' '.join(map(lambda x: str(x), current_level_exclude_nodes))}\n")





def parse_args():
  parser = argparse.ArgumentParser(description="Micro partitioner for toucan.")
  parser.add_argument('--graph', required=True, type=str, help='Input graph file name')
  parser.add_argument('--vector', required=True, type=str, help="Input Vector info")
  parser.add_argument('--output', required=True, type=str, help='Output file name')
  parser.add_argument('--vecmap', required=True, type=str, help='Output vector mapping file name')
  return parser.parse_args()

def load_vec_info_file(filename):
  ret = {}
  with open(filename) as f:
    for lineno, line in enumerate(f):
      if lineno < 2:
        continue
      dat = list(map(lambda x: int(x), line.strip().split(' ')))
      # a vector should have more than 1 elements

      assert(len(dat) >= 2)
      vecDecl_node_id = dat[0]
      vecElem_ids = dat[1:]
      assert(vecDecl_node_id not in ret)
      ret[vecDecl_node_id] = vecElem_ids
  return ret




if __name__ == "__main__":
  import time

  args = parse_args()

  vecDeclElementsInfo = load_vec_info_file(args.vector)

  g = ToucanGraph.ToucanGraph()
  g.load(args.graph)
  g.expand_VecDecl(vecDeclElementsInfo)
  g.remove_ConstDecl()
  g.save_vector_def_info(args.vecmap)
  # exit()



  exclude_nodes = find_exclude_nodes(g.graph)
  print(f"{len(exclude_nodes)} nodes need to be excluded")
  
  print("> partitioning")
  parts = partitioner2(g, exclude_nodes)
  print(f"Found {len(parts)} partitions")



  # report_part_info(parts)

  Utils.print_memory_usage()


  print("> Working on merge")

  merger = PartitionMerger(g, exclude_nodes)

  print("> Build part graph after initial partitioning")
  merger.build_part_mg(parts)

  merger.print_part_stat()

  print("> Merge with child")

  merge_cnt = merger.merge_direct_child()

  print(f"Merged {merge_cnt} parts")

  # re levelize
  merger.mg.levelize()
  
  merger.print_part_stat()

  while True:
    print("> Merge with child")
    merge_cnt = merger.merge_direct_child()
    print(f"Merged {merge_cnt} parts")

    # re levelize
    merger.mg.levelize()
    if merge_cnt < 10:
      break

  merger.print_part_stat()



  while True:
    print("> Merge adjacent groups")
    merge_cnt = merger.merge_adjacent_group()
    print(f"{merge_cnt} merge ops")

    # re levelize
    merger.mg.levelize()
    if merge_cnt == 0:
      break

  merger.print_part_stat()




  while True:
    print("> Merge siblings")
    merge_cnt = merger.merge_siblings()
    print(f"{merge_cnt} merge ops")

    # re levelize
    merger.mg.levelize()
    if merge_cnt == 0:
      break

  merger.print_part_stat()



  while True:
    print("> Merge with child2")
    merge_cnt = merger.merge_direct_child()
    print(f"Merged {merge_cnt} parts")

    # re levelize
    merger.mg.levelize()
    if merge_cnt < 10:
      break

  merger.print_part_stat()

  while True:
    print("> Merge adjacent groups2")
    merge_cnt = merger.merge_adjacent_group()
    print(f"{merge_cnt} merge ops")

    # re levelize
    merger.mg.levelize()
    if merge_cnt == 0:
      break

  merger.print_part_stat()

  while True:
    print("> Merge siblings")
    merge_cnt = merger.merge_siblings()
    print(f"{merge_cnt} merge ops")

    # re levelize
    merger.mg.levelize()
    if merge_cnt == 0:
      break

  merger.print_part_stat()

  while True:
    print("> Merge same level")
    merge_cnt = merger.merge_same_level()
    print(f"{merge_cnt} merge ops")

    # re levelize
    merger.mg.levelize()
    if merge_cnt == 0:
      break

  merger.print_part_stat()

  print("> Done")

  merger.save(args.output)
  Utils.print_memory_usage()