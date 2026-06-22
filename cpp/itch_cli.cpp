#include <fstream>
#include <stdexcept>
#include <format>
#include <cstdint>
#include <iostream>
#include <string_view>
#include <vector>

#include "itch_spec.hpp"
#include "itch_parser.hpp"
#include "lob.hpp"

constexpr std::size_t MIN_MESSAGE_SIZE = 19;

int main(int argc, char *argv[])
{
  if (argc < 2)
    throw std::invalid_argument("usage: itch_cli [--debug-lob] <bin_file>");

  bool debug_lob = false;
  const char *input_path = nullptr;
  for (int i = 1; i < argc; ++i)
  {
    const std::string_view arg(argv[i]);
    if (arg == "--debug-lob")
      debug_lob = true;
    else if (input_path == nullptr)
      input_path = argv[i];
    else
      throw std::invalid_argument(std::format("Unexpected argument {}.", argv[i]));
  }

  if (input_path == nullptr)
    throw std::invalid_argument("usage: itch_cli [--debug-lob] <bin_file>");

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
