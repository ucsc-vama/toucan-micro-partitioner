#pragma once

#include "NodeID.h"
#include <string>
#include <unordered_map>
#include <vector>

namespace Utils {
// Count occurrences of elements in a vector
std::unordered_map<NodeID, int> count_elements(const std::vector<NodeID> &lst);

// Load vector information from file
std::unordered_map<NodeID, std::vector<NodeID>> load_vec_info_file(const std::string &filename);

// String utilities
std::vector<std::string> split(const std::string &str, char delimiter);
std::string trim(const std::string &str);

// Statistics utilities
double mean(const std::vector<int> &values);
double median(std::vector<int> values); // Note: takes copy to sort
int min_value(const std::vector<int> &values);
int max_value(const std::vector<int> &values);
} // namespace Utils
