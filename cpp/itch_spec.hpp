#pragma once

#include <optional>
#include <ostream>

enum EventKind
{
  ADD = 0,
  EXECUTE = 1,
  CANCEL = 2,
  DELETE = 3,
  REPLACE = 4,
  ERROR = 7
};

char evkind2char(EventKind kind);

enum Side
{
  BUY = 0,
  SELL = 1
};

class ItchEvent
{
public:
  EventKind kind;
  unsigned short stock_locate;
  unsigned short tracking_number;
  unsigned long long timestamp;
  unsigned long long order_ref = 0;
  unsigned long long new_order_ref = 0;
  std::optional<Side> side = std::nullopt;
  unsigned int qty = 0;
  unsigned int price = 0;
  unsigned long long match_number = 0;
  char stock[8] = {0, 0, 0, 0, 0, 0, 0, 0};
  unsigned char valid_mask = 0;
  friend std::ostream &operator<<(std::ostream &out, const ItchEvent &ev);
};
