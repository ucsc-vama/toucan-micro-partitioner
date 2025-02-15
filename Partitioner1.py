
import ToucanGraph
import MergeAddMul



import networkx as nx
import copy

DEBUG = False


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
    part_size = len(p)

    if part_size in ret.keys():
      ret[part_size] += 1
    else:
      ret[part_size] = 1

  for k in sorted(ret.keys()):
    print(f"Part size {k}: {ret[k]}")

# initial grow of partitions. Limit max width
def partitioner1(G, exclude_nodes):
  G.levelize()

  g = G.graph

  ret_parts = []
  visited = set()

  for node in exclude_nodes:
    visited.add(node)


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


    # unvisited. Grow partitions
    part = set({seed})
    part_max_depth = 1

    part_input_nodes = set({seed})
    part_input_edges_src = set()

    mffc_fringe = set(g.predecessors(seed))
    mffc_fringe_next = set()

    last_level = g.nodes[seed]['level_id']
    assert(last_level is not None)

    # print("-" * 30)
    # print(f"Growing from node {seed} at level {last_level}")
      
    #  and (len(part_input_edges_src) + len(part_input_nodes) <= 32)
    while len(mffc_fringe) != 0:
      # print(f"> New iter, last level {last_level}")

      # collect nodes that are eligible for MFFC
      mffc_nodes = []
      for eachVtx in mffc_fringe:
        if all((w in part) for w in g.successors(eachVtx)) and eachVtx not in visited:
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

      # check if boundary is satisfiable, if yes, merge
      # Find nodes that are no longer input nodes
      nodes_no_longer_input = set()
      for eachVtx in part_candidates:
        for eachSucc in g.successors(eachVtx):
          if eachSucc in part_input_nodes:
            nodes_no_longer_input.add(eachSucc)
      # add new edge input
      for eachVtx in nodes_no_longer_input:
        for eachEdge in g.in_edges(eachVtx):
          src, dst = eachEdge
          if src not in part_candidates:
            # This node pushed to lower levels with edge from outside of the partition
            part_input_edges_src.add(src)
      # remove edge that are no longer input
      for eachVtx in part_candidates:
        for eachEdge in g.out_edges(eachVtx):
          src, dst = eachEdge
          if src in part_input_edges_src:
            part_input_edges_src.remove(src)
          if dst in part_input_edges_src:
            part_input_edges_src.remove(dst)

      # update input nodes
      for eachVtx in nodes_no_longer_input:
        part_input_nodes.remove(eachVtx)
      for eachVtx in part_candidates:
        part_input_nodes.add(eachVtx)
        for eachSucc in g.successors(eachVtx):
          assert(eachSucc in part)

      # check if sat
      if len(part_input_edges_src) + len(part_input_nodes) > 32:
        mffc_fringe = set()
        # print("Break due to full")
        break
      else:
        # confirm this
        assert(len(part.intersection(part_candidates)) == 0)
        part.update(part_candidates)

        # verify
        if DEBUG:
          in_nodes, in_edges_src = get_part_inputs(part, G)
          if in_nodes != part_input_nodes or in_edges_src != part_input_edges_src:
            print(f"Part max depth is {part_max_depth}")
            print(f"Error: input node expect {str(list(sorted(in_nodes)))} but got {str(list(sorted(part_input_nodes)))}, input edge src expect {str(list(sorted(in_edges_src)))} but got {str(list(sorted(part_input_edges_src)))}")
            assert(False)


      # lastly, update MFFC fringe
      # 
      mffc_fringe_next = mffc_fringe.difference(part_candidates)

      # mffc_fringe_next = mffc_fringe.difference(part)
      for eachVtx in part_candidates:
        for es in g.predecessors(eachVtx):
          mffc_fringe_next.add(es)
      mffc_fringe = mffc_fringe_next

      assert(last_level != 0)
      last_level -= 1
      part_max_depth += 1

  
    # done with one mffc
    ret_parts.append(part)


    for v in part:
      visited.add(v)

  return ret_parts


def get_part_inputs(part_nodes: set, G):
  sg = G.create_subgraph(list(part_nodes))
  sg.levelize()

  part_input_nodes = set()
  part_input_edges_src = set()

  for ev in sg.levels[0]:
    # Level 0 nodes 
    part_input_nodes.add(ev)

  for el in sg.levels[1:]:
    for ev in el:
      for edge in G.graph.in_edges(ev):
        src, dst = edge
        if src not in part_nodes:
          # an external input edge
          part_input_edges_src.add(src)
  
  return part_input_nodes, part_input_edges_src

def check_part_correctness(part_nodes: set, G):
  n, e = get_part_inputs(part_nodes, G)
  correct_width = len(n) + len(e) <= 32
  correct_acyclic = G.create_subgraph(list(part_nodes)).is_acyclic()
  return correct_width and correct_acyclic











def create_part_graph(G, parts, exclude_nodes):
  pg = ToucanGraph.ToucanGraph()

  unvisited = set(G.graph.nodes())

  # pid_to_original_nodes = {}
  original_node_to_pid = {}



  nodes_to_add = []
  new_pid = 0
  # Add partitions
  for p in parts:
    nodes_to_add.append((new_pid, {
      "sub_nodes": p,
      "is_part": True,
      "type": "Part",
      "weight": len(p)
    }))
    new_pid += 1
    for n in p:
      assert(n not in original_node_to_pid)
      original_node_to_pid[n] = new_pid

      assert(n in unvisited)
    unvisited.difference_update(p)
  
  pg.graph.add_nodes_from(nodes_to_add)

  # Add exclude nodes
  nodes_to_add.clear()
  for p in exclude_nodes:
    assert(p in unvisited)

    nodes_to_add.append((new_pid, {
      "sub_nodes": set({p}),
      "is_part": False,
      "type": G.graph.nodes[p]["op_name"],
      "weight": G.graph.nodes[p]["weight"]
    }))

    new_pid += 1

    assert(p not in original_node_to_pid)
    original_node_to_pid[p] = new_pid
    unvisited.remove(p)
  pg.graph.add_nodes_from(nodes_to_add)


  assert(len(unvisited) == 0)



  # add edge
  edge_dedup = {}
  for e in G.graph.edges():
    src, dst = e
    if not src in edge_dedup:
      edge_dedup[src] = set()
    edge_dedup[src].add(dst)
  edges_to_add = []
  for src in edge_dedup.keys():
    for dst in edge_dedup[src]:
      edges_to_add.append((src, dst))
  pg.graph.add_edges_from(edges_to_add)

  assert(pg.is_acyclic())


  return pg, original_node_to_pid






def ok_to_merge(G, *to_merge):
  new_part = set({})

  for ep in to_merge:
    new_part.update(ep)

  sub_graph = G.create_subgraph(list(new_part))

  n, e = get_part_inputs(new_part, G)
  correct_width = len(n) + len(e) <= 32
  correct_acyclic = sub_graph.is_acyclic()

  num_sink = 0
  for n in new_part:
    if sub_graph.graph.out_degree(n) == 0:
      num_sink += 1
  assert(num_sink != 0)

  if num_sink > 32:
    print(f"Note: This part has {num_sink} sinks, more than 32")

  return correct_width and correct_acyclic and num_sink <= 32




def merge_child(G, pg):
  pass





if __name__ == "__main__":
    
  g = MergeAddMul.test_graph()

  exclude_nodes = find_exclude_nodes(g.graph)
  print(f"{len(exclude_nodes)} nodes need to be excluded")
  
  parts = partitioner1(g, exclude_nodes)
  print(f"Found {len(parts)} partitions")

  for p in parts:
    good = check_part_correctness(p, g)
    assert(good)

  report_part_info(parts)


  part_graph, original_node_to_pid = create_part_graph(g, parts, exclude_nodes)

  part_graph.levelize()
  print(f"Part graph has {len(part_graph.levels)} levels")

  print(part_graph)



  longest_path = nx.dag_longest_path(g.graph)

  print(f"Longest path {str(longest_path)}")


  longest_part_path = []
  for n in longest_path:
    p = original_node_to_pid[n]
    if len(longest_part_path) != 0 and longest_part_path[-1][0] == p:
      longest_part_path[-1][1] += 1
    else:
      longest_part_path.append([p, 1])
    # longest_part_path.append(p)
  print(f"Longest path part {str(longest_part_path)}, len {len(longest_part_path)}")
