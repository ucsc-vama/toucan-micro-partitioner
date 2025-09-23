#pragma once

#include "ToucanGraph.h"
#include "MicroPartition.h"
#include "MergeGraph.h"
#include <memory>
#include <unordered_map>
#include <unordered_set>
#include <vector>
#include <string>

class PartitionMerger {
public:
    PartitionMerger(const ToucanGraph& G, const std::unordered_set<int>& exclude_nodes);
    ~PartitionMerger() = default;

    // Core functionality
    void build_part_mg(const std::vector<std::unique_ptr<MicroPartition>>& parts);
    void print_part_stat() const;
    void save(const std::string& filename) const;

    // Merging strategies
    int merge_direct_child();
    int merge_adjacent_group();
    int merge_siblings();
    int merge_same_level();

    // Utility
    void check_mg() const;

private:
    std::unique_ptr<MergeGraph> mg;
    const ToucanGraph& G;
    std::unordered_set<int> exclude_nodes;
    std::unordered_set<int> exclude_part_ids;
    
    // Maps partition ID to either MicroPartition or set of excluded nodes
    std::unordered_map<int, std::unique_ptr<MicroPartition>> node_id_to_part;
    std::unordered_map<int, std::unordered_set<int>> exclude_id_to_nodes;

    // Helper methods
    bool try_merge_upart_nodes(int to, const std::vector<int>& from_nodes, bool check_acyclic = false);
};
