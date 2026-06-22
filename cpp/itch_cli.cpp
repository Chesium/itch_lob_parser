#include <fstream>
#include <stdexcept>
#include <format>
#include <cstdint>
#include <iostream>
#include <vector>

#include "itch_spec.hpp"
#include "itch_parser.hpp"

constexpr std::size_t MIN_MESSAGE_SIZE = 19;

int main(int argc, char *argv[])
{
  if (argc < 2)
    throw std::invalid_argument("argc must be greater or equal to 2.");

  std::ifstream input_file(argv[1], std::ios::binary | std::ios::ate);
  if (not input_file)
    throw std::ios_base::failure(std::format("Cannot open file {}.", argv[1]));

  const std::streampos file_size = input_file.tellg();
  if (file_size == std::streampos(-1))
    throw std::ios_base::failure(std::format("Cannot determine size of file {}.", argv[1]));

  const std::size_t len = static_cast<std::size_t>(file_size);
  input_file.seekg(0, std::ios::beg);

  std::vector<std::uint8_t> bytes(len);
  if (not bytes.empty())
    input_file.read(reinterpret_cast<char *>(bytes.data()), static_cast<std::streamsize>(len));
  if (not input_file)
    throw std::ios_base::failure(std::format("Cannot read file {}.", argv[1]));

  ItchParser parser(bytes.size() / MIN_MESSAGE_SIZE);
  parser.start(bytes);
  for (const ItchEvent &event : parser.events)
    std::cout << event << std::endl;
  return 0;
}
