#pragma once

#include <cstddef>
#include <unordered_set>
#include <vector>

class MergeGraph {
  public:
    MergeGraph();
    ~MergeGraph() = default;

    // Node management
    void reserve_nodes(size_t node_count);
    int add_node();
    void add_edge(int source, int target);
    void add_edges(const std::vector<std::pair<int, int>> &edges);

    // Graph queries
    std::vector<int> get_node_successors(int node) const;
    std::vector<int> get_node_predecessors(int node) const;
    int get_node_in_degree(int node) const;
    bool has_node(int node) const;
    size_t num_nodes() const { return live_node_count; }

    // Graph operations
    bool merge_is_acyclic(const std::unordered_set<int> &nodes_to_merge);
    void merge_nodes(int to, const std::vector<int> &from_list);
    void graph_gc();
    void edge_dedup();
    void check_graph() const;
    void levelize();

    // Accessors
    const std::vector<std::vector<int>> &get_levels() const { return levels; }
    const std::vector<int> &get_node_to_level() const { return node_to_level; }

  private:
    std::vector<std::vector<int>> adjacency_list;         // node -> successors
    std::vector<std::vector<int>> reverse_adjacency_list; // node -> predecessors
    int next_id = 0;
    std::vector<bool> active;
    size_t live_node_count = 0;
    std::vector<std::vector<int>> levels;
    std::vector<int> node_to_level;
    std::vector<int> in_degree;
    std::vector<int> levelize_queue;
    std::vector<int> nodes_to_remove;
    std::vector<unsigned char> pending_removal;

    bool is_acyclic() const;
};
