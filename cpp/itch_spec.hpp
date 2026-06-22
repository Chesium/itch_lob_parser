#pragma once

#include <array>
#include <cstdint>
#include <optional>
#include <ostream>

enum class EventKind : std::uint8_t
{
  ADD = 0,
  EXECUTE = 1,
  CANCEL = 2,
  DELETE = 3,
  REPLACE = 4,
  ERROR = 7
};

char evkind2char(EventKind kind);

enum class Side : std::uint8_t
{
  BUY = 0,
  SELL = 1
};

namespace EventField
{
inline constexpr std::uint8_t ORDER_REF = 1u << 0;
inline constexpr std::uint8_t NEW_ORDER_REF = 1u << 1;
inline constexpr std::uint8_t SIDE = 1u << 2;
inline constexpr std::uint8_t QTY = 1u << 3;
inline constexpr std::uint8_t PRICE = 1u << 4;
inline constexpr std::uint8_t MATCH_NUMBER = 1u << 5;
inline constexpr std::uint8_t STOCK = 1u << 6;
} // namespace EventField

class ItchEvent
{
public:
  EventKind kind;
  std::uint16_t stock_locate;
  std::uint16_t tracking_number;
  std::uint64_t timestamp;
  std::uint64_t order_ref = 0;
  std::uint64_t new_order_ref = 0;
  std::optional<Side> side = std::nullopt;
  std::uint32_t qty = 0;
  std::uint32_t price = 0;
  std::uint64_t match_number = 0;
  std::array<char, 8> stock{};
  std::uint8_t valid_mask = 0;
  friend std::ostream &operator<<(std::ostream &out, const ItchEvent &ev);
};
