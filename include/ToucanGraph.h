#pragma once

#include "NodeID.h"
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
    NodeID original_vec_decl = -1; // For VecDecl_LUT_NOP nodes
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
    void expand_VecDecl(const std::unordered_map<NodeID, std::vector<NodeID>> &vecDeclElements);
    void remove_ConstDecl();
    void save_vector_def_info(const std::string &filename) const;

    // Accessors
    const std::unordered_map<NodeID, NodeAttributes> &get_nodes() const { return nodes; }
    const std::unordered_map<NodeID, std::vector<NodeID>> &get_adjacency_list() const {
        return adjacency_list;
    }
    const std::vector<std::vector<NodeID>> &get_levels() const { return levels; }

    // Graph queries
    const std::vector<NodeID> &get_predecessors(NodeID node) const;
    const std::vector<NodeID> &get_successors(NodeID node) const;
    bool has_node(NodeID node) const;
    bool has_edge(NodeID from, NodeID to) const;
    int get_in_degree(NodeID node) const;
    int get_out_degree(NodeID node) const;
    size_t num_nodes() const { return nodes.size(); }
    size_t num_edges() const { return edge_count; }
    NodeID max_node() const;

    // Subgraph creation
    std::unique_ptr<ToucanGraph> create_subgraph(const std::unordered_set<NodeID> &node_list) const;

  private:
    std::unordered_map<NodeID, NodeAttributes> nodes;
    std::unordered_map<NodeID, std::vector<NodeID>> adjacency_list; // node -> list of successors
    std::unordered_map<NodeID, std::vector<NodeID>>
        reverse_adjacency_list; // node -> list of predecessors
    std::vector<std::vector<NodeID>> levels;
    std::unordered_map<NodeID, std::vector<NodeID>> vecdecl_to_nop;
    NodeID max_node_id = 0;
    size_t edge_count = 0;

    void add_node(NodeID node_id, const NodeAttributes &attrs);
    void add_edge(NodeID from, NodeID to);
    void remove_node(NodeID node_id);
    void remove_nodes(const std::vector<NodeID> &nodes_to_remove);
};
