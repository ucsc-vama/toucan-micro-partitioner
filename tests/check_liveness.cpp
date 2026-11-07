#include "MicroPartition.h"
#include <algorithm>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>

struct Node {
    std::string tag;
    std::vector<NodeID> successors;
};

static ToucanGraph load_graph(const std::filesystem::path &path, const std::vector<Node> &nodes) {
    size_t edges = 0;
    for (const auto &node : nodes)
        edges += node.successors.size();
    std::ofstream out(path);
    out << edges << ' ' << nodes.size() << '\n';
    for (size_t i = 0; i < nodes.size(); ++i) {
        out << i << ' ' << nodes[i].tag << " 1";
        for (NodeID successor : nodes[i].successors)
            out << ' ' << successor;
        out << '\n';
    }
    out.close();
    if (!out)
        throw std::runtime_error("Cannot write test graph");
    ToucanGraph graph;
    graph.load(path.string());
    return graph;
}

static void require(bool condition, const std::string &message) {
    if (!condition)
        throw std::runtime_error(message);
}

static void expect(const std::string &name, const ToucanGraph &graph,
                   const std::unordered_set<NodeID> &nodes, bool accepted, int inputs = 0,
                   int outputs = 0, int peak = 0) {
    MicroPartition part(&graph);
    require(part.try_add_nodes(nodes) == accepted, name + ": acceptance");
    if (accepted) {
        require(part.get_num_input_vars() == inputs, name + ": inputs");
        require(part.get_num_output_vars() == outputs, name + ": outputs");
        require(part.get_max_live_vars() == peak, name + ": peak liveness");
    }
}

static void check_liveness(const std::filesystem::path &path) {
    // One scalar input is shared by consumers at different levels. Parallel
    // edges to a scalar consumer still refer to the same live value.
    auto shared =
        load_graph(path, {{"RegRead", {1, 1, 2}}, {"LUT", {2}}, {"LUT", {3}}, {"RegWrite", {}}});
    expect("shared scalar", shared, {1, 2}, true, 1, 1, 2);
    expect("shared scalar reversed insertion", shared, {2, 1}, true, 1, 1, 2);

    MicroPartition original(&shared);
    require(original.try_add_nodes({1}), "initial partition");
    MicroPartition candidate(original);
    require(candidate.try_add_nodes({2}), "candidate partition");
    require(original.get_nodes().size() == 1 && original.get_max_live_vars() == 1,
            "candidate must preserve the original partition");
    require(candidate.get_max_live_vars() == 2, "candidate liveness");

    // Each vector-result edge is distinct, including repeated edges from the
    // same producer to the same consumer.
    for (const std::string tag : {"VecRead", "VecArith"}) {
        auto graph =
            load_graph(path, {{tag, {1, 1, 2}}, {"LUT", {2}}, {"LUT", {3}}, {"RegWrite", {}}});
        expect(tag, graph, {1, 2}, true, 3, 1, 3);
    }

    // Values consumed and produced in the same level reuse their storage.
    std::vector<Node> chain = {{"RegRead", {1}}};
    std::unordered_set<NodeID> chain_nodes;
    for (NodeID i = 1; i <= 40; ++i) {
        chain.push_back({"LUT", {i + 1}});
        chain_nodes.insert(i);
    }
    chain.push_back({"RegWrite", {}});
    auto chain_graph = load_graph(path, chain);
    expect("long chain", chain_graph, chain_nodes, true, 1, 1, 1);

    for (int width : {32, 33}) {
        // Independent inputs and outputs exercise both sides of the warp limit.
        std::vector<Node> parallel;
        std::unordered_set<NodeID> part_nodes;
        for (NodeID i = 0; i < width; ++i)
            parallel.push_back({"RegRead", {width + i}});
        for (NodeID i = 0; i < width; ++i) {
            parallel.push_back({"LUT", {2 * width + i}});
            part_nodes.insert(width + i);
        }
        for (int i = 0; i < width; ++i)
            parallel.push_back({"RegWrite", {}});
        auto graph = load_graph(path, parallel);
        expect("parallel width " + std::to_string(width), graph, part_nodes, width == 32, width,
               width, width);

        // A single shared input can still produce too many simultaneously live outputs.
        std::vector<Node> fanout = {{"RegRead", {}}};
        part_nodes.clear();
        for (NodeID i = 1; i <= width; ++i) {
            fanout[0].successors.push_back(i);
            fanout.push_back({"LUT", {width + 1}});
            part_nodes.insert(i);
        }
        fanout.push_back({"RegWrite", {}});
        auto fanout_graph = load_graph(path, fanout);
        expect("output width " + std::to_string(width), fanout_graph, part_nodes, width == 32, 1,
               width, width);

        // Consume the fanout through a chain of two-input nodes. Inputs and
        // outputs both fit in one slot, but the intermediate width can exceed
        // the limit.
        fanout.pop_back();
        for (NodeID i = 1; i <= width; ++i)
            fanout[i].successors = {width + std::max(1, i - 1)};
        for (NodeID i = width + 1; i < 2 * width; ++i) {
            fanout.push_back({"LUT", {i + 1}});
            part_nodes.insert(i);
        }
        fanout.push_back({"RegWrite", {}});
        auto intermediate_graph = load_graph(path, fanout);
        expect("intermediate width " + std::to_string(width), intermediate_graph, part_nodes,
               width == 32, 1, 1, width);
    }
}

int main(int argc, char **argv) {
    if (argc != 2) {
        std::cerr << "Usage: check_liveness <temporary-graph-path>\n";
        return 1;
    }
    try {
        check_liveness(argv[1]);
        std::filesystem::remove(argv[1]);
        std::cout << "Liveness checks passed\n";
    } catch (const std::exception &error) {
        std::filesystem::remove(argv[1]);
        std::cerr << error.what() << '\n';
        return 1;
    }
}
