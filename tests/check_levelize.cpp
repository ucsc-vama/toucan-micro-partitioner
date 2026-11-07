#include "MergeGraph.h"
#include <algorithm>
#include <iostream>
#include <random>
#include <stdexcept>
#include <string>
#include <utility>

static void require(bool condition, const std::string &message) {
    if (!condition)
        throw std::runtime_error(message);
}

// Always start from scratch, using the public graph and its current edge order.
static std::vector<std::vector<NodeID>> reference_levels(const MergeGraph &graph) {
    std::vector<int> degrees(graph.node_id_capacity());
    std::vector<NodeID> ready;
    for (NodeID node = 0; static_cast<size_t>(node) < graph.node_id_capacity(); ++node) {
        if (!graph.has_node(node))
            continue;
        degrees[node] = graph.get_node_in_degree(node);
        if (degrees[node] == 0)
            ready.push_back(node);
    }

    std::vector<std::vector<NodeID>> result;
    size_t visited = 0;
    while (!ready.empty()) {
        result.push_back(ready);
        visited += ready.size();
        std::vector<NodeID> next;
        for (NodeID node : ready) {
            for (NodeID successor : graph.get_node_successors(node)) {
                require(graph.has_node(successor), "Edge to removed node");
                if (--degrees[successor] == 0)
                    next.push_back(successor);
            }
        }
        ready = std::move(next);
    }
    require(visited == graph.num_nodes(), "Test graph must be acyclic");
    return result;
}

static void check(MergeGraph &graph) {
    auto expected = reference_levels(graph);
    graph.levelize();
    require(graph.get_levels() == expected, "Level contents or traversal order differ");
    for (size_t level = 0; level < expected.size(); ++level) {
        for (NodeID node : expected[level]) {
            require(graph.get_node_to_level()[node] == static_cast<int>(level),
                    "Node-to-level map differs");
        }
    }
    graph.levelize();
    require(graph.get_levels() == expected, "Repeated levelization differs");
}

static MergeGraph chain(int length) {
    MergeGraph graph;
    graph.reserve_nodes(length);
    for (int i = 0; i < length; ++i)
        graph.add_node();
    for (NodeID i = 1; i < length; ++i)
        graph.add_edge(i - 1, i);
    return graph;
}

static void check_boundaries() {
    auto graph = chain(16);
    for (int i = 16; i < 22; ++i)
        graph.add_node();
    graph.add_edges(
        {{15, 18}, {15, 16}, {15, 17}, {18, 20}, {16, 20}, {17, 19}, {20, 21}, {19, 21}});
    check(graph);
    require(graph.get_levels()[16] == std::vector<NodeID>({18, 16, 17}), "Initial order");

    // Added parallel edges change queue order at the first affected level.
    // Reusing that level without replaying its predecessor would be incorrect.
    graph.merge_nodes(18, {16});
    graph.graph_gc();
    check(graph);
    require(graph.get_levels()[16] == std::vector<NodeID>({17, 18}), "Merged order");

    graph.add_edge(15, 17);
    check(graph);
    require(graph.get_levels()[16] == std::vector<NodeID>({18, 17}), "Added-edge order");
    graph.edge_dedup();
    check(graph);

    auto added = graph.add_node();
    check(graph);
    graph.add_edge(21, added);
    check(graph);

    // Track the earliest change across several contractions before collection.
    auto batched = chain(64);
    check(batched);
    batched.merge_nodes(50, {51});
    batched.merge_nodes(60, {61, 62});
    batched.graph_gc();
    check(batched);
    // The retained node can itself move to an earlier level.
    batched.merge_nodes(54, {53});
    batched.graph_gc();
    check(batched);
    batched.merge_nodes(0, {1});
    batched.graph_gc();
    check(batched);
}

static void check_random_merges() {
    for (unsigned seed = 0; seed < 64; ++seed) {
        std::mt19937 random(seed);
        auto graph = chain(32);
        std::vector<NodeID> previous = {31};
        std::vector<std::pair<NodeID, NodeID>> edges;
        for (int layer = 0; layer < 10; ++layer) {
            std::vector<NodeID> current;
            for (int i = 0; i < 6; ++i) {
                auto node = graph.add_node();
                current.push_back(node);
                for (int j = 0; j < 3; ++j)
                    edges.emplace_back(previous[random() % previous.size()], node);
                if (random() % 2)
                    edges.emplace_back(random() % 32, node);
            }
            previous = std::move(current);
        }
        std::shuffle(edges.begin(), edges.end(), random);
        graph.add_edges(edges);
        check(graph);

        for (int iteration = 0; iteration < 40; ++iteration) {
            std::vector<size_t> candidates;
            const auto &levels = graph.get_levels();
            for (size_t i = 0; i < levels.size(); ++i) {
                if (levels[i].size() >= 2)
                    candidates.push_back(i);
            }
            if (candidates.empty())
                break;
            const auto &level = levels[candidates[random() % candidates.size()]];
            size_t a = random() % level.size();
            size_t b = (a + 1 + random() % (level.size() - 1)) % level.size();
            graph.merge_nodes(level[a], {level[b]});
            graph.graph_gc();
            check(graph);
            if (iteration % 7 == 0) {
                graph.edge_dedup();
                check(graph);
            }
        }
    }
}

int main() {
    try {
        check_boundaries();
        check_random_merges();
        std::cout << "Levelization checks passed\n";
    } catch (const std::exception &error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
