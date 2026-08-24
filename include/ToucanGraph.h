#pragma once

#include <memory>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>

enum class NodeTag : uint8_t {
    ConstDecl = 0,
    RegRead = 1,
    MemRead = 2,
    VecDecl = 3,
    VecDecl_LUT_NOP = 4,
    VecRead = 5,
    LUT = 6,
    VecArith = 7,
    VecLogic = 8,
    Print = 9,
    Stop = 10,
    RegWrite = 11,
    MemWrite = 12,
    UNKNOWN = 255
};

// Utility functions for NodeTag
NodeTag string_to_node_tag(const std::string &str);
const char *node_tag_to_string(NodeTag tag);
bool is_valid_node_tag(NodeTag tag);
bool is_exclude_node_tag(NodeTag tag);
bool is_merge_result_node_tag(NodeTag tag);

struct NodeAttributes {
    NodeTag tag;
    int weight;
    int level_id = -1;
    int original_vec_decl = -1; // For VecDecl_LUT_NOP nodes
};

class ToucanGraph {
  public:
    ToucanGraph();
    ~ToucanGraph() = default;

    // Core functionality
    void load(const std::string &file_path);
    void levelize();
    bool is_acyclic() const;
    bool is_levelized() const { return !levels.empty(); }

    // Graph manipulation
    void expand_VecDecl(const std::unordered_map<int, std::vector<int>> &vecDeclElements);
    void remove_ConstDecl();
    void save_vector_def_info(const std::string &filename) const;

    // Accessors
    const std::unordered_map<int, NodeAttributes> &get_nodes() const { return nodes; }
    const std::unordered_map<int, std::vector<int>> &get_adjacency_list() const {
        return adjacency_list;
    }
    const std::vector<std::vector<int>> &get_levels() const { return levels; }

    // Graph queries
    std::vector<int> get_predecessors(int node) const;
    std::vector<int> get_successors(int node) const;
    bool has_node(int node) const;
    bool has_edge(int from, int to) const;
    int get_in_degree(int node) const;
    int get_out_degree(int node) const;
    size_t num_nodes() const { return nodes.size(); }
    size_t num_edges() const { return edge_count; }
    int max_node() const;

    // Subgraph creation
    std::unique_ptr<ToucanGraph> create_subgraph(const std::unordered_set<int> &node_list) const;

  private:
    std::unordered_map<int, NodeAttributes> nodes;
    std::unordered_map<int, std::vector<int>> adjacency_list; // node -> list of successors
    std::unordered_map<int, std::vector<int>>
        reverse_adjacency_list; // node -> list of predecessors
    std::vector<std::vector<int>> levels;
    std::unordered_map<int, std::vector<int>> vecdecl_to_nop;
    int max_node_id = 0;
    size_t edge_count = 0;

    void add_node(int node_id, const NodeAttributes &attrs);
    void add_edge(int from, int to);
    void remove_node(int node_id);
    void remove_nodes(const std::vector<int> &nodes_to_remove);
};
