#pragma once

#include <cstdlib>
#include <cstdint>

#include "itch_spec.hpp"

class ItchParser
{
public:
  ItchParser(size_t cache_size);
  ~ItchParser();
  void reset();
  void start(char *ptr, size_t len);
  ItchEvent *events;
  size_t eventN;

private:
  char *stream;
  size_t eventCacheSize;
  size_t cursor;
  size_t len;

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
