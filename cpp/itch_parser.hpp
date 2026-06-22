#pragma once

#include <cstdint>
#include <cstdlib>
#include <span>
#include <vector>

#include "itch_spec.hpp"

class ItchParser
{
public:
  ItchParser(size_t cache_size);
  void reset();
  void start(std::span<const std::uint8_t> bytes);
  std::vector<ItchEvent> events;

private:
  std::span<const std::uint8_t> stream;
  size_t cursor;

  uint8_t parseByte();
  uint16_t parseU16();
  uint32_t parseU32();
  uint64_t parseU48();
  uint64_t parseU64();
  void parseHeader(ItchEvent *ev);
  void parseAdd(ItchEvent *ev);
  void parseExecute(ItchEvent *ev);
  void parseCancel(ItchEvent *ev);
  void parseDelete(ItchEvent *ev);
  void parseReplace(ItchEvent *ev);
};
