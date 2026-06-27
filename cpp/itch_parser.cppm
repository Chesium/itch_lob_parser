export module itch.parser;

import std;
import itch.spec;

export class ItchParser
{
public:
  ItchParser(std::size_t cache_size);
  void reset();
  void start(std::span<const std::uint8_t> bytes);
  std::vector<ItchEvent> events;

private:
  std::span<const std::uint8_t> stream;
  std::size_t cursor;

  std::uint8_t parseByte();
  std::uint16_t parseU16();
  std::uint32_t parseU32();
  std::uint64_t parseU48();
  std::uint64_t parseU64();
  void parseHeader(ItchEvent *ev);
  void parseAdd(ItchEvent *ev);
  void parseExecute(ItchEvent *ev);
  void parseCancel(ItchEvent *ev);
  void parseDelete(ItchEvent *ev);
  void parseReplace(ItchEvent *ev);
};
