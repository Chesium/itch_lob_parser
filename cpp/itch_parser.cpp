
#include "itch_parser.hpp"
#include <stdexcept>
#include <format>

ItchParser::ItchParser(size_t cache_size)
{
  this->eventCacheSize = cache_size;
  this->reset();
  this->events = new ItchEvent[this->eventCacheSize];
}

ItchParser::~ItchParser()
{
  delete[] this->events;
}

void ItchParser::reset()
{
  this->eventN = 0;
}

void ItchParser::start(char *ptr, size_t len)
{
  this->stream = ptr;
  this->cursor = 0;
  this->len = len;
  while (this->cursor < this->len)
  {
    ItchEvent *ev = this->events + (this->eventN++);
    *ev = ItchEvent{};
    switch (this->parseByte())
    {
    case 'A': // ADD
      this->parseAdd(ev);
      break;
    case 'E': // EXECUTE
      this->parseExecute(ev);
      break;
    case 'X': // CANCEL
      this->parseCancel(ev);
      break;
    case 'D': // DELETE
      this->parseDelete(ev);
      break;
    case 'U': // REPLACE
      this->parseReplace(ev);
      break;
    default:
      throw std::domain_error(std::format("Unknown MsgType at byte {}.", this->cursor - 1));
      break;
    }
  }
}

uint8_t ItchParser::parseByte()
{
  return static_cast<uint8_t>(*(this->stream + (this->cursor++)));
}

uint16_t ItchParser::parseU16()
{
  uint16_t b1 = parseByte();
  uint16_t b2 = parseByte();
  return static_cast<uint16_t>((b1 << 8) | b2);
}

uint32_t ItchParser::parseU32()
{
  uint32_t r = 0;
  for (size_t i = 0; i < 4; i++)
    r = (r << 8) | parseByte();
  return r;
}

uint64_t ItchParser::parseU48()
{
  uint64_t r = 0;
  for (size_t i = 0; i < 6; i++)
    r = (r << 8) | parseByte();
  return r;
}

uint64_t ItchParser::parseU64()
{
  uint64_t r = 0;
  for (size_t i = 0; i < 8; i++)
    r = (r << 8) | parseByte();
  return r;
}

void ItchParser::parseHeader(ItchEvent *ev)
{
  ev->stock_locate = parseU16();
  ev->tracking_number = parseU16();
  ev->timestamp = parseU48();
  ev->order_ref = parseU64();
}

void ItchParser::parseAdd(ItchEvent *ev)
{
  // Length: 36
  ev->kind = EventKind::ADD;
  ev->valid_mask = 0b01011101;
  this->parseHeader(ev);
  switch (this->parseByte())
  {
  case 'B':
    ev->side = Side::BUY;
    break;
  case 'S':
    ev->side = Side::SELL;
    break;
  default:
    throw std::domain_error(std::format("Unknown Add-Messgae Side Symbol at byte {}.", this->cursor - 1));
    break;
  }
  ev->qty = this->parseU32();
  for (int i = 0; i < 8; i++)
    ev->stock[i] = this->parseByte();
  ev->price = this->parseU32();
}

void ItchParser::parseExecute(ItchEvent *ev)
{
  // Length: 31
  ev->kind = EventKind::EXECUTE;
  ev->valid_mask = 0b00101001;
  this->parseHeader(ev);
  ev->qty = this->parseU32();
  ev->match_number = this->parseU64();
}

void ItchParser::parseCancel(ItchEvent *ev)
{
  // Length: 23
  ev->kind = EventKind::CANCEL;
  ev->valid_mask = 0b00001001;
  this->parseHeader(ev);
  ev->qty = this->parseU32();
}

void ItchParser::parseDelete(ItchEvent *ev)
{
  // Length: 19
  ev->kind = EventKind::DELETE;
  ev->valid_mask = 0b00000001;
  this->parseHeader(ev);
}

void ItchParser::parseReplace(ItchEvent *ev)
{
  // Length: 35
  ev->kind = EventKind::REPLACE;
  ev->valid_mask = 0b00011011;
  this->parseHeader(ev);
  ev->new_order_ref = this->parseU64();
  ev->qty = this->parseU32();
  ev->price = this->parseU32();
}
