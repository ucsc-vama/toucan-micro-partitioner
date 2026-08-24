#include "ToucanGraph.h"
#include "Utils.h"
#include <fstream>
#include <sstream>
#include <iostream>
#include <algorithm>
#include <queue>
#include <cassert>
#include <functional>
#include <stdexcept>

// NodeTag utility functions implementation
NodeTag string_to_node_tag(const std::string& str) {
    if (str == "ConstDecl") return NodeTag::ConstDecl;
    if (str == "RegRead") return NodeTag::RegRead;
    if (str == "MemRead") return NodeTag::MemRead;
    if (str == "VecDecl") return NodeTag::VecDecl;
    if (str == "VecDecl_LUT_NOP") return NodeTag::VecDecl_LUT_NOP;
    if (str == "VecRead") return NodeTag::VecRead;
    if (str == "LUT") return NodeTag::LUT;
    if (str == "VecArith") return NodeTag::VecArith;
    if (str == "VecLogic") return NodeTag::VecLogic;
    if (str == "Print") return NodeTag::Print;
    if (str == "Stop") return NodeTag::Stop;
    if (str == "RegWrite") return NodeTag::RegWrite;
    if (str == "MemWrite") return NodeTag::MemWrite;
    return NodeTag::UNKNOWN;
}

const char* node_tag_to_string(NodeTag tag) {
    switch (tag) {
        case NodeTag::ConstDecl: return "ConstDecl";
        case NodeTag::RegRead: return "RegRead";
        case NodeTag::MemRead: return "MemRead";
        case NodeTag::VecDecl: return "VecDecl";
        case NodeTag::VecDecl_LUT_NOP: return "VecDecl_LUT_NOP";
        case NodeTag::VecRead: return "VecRead";
        case NodeTag::LUT: return "LUT";
        case NodeTag::VecArith: return "VecArith";
        case NodeTag::VecLogic: return "VecLogic";
        case NodeTag::Print: return "Print";
        case NodeTag::Stop: return "Stop";
        case NodeTag::RegWrite: return "RegWrite";
        case NodeTag::MemWrite: return "MemWrite";
        case NodeTag::UNKNOWN: return "UNKNOWN";
    }
    return "UNKNOWN";
}

bool is_valid_node_tag(NodeTag tag) {
    return tag != NodeTag::UNKNOWN;
}

bool is_exclude_node_tag(NodeTag tag) {
    switch (tag) {
        case NodeTag::ConstDecl:
        case NodeTag::RegRead:
        case NodeTag::MemRead:
        case NodeTag::VecDecl:
        case NodeTag::VecRead:
        case NodeTag::VecArith:
        case NodeTag::VecLogic:
        case NodeTag::Print:
        case NodeTag::Stop:
        case NodeTag::RegWrite:
        case NodeTag::MemWrite:
            return true;
        default:
            return false;
    }
}

bool is_merge_result_node_tag(NodeTag tag) {
    return tag == NodeTag::VecArith || tag == NodeTag::VecRead;
}

ToucanGraph::ToucanGraph() : max_node_id(0), edge_count(0) {}

void ToucanGraph::load(const std::string& file_path) {
    std::ifstream file(file_path);
    if (!file.is_open()) {
        throw std::runtime_error("Cannot open file: " + file_path);
    }

    std::string line;
    int lineno = 0;
    int num_edges = 0, num_nodes = 0;
    std::vector<std::pair<int, int>> edges_to_add;
    std::unordered_set<int> invalid_nodes;

    while (std::getline(file, line)) {
        if (lineno == 0) {
            // Read the first line for number of edges and nodes
            std::istringstream iss(line);
            iss >> num_edges >> num_nodes;
            lineno++;
            continue;
        }

        std::vector<std::string> parts = Utils::split(line, ' ');
        if (parts.empty()) continue;

        int node_id = std::stoi(parts[0]);
        max_node_id = std::max(node_id, max_node_id);

        if (parts.size() < 3) {
            throw std::runtime_error("Node " + std::to_string(node_id) + " is missing weight or neighbors.");
        }

        std::string label = parts[1];
        if (label.empty()) {
            throw std::runtime_error("Node " + std::to_string(node_id) + " has an empty label, which is illegal.");
        }

        int weight = std::stoi(parts[2]);

        // Skip invalid nodes
        if (weight < 0) {
            invalid_nodes.insert(node_id);
            lineno++;
            continue;
        }

        // Convert string label to NodeTag enum
        NodeTag tag = string_to_node_tag(label);
        if (tag == NodeTag::UNKNOWN) {
            throw std::runtime_error("Unknown node tag/label '" + label + "' at node " + std::to_string(node_id));
        }

        // Add node
        NodeAttributes attrs;
        attrs.tag = tag;
        attrs.weight = weight;
        add_node(node_id, attrs);

        // Collect edges
        for (size_t i = 3; i < parts.size(); ++i) {
            int neighbor = std::stoi(parts[i]);
            edges_to_add.emplace_back(node_id, neighbor);
        }

        lineno++;
    }

    // Add all edges
    int actual_edge_count = 0;
    for (const auto& edge : edges_to_add) {
        int source = edge.first, target = edge.second;
        
        if (invalid_nodes.contains(source) || invalid_nodes.contains(target)) {
            continue;
        }
        
        if (!has_node(source) || !has_node(target)) {
            throw std::runtime_error("Edge from " + std::to_string(source) + 
                                   " to " + std::to_string(target) + " refers to non-existent node.");
        }
        
        add_edge(source, target);
        actual_edge_count++;
    }

    // Verify counts
    if (nodes.size() != static_cast<size_t>(num_nodes)) {
        throw std::runtime_error("Expected " + std::to_string(num_nodes) + 
                               " nodes, found " + std::to_string(nodes.size()));
    }
    if (actual_edge_count != num_edges) {
        throw std::runtime_error("Expected " + std::to_string(num_edges) + 
                               " edges, found " + std::to_string(actual_edge_count));
    }
}

void ToucanGraph::levelize() {
    if (!is_acyclic()) {
        throw std::runtime_error("The graph must be a Directed Acyclic Graph (DAG) to levelize.");
    }

    levels.clear();
    
    // Calculate in-degrees
    std::unordered_map<int, int> in_degree;
    for (const auto& node : nodes) {
        in_degree[node.first] = get_in_degree(node.first);
    }

    // Topological sort using Kahn's algorithm
    std::queue<int> queue;
    for (const auto& pair : in_degree) {
        if (pair.second == 0) {
            queue.push(pair.first);
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
            nodes[node].level_id = current_level;
            
            // Reduce in-degree of successors
            for (int successor : get_successors(node)) {
                in_degree[successor]--;
                if (in_degree[successor] == 0) {
                    queue.push(successor);
                }
            }
        }
        
        levels.push_back(current_level_nodes);
        current_level++;
    }
}

bool ToucanGraph::is_acyclic() const {
    // Use DFS to detect cycles
    std::unordered_set<int> white, gray, black;
    
    for (const auto& node : nodes) {
        white.insert(node.first);
    }
    
    std::function<bool(int)> dfs = [&](int node) -> bool {
        white.erase(node);
        gray.insert(node);
        
        for (int successor : get_successors(node)) {
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

void ToucanGraph::expand_VecDecl(const std::unordered_map<int, std::vector<int>>& vecDeclElements) {
    std::vector<int> vecDecl_node_ids;
    std::vector<int> nodes_to_remove;
    int num_new_nodes = 0;

    // Find all VecDecl nodes
    for (const auto& node : nodes) {
        if (node.second.tag == NodeTag::VecDecl) {
            vecDecl_node_ids.push_back(node.first);
            nodes_to_remove.push_back(node.first);
        }
    }

    for (int node : vecDecl_node_ids) {
        std::vector<int> vec_input_nodes = get_predecessors(node);
        std::vector<int> vec_user_nodes = get_successors(node);
        int weight = nodes[node].weight;

        // Vec info file should be consistent with graph info
        auto it = vecDeclElements.find(node);
        assert(it != vecDeclElements.end());

        const std::vector<int>& vec_element_op_ids = it->second;

        // At least one vecDecl element
        assert(weight > 0);
        int nop_node_weight = weight / vec_element_op_ids.size();
        assert(vec_input_nodes.size() <= static_cast<size_t>(weight));

        std::vector<int> new_node_list;
        for (size_t i = 0; i < vec_element_op_ids.size(); ++i) {
            // Insert NOP
            max_node_id++;
            int node_id = max_node_id;
            assert(!has_node(node_id));

            NodeAttributes attrs;
            attrs.tag = NodeTag::VecDecl_LUT_NOP;
            attrs.weight = nop_node_weight;
            attrs.original_vec_decl = node;
            add_node(node_id, attrs);
            new_node_list.push_back(node_id);

            int edge_src = vec_element_op_ids[i];
            assert(std::find(vec_input_nodes.begin(), vec_input_nodes.end(), edge_src) != vec_input_nodes.end());
            add_edge(edge_src, node_id);
            
            for (int d : vec_user_nodes) {
                add_edge(node_id, d);
            }
        }

        assert(vecdecl_to_nop.find(node) == vecdecl_to_nop.end());
        vecdecl_to_nop[node] = new_node_list;
        num_new_nodes += new_node_list.size();

        // Verify in-degree
        for ([[maybe_unused]] int new_node : new_node_list) {
            assert(get_in_degree(new_node) == 1);
        }
    }

    assert(nodes_to_remove.size() <= vecDeclElements.size());
    remove_nodes(nodes_to_remove);
    std::cout << "Expand " << nodes_to_remove.size() << " vectors, add " << num_new_nodes << " new VecDecl_LUT_NOP nodes\n";
}

void ToucanGraph::remove_ConstDecl() {
    std::vector<int> nodes_to_remove;
    for (const auto& node : nodes) {
        if (node.second.tag == NodeTag::ConstDecl) {
            nodes_to_remove.push_back(node.first);
        }
    }
    std::cout << "Remove " << nodes_to_remove.size() << " ConstDecl nodes\n";
    remove_nodes(nodes_to_remove);
}

void ToucanGraph::save_vector_def_info(const std::string& filename) const {
    std::ofstream out(filename);
    if (!out.is_open()) {
        throw std::runtime_error("Cannot open file for writing: " + filename);
    }

    for (const auto& pair : vecdecl_to_nop) {
        out << pair.first;
        for (int nop : pair.second) {
            out << " " << nop;
        }
        out << "\n";
    }
    out.close();
}

std::vector<int> ToucanGraph::get_predecessors(int node) const {
    if (reverse_adjacency_list.contains(node)) {
        return reverse_adjacency_list.at(node);
    }
    return {};
}

std::vector<int> ToucanGraph::get_successors(int node) const {
    if (adjacency_list.contains(node)) {
        return adjacency_list.at(node);
    }
    return {};
}

bool ToucanGraph::has_node(int node) const {
    return nodes.contains(node);
}

bool ToucanGraph::has_edge(int from, int to) const {
    auto it = adjacency_list.find(from);
    if (it != adjacency_list.end()) {
        const auto& successors = it->second;
        return std::find(successors.begin(), successors.end(), to) != successors.end();
    }
    return false;
}

int ToucanGraph::get_in_degree(int node) const {
    auto it = reverse_adjacency_list.find(node);
    return it != reverse_adjacency_list.end() ? it->second.size() : 0;
}

int ToucanGraph::get_out_degree(int node) const {
    auto it = adjacency_list.find(node);
    return it != adjacency_list.end() ? it->second.size() : 0;
}

int ToucanGraph::max_node() const {
    if (nodes.empty()) {
        return -1; // No nodes in graph
    }
    
    int max_id = -1;
    for (const auto& pair : nodes) {
        max_id = std::max(max_id, pair.first);
    }
    return max_id;
}

std::unique_ptr<ToucanGraph> ToucanGraph::create_subgraph(const std::unordered_set<int>& node_list) const {
    auto subgraph = std::make_unique<ToucanGraph>();
    
    // Add nodes
    for (int node : node_list) {
        if (has_node(node)) {
            subgraph->add_node(node, nodes.at(node));
        }
    }
    
    // Add edges
    for (int node : node_list) {
        for (int successor : get_successors(node)) {
            if (node_list.count(successor)) {
                subgraph->add_edge(node, successor);
            }
        }
    }
    
    return subgraph;
}

void ToucanGraph::add_node(int node_id, const NodeAttributes& attrs) {
    nodes[node_id] = attrs;
    adjacency_list[node_id] = {};
    reverse_adjacency_list[node_id] = {};
}

void ToucanGraph::add_edge(int from, int to) {
    adjacency_list[from].push_back(to);
    reverse_adjacency_list[to].push_back(from);
    edge_count++;
}

void ToucanGraph::remove_node(int node_id) {
    if (!has_node(node_id)) return;
    
    // Remove all edges involving this node
    for (int predecessor : get_predecessors(node_id)) {
        auto& successors = adjacency_list[predecessor];
        successors.erase(std::remove(successors.begin(), successors.end(), node_id), successors.end());
        edge_count--;
    }
    
    for (int successor : get_successors(node_id)) {
        auto& predecessors = reverse_adjacency_list[successor];
        predecessors.erase(std::remove(predecessors.begin(), predecessors.end(), node_id), predecessors.end());
    }
    
    // Remove node
    nodes.erase(node_id);
    adjacency_list.erase(node_id);
    reverse_adjacency_list.erase(node_id);
}

void ToucanGraph::remove_nodes(const std::vector<int>& nodes_to_remove) {
    for (int node : nodes_to_remove) {
        remove_node(node);
    }
}
