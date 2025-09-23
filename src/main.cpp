#include "ToucanGraph.h"
#include "MicroPartition.h"
#include "PartitionMerger.h"
#include "Utils.h"
#include <iostream>
#include <string>
#include <chrono>

struct Args {
    std::string graph;
    std::string vector;
    std::string output;
    std::string vecmap;
    int max_part_size = 99999;
};

Args parse_args(int argc, char* argv[]) {
    Args args;
    
    for (int i = 1; i < argc; i++) {
        std::string arg = argv[i];
        
        if (arg == "--graph" && i + 1 < argc) {
            args.graph = argv[++i];
        } else if (arg == "--vector" && i + 1 < argc) {
            args.vector = argv[++i];
        } else if (arg == "--output" && i + 1 < argc) {
            args.output = argv[++i];
        } else if (arg == "--vecmap" && i + 1 < argc) {
            args.vecmap = argv[++i];
        } else if (arg == "--max-part-size" && i + 1 < argc) {
            args.max_part_size = std::stoi(argv[++i]);
        }
    }
    
    if (args.graph.empty() || args.vector.empty() || args.output.empty() || args.vecmap.empty()) {
        std::cerr << "Usage: " << argv[0] << " --graph <file> --vector <file> --output <file> --vecmap <file> [--max-part-size <size>]\n";
        exit(1);
    }
    
    return args;
}

int main(int argc, char* argv[]) {
    try {
        auto start_time = std::chrono::high_resolution_clock::now();
        
        Args args = parse_args(argc, argv);
        
        // Load vector information
        auto vecDeclElementsInfo = Utils::load_vec_info_file(args.vector);
        
        // Load and process graph
        ToucanGraph g;
        g.load(args.graph);
        g.expand_VecDecl(vecDeclElementsInfo);
        g.remove_ConstDecl();
        g.save_vector_def_info(args.vecmap);
        
        // Levelize the graph (required for partitioning)
        g.levelize();
        
        // Find nodes to exclude
        auto exclude_nodes = find_exclude_nodes(g);
        std::cout << exclude_nodes.size() << " nodes need to be excluded\n";
        
        // Partitioning
        std::cout << "> partitioning\n";
        auto parts = partitioner2(g, exclude_nodes);
        std::cout << "Found " << parts.size() << " partitions\n";

        
        // Merging
        std::cout << "> Working on merge\n";
        PartitionMerger merger(g, exclude_nodes);
        
        std::cout << "> Build part graph after initial partitioning\n";
        merger.build_part_mg(parts);
        merger.print_part_stat();

        int merge_cnt = 0;

        // Multiple merge phases
        std::cout << "> Merge with child\n";
        merge_cnt = merger.merge_direct_child();
        // int merge_cnt = merger.merge_direct_child();
        std::cout << "Merged " << merge_cnt << " parts\n";
        merger.print_part_stat();
        
        while (true) {
            std::cout << "> Merge with child\n";
            merge_cnt = merger.merge_direct_child();
            std::cout << "Merged " << merge_cnt << " parts\n";
            if (merge_cnt < 10) break;
        }
        merger.print_part_stat();
        
        while (true) {
            std::cout << "> Merge adjacent groups\n";
            merge_cnt = merger.merge_adjacent_group();
            std::cout << merge_cnt << " merge ops\n";
            if (merge_cnt == 0) break;
        }
        merger.print_part_stat();

        
        while (true) {
            std::cout << "> Merge siblings\n";
            merge_cnt = merger.merge_siblings();
            std::cout << merge_cnt << " merge ops\n";
            if (merge_cnt == 0) break;
        }
        merger.print_part_stat();
        
        while (true) {
            std::cout << "> Merge with child2\n";
            merge_cnt = merger.merge_direct_child();
            std::cout << "Merged " << merge_cnt << " parts\n";
            if (merge_cnt < 10) break;
        }
        merger.print_part_stat();
        
        while (true) {
            std::cout << "> Merge adjacent groups2\n";
            merge_cnt = merger.merge_adjacent_group();
            std::cout << merge_cnt << " merge ops\n";
            if (merge_cnt == 0) break;
        }
        merger.print_part_stat();
        
        while (true) {
            std::cout << "> Merge siblings\n";
            merge_cnt = merger.merge_siblings();
            std::cout << merge_cnt << " merge ops\n";
            if (merge_cnt == 0) break;
        }
        merger.print_part_stat();
        
        std::cout << "> Done\n";
        merger.save(args.output);
        
        auto end_time = std::chrono::high_resolution_clock::now();
        auto duration = std::chrono::duration_cast<std::chrono::milliseconds>(end_time - start_time);
        std::cout << "Total execution time: " << duration.count() << " ms\n";
        
    } catch (const std::exception& e) {
        std::cerr << "Error: " << e.what() << std::endl;
        return 1;
    }
    
    return 0;
}
