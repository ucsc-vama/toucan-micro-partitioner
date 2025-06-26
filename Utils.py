# import psutil
# import os

# def print_memory_usage():
#   process = psutil.Process(os.getpid())
#   memory_usage = process.memory_info().rss / (1024 ** 2)  # Convert bytes to MB
#   print(f"Memory usage: {memory_usage:.2f} MB")


def count_elements(lst):
  counts = {}
  for num in lst:
    counts[num] = counts.get(num, 0) + 1
  return counts


# if __name__ == "__main__":
#   print_memory_usage()