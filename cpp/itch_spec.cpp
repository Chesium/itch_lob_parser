#include "itch_spec.hpp"
#include <iostream>
#include <iomanip>

std::ostream &operator<<(std::ostream &out, const ItchEvent &ev)
{
  out << ev.kind << ' ' << ev.stock_locate << ' ' << ev.timestamp << ' ' << (ev.valid_mask & 0b1 ? ev.order_ref : 'N') << ' ' << (ev.valid_mask & 0b10 ? ev.new_order_ref : 'N') << ' ';
  if (ev.side && (ev.valid_mask & 0b100))
    out << (*ev.side ? 'S' : 'B');
  else
    out << 'N';
  out << std::fixed << std::setprecision(4);
  out << ' ' << ((ev.valid_mask & 0b1000) ? ev.qty : 'N') << ' ' << ((ev.valid_mask & 0b10000) ? (double)ev.price / 10000 : 'N') << ' ' << ((ev.valid_mask & 0b100000) ? ev.match_number : 'N') << ' ';
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
