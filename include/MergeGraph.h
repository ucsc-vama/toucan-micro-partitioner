#pragma once

#include "NodeID.h"
#include <cstddef>
#include <unordered_set>
#include <vector>

class MergeGraph {
  public:
    MergeGraph();
    ~MergeGraph() = default;

    // Node management
    void reserve_nodes(size_t node_count);
    NodeID add_node();
    void add_edge(NodeID source, NodeID target);
    void add_edges(const std::vector<std::pair<NodeID, NodeID>> &edges);

    // Graph queries
    const std::vector<NodeID> &get_node_successors(NodeID node) const;
    const std::vector<NodeID> &get_node_predecessors(NodeID node) const;
    int get_node_in_degree(NodeID node) const;
    bool has_node(NodeID node) const;
    size_t num_nodes() const { return live_node_count; }

    // Graph operations
    bool merge_is_acyclic(const std::unordered_set<NodeID> &nodes_to_merge);
    void merge_nodes(NodeID to, const std::vector<NodeID> &from_list);
    void graph_gc();
    void edge_dedup();
    void check_graph() const;
    void levelize();

    // Accessors
    const std::vector<std::vector<NodeID>> &get_levels() const { return levels; }
    const std::vector<int> &get_node_to_level() const { return node_to_level; }

  private:
    std::vector<std::vector<NodeID>> adjacency_list;         // node -> successors
    std::vector<std::vector<NodeID>> reverse_adjacency_list; // node -> predecessors
    NodeID next_id = 0;
    std::vector<bool> active;
    size_t live_node_count = 0;
    std::vector<std::vector<NodeID>> levels;
    std::vector<int> node_to_level;
    std::vector<int> in_degree;
    std::vector<NodeID> levelize_queue;
    std::vector<NodeID> nodes_to_remove;
    std::vector<unsigned char> pending_removal;

    bool is_acyclic() const;
};
