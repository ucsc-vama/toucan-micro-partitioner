#include "Utils.h"
#include <algorithm>
#include <fstream>
#include <numeric>
#include <sstream>
#include <stdexcept>

namespace Utils {

std::unordered_map<int, int> count_elements(const std::vector<int> &lst) {
    std::unordered_map<int, int> counts;
    for (int num : lst) {
        counts[num]++;
    }
    return counts;
}

std::unordered_map<int, std::vector<int>> load_vec_info_file(const std::string &filename) {
    std::unordered_map<int, std::vector<int>> ret;
    std::ifstream file(filename);
    if (!file.is_open()) {
        throw std::runtime_error("Cannot open file: " + filename);
    }

    std::string line;
    int lineno = 0;
    while (std::getline(file, line)) {
        if (lineno < 2) {
            lineno++;
            continue;
        }

        std::vector<std::string> parts = split(line, ' ');
        if (parts.empty())
            continue;

        std::vector<int> dat;
        for (const std::string &part : parts) {
            if (!part.empty()) {
                dat.push_back(std::stoi(part));
            }
        }

        // A vector should have more than 1 element
        if (dat.size() < 2)
            continue;

        int vecDecl_node_id = dat[0];
        std::vector<int> vecElem_ids(dat.begin() + 1, dat.end());

        if (ret.find(vecDecl_node_id) != ret.end()) {
            throw std::runtime_error("Duplicate vecDecl_node_id: " +
                                     std::to_string(vecDecl_node_id));
        }
        ret[vecDecl_node_id] = vecElem_ids;
        lineno++;
    }
    return ret;
}

std::vector<std::string> split(const std::string &str, char delimiter) {
    std::vector<std::string> tokens;
    std::stringstream ss(str);
    std::string token;

    while (std::getline(ss, token, delimiter)) {
        if (!token.empty()) {
            tokens.push_back(token);
        }
    }
    return tokens;
}

std::string trim(const std::string &str) {
    size_t start = str.find_first_not_of(" \t\n\r");
    if (start == std::string::npos)
        return "";

    size_t end = str.find_last_not_of(" \t\n\r");
    return str.substr(start, end - start + 1);
}

double mean(const std::vector<int> &values) {
    if (values.empty())
        return 0.0;
    return static_cast<double>(std::accumulate(values.begin(), values.end(), 0)) / values.size();
}

double median(std::vector<int> values) {
    if (values.empty())
        return 0.0;

    std::sort(values.begin(), values.end());
    size_t n = values.size();

    if (n % 2 == 0) {
        return (values[n / 2 - 1] + values[n / 2]) / 2.0;
    } else {
        return values[n / 2];
    }
}

int min_value(const std::vector<int> &values) {
    if (values.empty())
        throw std::runtime_error("Cannot find min of empty vector");
    return *std::min_element(values.begin(), values.end());
}

int max_value(const std::vector<int> &values) {
    if (values.empty())
        throw std::runtime_error("Cannot find max of empty vector");
    return *std::max_element(values.begin(), values.end());
}

} // namespace Utils
