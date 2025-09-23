cmake_minimum_required(VERSION 3.16)
project(ToucanMicroPartitioner)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Compiler flags for optimization
set(CMAKE_CXX_FLAGS_RELEASE "-O3 -DNDEBUG -march=native")
set(CMAKE_CXX_FLAGS_DEBUG "-g -O0 -DDEBUG")

# Default to Release build
if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release)
endif()

# Source files
set(SOURCES
    src/main.cpp
    src/ToucanGraph.cpp
    src/MicroPartition.cpp
    src/MergeGraph.cpp
    src/PartitionMerger.cpp
    src/Utils.cpp
)

# Header files
set(HEADERS
    include/ToucanGraph.h
    include/MicroPartition.h
    include/MergeGraph.h
    include/PartitionMerger.h
    include/Utils.h
)

# Include directories
include_directories(include)

# Create executable
add_executable(micro_partitioner ${SOURCES} ${HEADERS})

# Enable compiler warnings
target_compile_options(micro_partitioner PRIVATE
    -Wall -Wextra -Wpedantic
)

# Link libraries (if needed)
# target_link_libraries(micro_partitioner PRIVATE some_library)

# Install target
install(TARGETS micro_partitioner DESTINATION bin)
