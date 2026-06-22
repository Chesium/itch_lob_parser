#include "itch_spec.hpp"
#include <iostream>
#include <iomanip>

char evkind2char(EventKind kind)
{
  switch (kind)
  {
  case EventKind::ADD:
    return 'A';
  case EventKind::EXECUTE:
    return 'E';
  case EventKind::CANCEL:
    return 'X';
  case EventKind::DELETE:
    return 'D';
  case EventKind::REPLACE:
    return 'U';
  default:
    return '*';
  }
}

std::ostream &operator<<(std::ostream &out, const ItchEvent &ev)
{
  out << evkind2char(ev.kind) << ' ' << ev.stock_locate << ' ' << ev.timestamp << ' ';
  if (ev.valid_mask & EventField::ORDER_REF)
    out << ev.order_ref;
  else
    out << 'N';
  out << ' ';
  if (ev.valid_mask & EventField::NEW_ORDER_REF)
    out << ev.new_order_ref;
  else
    out << 'N';
  out << ' ';
  if (ev.side && (ev.valid_mask & EventField::SIDE))
    out << ((*ev.side == Side::SELL) ? 'S' : 'B');
  else
    out << 'N';
  out << std::fixed << std::setprecision(4);
  out << ' ';
  if (ev.valid_mask & EventField::QTY)
    out << ev.qty;
  else
    out << 'N';
  out << ' ';
  if (ev.valid_mask & EventField::PRICE)
    out << (double)ev.price / 10000;
  else
    out << 'N';
  out << ' ';
  if (ev.valid_mask & EventField::MATCH_NUMBER)
    out << ev.match_number;
  else
    out << 'N';
  out << ' ';
  if (ev.valid_mask & EventField::STOCK)
  {
    for (int i = 0; i < 8; i++)
      if (ev.stock[i] >= 'A' && ev.stock[i] <= 'Z')
        out << ev.stock[i];
      else
        break;
  }
  else
    out << 'N';
  out << ' ';
  for (int i = 7; i >= 0; i--)
    out << (((ev.valid_mask >> i) & 1) ? '1' : '0');
  return out;
}
