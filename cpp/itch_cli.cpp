import std;
import itch;

constexpr std::size_t MIN_MESSAGE_SIZE = 19;

struct TypeStats
{
  char type;
  const char *name;
  std::size_t messages = 0;
  std::size_t bytes = 0;
};

std::vector<std::byte> read_file(const char *input_path)
{
  std::ifstream input_file(input_path, std::ios::binary | std::ios::ate);
  if (not input_file)
    throw std::ios_base::failure(std::format("Cannot open file {}.", input_path));

  const std::streampos file_size = input_file.tellg();
  if (file_size == std::streampos(-1))
    throw std::ios_base::failure(std::format("Cannot determine size of file {}.", input_path));

  const std::size_t len = static_cast<std::size_t>(file_size);
  input_file.seekg(0, std::ios::beg);

  std::vector<std::byte> bytes(len);
  if (not bytes.empty())
    input_file.read(reinterpret_cast<char *>(bytes.data()), static_cast<std::streamsize>(len));
  if (not input_file)
    throw std::ios_base::failure(std::format("Cannot read file {}.", input_path));
  return bytes;
}

void report_parse_error(const ParseErr &err)
{
  std::println(std::cerr, "parse error at byte {}: {}", err.offset, err.message);
}

template<typename T>
std::string stream_to_string(const T &value)
{
  std::ostringstream out;
  out << value;
  return out.str();
}

std::expected<std::vector<ItchEvent>, ParseErr> parse_stream(std::span<const std::byte> bytes)
{
  ItchParser parser(bytes.size() / MIN_MESSAGE_SIZE);
  return parser.start(bytes);
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
      std::print(",");
    std::print("{}", values[i]);
  }
}

int run_benchmark(const char *input_path, int repeat, bool json_output)
{
  if (repeat <= 0)
    throw std::invalid_argument("--repeat must be greater than 0.");

  const std::vector<std::byte> bytes = read_file(input_path);
  std::vector<std::uint64_t> elapsed_ns;
  elapsed_ns.reserve(static_cast<std::size_t>(repeat));
  std::size_t events_parsed = 0;

  for (int i = 0; i < repeat; ++i)
  {
    const auto start = std::chrono::steady_clock::now();
    const auto parsed = parse_stream(bytes);
    const auto stop = std::chrono::steady_clock::now();
    if (!parsed)
    {
      report_parse_error(parsed.error());
      return 1;
    }

    elapsed_ns.push_back(static_cast<std::uint64_t>(
        std::chrono::duration_cast<std::chrono::nanoseconds>(stop - start).count()));

    if (i == 0)
      events_parsed = parsed->size();
    else if (events_parsed != parsed->size())
      throw std::runtime_error("Benchmark parse event count changed between repeats.");
  }

  const double med_ns = median_ns(elapsed_ns);
  const double median_seconds = med_ns / 1'000'000'000.0;
  const double mbps = median_seconds > 0.0 ? (static_cast<double>(bytes.size()) / 1'000'000.0) / median_seconds : 0.0;
  const double msgps = median_seconds > 0.0 ? static_cast<double>(events_parsed) / median_seconds : 0.0;

  if (json_output)
  {
    std::print("{{\"parser\":\"cpp\",\"bytes\":{},\"events\":{},\"repeat\":{},\"elapsed_ns\":[",
               bytes.size(), events_parsed, repeat);
    for (std::size_t i = 0; i < elapsed_ns.size(); ++i)
    {
      if (i)
        std::print(",");
      std::print("{}", elapsed_ns[i]);
    }
    std::println("],\"median_seconds\":{},\"mb_per_sec\":{},\"messages_per_sec\":{}}}",
                 median_seconds, mbps, msgps);
    return 0;
  }

  std::println("cpp {} bytes {} events median_seconds={} MB/s={} messages/s={}",
               bytes.size(), events_parsed, median_seconds, mbps, msgps);
  return 0;
}

int run_benchmark_breakdown(const char *input_path, int repeat, bool apply_lob, bool json_output)
{
  if (repeat <= 0)
    throw std::invalid_argument("--repeat must be greater than 0.");

  const auto read_start = std::chrono::steady_clock::now();
  const std::vector<std::byte> bytes = read_file(input_path);
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
    const auto parsed = parser.start(bytes);
    const auto parse_stop = std::chrono::steady_clock::now();
    if (!parsed)
    {
      report_parse_error(parsed.error());
      return 1;
    }

    const std::uint64_t this_parse_ns = static_cast<std::uint64_t>(
        std::chrono::duration_cast<std::chrono::nanoseconds>(parse_stop - parse_start).count());
    parse_ns.push_back(this_parse_ns);

    if (apply_lob)
    {
      LOB lob;
      const auto lob_start = std::chrono::steady_clock::now();
      for (const ItchEvent &event : *parsed)
        lob.apply(event);
      const auto lob_stop = std::chrono::steady_clock::now();
      const std::uint64_t this_lob_ns = static_cast<std::uint64_t>(
          std::chrono::duration_cast<std::chrono::nanoseconds>(lob_stop - lob_start).count());
      lob_ns.push_back(this_lob_ns);
      parse_lob_ns.push_back(this_parse_ns + this_lob_ns);
    }

    if (i == 0)
    {
      events_parsed = parsed->size();
      type_stats = collect_type_stats(*parsed);
    }
    else if (events_parsed != parsed->size())
      throw std::runtime_error("Benchmark parse event count changed between repeats.");
  }

  const double med_parse_ns = median_ns(parse_ns);
  const double median_seconds = med_parse_ns / 1'000'000'000.0;
  const double mbps = median_seconds > 0.0 ? (static_cast<double>(bytes.size()) / 1'000'000.0) / median_seconds : 0.0;
  const double msgps = median_seconds > 0.0 ? static_cast<double>(events_parsed) / median_seconds : 0.0;

  if (json_output)
  {
    std::print("{{\"parser\":\"cpp_breakdown\",\"bytes\":{},\"events\":{},\"repeat\":{},\"apply_lob\":{},\"read_file_ns\":{},\"construct_ns\":[",
               bytes.size(), events_parsed, repeat, apply_lob ? "true" : "false", read_file_ns);
    print_u64_array_json(construct_ns);
    std::print("],\"parse_ns\":[");
    print_u64_array_json(parse_ns);
    std::print("],\"median_construct_ns\":{},\"median_parse_ns\":{},\"median_parse_seconds\":{},\"median_ns_per_message\":{},\"mb_per_sec\":{},\"messages_per_sec\":{}",
               median_ns(construct_ns), med_parse_ns, median_seconds,
               events_parsed ? med_parse_ns / static_cast<double>(events_parsed) : 0.0, mbps, msgps);
    if (apply_lob)
    {
      const double med_lob_ns = median_ns(lob_ns);
      const double med_parse_lob_ns = median_ns(parse_lob_ns);
      const double parse_lob_seconds = med_parse_lob_ns / 1'000'000'000.0;
      std::print(",\"lob_apply_ns\":[");
      print_u64_array_json(lob_ns);
      std::print("],\"median_lob_apply_ns\":{},\"median_parse_lob_ns\":{},\"median_parse_lob_seconds\":{},\"parse_lob_mb_per_sec\":{},\"parse_lob_messages_per_sec\":{}",
                 med_lob_ns, med_parse_lob_ns, parse_lob_seconds,
                 parse_lob_seconds > 0.0 ? (static_cast<double>(bytes.size()) / 1'000'000.0) / parse_lob_seconds : 0.0,
                 parse_lob_seconds > 0.0 ? static_cast<double>(events_parsed) / parse_lob_seconds : 0.0);
    }
    std::print(",\"message_types\":{{");
    for (std::size_t i = 0; i < type_stats.size(); ++i)
    {
      if (i)
        std::print(",");
      const TypeStats &stats = type_stats[i];
      std::print("\"{}\":{{\"name\":\"{}\",\"messages\":{},\"bytes\":{}}}",
                 stats.type, stats.name, stats.messages, stats.bytes);
    }
    std::println("}}}}");
    return 0;
  }

  std::println("cpp_breakdown {} bytes {} events median_parse_seconds={} MB/s={} messages/s={}",
               bytes.size(), events_parsed, median_seconds, mbps, msgps);
  return 0;
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
    return run_benchmark(input_path, repeat, json_output);
  if (bench_breakdown)
    return run_benchmark_breakdown(input_path, repeat, apply_lob, json_output);

  const std::vector<std::byte> bytes = read_file(input_path);
  const auto parsed = parse_stream(bytes);
  if (!parsed)
  {
    report_parse_error(parsed.error());
    return 1;
  }

  LOB lob;
  for (const ItchEvent &event : *parsed)
  {
    std::println("{}", stream_to_string(event));
    if (debug_lob)
    {
      lob.apply(event);
      const auto rows = lob.snapshot();
      std::println(std::cerr, "[lob] applied {}", stream_to_string(event));
      std::println(std::cerr, "[lob] active_orders={}", rows.size());
      for (const auto &[order_ref, order] : rows)
        std::println(std::cerr, "[lob] order {} {}", order_ref, stream_to_string(order));
    }
  }
  return 0;
}
