#include "MergeGraph.h"
#include <algorithm>
#include <cassert>
#include <functional>
#include <iostream>
#include <queue>
#include <stdexcept>

MergeGraph::MergeGraph() : next_id(0) {}

int MergeGraph::add_node() {
    int node_id = next_id++;
    adjacency_list[node_id] = {};
    reverse_adjacency_list[node_id] = {};
    return node_id;
}

void MergeGraph::add_edge(int source, int target) {
    adjacency_list[source].push_back(target);
    reverse_adjacency_list[target].push_back(source);
}

void MergeGraph::add_edges(const std::vector<std::pair<int, int>> &edges) {
    for (const auto &edge : edges) {
        add_edge(edge.first, edge.second);
    }
}

std::vector<int> MergeGraph::get_node_successors(int node) const {
    auto it = adjacency_list.find(node);
    if (it != adjacency_list.end()) {
        return it->second;
    }
    return {};
}

std::vector<int> MergeGraph::get_node_predecessors(int node) const {
    auto it = reverse_adjacency_list.find(node);
    if (it != reverse_adjacency_list.end()) {
        return it->second;
    }
    return {};
}

int MergeGraph::get_node_in_degree(int node) const {
    if (reverse_adjacency_list.contains(node)) {
        return reverse_adjacency_list.at(node).size();
    }
    return 0;
}

bool MergeGraph::has_node(int node) const { return adjacency_list.contains(node); }

int MergeGraph::max_node() const {
    if (adjacency_list.empty()) {
        return -1; // No nodes in graph
    }

    int max_id = -1;
    for (const auto &pair : adjacency_list) {
        max_id = std::max(max_id, pair.first);
    }
    return max_id;
}

bool MergeGraph::merge_is_acyclic(const std::unordered_set<int> &nodes_to_merge) {
    if (levels.empty()) {
        levelize();
    }

    // Group nodes by level
    std::vector<std::pair<int, std::vector<int>>> node_groups_by_level;
    std::unordered_map<int, std::vector<int>> level_to_nodes;

    for (int node : nodes_to_merge) {
        int level = node_to_level[node];
        level_to_nodes[level].push_back(node);
    }

    for (const auto &pair : level_to_nodes) {
        node_groups_by_level.emplace_back(pair.first, pair.second);
    }

    std::sort(node_groups_by_level.begin(), node_groups_by_level.end());

    if (node_groups_by_level.size() <= 1) {
        return true; // Single level, always acyclic
    }

    // Check for external paths between different levels
    for (size_t i = 0; i < node_groups_by_level.size(); ++i) {
        int source_level = node_groups_by_level[i].first;
        const std::vector<int> &source_nodes = node_groups_by_level[i].second;

        std::unordered_set<int> visited;
        std::queue<int> queue;

        // Start BFS from source nodes
        for (int node : source_nodes) {
            queue.push(node);
            visited.insert(node);
        }

        while (!queue.empty()) {
            int current = queue.front();
            queue.pop();

            if (adjacency_list.contains(current)) {
                for (auto &successor : adjacency_list[current]) {
                    if (visited.count(successor))
                        continue;

                    // Check if this successor is in nodes_to_merge but at a
                    // different level
                    if (nodes_to_merge.count(successor)) {
                        int succ_level = node_to_level[successor];
                        if (succ_level != source_level) {
                            // Found external path between merge nodes at
                            // different levels
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
    }

    return true;
}

void MergeGraph::merge_nodes(int to, const std::vector<int> &from_list) {
    std::unordered_set<int> from_set(from_list.begin(), from_list.end());

    // Collect new edges for the 'to' node
    std::unordered_set<int> new_predecessors;
    std::unordered_set<int> new_successors;

    for (int from_node : from_list) {
        // Add predecessors
        for (int pred : get_node_predecessors(from_node)) {
            if (pred != to && from_set.find(pred) == from_set.end()) {
                new_predecessors.insert(pred);
            }
        }

        // Add successors
        for (int succ : get_node_successors(from_node)) {
            if (succ != to && from_set.find(succ) == from_set.end()) {
                new_successors.insert(succ);
            }
        }
    }

    // Add new edges
    for (int pred : new_predecessors) {
        add_edge(pred, to);
    }
    for (int succ : new_successors) {
        add_edge(to, succ);
    }

    // Remove the merged nodes
    for (int from_node : from_list) {
        nodes_to_remove.insert(from_node);
    }
}

void MergeGraph::graph_gc() {
    for (int node : nodes_to_remove) {
        // Remove all edges involving this node
        for (int pred : get_node_predecessors(node)) {
            auto &successors = adjacency_list[pred];
            successors.erase(std::remove(successors.begin(), successors.end(), node),
                             successors.end());
        }

        for (int succ : get_node_successors(node)) {
            auto &predecessors = reverse_adjacency_list[succ];
            predecessors.erase(std::remove(predecessors.begin(), predecessors.end(), node),
                               predecessors.end());
        }

        // Remove node from adjacency lists
        adjacency_list.erase(node);
        reverse_adjacency_list.erase(node);
    }

    nodes_to_remove.clear();
}

void MergeGraph::edge_dedup() {
    // Remove parallel edges by converting vectors to sets and back
    for (auto &pair : adjacency_list) {
        auto &successors = pair.second;
        if (successors.size() > 1) {
            // Convert to set to remove duplicates, then back to vector
            std::unordered_set<int> unique_successors(successors.begin(), successors.end());
            successors.assign(unique_successors.begin(), unique_successors.end());
            // Sort for consistent ordering
            std::sort(successors.begin(), successors.end());
        }
    }

    // Do the same for reverse adjacency list
    for (auto &pair : reverse_adjacency_list) {
        auto &predecessors = pair.second;
        if (predecessors.size() > 1) {
            // Convert to set to remove duplicates, then back to vector
            std::unordered_set<int> unique_predecessors(predecessors.begin(), predecessors.end());
            predecessors.assign(unique_predecessors.begin(), unique_predecessors.end());
            // Sort for consistent ordering
            std::sort(predecessors.begin(), predecessors.end());
        }
    }
}

void MergeGraph::check_graph() const {
    if (!is_acyclic()) {
        throw std::runtime_error("Graph contains cycles");
    }
}

void MergeGraph::levelize() {
    levels.clear();
    node_to_level.clear();

    // Calculate in-degrees
    auto max_node_id = max_node();
    assert(max_node_id >= 0);
    std::vector<int> in_degree;
    in_degree.resize(max_node_id + 1, -1);
    // std::unordered_map<int, int> in_degree;
    // in_degree.reserve(adjacency_list.size());
    for (const auto &pair : adjacency_list) {
        int node = pair.first;
        assert(static_cast<size_t>(node) < in_degree.size());
        in_degree[node] = get_node_in_degree(node);
    }

    // Topological sort using Kahn's algorithm
    std::queue<int> queue;
    for (int v = 0; v < static_cast<int>(in_degree.size()); v++) {
        auto degree = in_degree[v];
        if (degree == 0) {
            queue.push(v);
        }
    }

    int current_level = 0;
    while (!queue.empty()) {
        int level_size = queue.size();
        std::vector<int> current_level_nodes;

        for (int i = 0; i < level_size; ++i) {
            int node = queue.front();
            queue.pop();

            current_level_nodes.push_back(node);
            node_to_level[node] = current_level;

            // Reduce in-degree of successors
            if (adjacency_list.contains(node)) {
                for (auto &successor : adjacency_list[node]) {
                    in_degree[successor]--;
                    assert(in_degree[successor] >= 0);
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

bool MergeGraph::is_acyclic() const {
    // Use DFS to detect cycles
    std::unordered_set<int> white, gray, black;

    for (const auto &pair : adjacency_list) {
        white.insert(pair.first);
    }

    std::function<bool(int)> dfs = [&](int node) -> bool {
        white.erase(node);
        gray.insert(node);

        for (int successor : get_node_successors(node)) {
            if (gray.count(successor)) {
                return false; // Back edge found, cycle detected
            }
            if (white.count(successor) && !dfs(successor)) {
                return false;
            }
        }

        gray.erase(node);
        black.insert(node);
        return true;
    };

    while (!white.empty()) {
        int start = *white.begin();
        if (!dfs(start)) {
            return false;
        }
    }

    return true;
}

void MergeGraph::remove_edge(int from, int to) {
    auto &successors = adjacency_list[from];
    successors.erase(std::remove(successors.begin(), successors.end(), to), successors.end());

    auto &predecessors = reverse_adjacency_list[to];
    predecessors.erase(std::remove(predecessors.begin(), predecessors.end(), from),
                       predecessors.end());
}
