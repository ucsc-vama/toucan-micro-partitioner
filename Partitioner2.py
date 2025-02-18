
import ToucanGraph
import MergeAddMul
import Utils

import HyperGraph
import statistics


import networkx as nx
import copy

DEBUG = True


def find_exclude_nodes(g: nx.DiGraph):
  exclude_node_tags = ['VecRead', 'VecOp', 'VecDecl', "MemRead", "MemWrite"]

  error_node_tags = ["ConstDecl"]

  ret = []
  for node, attrs in g.nodes(data=True):
    tagValue = attrs.get("op_name")

    # Note: tagValue could be None for inserted dummy nodes
    # assert(tagValue is not None)

    if tagValue in exclude_node_tags:
      ret.append(node)

    assert(tagValue not in error_node_tags)
  return ret
  
 
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






from collections import defaultdict

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
    seed_opname = g.nodes[seed]['op_name']
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
    self.hg = None
    self.G = G
    self.g = G.graph
    self.exclude_nodes = exclude_nodes

    self.exclude_part_ids = set()
    self.node_id_to_part = {}



  def build_part_hg(self, parts):
    hg = HyperGraph.DirectedHyperGraph()

    # add nodes for all parts
    for i, p in enumerate(parts):
      part_id = hg.add_node()
      assert(part_id == i)
      self.node_id_to_part[part_id] = p

    # add exclude parts
    for n in self.exclude_nodes:
      part_id = hg.add_node()

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
    
    # build hyper edges
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

      new_he = {}
      for eachEdge in part_output_edges:
        src, dst = eachEdge
        srcPart = node_id_to_part_id[src]
        dstPart = node_id_to_part_id[dst]
        if srcPart not in new_he:
          new_he[srcPart] = set()
        new_he[srcPart].add(dstPart)
      
      # We only need the dep relationship. Each he only represents dependency exists
      # thus a part should only produce at most 1 hyperedge
      assert(len(new_he) <= 1)

      for src, dsts in new_he.items():
        # print(f"Add he from {src} to {str(dsts)}")
        hg.add_hyperedge(src, dsts)

    self.hg = hg


  def print_part_stat(self):
    self.hg.levelize()

    max_levels = len(self.hg.levels)
    
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
      is_acyclic = self.hg.merge_is_acyclic(all_nodes)
      if not is_acyclic:
        return False
    else:
      assert(self.hg.merge_is_acyclic(all_nodes))

    for n in all_nodes:
      assert(n in self.node_id_to_part)
      assert(n in self.hg.graph.nodes())
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


    self.hg.merge_nodes(to, from_nodes)

    for n in from_nodes:
      del self.node_id_to_part[n]
      # assert(n not in self.hg.graph.nodes())

    return True



  def check_hg(self):
    for n in self.hg.all_nodes():
      assert(self.hg.graph.out_degree(n) <= 1)
      if isinstance(self.node_id_to_part[n], MicroPartition):
        assert(self.node_id_to_part[n].max_live_vars is not None)

    for he in self.hg.all_hyperedges():
      assert(len(self.hg.get_hyperedge_sources(he)) == 1)

  def merge_direct_child(self):

    self.check_hg()

    merge_cnt = 0

    merge_queue = []

    for he in self.hg.all_hyperedges():
      # each hyper edge
      he_src = self.hg.get_hyperedge_sources(he)
      he_dsts = self.hg.get_hyperedge_targets(he)

      assert(len(he_src) == 1)
      assert(len(he_dsts) != 0)
      he_src = he_src[0]

      if he_src in self.exclude_part_ids:
        continue


      # for he_dst in he_dsts:
      if len(he_dsts) != 1:
        continue

      he_dst = he_dsts[0]
      he_src_level = self.hg.node_to_level[he_src]
      he_dst_level = self.hg.node_to_level[he_dst]

      if he_dst in self.exclude_part_ids:
        continue

      if he_dst_level != he_src_level + 1:
        # unnecessary and may cause cycle
        continue

      # can be considered to merge
      merge_queue.append((he_src, he_dst))

    # merge parts from small child to large
    merge_queue.sort(key = lambda pids: len(self.node_id_to_part[pids[1]].nodes))
    # merge parts from longest path
    merge_queue.sort(key = lambda pids: self.hg.node_to_level[pids[1]], reverse=True)

    print(f" {len(merge_queue)} pending merges")
    for pa, pb in merge_queue:
      # merge if both part has not been merged
      if pa in self.node_id_to_part and pb in self.node_id_to_part:
        merge_ok = self.try_merge_upart_nodes(pa, [pb])
        if merge_ok:
          merge_cnt += 1
    self.hg.graph_gc()


    assert(len(self.node_id_to_part) == len(self.hg.all_nodes()))
    self.hg.check_graph()

    return merge_cnt


  def merge_direct_childs(self):

    self.check_hg()

    merge_cnt = 0

    merge_queue = []

    for he in self.hg.all_hyperedges():
      # each hyper edge
      he_src = self.hg.get_hyperedge_sources(he)
      he_dsts = self.hg.get_hyperedge_targets(he)

      assert(len(he_src) == 1)
      assert(len(he_dsts) != 0)
      he_src = he_src[0]

      if he_src in self.exclude_part_ids:
        continue

      if True in set(map(lambda x: x in self.exclude_part_ids, he_dsts)):
        continue


      # for he_dst in he_dsts:
      if len(he_dsts) != 1:
        continue


      he_src_level = self.hg.node_to_level[he_src]
      he_dsts_levels = list(map(lambda x: self.hg.node_to_level[x], he_dsts))

      if not all(map(lambda x: x == he_src_level + 1, he_dsts_levels)):
        continue

      # can be considered to merge
      merge_queue.append((he_src, he_dsts))

    # try merge more parts
    merge_queue.sort(key = lambda pids: len(pids[1]))
    # merge parts from longest path
    merge_queue.sort(key = lambda pids: self.hg.node_to_level[pids[0]], reverse=True)

    print(f" {len(merge_queue)} pending merges")
    for pa, pbs in merge_queue:
      # merge if all parts has not been merged
      if pa in self.node_id_to_part and all(map(lambda x: x in self.node_id_to_part, pbs)):
        merge_ok = self.try_merge_upart_nodes(pa, pbs)
        if merge_ok:
          merge_cnt += 1
    self.hg.graph_gc()


    assert(len(self.node_id_to_part) == len(self.hg.all_nodes()))
    self.hg.check_graph()

    return merge_cnt
  

  def merge_adjacent_group_2(self):
    self.check_hg()

    total_merge_cnt = 0


    iter_start_level = 0

    while len(self.hg.levels) > iter_start_level + 1:
      merge_cnt = 0


      level_id = iter_start_level
      level_nodes = self.hg.levels[level_id]



      nodes_visited = set()
      merge_queue = []

      for each_node in level_nodes:
        if each_node in nodes_visited or each_node in self.exclude_part_ids:
          continue

        childs = self.hg.get_node_successors(each_node)
        childs_next_level = set(filter(lambda x: self.hg.node_to_level[x] == level_id + 1, childs))

        if len(childs_next_level) == 0:
          continue

        child_all_predecessors = set()
        for c in childs_next_level:
          child_all_predecessors.update(self.hg.get_node_predecessors(c))
        
        child_all_predecessors_this_level = set(filter(lambda x: self.hg.node_to_level[x] == level_id, child_all_predecessors))
        
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

      self.hg.graph_gc()
      self.hg.levelize()


      if merge_cnt == 0:
        # nothing to do for this level. go to next
        iter_start_level += 1
        # print(f"Go to level {iter_start_level}")
      else:
        # stay in this level
        total_merge_cnt += merge_cnt
        # print(f"Merged {merge_cnt} times. Keep working on level {iter_start_level}")
    return total_merge_cnt



  def merge_adjacent_group(self):

    self.check_hg()

    merge_cnt = 0

    merge_queue = []


    assert(len(self.hg.levels) != 0)

    for level_id, level_nodes in enumerate(self.hg.levels):
      # merge each level to next level
      # if level_id % 2 == 1:
      #   continue

      nodes_visited = set()

      for each_node in level_nodes:
        if each_node in nodes_visited or each_node in self.exclude_part_ids:
          continue

        childs = self.hg.get_node_successors(each_node)
        childs_next_level = set(filter(lambda x: self.hg.node_to_level[x] == level_id + 1, childs))

        if len(childs_next_level) == 0:
          continue

        child_all_predecessors = set()
        for c in childs_next_level:
          child_all_predecessors.update(self.hg.get_node_predecessors(c))
        
        child_all_predecessors_this_level = set(filter(lambda x: self.hg.node_to_level[x] == level_id, child_all_predecessors))
        
        assert(len(child_all_predecessors_this_level) != 0)
        assert(each_node in child_all_predecessors_this_level)

        # nodes if merge. Even they cannot be merged, they don't need to be visited again
        new_part_vtxes = set()
        new_part_vtxes.update(childs_next_level)
        new_part_vtxes.update(child_all_predecessors_this_level)
        nodes_visited.update(new_part_vtxes)


        if not new_part_vtxes.isdisjoint(self.exclude_part_ids):
          continue


        # is self contained part?
        # self contained: No fan out until last level
        # child_all_predecessors_successors = set()
        # for n in child_all_predecessors:
        #   child_all_predecessors_successors.update(self.hg.get_node_successors(n))
        
        # if child_all_predecessors_successors == childs:
          # is self contained. do merge
        new_part_vtxes.remove(each_node)
        merge_queue.append((each_node, new_part_vtxes))


    # # try merge more parts
    # merge_queue.sort(key = lambda pids: len(pids[1]))
    # merge parts from longest path
    # merge_queue.sort(key = lambda pids: self.hg.node_to_level[pids[0]], reverse=True)


    print(f" {len(merge_queue)} pending merges")
    
    for pa, pbs in merge_queue:
      # merge if all parts has not been merged
      if pa in self.node_id_to_part and all(map(lambda x: x in self.node_id_to_part, pbs)):
        # assert(self.exclude_part_ids == exclude_part_ids_old)
        assert(pa not in self.exclude_part_ids)
        assert(pbs.isdisjoint(self.exclude_part_ids))
        merge_ok = self.try_merge_upart_nodes(pa, pbs, True)
        if merge_ok:
          merge_cnt += 1

          if merge_cnt % 200 == 0:
            self.hg.levelize()
    self.hg.graph_gc()


    assert(len(self.node_id_to_part) == len(self.hg.all_nodes()))
    self.hg.check_graph()

    return merge_cnt


  def merge_on_critical_path(self):


    self.check_hg()


    # collect all nodes on critical path
    # print("Collecting critical path nodes")
    critical_path_nodes = set(self.hg.levels[-1])
    fringe = critical_path_nodes.copy()
    while len(fringe) != 0:
      fringe_next = set()
      for n in fringe:
        fringe_next.update(self.hg.get_node_predecessors(n))
      fringe_next.difference_update(critical_path_nodes)
      critical_path_nodes.update(fringe_next)
      fringe = fringe_next

    current_level = 0
    # max_level = len(self.hg.levels) - 1
    total_merge_cnt = 0

    while current_level < len(self.hg.levels) - 1:

      print(f"New iter on level {current_level}")


      fringe = set()
      for n in self.hg.levels[current_level + 1]:
        if n in critical_path_nodes:
          fringe.add(n)

      # fringe = list(filter(lambda x: x in critical_path_nodes, self.hg.levels[current_level + 1]))
      
      if (len(fringe) == 0):
        print("Empty level on critical path? skip to next")
        current_level += 1
        continue

      merge_cnt = 0
      for n in fringe:
        predecessors = set(self.hg.get_node_predecessors(n))
        if predecessors.isdisjoint(self.exclude_part_ids):
          from_nodes = predecessors.copy()
          to_node = from_nodes.pop()
          from_nodes.add(n)
          all_nodes = set()
          all_nodes.add(to_node)
          all_nodes.update(from_nodes)
          if  all(map(lambda x: x not in self.exclude_part_ids, all_nodes)) and all(map(lambda x: x in self.node_id_to_part, all_nodes)):
            success = self.try_merge_upart_nodes(to_node, from_nodes, True)
            if success:
              # print("yey")
              merge_cnt += 1
      if merge_cnt != 0:
        # succesfully do some merge
        total_merge_cnt += merge_cnt
        print(f"Merge {merge_cnt}")
        self.hg.graph_gc()
        self.hg.levelize()
      else:
        # Move to next level
        current_level += 1
        print(f"Move to level {current_level}")
    return total_merge_cnt

  def merge_siblings(self):

    self.check_hg()


    merge_queue = []

    total_merge_cnt = 0

    current_level = 0

    nodes_no_feasible_merge = set()

    while len(self.hg.levels) > current_level + 1:
      merge_cnt = 0

      for n in self.hg.levels[current_level]:
        if n in nodes_no_feasible_merge:
          continue

        successors = list(filter(lambda x: x not in self.exclude_part_ids and self.hg.node_to_level[x] == current_level + 1, self.hg.get_node_successors(n)))

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
            # self.hg.graph_gc()
            # self.hg.levelize()
            # self.hg.check_graph()
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

        self.hg.graph_gc()
        self.hg.levelize()
    return total_merge_cnt
  

  def merge_same_level(self):
    self.check_hg()


    total_merge_cnt = 0

    current_level = 0

    # nodes_no_feasible_merge = set()

    while len(self.hg.levels) > current_level + 1:
      merge_cnt = 0


      nodes_valid = list(filter(lambda x: x in self.node_id_to_part and x not in self.exclude_part_ids, self.hg.levels[current_level]))

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

        self.hg.graph_gc()
        self.hg.levelize()
    return total_merge_cnt
  





if __name__ == "__main__":
  import time
    
  g = MergeAddMul.test_graph()

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
  merger.build_part_hg(parts)

  merger.print_part_stat()

  print("> Merge with child")

  merge_cnt = merger.merge_direct_child()

  print(f"Merged {merge_cnt} parts")

  # re levelize
  merger.hg.levelize()
  
  merger.print_part_stat()

  while True:
    print("> Merge with child")
    merge_cnt = merger.merge_direct_child()
    print(f"Merged {merge_cnt} parts")

    # re levelize
    merger.hg.levelize()
    if merge_cnt < 10:
      break

  merger.print_part_stat()


  # while True:
  #   print("> Merge with multiple childs")
  #   merge_cnt = merger.merge_direct_childs()
  #   print(f"{merge_cnt} merge ops")

  #   # re levelize
  #   merger.hg.levelize()
  #   if merge_cnt == 0:
  #     break

  # merger.print_part_stat()


  while True:
    print("> Merge adjacent groups")
    merge_cnt = merger.merge_adjacent_group_2()
    print(f"{merge_cnt} merge ops")

    # re levelize
    merger.hg.levelize()
    if merge_cnt == 0:
      break

  merger.print_part_stat()



  # while True:
  #   print("> Merge adjacent groups")
  #   merge_cnt = merger.merge_adjacent_group()
  #   print(f"{merge_cnt} merge ops")

  #   # re levelize
  #   merger.hg.levelize()
  #   if merge_cnt == 0:
  #     break

  # merger.print_part_stat()




  # while True:
  #   print("> Merge critical path")
  #   merge_cnt = merger.merge_on_critical_path()
  #   print(f"{merge_cnt} merge ops")

  #   # re levelize
  #   merger.hg.levelize()
  #   if merge_cnt == 0:
  #     break

  # merger.print_part_stat()



  while True:
    print("> Merge siblings")
    merge_cnt = merger.merge_siblings()
    print(f"{merge_cnt} merge ops")

    # re levelize
    merger.hg.levelize()
    if merge_cnt == 0:
      break

  merger.print_part_stat()



  while True:
    print("> Merge with child2")
    merge_cnt = merger.merge_direct_child()
    print(f"Merged {merge_cnt} parts")

    # re levelize
    merger.hg.levelize()
    if merge_cnt < 10:
      break

  merger.print_part_stat()

  while True:
    print("> Merge adjacent groups2")
    merge_cnt = merger.merge_adjacent_group_2()
    print(f"{merge_cnt} merge ops")

    # re levelize
    merger.hg.levelize()
    if merge_cnt == 0:
      break

  merger.print_part_stat()



  while True:
    print("> Merge same level")
    merge_cnt = merger.merge_same_level()
    print(f"{merge_cnt} merge ops")

    # re levelize
    merger.hg.levelize()
    if merge_cnt == 0:
      break

  merger.print_part_stat()

  print("> Done")
  Utils.print_memory_usage()