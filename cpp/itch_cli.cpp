#include <fstream>
#include <stdexcept>
#include <format>
#include <cstdlib>
#include <iostream>
#include <cstring>

#include "itch_spec.hpp"
#include "itch_parser.hpp"

#define STREAM_BUF_SIZE 100000
#define EVENT_BUF_SIZE (size_t)((int)STREAM_BUF_SIZE / 19)

int main(int argc, char *argv[])
{
  std::ifstream input_file;
  char buf[STREAM_BUF_SIZE];
  if (argc < 2)
    throw std::invalid_argument("argc must be greater or equal to 2.");
  input_file.open(argv[1], std::ios::in);
  if (not input_file)
    throw std::ios_base::failure(std::format("Cannot open file {}.", argv[1]));
  input_file.read(buf, STREAM_BUF_SIZE);
  size_t len = input_file.gcount();
  ItchParser parser(EVENT_BUF_SIZE);
  parser.start(buf, len);
  for (size_t i = 0; i < parser.eventN; i++)
    std::cout << parser.events[i] << std::endl;
  input_file.close();
  return 0;
}
