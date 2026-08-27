#pragma once

#include "Common.h"
#include "ToucanGraph.h"
#include <memory>
#include <unordered_map>
#include <unordered_set>
#include <vector>

class MicroPartition {
  public:
    MicroPartition(const ToucanGraph *graph);
    ~MicroPartition() = default;

    MicroPartition(const MicroPartition &) = default;
    MicroPartition &operator=(const MicroPartition &) = default;

    // Core functionality
    bool check_correctness();
    bool try_add_nodes(const std::unordered_set<NodeID> &new_nodes);

    // Accessors
    const std::unordered_set<NodeID> &get_nodes() const { return nodes; }
    const std::vector<std::vector<NodeID>> &get_levels() const { return levels; }
    const std::unordered_map<NodeID, int> &get_node_levels() const { return node_levels; }
    int get_max_live_vars() const { return max_live_vars; }
    int get_num_input_vars() const { return num_input_vars; }
    int get_num_output_vars() const { return num_output_vars; }

  private:
    const ToucanGraph *G;
    std::unordered_set<NodeID> nodes;
    std::vector<std::vector<NodeID>> levels;
    std::unordered_map<NodeID, int> node_levels;

    // Variable lifecycle: node_id -> (life_start, life_end)
    std::unordered_map<NodeID, std::pair<int, int>> var_life_cycle;

    int max_live_vars = -1;
    int num_input_vars = -1;
    int num_output_vars = -1;

    // Helper methods
    void calculate_node_level();
    void collect_variable_liveness();
    bool check_liveness_constraint();
};

// Partitioning functions
std::vector<std::unique_ptr<MicroPartition>>
partitioner2(const ToucanGraph &G, const std::unordered_set<NodeID> &excluded_nodes);

std::unordered_set<NodeID> find_exclude_nodes(const ToucanGraph &g);
void report_part_info(const std::vector<std::unique_ptr<MicroPartition>> &parts);
