#include "PartitionMerger.h"
#include "Utils.h"
#include <algorithm>
#include <cassert>
#include <fstream>
#include <iostream>

PartitionMerger::PartitionMerger(const ToucanGraph &G,
                                 const std::unordered_set<NodeID> &exclude_nodes)
    : G(G), exclude_nodes(exclude_nodes) {
    mg = std::make_unique<MergeGraph>();
}

void PartitionMerger::build_part_mg(const std::vector<std::unique_ptr<MicroPartition>> &parts) {
    mg->reserve_nodes(parts.size() + exclude_nodes.size());

    // Add nodes for all parts
    for (size_t i = 0; i < parts.size(); ++i) {
        NodeID part_id = mg->add_node();
        assert(part_id == static_cast<NodeID>(i));
        node_id_to_part[part_id] = std::make_unique<MicroPartition>(*parts[i]);
    }

    // Add exclude parts
    for (NodeID n : exclude_nodes) {
        NodeID part_id = mg->add_node();
        exclude_part_ids.insert(part_id);
        exclude_id_to_nodes[part_id] = {n};
    }

    // Map from node_id to part_id
    std::unordered_map<NodeID, NodeID> node_id_to_part_id;
    for (const auto &pair : node_id_to_part) {
        NodeID part_id = pair.first;
        const auto &part = pair.second;
        for (NodeID n : part->get_nodes()) {
            assert(!node_id_to_part_id.contains(n));
            node_id_to_part_id[n] = part_id;
        }
    }

    for (const auto &pair : exclude_id_to_nodes) {
        NodeID part_id = pair.first;
        const auto &nodes = pair.second;
        for (NodeID n : nodes) {
            assert(!node_id_to_part_id.contains(n));
            node_id_to_part_id[n] = part_id;
        }
    }

    // Build edges
    std::vector<std::pair<NodeID, NodeID>> edges_to_add;
    for (const auto &pair : node_id_to_part) {
        NodeID part_id = pair.first;
        const auto &part = pair.second;

        std::unordered_set<NodeID> part_output_edges;
        for (NodeID n : part->get_nodes()) {
            for (NodeID successor : G.get_successors(n)) {
                if (!part->get_nodes().contains(successor)) {
                    // Edge points outside current part
                    NodeID dst_part_id = node_id_to_part_id[successor];
                    if (!part_output_edges.contains(dst_part_id)) {
                        edges_to_add.emplace_back(part_id, dst_part_id);
                        part_output_edges.insert(dst_part_id);
                    }
                }
            }
        }
    }

    for (const auto &pair : exclude_id_to_nodes) {
        NodeID part_id = pair.first;
        const auto &nodes = pair.second;

        std::unordered_set<NodeID> part_output_edges;
        for (NodeID n : nodes) {
            for (NodeID successor : G.get_successors(n)) {
                if (!nodes.contains(successor)) {
                    // Edge points outside current part
                    NodeID dst_part_id = node_id_to_part_id[successor];
                    if (!part_output_edges.contains(dst_part_id)) {
                        edges_to_add.emplace_back(part_id, dst_part_id);
                        part_output_edges.insert(dst_part_id);
                    }
                }
            }
        }
    }

    mg->add_edges(edges_to_add);

    // Note: should not have parallel edge. though using std::unordered_set may be a good option, do
    // manual hack for memory usage.
    mg->edge_dedup();
}

void PartitionMerger::print_part_stat() const {
    mg->levelize();

    int max_levels = mg->get_levels().size();

    std::vector<int> norm_part_size;
    std::vector<int> norm_part_depth;
    std::vector<int> norm_part_inputs;
    std::vector<int> norm_part_outputs;
    std::vector<int> norm_part_active_vars;
    std::vector<int> special_part_size;
    std::vector<int> special_part_depth;

    for (const auto &pair : node_id_to_part) {
        NodeID pid = pair.first;
        const auto &part = pair.second;
        if (!exclude_part_ids.contains(pid)) {
            norm_part_size.push_back(part->get_nodes().size());
            norm_part_depth.push_back(part->get_levels().size());
            norm_part_inputs.push_back(part->get_num_input_vars());
            norm_part_outputs.push_back(part->get_num_output_vars());
            norm_part_active_vars.push_back(part->get_max_live_vars());
        }
    }

    for (const auto &pair : exclude_id_to_nodes) {
        NodeID pid = pair.first;
        const auto &nodes = pair.second;
        if (exclude_nodes.contains(pid)) {
            special_part_size.push_back(nodes.size());
            special_part_depth.push_back(1);
        }
    }

    std::cout << "Part graph has " << max_levels << " levels\n";
    std::cout << "Has " << norm_part_size.size() << " normal parts:\n";
    if (!norm_part_size.empty()) {
        std::cout << "size: mean " << Utils::mean(norm_part_size) << ", min "
                  << Utils::min_value(norm_part_size) << ", max "
                  << Utils::max_value(norm_part_size) << ", median "
                  << Utils::median(norm_part_size) << "\n";
        std::cout << "depth: mean " << Utils::mean(norm_part_depth) << ", min "
                  << Utils::min_value(norm_part_depth) << ", max "
                  << Utils::max_value(norm_part_depth) << ", median "
                  << Utils::median(norm_part_depth) << "\n";
        std::cout << "input vars: mean " << Utils::mean(norm_part_inputs) << ", min "
                  << Utils::min_value(norm_part_inputs) << ", max "
                  << Utils::max_value(norm_part_inputs) << ", median "
                  << Utils::median(norm_part_inputs) << "\n";
        std::cout << "output vars: mean " << Utils::mean(norm_part_outputs) << ", min "
                  << Utils::min_value(norm_part_outputs) << ", max "
                  << Utils::max_value(norm_part_outputs) << ", median "
                  << Utils::median(norm_part_outputs) << "\n";
        std::cout << "max live vars: mean " << Utils::mean(norm_part_active_vars) << ", min "
                  << Utils::min_value(norm_part_active_vars) << ", max "
                  << Utils::max_value(norm_part_active_vars) << ", median "
                  << Utils::median(norm_part_active_vars) << "\n";
    }

    std::cout << "Has " << special_part_size.size() << " special (vector) parts";
    if (!special_part_size.empty()) {
        std::cout << ", size: mean " << Utils::mean(special_part_size) << ", min "
                  << Utils::min_value(special_part_size) << ", max "
                  << Utils::max_value(special_part_size) << ", median "
                  << Utils::median(special_part_size) << ", depth: mean "
                  << Utils::mean(special_part_depth) << ", min "
                  << Utils::min_value(special_part_depth) << ", max "
                  << Utils::max_value(special_part_depth) << ", median "
                  << Utils::median(special_part_depth);
    }
    std::cout << "\n";
}

int PartitionMerger::get_mp_vtx_cnt() {
    const auto &levels = mg->get_levels();
    std::unordered_set<NodeID> allMPVtxes;

    for (size_t level_id = 0; level_id < levels.size(); ++level_id) {

        for (NodeID pid : levels[level_id]) {
            if (exclude_part_ids.contains(pid)) {
            } else {
                // Normal part
                const auto &part = node_id_to_part.at(pid);

                for (const auto &eachLevel : part->get_levels()) {
                    for (NodeID n : eachLevel) {
                        assert(!allMPVtxes.contains(n));
                        allMPVtxes.insert(n);
                    }
                }
            }
        }
    }

    return allMPVtxes.size();
}

void PartitionMerger::print_mp_vtx_cnt() {
    const auto &levels = mg->get_levels();
    std::unordered_set<NodeID> allMPVtxes, allExcludeVtxes;

    for (size_t level_id = 0; level_id < levels.size(); ++level_id) {

        for (NodeID pid : levels[level_id]) {
            if (exclude_part_ids.contains(pid)) {
                // Exclude part
                const auto &nodes = exclude_id_to_nodes.at(pid);
                assert(nodes.size() == 1);
                allExcludeVtxes.insert(*nodes.begin());
            } else {
                // Normal part
                const auto &part = node_id_to_part.at(pid);

                for (const auto &eachLevel : part->get_levels()) {
                    for (NodeID n : eachLevel) {
                        assert(!allMPVtxes.contains(n));
                        allMPVtxes.insert(n);
                    }
                }
            }
        }
    }

    std::cerr << " >>>>>>>---> Has " << allMPVtxes.size() << " MP vtxes, " << allExcludeVtxes.size()
              << " exclude vtxes\n";
}

void PartitionMerger::save(const std::string &filename) const {
    mg->levelize();

    std::ofstream out(filename);
    if (!out.is_open()) {
        throw std::runtime_error("Cannot open file for writing: " + filename);
    }

    const auto &levels = mg->get_levels();
    for (size_t level_id = 0; level_id < levels.size(); ++level_id) {
        const auto &level_nodes = levels[level_id];
        out << "L " << level_id << "\n";

        std::vector<NodeID> current_level_exclude_nodes;

        for (NodeID pid : level_nodes) {
            if (exclude_part_ids.contains(pid)) {
                // Exclude part
                const auto &nodes = exclude_id_to_nodes.at(pid);
                assert(nodes.size() == 1);
                current_level_exclude_nodes.push_back(*nodes.begin());
            } else {
                // Normal part
                const auto &part = node_id_to_part.at(pid);
                assert(!part->get_nodes().empty());
                assert(!part->get_levels().empty());

                out << "n";
                for (const auto &eachLevel : part->get_levels()) {
                    assert(!eachLevel.empty());
                    out << " l";
                    std::vector<NodeID> sorted_level(eachLevel.begin(), eachLevel.end());
                    std::sort(sorted_level.begin(), sorted_level.end());
                    for (NodeID node : sorted_level) {
                        out << " " << node;
                    }
                }
                out << "\n";
            }
        }

        // Save exclude nodes if exists
        if (!current_level_exclude_nodes.empty()) {
            std::sort(current_level_exclude_nodes.begin(), current_level_exclude_nodes.end());
            out << "e";
            for (NodeID node : current_level_exclude_nodes) {
                out << " " << node;
            }
            out << "\n";
        }
    }
    out.close();
}

int PartitionMerger::merge_direct_child() {
    check_mg();

    int merge_cnt = 0;
    std::vector<std::pair<NodeID, NodeID>> merge_queue;

    for (const auto &pair : node_id_to_part) {
        NodeID merge_to = pair.first;
        if (exclude_part_ids.contains(merge_to)) {
            continue;
        }

        const auto &merge_froms = mg->get_node_successors(merge_to);
        if (merge_froms.size() != 1) {
            continue;
        }

        NodeID merge_from = merge_froms[0];
        if (exclude_part_ids.contains(merge_from)) {
            continue;
        }

        const auto &node_to_level = mg->get_node_to_level();
        int merge_to_level = node_to_level.at(merge_to);
        int merge_from_level = node_to_level.at(merge_from);

        if (merge_from_level != merge_to_level + 1) {
            continue;
        }

        merge_queue.emplace_back(merge_to, merge_from);
    }

    // Sort merge queue
    std::sort(merge_queue.begin(), merge_queue.end(),
              [&](const std::pair<NodeID, NodeID> &a, const std::pair<NodeID, NodeID> &b) {
                  return node_id_to_part.at(a.second)->get_nodes().size() <
                         node_id_to_part.at(b.second)->get_nodes().size();
              });

    std::cout << " " << merge_queue.size() << " pending merges\n";
    for (const auto &pair : merge_queue) {
        NodeID pa = pair.first, pb = pair.second;
        if (node_id_to_part.contains(pa) && node_id_to_part.contains(pb)) {
            if (try_merge_upart_nodes(pa, {pb})) {
                merge_cnt++;
            }
        }
    }

    mg->graph_gc();
    assert(node_id_to_part.size() == mg->num_nodes() - exclude_part_ids.size());
    mg->check_graph();

    return merge_cnt;
}

int PartitionMerger::merge_adjacent_group() {
    check_mg();

    int total_merge_cnt = 0;
    int iter_start_level = 0;

    while (static_cast<size_t>(iter_start_level + 1) < mg->get_levels().size()) {
        int merge_cnt = 0;

        const auto &levels = mg->get_levels();
        const auto &level_nodes = levels[iter_start_level];

        std::unordered_set<NodeID> nodes_visited;
        std::vector<std::pair<NodeID, std::unordered_set<NodeID>>> merge_queue;

        for (NodeID each_node : level_nodes) {
            if (nodes_visited.count(each_node) || exclude_part_ids.count(each_node)) {
                continue;
            }

            const auto &childs = mg->get_node_successors(each_node);
            std::unordered_set<NodeID> childs_next_level;

            const auto &node_to_level = mg->get_node_to_level();
            for (NodeID child : childs) {
                if (node_to_level.at(child) == iter_start_level + 1) {
                    childs_next_level.insert(child);
                }
            }

            if (childs_next_level.empty()) {
                continue;
            }

            // Find all predecessors of children at this level
            std::unordered_set<NodeID> child_all_predecessors;
            for (NodeID c : childs_next_level) {
                const auto &preds = mg->get_node_predecessors(c);
                child_all_predecessors.insert(preds.begin(), preds.end());
            }

            std::unordered_set<NodeID> child_all_predecessors_this_level;
            for (NodeID pred : child_all_predecessors) {
                if (node_to_level.at(pred) == iter_start_level) {
                    child_all_predecessors_this_level.insert(pred);
                }
            }

            assert(!child_all_predecessors_this_level.empty());
            assert(child_all_predecessors_this_level.count(each_node));

            // Nodes to merge
            std::unordered_set<NodeID> new_part_vtxes;
            new_part_vtxes.insert(childs_next_level.begin(), childs_next_level.end());
            new_part_vtxes.insert(child_all_predecessors_this_level.begin(),
                                  child_all_predecessors_this_level.end());
            nodes_visited.insert(new_part_vtxes.begin(), new_part_vtxes.end());

            // Skip if contains exclude parts
            bool has_exclude = false;
            for (NodeID vtx : new_part_vtxes) {
                if (exclude_part_ids.count(vtx)) {
                    has_exclude = true;
                    break;
                }
            }
            if (has_exclude)
                continue;

            new_part_vtxes.erase(each_node);
            merge_queue.emplace_back(each_node, new_part_vtxes);
        }

        for (const auto &pair : merge_queue) {
            NodeID pa = pair.first;
            const auto &pbs = pair.second;

            // Check if all parts still exist
            if (!node_id_to_part.contains(pa))
                continue;
            bool all_exist = true;
            for (NodeID pb : pbs) {
                if (!node_id_to_part.contains(pb)) {
                    all_exist = false;
                    break;
                }
            }
            if (!all_exist)
                continue;

            assert(!exclude_part_ids.contains(pa));
            for ([[maybe_unused]] NodeID pb : pbs) {
                assert(!exclude_part_ids.contains(pb));
            }

            std::vector<NodeID> pbs_vec(pbs.begin(), pbs.end());
            if (try_merge_upart_nodes(pa, pbs_vec, false)) {
                merge_cnt++;
            }
        }

        mg->graph_gc();
        mg->levelize();

        if (merge_cnt == 0) {
            iter_start_level++;
        } else {
            total_merge_cnt += merge_cnt;
        }
    }

    return total_merge_cnt;
}

int PartitionMerger::merge_siblings() {
    check_mg();

    int total_merge_cnt = 0;
    int current_level = 0;
    std::unordered_set<NodeID> nodes_no_feasible_merge;

    while (static_cast<size_t>(current_level + 1) < mg->get_levels().size()) {
        int merge_cnt = 0;

        const auto &levels = mg->get_levels();
        for (NodeID n : levels[current_level]) {
            if (nodes_no_feasible_merge.count(n)) {
                continue;
            }

            // Get successors at next level that are not excluded
            std::unordered_set<NodeID> unique_successors;
            std::vector<NodeID> successors;
            const auto &node_to_level = mg->get_node_to_level();
            for (NodeID succ : mg->get_node_successors(n)) {
                if ((!exclude_part_ids.contains(succ)) &&
                    node_to_level.at(succ) == current_level + 1 && node_id_to_part.contains(succ)) {
                    unique_successors.insert(succ);
                }
            }
            successors.assign(unique_successors.begin(), unique_successors.end());

            // Sort by live vars (smallest first)
            std::sort(successors.begin(), successors.end(), [&](NodeID a, NodeID b) {
                return node_id_to_part.at(a)->get_max_live_vars() <
                       node_id_to_part.at(b)->get_max_live_vars();
            });

            if (successors.size() < 2) {
                nodes_no_feasible_merge.insert(n);
                continue;
            }

            // Check if total live vars is feasible
            std::vector<int> successors_live_vars;
            for (int succ : successors) {
                successors_live_vars.push_back(node_id_to_part.at(succ)->get_max_live_vars());
            }

            while (successors.size() > 1) {
                int total_live_vars = 0;
                for (int vars : successors_live_vars) {
                    total_live_vars += vars;
                }
                if (total_live_vars <= 32) {
                    break;
                } else {
                    // Remove largest part
                    successors.pop_back();
                    successors_live_vars.pop_back();
                }
            }

            if (successors.size() <= 2) {
                nodes_no_feasible_merge.insert(n);
                continue;
            }

            // Try to merge successors
            while (successors.size() >= 2) {
                NodeID to = successors[0];
                std::vector<NodeID> from_nodes(successors.begin() + 1, successors.end());

                if (try_merge_upart_nodes(to, from_nodes, true)) {
                    merge_cnt++;
                    break;
                } else {
                    successors.pop_back();
                }
            }
        }

        if (merge_cnt != 0) {
            total_merge_cnt += merge_cnt;
        } else {
            current_level++;
            nodes_no_feasible_merge.clear();
            mg->graph_gc();
            mg->levelize();
        }
    }

    return total_merge_cnt;
}

int PartitionMerger::merge_same_level() {
    check_mg();

    int total_merge_cnt = 0;
    int current_level = 0;

    while (static_cast<size_t>(current_level + 1) < mg->get_levels().size()) {
        int merge_cnt = 0;

        const auto &levels = mg->get_levels();

        // Get valid nodes at current level (not excluded, with live vars < 32)
        std::vector<NodeID> nodes_valid;
        for (NodeID n : levels[current_level]) {
            if (node_id_to_part.contains(n) && (!exclude_part_ids.contains(n))) {
                nodes_valid.push_back(n);
            }
        }

        // Filter nodes with live vars < 32
        std::vector<NodeID> nodes_to_consider;
        for (NodeID n : nodes_valid) {
            if (node_id_to_part.at(n)->get_max_live_vars() < 32) {
                nodes_to_consider.push_back(n);
            }
        }

        // Sort by live vars (smallest first)
        std::sort(nodes_to_consider.begin(), nodes_to_consider.end(), [&](NodeID a, NodeID b) {
            return node_id_to_part.at(a)->get_max_live_vars() <
                   node_id_to_part.at(b)->get_max_live_vars();
        });

        // Try to merge pairs
        while (nodes_to_consider.size() > 1) {
            NodeID largest_node_id = nodes_to_consider.back();
            NodeID smallest_node_id = nodes_to_consider.front();

            if (try_merge_upart_nodes(largest_node_id, {smallest_node_id}, false)) {
                merge_cnt++;
                nodes_to_consider.erase(nodes_to_consider.begin()); // Remove smallest
            } else {
                nodes_to_consider.pop_back(); // Remove largest
            }
        }

        if (merge_cnt != 0) {
            total_merge_cnt += merge_cnt;
        } else {
            current_level++;
            mg->graph_gc();
            mg->levelize();
        }
    }

    return total_merge_cnt;
}

void PartitionMerger::check_mg() const {
    for ([[maybe_unused]] const auto &pair : node_id_to_part) {
        assert(pair.second->get_max_live_vars() != -1);
    }
    mg->check_graph();
}

bool PartitionMerger::try_merge_upart_nodes(NodeID to, const std::vector<NodeID> &from_nodes,
                                            bool check_acyclic) {
    std::unordered_set<NodeID> all_nodes = {to};
    all_nodes.insert(from_nodes.begin(), from_nodes.end());
    assert(all_nodes.size() == (from_nodes.size() + 1));

    if (check_acyclic) {
        if (!mg->merge_is_acyclic(all_nodes)) {
            return false;
        }
    }

    for ([[maybe_unused]] NodeID n : all_nodes) {
        assert(node_id_to_part.contains(n));
        assert(!exclude_part_ids.contains(n));
    }

    // Create new merged partition
    auto new_part = std::make_unique<MicroPartition>(*node_id_to_part[to]);
    std::unordered_set<NodeID> new_nodes;
    for (NodeID n : from_nodes) {
        const auto &from_part = node_id_to_part[n];
        new_nodes.insert(from_part->get_nodes().begin(), from_part->get_nodes().end());
    }

    assert(!new_nodes.empty());
    if (!new_part->try_add_nodes(new_nodes)) {
        return false;
    }

    // OK to merge
    node_id_to_part[to] = std::move(new_part);
    mg->merge_nodes(to, from_nodes);

    for (NodeID n : from_nodes) {
        node_id_to_part.erase(n);
    }

    return true;
}
