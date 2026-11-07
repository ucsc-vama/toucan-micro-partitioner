#include "MergeGraph.h"
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <functional>
#include <queue>
#include <stdexcept>

namespace {
enum VisitColor : uint8_t {
    kUnvisited,
    kVisiting,
    kVisited,
};
} // namespace

MergeGraph::MergeGraph() = default;

void MergeGraph::reserve_nodes(size_t node_count) {
    adjacency_list.reserve(node_count);
    reverse_adjacency_list.reserve(node_count);
    active.reserve(node_count);
    node_to_level.reserve(node_count);
    in_degree.reserve(node_count);
    levelize_queue.reserve(node_count);
    pending_removal.reserve(node_count);
}

NodeID MergeGraph::add_node() {
    first_dirty_level = 0;
    NodeID node_id = next_id++;
    adjacency_list.emplace_back();
    reverse_adjacency_list.emplace_back();
    active.push_back(true);
    live_node_count++;
    node_to_level.push_back(-1);
    in_degree.push_back(0);
    pending_removal.push_back(false);
    return node_id;
}

void MergeGraph::add_edge(NodeID source, NodeID target) {
    first_dirty_level = 0;
    append_edge(source, target);
}

void MergeGraph::append_edge(NodeID source, NodeID target) {
    assert(has_node(source));
    assert(has_node(target));
    adjacency_list[source].push_back(target);
    reverse_adjacency_list[target].push_back(source);
}

void MergeGraph::add_edges(const std::vector<std::pair<NodeID, NodeID>> &edges) {
    for (const auto &edge : edges) {
        add_edge(edge.first, edge.second);
    }
}

const std::vector<NodeID> &MergeGraph::get_node_successors(NodeID node) const {
    if (has_node(node)) {
        return adjacency_list[node];
    }
    static const std::vector<NodeID> empty;
    return empty;
}

const std::vector<NodeID> &MergeGraph::get_node_predecessors(NodeID node) const {
    if (has_node(node)) {
        return reverse_adjacency_list[node];
    }
    static const std::vector<NodeID> empty;
    return empty;
}

int MergeGraph::get_node_in_degree(NodeID node) const {
    return has_node(node) ? static_cast<int>(reverse_adjacency_list[node].size()) : 0;
}

bool MergeGraph::has_node(NodeID node) const {
    return node >= 0 && static_cast<size_t>(node) < active.size() && active[node];
}

bool MergeGraph::merge_is_acyclic(const std::unordered_set<NodeID> &nodes_to_merge) {
    if (levels.empty()) {
        levelize();
    }

    // Merge candidates are small, so a vector avoids a hash allocation here.
    std::vector<std::pair<int, std::vector<NodeID>>> node_groups_by_level;
    for (NodeID node : nodes_to_merge) {
        int level = node_to_level.at(node);
        auto group_it = std::find_if(node_groups_by_level.begin(), node_groups_by_level.end(),
                                     [level](const auto &group) { return group.first == level; });
        if (group_it == node_groups_by_level.end()) {
            node_groups_by_level.emplace_back(level, std::vector<NodeID>{node});
        } else {
            group_it->second.push_back(node);
        }
    }

    std::sort(node_groups_by_level.begin(), node_groups_by_level.end());

    if (node_groups_by_level.size() <= 1) {
        return true; // Single level, always acyclic
    }

    // Check for external paths between different levels
    for (const auto &[source_level, source_nodes] : node_groups_by_level) {
        std::unordered_set<NodeID> visited;
        std::queue<NodeID> queue;

        // Start BFS from source nodes
        for (NodeID node : source_nodes) {
            queue.push(node);
            visited.insert(node);
        }

        while (!queue.empty()) {
            NodeID current = queue.front();
            queue.pop();

            for (NodeID successor : adjacency_list[current]) {
                if (visited.count(successor))
                    continue;

                // Check if this successor is in nodes_to_merge but at a different level
                if (nodes_to_merge.count(successor)) {
                    int succ_level = node_to_level[successor];
                    if (succ_level != source_level) {
                        return false;
                    }
                } else {
                    // Continue BFS through external nodes
                    visited.insert(successor);
                    queue.push(successor);
                }
            }
        }
    }

    return true;
}

void MergeGraph::merge_nodes(NodeID to, const std::vector<NodeID> &from_list) {
    // Contracting a group cannot affect levels before its earliest member. Keep
    // that prefix, including its traversal order, until the next levelization.
    first_dirty_level = std::min(first_dirty_level, std::max(0, node_to_level[to]));
    for (NodeID from : from_list) {
        first_dirty_level = std::min(first_dirty_level, std::max(0, node_to_level[from]));
    }
    std::unordered_set<NodeID> from_set(from_list.begin(), from_list.end());

    // Collect new edges for the 'to' node
    std::unordered_set<NodeID> new_predecessors;
    std::unordered_set<NodeID> new_successors;

    for (NodeID from_node : from_list) {
        // Add predecessors
        for (NodeID pred : get_node_predecessors(from_node)) {
            if (pred != to && from_set.find(pred) == from_set.end()) {
                new_predecessors.insert(pred);
            }
        }

        // Add successors
        for (NodeID succ : get_node_successors(from_node)) {
            if (succ != to && from_set.find(succ) == from_set.end()) {
                new_successors.insert(succ);
            }
        }
    }

    // Add new edges
    for (NodeID pred : new_predecessors) {
        append_edge(pred, to);
    }
    for (NodeID succ : new_successors) {
        append_edge(to, succ);
    }

    // Remove the merged nodes
    for (NodeID from_node : from_list) {
        if (!pending_removal[from_node]) {
            pending_removal[from_node] = true;
            nodes_to_remove.push_back(from_node);
        }
    }
}

void MergeGraph::graph_gc() {
    for (NodeID node : nodes_to_remove) {
        assert(has_node(node));
        first_dirty_level = std::min(first_dirty_level, std::max(0, node_to_level[node]));

        // Remove all edges involving this node
        for (NodeID pred : get_node_predecessors(node)) {
            auto &successors = adjacency_list[pred];
            successors.erase(std::remove(successors.begin(), successors.end(), node),
                             successors.end());
        }

        for (NodeID succ : get_node_successors(node)) {
            auto &predecessors = reverse_adjacency_list[succ];
            predecessors.erase(std::remove(predecessors.begin(), predecessors.end(), node),
                               predecessors.end());
        }

        // Free the adjacency storage for removed nodes while preserving their stable IDs.
        std::vector<NodeID>().swap(adjacency_list[node]);
        std::vector<NodeID>().swap(reverse_adjacency_list[node]);
        pending_removal[node] = false;
        active[node] = false;
        live_node_count--;
    }

    nodes_to_remove.clear();
}

void MergeGraph::edge_dedup() {
    // Sorting adjacency lists can change Kahn's traversal order even when the
    // graph's levels do not change.
    first_dirty_level = 0;
    // Sort each adjacency list, then remove parallel edges in place.
    for (NodeID node = 0; node < next_id; ++node) {
        if (!active[node]) {
            continue;
        }
        auto &successors = adjacency_list[node];
        if (successors.size() > 1) {
            std::sort(successors.begin(), successors.end());
            successors.erase(std::unique(successors.begin(), successors.end()), successors.end());
        }
    }

    // Do the same for reverse adjacency list
    for (NodeID node = 0; node < next_id; ++node) {
        if (!active[node]) {
            continue;
        }
        auto &predecessors = reverse_adjacency_list[node];
        if (predecessors.size() > 1) {
            std::sort(predecessors.begin(), predecessors.end());
            predecessors.erase(std::unique(predecessors.begin(), predecessors.end()),
                               predecessors.end());
        }
    }
}

void MergeGraph::check_graph() const {
    if (!is_acyclic()) {
        throw std::runtime_error("Graph contains cycles");
    }
}

void MergeGraph::levelize() {
    assert(live_node_count != 0);

    if (!levels.empty() && static_cast<size_t>(first_dirty_level) == levels.size()) {
        return;
    }

    // Replay the unchanged level immediately before the affected region. Its
    // outgoing edges determine the exact queue order of the first changed level.
    int start_level = std::max(0, first_dirty_level - 1);
    size_t prefix_nodes = 0;
    for (int level = 0; level < start_level; ++level) {
        prefix_nodes += levels[level].size();
    }
    // Rebuilding a suffix also scans its incoming edges. Use the full traversal
    // when too little of the graph can be skipped to offset that extra work.
    if (prefix_nodes < live_node_count / 2) {
        start_level = 0;
    }

    levelize_queue.clear();
    if (start_level == 0) {
        // Calculate in-degrees and initialize the topological-sort queue.
        for (NodeID node = 0; node < next_id; ++node) {
            if (!active[node]) {
                continue;
            }
            in_degree[node] = static_cast<int>(reverse_adjacency_list[node].size());
            node_to_level[node] = -1;
            if (in_degree[node] == 0) {
                levelize_queue.push_back(node);
            }
        }
    } else {
        levelize_queue.assign(levels[start_level].begin(), levels[start_level].end());
        for (size_t level = start_level + 1; level < levels.size(); ++level) {
            for (NodeID node : levels[level]) {
                if (!active[node]) {
                    continue;
                }
                int remaining = 0;
                for (NodeID pred : reverse_adjacency_list[node]) {
                    remaining += node_to_level[pred] >= start_level;
                }
                // Nodes in the affected region cannot move into the saved prefix.
                assert(remaining > 0);
                in_degree[node] = remaining;
            }
        }
    }

    // Topological sort using Kahn's algorithm. Reuse storage from prior runs.
    size_t queue_head = 0;
    size_t level_index = start_level;
    int current_level = start_level;
    while (queue_head < levelize_queue.size()) {
        size_t level_end = levelize_queue.size();
        if (level_index == levels.size()) {
            levels.emplace_back();
        }
        auto &current_level_nodes = levels[level_index];
        current_level_nodes.clear();
        current_level_nodes.reserve(level_end - queue_head);

        while (queue_head < level_end) {
            NodeID node = levelize_queue[queue_head++];
            current_level_nodes.push_back(node);
            node_to_level[node] = current_level;

            // Reduce in-degree of successors
            for (NodeID successor : adjacency_list[node]) {
                in_degree[successor]--;
                assert(in_degree[successor] >= 0);
                if (in_degree[successor] == 0) {
                    levelize_queue.push_back(successor);
                }
            }
        }

        level_index++;
        current_level++;
    }
    levels.resize(level_index);
    first_dirty_level = static_cast<int>(levels.size());
}

bool MergeGraph::is_acyclic() const {
    std::vector<uint8_t> color(next_id, kUnvisited);

    std::function<bool(NodeID)> dfs = [&](NodeID node) -> bool {
        color[node] = kVisiting;

        for (NodeID successor : adjacency_list[node]) {
            if (color[successor] == kVisiting) {
                return false; // Back edge found, cycle detected
            }
            if (color[successor] == kUnvisited && !dfs(successor)) {
                return false;
            }
        }

        color[node] = kVisited;
        return true;
    };

    for (NodeID node = 0; node < next_id; ++node) {
        if (active[node] && color[node] == kUnvisited && !dfs(node)) {
            return false;
        }
    }

    return true;
}
