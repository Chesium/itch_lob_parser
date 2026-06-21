#include "itch_spec.hpp"
#include <iostream>
#include <iomanip>

char evkind2char(EventKind kind)
{
  switch (kind)
  {
  case ADD:
    return 'A';
  case EXECUTE:
    return 'E';
  case CANCEL:
    return 'X';
  case DELETE:
    return 'D';
  case REPLACE:
    return 'U';
  default:
    return '*';
  }
}

std::ostream &operator<<(std::ostream &out, const ItchEvent &ev)
{
  out << evkind2char(ev.kind) << ' ' << ev.stock_locate << ' ' << ev.timestamp << ' ';
  if (ev.valid_mask & 0b1)
    out << ev.order_ref;
  else
    out << 'N';
  out << ' ';
  if (ev.valid_mask & 0b10)
    out << ev.new_order_ref;
  else
    out << 'N';
  out << ' ';
  if (ev.side && (ev.valid_mask & 0b100))
    out << (*ev.side ? 'S' : 'B');
  else
    out << 'N';
  out << std::fixed << std::setprecision(4);
  out << ' ';
  if (ev.valid_mask & 0b1000)
    out << ev.qty;
  else
    out << 'N';
  out << ' ';
  if (ev.valid_mask & 0b10000)
    out << (double)ev.price / 10000;
  else
    out << 'N';
  out << ' ';
  if (ev.valid_mask & 0b100000)
    out << ev.match_number;
  else
    out << 'N';
  out << ' ';
  if (ev.valid_mask & 0b1000000)
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
