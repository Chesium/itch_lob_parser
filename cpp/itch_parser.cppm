export module itch.parser;

import std;
import itch.spec;

export enum class ParseErrKind
{
  UnexpectedEof,
  UnknownMessageType,
  UnknownSide
};

export struct ParseErr
{
  ParseErrKind kind;
  std::size_t offset;
  std::string message;
};

export class ItchParser
{
public:
  explicit ItchParser(std::size_t cache_size);

  std::expected<std::vector<ItchEvent>, ParseErr> start(std::span<const std::byte> bytes);

private:
  std::size_t cache_size;
  std::span<const std::byte> stream;
  std::size_t cursor;

  std::expected<std::byte, ParseErr> parseByte();
  std::expected<std::uint16_t, ParseErr> parseU16();
  std::expected<std::uint32_t, ParseErr> parseU32();
  std::expected<std::uint64_t, ParseErr> parseU48();
  std::expected<std::uint64_t, ParseErr> parseU64();
  std::expected<void, ParseErr> parseHeader(ItchEvent *ev);
  std::expected<void, ParseErr> parseAdd(ItchEvent *ev);
  std::expected<void, ParseErr> parseExecute(ItchEvent *ev);
  std::expected<void, ParseErr> parseCancel(ItchEvent *ev);
  std::expected<void, ParseErr> parseDelete(ItchEvent *ev);
  std::expected<void, ParseErr> parseReplace(ItchEvent *ev);
};
