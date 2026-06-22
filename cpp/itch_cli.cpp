#include <fstream>
#include <stdexcept>
#include <format>
#include <algorithm>
#include <chrono>
#include <cstdint>
#include <iostream>
#include <string_view>
#include <vector>

#include "itch_spec.hpp"
#include "itch_parser.hpp"
#include "lob.hpp"

constexpr std::size_t MIN_MESSAGE_SIZE = 19;

std::vector<std::uint8_t> read_file(const char *input_path)
{
  std::ifstream input_file(input_path, std::ios::binary | std::ios::ate);
  if (not input_file)
    throw std::ios_base::failure(std::format("Cannot open file {}.", input_path));

  const std::streampos file_size = input_file.tellg();
  if (file_size == std::streampos(-1))
    throw std::ios_base::failure(std::format("Cannot determine size of file {}.", input_path));

  const std::size_t len = static_cast<std::size_t>(file_size);
  input_file.seekg(0, std::ios::beg);

  std::vector<std::uint8_t> bytes(len);
  if (not bytes.empty())
    input_file.read(reinterpret_cast<char *>(bytes.data()), static_cast<std::streamsize>(len));
  if (not input_file)
    throw std::ios_base::failure(std::format("Cannot read file {}.", input_path));
  return bytes;
}

double median_ns(std::vector<std::uint64_t> values)
{
  if (values.empty())
    return 0.0;
  std::sort(values.begin(), values.end());
  const std::size_t middle = values.size() / 2;
  if (values.size() % 2 == 1)
    return static_cast<double>(values[middle]);
  return (static_cast<double>(values[middle - 1]) + static_cast<double>(values[middle])) / 2.0;
}

void run_benchmark(const char *input_path, int repeat, bool json_output)
{
  if (repeat <= 0)
    throw std::invalid_argument("--repeat must be greater than 0.");

  const std::vector<std::uint8_t> bytes = read_file(input_path);
  std::vector<std::uint64_t> elapsed_ns;
  elapsed_ns.reserve(static_cast<std::size_t>(repeat));
  std::size_t events_parsed = 0;

  for (int i = 0; i < repeat; ++i)
  {
    ItchParser parser(bytes.size() / MIN_MESSAGE_SIZE);
    const auto start = std::chrono::steady_clock::now();
    parser.start(bytes);
    const auto stop = std::chrono::steady_clock::now();
    elapsed_ns.push_back(static_cast<std::uint64_t>(
        std::chrono::duration_cast<std::chrono::nanoseconds>(stop - start).count()));

    if (i == 0)
      events_parsed = parser.events.size();
    else if (events_parsed != parser.events.size())
      throw std::runtime_error("Benchmark parse event count changed between repeats.");
  }

  const double med_ns = median_ns(elapsed_ns);
  const double median_seconds = med_ns / 1'000'000'000.0;
  const double mbps = median_seconds > 0.0 ? (static_cast<double>(bytes.size()) / 1'000'000.0) / median_seconds : 0.0;
  const double msgps = median_seconds > 0.0 ? static_cast<double>(events_parsed) / median_seconds : 0.0;

  if (json_output)
  {
    std::cout << "{\"parser\":\"cpp\",\"bytes\":" << bytes.size()
              << ",\"events\":" << events_parsed
              << ",\"repeat\":" << repeat
              << ",\"elapsed_ns\":[";
    for (std::size_t i = 0; i < elapsed_ns.size(); ++i)
    {
      if (i)
        std::cout << ',';
      std::cout << elapsed_ns[i];
    }
    std::cout << "],\"median_seconds\":" << median_seconds
              << ",\"mb_per_sec\":" << mbps
              << ",\"messages_per_sec\":" << msgps << "}\n";
    return;
  }

  std::cout << "cpp " << bytes.size() << " bytes " << events_parsed
            << " events median_seconds=" << median_seconds
            << " MB/s=" << mbps
            << " messages/s=" << msgps << '\n';
}

int main(int argc, char *argv[])
{
  if (argc < 2)
    throw std::invalid_argument("usage: itch_cli [--debug-lob] [--bench] [--json] [--repeat N] <bin_file>");

  bool debug_lob = false;
  bool bench = false;
  bool json_output = false;
  int repeat = 5;
  const char *input_path = nullptr;
  for (int i = 1; i < argc; ++i)
  {
    const std::string_view arg(argv[i]);
    if (arg == "--debug-lob")
      debug_lob = true;
    else if (arg == "--bench")
      bench = true;
    else if (arg == "--json")
      json_output = true;
    else if (arg == "--repeat")
    {
      if (++i >= argc)
        throw std::invalid_argument("--repeat requires a value.");
      repeat = std::stoi(argv[i]);
    }
    else if (input_path == nullptr)
      input_path = argv[i];
    else
      throw std::invalid_argument(std::format("Unexpected argument {}.", argv[i]));
  }

  if (input_path == nullptr)
    throw std::invalid_argument("usage: itch_cli [--debug-lob] [--bench] [--json] [--repeat N] <bin_file>");
  if (bench && debug_lob)
    throw std::invalid_argument("--bench cannot be combined with --debug-lob.");

  if (bench)
  {
    run_benchmark(input_path, repeat, json_output);
    return 0;
  }

  const std::vector<std::uint8_t> bytes = read_file(input_path);

  ItchParser parser(bytes.size() / MIN_MESSAGE_SIZE);
  parser.start(bytes);
  LOB lob;
  for (const ItchEvent &event : parser.events)
  {
    std::cout << event << std::endl;
    if (debug_lob)
    {
      lob.apply(event);
      const auto rows = lob.snapshot();
      std::cerr << "[lob] applied " << event << '\n';
      std::cerr << "[lob] active_orders=" << rows.size() << '\n';
      for (const auto &[order_ref, order] : rows)
        std::cerr << "[lob] order " << order_ref << ' ' << order << '\n';
    }
  }
  return 0;
}
