module itch.parser;

import std;

ItchParser::ItchParser(std::size_t cache_size)
{
  this->events.reserve(cache_size);
}

void ItchParser::reset()
{
  this->events.clear();
}

void ItchParser::start(std::span<const std::uint8_t> bytes)
{
  this->stream = bytes;
  this->cursor = 0;
  this->reset();
  while (this->cursor < this->stream.size())
  {
    ItchEvent &ev = this->events.emplace_back();
    switch (this->parseByte())
    {
    case 'A': // ADD
      this->parseAdd(&ev);
      break;
    case 'E': // EXECUTE
      this->parseExecute(&ev);
      break;
    case 'X': // CANCEL
      this->parseCancel(&ev);
      break;
    case 'D': // DELETE
      this->parseDelete(&ev);
      break;
    case 'U': // REPLACE
      this->parseReplace(&ev);
      break;
    default:
      throw std::domain_error(std::format("Unknown MsgType at byte {}.", this->cursor - 1));
      break;
    }
  }
}

std::uint8_t ItchParser::parseByte()
{
  if (this->cursor >= this->stream.size())
    throw std::out_of_range(std::format("Unexpected end of stream at byte {}.", this->cursor));
  return this->stream[this->cursor++];
}

std::uint16_t ItchParser::parseU16()
{
  std::uint16_t b1 = parseByte();
  std::uint16_t b2 = parseByte();
  return static_cast<std::uint16_t>((b1 << 8) | b2);
}

std::uint32_t ItchParser::parseU32()
{
  std::uint32_t r = 0;
  for (std::size_t i = 0; i < 4; i++)
    r = (r << 8) | parseByte();
  return r;
}

std::uint64_t ItchParser::parseU48()
{
  std::uint64_t r = 0;
  for (std::size_t i = 0; i < 6; i++)
    r = (r << 8) | parseByte();
  return r;
}

std::uint64_t ItchParser::parseU64()
{
  std::uint64_t r = 0;
  for (std::size_t i = 0; i < 8; i++)
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
  ev->valid_mask = EventField::ORDER_REF | EventField::SIDE | EventField::QTY |
                   EventField::PRICE | EventField::STOCK;
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
  ev->valid_mask = EventField::ORDER_REF | EventField::QTY | EventField::MATCH_NUMBER;
  this->parseHeader(ev);
  ev->qty = this->parseU32();
  ev->match_number = this->parseU64();
}

void ItchParser::parseCancel(ItchEvent *ev)
{
  // Length: 23
  ev->kind = EventKind::CANCEL;
  ev->valid_mask = EventField::ORDER_REF | EventField::QTY;
  this->parseHeader(ev);
  ev->qty = this->parseU32();
}

void ItchParser::parseDelete(ItchEvent *ev)
{
  // Length: 19
  ev->kind = EventKind::DELETE;
  ev->valid_mask = EventField::ORDER_REF;
  this->parseHeader(ev);
}

void ItchParser::parseReplace(ItchEvent *ev)
{
  // Length: 35
  ev->kind = EventKind::REPLACE;
  ev->valid_mask = EventField::ORDER_REF | EventField::NEW_ORDER_REF | EventField::QTY |
                   EventField::PRICE;
  this->parseHeader(ev);
  ev->new_order_ref = this->parseU64();
  ev->qty = this->parseU32();
  ev->price = this->parseU32();
}
