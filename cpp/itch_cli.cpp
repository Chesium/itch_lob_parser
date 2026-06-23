#include <fstream>
#include <stdexcept>
#include <format>
#include <algorithm>
#include <chrono>
#include <cstdint>
#include <iostream>
#include <string_view>
#include <vector>
#include <array>

#include "itch_spec.hpp"
#include "itch_parser.hpp"
#include "lob.hpp"

constexpr std::size_t MIN_MESSAGE_SIZE = 19;

struct TypeStats
{
  char type;
  const char *name;
  std::size_t messages = 0;
  std::size_t bytes = 0;
};

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

std::size_t message_length(EventKind kind)
{
  switch (kind)
  {
  case EventKind::ADD:
    return 36;
  case EventKind::EXECUTE:
    return 31;
  case EventKind::CANCEL:
    return 23;
  case EventKind::DELETE:
    return 19;
  case EventKind::REPLACE:
    return 35;
  case EventKind::ERROR:
    return 0;
  }
  return 0;
}

std::size_t type_index(EventKind kind)
{
  switch (kind)
  {
  case EventKind::ADD:
    return 0;
  case EventKind::EXECUTE:
    return 1;
  case EventKind::CANCEL:
    return 2;
  case EventKind::DELETE:
    return 3;
  case EventKind::REPLACE:
    return 4;
  case EventKind::ERROR:
    return 5;
  }
  return 5;
}

std::array<TypeStats, 5> collect_type_stats(const std::vector<ItchEvent> &events)
{
  std::array<TypeStats, 5> stats = {
      TypeStats{'A', "add"},
      TypeStats{'E', "execute"},
      TypeStats{'X', "cancel"},
      TypeStats{'D', "delete"},
      TypeStats{'U', "replace"},
  };
  for (const ItchEvent &event : events)
  {
    const std::size_t index = type_index(event.kind);
    if (index >= stats.size())
      continue;
    stats[index].messages += 1;
    stats[index].bytes += message_length(event.kind);
  }
  return stats;
}

void print_u64_array_json(const std::vector<std::uint64_t> &values)
{
  for (std::size_t i = 0; i < values.size(); ++i)
  {
    if (i)
      std::cout << ',';
    std::cout << values[i];
  }
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

void run_benchmark_breakdown(const char *input_path, int repeat, bool apply_lob, bool json_output)
{
  if (repeat <= 0)
    throw std::invalid_argument("--repeat must be greater than 0.");

  const auto read_start = std::chrono::steady_clock::now();
  const std::vector<std::uint8_t> bytes = read_file(input_path);
  const auto read_stop = std::chrono::steady_clock::now();
  const std::uint64_t read_file_ns = static_cast<std::uint64_t>(
      std::chrono::duration_cast<std::chrono::nanoseconds>(read_stop - read_start).count());

  std::vector<std::uint64_t> construct_ns;
  std::vector<std::uint64_t> parse_ns;
  std::vector<std::uint64_t> lob_ns;
  std::vector<std::uint64_t> parse_lob_ns;
  construct_ns.reserve(static_cast<std::size_t>(repeat));
  parse_ns.reserve(static_cast<std::size_t>(repeat));
  lob_ns.reserve(static_cast<std::size_t>(repeat));
  parse_lob_ns.reserve(static_cast<std::size_t>(repeat));

  std::size_t events_parsed = 0;
  std::array<TypeStats, 5> type_stats = {
      TypeStats{'A', "add"},
      TypeStats{'E', "execute"},
      TypeStats{'X', "cancel"},
      TypeStats{'D', "delete"},
      TypeStats{'U', "replace"},
  };

  for (int i = 0; i < repeat; ++i)
  {
    const auto construct_start = std::chrono::steady_clock::now();
    ItchParser parser(bytes.size() / MIN_MESSAGE_SIZE);
    const auto construct_stop = std::chrono::steady_clock::now();
    construct_ns.push_back(static_cast<std::uint64_t>(
        std::chrono::duration_cast<std::chrono::nanoseconds>(construct_stop - construct_start).count()));

    const auto parse_start = std::chrono::steady_clock::now();
    parser.start(bytes);
    const auto parse_stop = std::chrono::steady_clock::now();
    const std::uint64_t this_parse_ns = static_cast<std::uint64_t>(
        std::chrono::duration_cast<std::chrono::nanoseconds>(parse_stop - parse_start).count());
    parse_ns.push_back(this_parse_ns);

    if (apply_lob)
    {
      LOB lob;
      const auto lob_start = std::chrono::steady_clock::now();
      for (const ItchEvent &event : parser.events)
        lob.apply(event);
      const auto lob_stop = std::chrono::steady_clock::now();
      const std::uint64_t this_lob_ns = static_cast<std::uint64_t>(
          std::chrono::duration_cast<std::chrono::nanoseconds>(lob_stop - lob_start).count());
      lob_ns.push_back(this_lob_ns);
      parse_lob_ns.push_back(this_parse_ns + this_lob_ns);
    }

    if (i == 0)
    {
      events_parsed = parser.events.size();
      type_stats = collect_type_stats(parser.events);
    }
    else if (events_parsed != parser.events.size())
      throw std::runtime_error("Benchmark parse event count changed between repeats.");
  }

  const double med_parse_ns = median_ns(parse_ns);
  const double median_seconds = med_parse_ns / 1'000'000'000.0;
  const double mbps = median_seconds > 0.0 ? (static_cast<double>(bytes.size()) / 1'000'000.0) / median_seconds : 0.0;
  const double msgps = median_seconds > 0.0 ? static_cast<double>(events_parsed) / median_seconds : 0.0;

  if (json_output)
  {
    std::cout << "{\"parser\":\"cpp_breakdown\",\"bytes\":" << bytes.size()
              << ",\"events\":" << events_parsed
              << ",\"repeat\":" << repeat
              << ",\"apply_lob\":" << (apply_lob ? "true" : "false")
              << ",\"read_file_ns\":" << read_file_ns
              << ",\"construct_ns\":[";
    print_u64_array_json(construct_ns);
    std::cout << "],\"parse_ns\":[";
    print_u64_array_json(parse_ns);
    std::cout << "],\"median_construct_ns\":" << median_ns(construct_ns)
              << ",\"median_parse_ns\":" << med_parse_ns
              << ",\"median_parse_seconds\":" << median_seconds
              << ",\"median_ns_per_message\":" << (events_parsed ? med_parse_ns / static_cast<double>(events_parsed) : 0.0)
              << ",\"mb_per_sec\":" << mbps
              << ",\"messages_per_sec\":" << msgps;
    if (apply_lob)
    {
      const double med_lob_ns = median_ns(lob_ns);
      const double med_parse_lob_ns = median_ns(parse_lob_ns);
      const double parse_lob_seconds = med_parse_lob_ns / 1'000'000'000.0;
      std::cout << ",\"lob_apply_ns\":[";
      print_u64_array_json(lob_ns);
      std::cout << "],\"median_lob_apply_ns\":" << med_lob_ns
                << ",\"median_parse_lob_ns\":" << med_parse_lob_ns
                << ",\"median_parse_lob_seconds\":" << parse_lob_seconds
                << ",\"parse_lob_mb_per_sec\":" << (parse_lob_seconds > 0.0 ? (static_cast<double>(bytes.size()) / 1'000'000.0) / parse_lob_seconds : 0.0)
                << ",\"parse_lob_messages_per_sec\":" << (parse_lob_seconds > 0.0 ? static_cast<double>(events_parsed) / parse_lob_seconds : 0.0);
    }
    std::cout << ",\"message_types\":{";
    for (std::size_t i = 0; i < type_stats.size(); ++i)
    {
      if (i)
        std::cout << ',';
      const TypeStats &stats = type_stats[i];
      std::cout << "\"" << stats.type << "\":{\"name\":\"" << stats.name
                << "\",\"messages\":" << stats.messages
                << ",\"bytes\":" << stats.bytes << "}";
    }
    std::cout << "}}\n";
    return;
  }

  std::cout << "cpp_breakdown " << bytes.size() << " bytes " << events_parsed
            << " events median_parse_seconds=" << median_seconds
            << " MB/s=" << mbps
            << " messages/s=" << msgps << '\n';
}

int main(int argc, char *argv[])
{
  if (argc < 2)
    throw std::invalid_argument("usage: itch_cli [--debug-lob] [--bench] [--bench-breakdown] [--apply-lob] [--json] [--repeat N] <bin_file>");

  bool debug_lob = false;
  bool bench = false;
  bool bench_breakdown = false;
  bool apply_lob = false;
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
    else if (arg == "--bench-breakdown")
      bench_breakdown = true;
    else if (arg == "--apply-lob")
      apply_lob = true;
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
    throw std::invalid_argument("usage: itch_cli [--debug-lob] [--bench] [--bench-breakdown] [--apply-lob] [--json] [--repeat N] <bin_file>");
  if (bench && debug_lob)
    throw std::invalid_argument("--bench cannot be combined with --debug-lob.");
  if (bench_breakdown && debug_lob)
    throw std::invalid_argument("--bench-breakdown cannot be combined with --debug-lob.");
  if (bench && bench_breakdown)
    throw std::invalid_argument("--bench and --bench-breakdown cannot be combined.");
  if (apply_lob && !bench_breakdown)
    throw std::invalid_argument("--apply-lob requires --bench-breakdown.");

  if (bench)
  {
    run_benchmark(input_path, repeat, json_output);
    return 0;
  }
  if (bench_breakdown)
  {
    run_benchmark_breakdown(input_path, repeat, apply_lob, json_output);
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
