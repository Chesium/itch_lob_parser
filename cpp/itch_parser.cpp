module itch.parser;

import std;

namespace
{

template<std::unsigned_integral T>
std::expected<T, ParseErr> read_be(std::span<const std::byte> stream, std::size_t &cursor)
{
  constexpr std::size_t width = sizeof(T);
  if (cursor + width > stream.size())
  {
    return std::unexpected(ParseErr{
        ParseErrKind::UnexpectedEof,
        cursor,
        std::format("Unexpected end of stream at byte {}.", cursor),
    });
  }

  T value{};
  std::memcpy(&value, stream.data() + cursor, width);
  cursor += width;
  if constexpr (std::endian::native == std::endian::little)
    value = std::byteswap(value);
  return value;
}

char byte_as_char(std::byte value)
{
  return static_cast<char>(std::to_integer<unsigned char>(value));
}

} // namespace

ItchParser::ItchParser(std::size_t cache_size)
    : cache_size(cache_size)
{
}

std::expected<std::vector<ItchEvent>, ParseErr> ItchParser::start(std::span<const std::byte> bytes)
{
  this->stream = bytes;
  this->cursor = 0;

  std::vector<ItchEvent> events;
  events.reserve(this->cache_size);

  while (this->cursor < this->stream.size())
  {
    ItchEvent &ev = events.emplace_back();
    const auto msg_type = this->parseByte();
    if (!msg_type)
      return std::unexpected(msg_type.error());

    switch (byte_as_char(*msg_type))
    {
    case 'A':
      if (const auto err = this->parseAdd(&ev); !err)
        return std::unexpected(err.error());
      break;
    case 'E':
      if (const auto err = this->parseExecute(&ev); !err)
        return std::unexpected(err.error());
      break;
    case 'X':
      if (const auto err = this->parseCancel(&ev); !err)
        return std::unexpected(err.error());
      break;
    case 'D':
      if (const auto err = this->parseDelete(&ev); !err)
        return std::unexpected(err.error());
      break;
    case 'U':
      if (const auto err = this->parseReplace(&ev); !err)
        return std::unexpected(err.error());
      break;
    default:
      return std::unexpected(ParseErr{
          ParseErrKind::UnknownMessageType,
          this->cursor - 1,
          std::format("Unknown MsgType at byte {}.", this->cursor - 1),
      });
    }
  }

  return events;
}

std::expected<std::byte, ParseErr> ItchParser::parseByte()
{
  if (this->cursor >= this->stream.size())
  {
    return std::unexpected(ParseErr{
        ParseErrKind::UnexpectedEof,
        this->cursor,
        std::format("Unexpected end of stream at byte {}.", this->cursor),
    });
  }
  return this->stream[this->cursor++];
}

std::expected<std::uint16_t, ParseErr> ItchParser::parseU16()
{
  return read_be<std::uint16_t>(this->stream, this->cursor);
}

std::expected<std::uint32_t, ParseErr> ItchParser::parseU32()
{
  return read_be<std::uint32_t>(this->stream, this->cursor);
}

std::expected<std::uint64_t, ParseErr> ItchParser::parseU48()
{
  std::uint64_t value = 0;
  for (std::size_t i = 0; i < 6; ++i)
  {
    const auto byte = this->parseByte();
    if (!byte)
      return std::unexpected(byte.error());
    value = (value << 8) | std::to_integer<std::uint64_t>(*byte);
  }
  return value;
}

std::expected<std::uint64_t, ParseErr> ItchParser::parseU64()
{
  return read_be<std::uint64_t>(this->stream, this->cursor);
}

std::expected<void, ParseErr> ItchParser::parseHeader(ItchEvent *ev)
{
  if (const auto stock_locate = this->parseU16(); stock_locate)
    ev->stock_locate = *stock_locate;
  else
    return std::unexpected(stock_locate.error());

  if (const auto tracking_number = this->parseU16(); tracking_number)
    ev->tracking_number = *tracking_number;
  else
    return std::unexpected(tracking_number.error());

  if (const auto timestamp = this->parseU48(); timestamp)
    ev->timestamp = *timestamp;
  else
    return std::unexpected(timestamp.error());

  if (const auto order_ref = this->parseU64(); order_ref)
    ev->order_ref = *order_ref;
  else
    return std::unexpected(order_ref.error());

  return {};
}

std::expected<void, ParseErr> ItchParser::parseAdd(ItchEvent *ev)
{
  ev->kind = EventKind::ADD;
  ev->valid_mask = EventField::ORDER_REF | EventField::SIDE | EventField::QTY |
                   EventField::PRICE | EventField::STOCK;

  if (const auto err = this->parseHeader(ev); !err)
    return err;

  const auto side_byte = this->parseByte();
  if (!side_byte)
    return std::unexpected(side_byte.error());

  switch (byte_as_char(*side_byte))
  {
  case 'B':
    ev->side = Side::BUY;
    break;
  case 'S':
    ev->side = Side::SELL;
    break;
  default:
    return std::unexpected(ParseErr{
        ParseErrKind::UnknownSide,
        this->cursor - 1,
        std::format("Unknown Add-Messgae Side Symbol at byte {}.", this->cursor - 1),
    });
  }

  if (const auto qty = this->parseU32(); qty)
    ev->qty = *qty;
  else
    return std::unexpected(qty.error());

  for (int i = 0; i < 8; ++i)
  {
    const auto ch = this->parseByte();
    if (!ch)
      return std::unexpected(ch.error());
    ev->stock[i] = byte_as_char(*ch);
  }

  if (const auto price = this->parseU32(); price)
    ev->price = *price;
  else
    return std::unexpected(price.error());

  return {};
}

std::expected<void, ParseErr> ItchParser::parseExecute(ItchEvent *ev)
{
  ev->kind = EventKind::EXECUTE;
  ev->valid_mask = EventField::ORDER_REF | EventField::QTY | EventField::MATCH_NUMBER;

  if (const auto err = this->parseHeader(ev); !err)
    return err;

  if (const auto qty = this->parseU32(); qty)
    ev->qty = *qty;
  else
    return std::unexpected(qty.error());

  if (const auto match_number = this->parseU64(); match_number)
    ev->match_number = *match_number;
  else
    return std::unexpected(match_number.error());

  return {};
}

std::expected<void, ParseErr> ItchParser::parseCancel(ItchEvent *ev)
{
  ev->kind = EventKind::CANCEL;
  ev->valid_mask = EventField::ORDER_REF | EventField::QTY;

  if (const auto err = this->parseHeader(ev); !err)
    return err;

  if (const auto qty = this->parseU32(); qty)
    ev->qty = *qty;
  else
    return std::unexpected(qty.error());

  return {};
}

std::expected<void, ParseErr> ItchParser::parseDelete(ItchEvent *ev)
{
  ev->kind = EventKind::DELETE;
  ev->valid_mask = EventField::ORDER_REF;
  return this->parseHeader(ev);
}

std::expected<void, ParseErr> ItchParser::parseReplace(ItchEvent *ev)
{
  ev->kind = EventKind::REPLACE;
  ev->valid_mask = EventField::ORDER_REF | EventField::NEW_ORDER_REF | EventField::QTY |
                   EventField::PRICE;

  if (const auto err = this->parseHeader(ev); !err)
    return err;

  if (const auto new_order_ref = this->parseU64(); new_order_ref)
    ev->new_order_ref = *new_order_ref;
  else
    return std::unexpected(new_order_ref.error());

  if (const auto qty = this->parseU32(); qty)
    ev->qty = *qty;
  else
    return std::unexpected(qty.error());

  if (const auto price = this->parseU32(); price)
    ev->price = *price;
  else
    return std::unexpected(price.error());

  return {};
}
