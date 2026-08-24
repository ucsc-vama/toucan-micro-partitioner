#include "MicroPartition.h"
#include <algorithm>
#include <cassert>
#include <climits>
#include <cstdint>
#include <iostream>
#include <queue>
#include <unordered_set>

MicroPartition::MicroPartition(const ToucanGraph *graph) : G(graph) {}

MicroPartition::MicroPartition(const MicroPartition &other)
    : G(other.G), nodes(other.nodes), levels(other.levels), node_levels(other.node_levels),
      var_life_cycle(other.var_life_cycle), max_live_vars(other.max_live_vars),
      num_input_vars(other.num_input_vars), num_output_vars(other.num_output_vars) {}

MicroPartition &MicroPartition::operator=(const MicroPartition &other) {
    if (this != &other) {
        G = other.G;
        // excluded_nodes = other.excluded_nodes;
        nodes = other.nodes;
        levels = other.levels;
        node_levels = other.node_levels;
        var_life_cycle = other.var_life_cycle;
        max_live_vars = other.max_live_vars;
        num_input_vars = other.num_input_vars;
        num_output_vars = other.num_output_vars;
    }
    return *this;
}

void MicroPartition::calculate_node_level() {
    for ([[maybe_unused]] int node : nodes) {
        // assert(excluded_nodes.find(node) == excluded_nodes.end());
        assert(G->has_node(node));
    }

    // Create subgraph for this partition
    auto subgraph = G->create_subgraph(nodes);

    if (!subgraph->is_acyclic()) {
        throw std::runtime_error("The graph must be a Directed Acyclic Graph (DAG) to levelize.");
    }

    // Topological sort to assign levels
    levels.clear();
    node_levels.clear();

    std::unordered_map<int, int> in_degree;
    for (int node : nodes) {
        in_degree[node] = 0;
        for (int pred : G->get_predecessors(node)) {
            if (nodes.count(pred)) {
                in_degree[node]++;
            }
        }
    }

    std::queue<int> queue;
    for (const auto &pair : in_degree) {
        if (pair.second == 0) {
            queue.push(pair.first);
        }
    }

    int current_level = 0;
    while (!queue.empty()) {
        if (current_level >= PART_MAX_LEVEL) {
            throw std::runtime_error("Partition level exceeded maximum");
        }

        int level_size = queue.size();
        std::vector<int> current_level_nodes;

        for (int i = 0; i < level_size; ++i) {
            int node = queue.front();
            queue.pop();

            current_level_nodes.push_back(node);
            node_levels[node] = current_level;

            for (int successor : G->get_successors(node)) {
                if (nodes.count(successor)) {
                    in_degree[successor]--;
                    if (in_degree[successor] == 0) {
                        queue.push(successor);
                    }
                }
            }
        }

        levels.push_back(current_level_nodes);
        current_level++;
    }
}

void MicroPartition::collect_variable_liveness() {
    assert(!levels.empty());

    var_life_cycle.clear();

    // Calculate variable lifetimes
    for (int node : nodes) {
        int life_start = node_levels[node];
        int life_end = life_start;

        for (int successor : G->get_successors(node)) {
            if (nodes.find(successor) == nodes.end()) {
                // Edge points outside partition
                life_end = PART_MAX_LEVEL;
                break;
            } else {
                assert(node_levels[successor] > life_start);
                life_end = std::max(life_end, node_levels[successor]);
            }
        }

        if (life_start != life_end) {
            assert(!var_life_cycle.contains(node));
            var_life_cycle[node] = {life_start, life_end};
        } else {
            // Sink node - should not happen in normal cases
            assert(false);
        }
    }

    // Handle external inputs
    // Since in micro partitioner, we cannot distinguish different VecArith result segments, just
    // treat each reference as unique for safety.
    int nextUnusedVarId = INT_MAX;
    for (int node : nodes) {
        for (int pred : G->get_predecessors(node)) {
            const auto &pred_attrs = G->get_nodes().at(pred);

            int var_id = pred;
            if (is_merge_result_node_tag(pred_attrs.tag)) {
                // Special handling for VecArith
                // Don't care exact id, just make it unique
                var_id = nextUnusedVarId;
                nextUnusedVarId--;
                assert(nextUnusedVarId > 0);
                assert(!var_life_cycle.contains(var_id));
                assert(!nodes.contains(var_id) && "If this hit, there may be too many nodes");
            }
            if (nodes.count(pred)) {
                assert(var_life_cycle.count(var_id));
            } else {
                // External edge
                int life_start = -1;
                int life_end = node_levels[node];

                if (var_life_cycle.count(var_id)) {
                    int old_life_end = var_life_cycle[var_id].second;
                    var_life_cycle[var_id] = {life_start, std::max(life_end, old_life_end)};
                } else {
                    var_life_cycle[var_id] = {life_start, life_end};
                }
            }
        }
    }
}

bool MicroPartition::check_liveness_constraint() {
    assert(!var_life_cycle.empty());

    std::unordered_map<int, std::unordered_set<int>> level_var_active;
    std::unordered_map<int, std::unordered_set<int>> level_var_deactive;

    for (const auto &pair : var_life_cycle) {
        int var = pair.first;
        int life_start = pair.second.first;
        int life_end = pair.second.second;

        level_var_active[life_start].insert(var);
        level_var_deactive[life_end].insert(var);
    }

    // External vars
    std::unordered_set<int> current_live_vars;
    if (level_var_active.count(-1)) {
        current_live_vars = level_var_active[-1];
    }

    max_live_vars = current_live_vars.size();
    num_input_vars = current_live_vars.size();

    for (int level = 0; level < static_cast<int>(levels.size()); ++level) {
        max_live_vars = std::max(static_cast<int>(current_live_vars.size()), max_live_vars);

        if (current_live_vars.size() > GPU_WARP_SIZE) {
            return false;
        }

        // Deactivate variables
        if (level_var_deactive.count(level)) {
            for (int var : level_var_deactive[level]) {
                assert(current_live_vars.count(var));
                current_live_vars.erase(var);
            }
        }

        // Activate variables
        if (level_var_active.count(level)) {
            for (int var : level_var_active[level]) {
                assert(current_live_vars.find(var) == current_live_vars.end());
                current_live_vars.insert(var);
            }
        }
    }

    // Handle final variables
    if (level_var_deactive.count(PART_MAX_LEVEL)) {
        for ([[maybe_unused]] int var : level_var_deactive[PART_MAX_LEVEL]) {
            assert(current_live_vars.count(var));
        }
        assert(current_live_vars.size() == level_var_deactive[PART_MAX_LEVEL].size());
    } else {
        assert(current_live_vars.empty());
    }

    num_output_vars = current_live_vars.size();
    max_live_vars = std::max(static_cast<int>(current_live_vars.size()), max_live_vars);

    if (current_live_vars.size() > GPU_WARP_SIZE) {
        return false;
    }

    assert(max_live_vars <= GPU_WARP_SIZE);
    return true;
}

bool MicroPartition::check_correctness() {
    if (nodes.size() > MAX_PARTITION_SIZE) {
        return false;
    }

    calculate_node_level();
    collect_variable_liveness();
    return check_liveness_constraint();
}

bool MicroPartition::try_add_nodes(const std::unordered_set<int> &new_nodes) {
    // for (int node : new_nodes) {
    //     assert(excluded_nodes.find(node) == excluded_nodes.end());
    // }

    nodes.insert(new_nodes.begin(), new_nodes.end());
    return check_correctness();
}

std::unordered_set<int> find_exclude_nodes(const ToucanGraph &g) {
    std::unordered_set<int> ret;

    for (const auto &node_pair : g.get_nodes()) {
        int node = node_pair.first;
        const NodeAttributes &attrs = node_pair.second;

        if (is_exclude_node_tag(attrs.tag)) {
            ret.insert(node);
        }

        if (!is_valid_node_tag(attrs.tag)) {
            std::cout << "Invalid tag: " << node_tag_to_string(attrs.tag) << std::endl;
            assert(false);
        }
    }

    return ret;
}

void report_part_info(const std::vector<std::unique_ptr<MicroPartition>> &parts) {
    std::unordered_map<int, int> size_counts;
    std::unordered_map<int, int> depth_counts;

    for (const auto &part : parts) {
        int part_size = part->get_nodes().size();
        size_counts[part_size]++;

        int part_depth = part->get_levels().size();
        depth_counts[part_depth]++;
    }

    // Print size distribution
    std::vector<int> sizes;
    for (const auto &pair : size_counts) {
        sizes.push_back(pair.first);
    }
    std::sort(sizes.begin(), sizes.end());

    for (int size : sizes) {
        std::cout << "Part size " << size << ": " << size_counts[size] << std::endl;
    }

    // Print depth distribution
    std::vector<int> depths;
    for (const auto &pair : depth_counts) {
        depths.push_back(pair.first);
    }
    std::sort(depths.begin(), depths.end());

    for (int depth : depths) {
        std::cout << "Part depth " << depth << ": " << depth_counts[depth] << std::endl;
    }

    // Calculate average depth
    double total_depth = 0;
    for (const auto &part : parts) {
        total_depth += part->get_levels().size();
    }
    double avg_depth = total_depth / parts.size();
    std::cout << "Avg depth " << avg_depth << " of " << parts.size() << " parts" << std::endl;
}

std::vector<std::unique_ptr<MicroPartition>>
partitioner2(const ToucanGraph &G, const std::unordered_set<int> &excluded_nodes) {

    std::vector<std::unique_ptr<MicroPartition>> partitions;
    std::unordered_set<int> visited = excluded_nodes;

    // Ensure graph is levelized
    if (!G.is_levelized()) {
        throw std::runtime_error("Graph must be levelized before partitioning");
    }

    // Create vertex-to-level mapping for O(1) lookups
    std::unordered_map<int, int> vtx_to_level;
    vtx_to_level.reserve(G.get_nodes().size());
    const auto &levels = G.get_levels();
    for (size_t level_id = 0; level_id < levels.size(); ++level_id) {
        for (int node : levels[level_id]) {
            vtx_to_level[node] = static_cast<int>(level_id);
        }
    }

    // Get topological order (reverse to start from sinks)
    std::vector<int> topo_order;
    for (const auto &level : levels) {
        for (int node : level) {
            topo_order.push_back(node);
        }
    }
    std::reverse(topo_order.begin(), topo_order.end());

    for (int seed : topo_order) {
        if (visited.count(seed)) {
            continue;
        }

        // Check if seed has too many inputs
        int seed_in_degree = G.get_in_degree(seed);
        if (seed_in_degree > 3) {
            const auto &seed_attrs = G.get_nodes().at(seed);
            std::cout << "Node " << seed << " has more than 3 inputs (" << seed_in_degree
                      << "). This node is a " << node_tag_to_string(seed_attrs.tag) << std::endl;
            exit(-1);
        }

        // Create new partition starting with seed
        auto part = std::make_unique<MicroPartition>(&G);
        [[maybe_unused]] bool success = part->try_add_nodes({seed});
        assert(success);

        // Get seed's level for MFFC traversal using O(1) lookup
        int seed_level = vtx_to_level.at(seed);

        // MFFC (Maximum Fanout-Free Cone) traversal
        std::unordered_set<int> mffc_fringe;
        for (int pred : G.get_predecessors(seed)) {
            mffc_fringe.insert(pred);
        }

        int last_level = seed_level;

        while (!mffc_fringe.empty()) {
            // Find MFFC nodes (nodes whose all successors are in current partition)
            std::vector<int> mffc_nodes;
            for (int vtx : mffc_fringe) {
                if (visited.count(vtx))
                    continue;

                bool all_successors_in_part = true;
                for (int succ : G.get_successors(vtx)) {
                    if (part->get_nodes().find(succ) == part->get_nodes().end()) {
                        all_successors_in_part = false;
                        break;
                    }
                }

                if (all_successors_in_part) {
                    mffc_nodes.push_back(vtx);
                }
            }

            if (mffc_nodes.empty()) {
                break;
            }

            // Find nodes at the right level distance using O(1) lookups
            std::unordered_set<int> part_candidates;
            int mffc_max_level = -1;
            for (int node : mffc_nodes) {
                int node_level = vtx_to_level.at(node);
                mffc_max_level = std::max(mffc_max_level, node_level);
            }

            if (mffc_max_level + 1 != last_level) {
                // Level gap - stop expansion
                break;
            }

            for (int vtx : mffc_nodes) {
                int vtx_level = vtx_to_level.at(vtx);
                if (vtx_level + 1 == last_level) {
                    part_candidates.insert(vtx);
                }
            }

            if (part_candidates.empty()) {
                break;
            }

            // Try to add candidates to partition
            auto part_backup = std::make_unique<MicroPartition>(*part);
            bool good_to_add = part->try_add_nodes(part_candidates);

            if (!good_to_add) {
                // Restore backup and stop
                part = std::move(part_backup);
                break;
            }

            // Update fringe for next iteration
            std::unordered_set<int> mffc_fringe_next = mffc_fringe;
            for (int vtx : part_candidates) {
                mffc_fringe_next.erase(vtx);
                for (int pred : G.get_predecessors(vtx)) {
                    mffc_fringe_next.insert(pred);
                }
            }
            mffc_fringe = mffc_fringe_next;

            assert(last_level > 0);
            last_level--;
        }

        assert(part->check_correctness());
        partitions.push_back(std::move(part));

        // Mark all nodes in this partition as visited
        for (int node : partitions.back()->get_nodes()) {
            visited.insert(node);
        }
    }

    return partitions;
}
