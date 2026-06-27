module itch.lob;

import std;

void LOB::apply(const ItchEvent &ev)
{
  switch (ev.kind)
  {
  case EventKind::ADD:
    this->addOrder(ev);
    break;
  case EventKind::EXECUTE:
    this->reduceOrder(ev.order_ref, ev.qty, "execute");
    break;
  case EventKind::CANCEL:
    this->reduceOrder(ev.order_ref, ev.qty, "cancel");
    break;
  case EventKind::DELETE:
    this->deleteOrder(ev.order_ref);
    break;
  case EventKind::REPLACE:
    this->replaceOrder(ev.order_ref, ev.new_order_ref, ev.qty, ev.price);
    break;
  case EventKind::ERROR:
    throw std::runtime_error("Encounter ItchEvent with EventKind ERROR.");
    break;
  }
}

void LOB::addOrder(const ItchEvent &ev)
{
  if (this->orders.find(ev.order_ref) != this->orders.end())
    throw std::runtime_error(std::format("duplicate order_ref {}.", ev.order_ref));
  if (ev.side == std::nullopt)
    throw std::runtime_error("ADD event side is missing.");
  if (ev.qty == 0)
    throw std::runtime_error("ADD quantity must be greater than 0.");
  this->orders.insert({ev.order_ref, Order{ev.stock_locate, ev.stock, *ev.side, ev.qty, ev.price}});
}

void LOB::reduceOrder(std::uint64_t order_ref, std::uint32_t qty, const std::string &action)
{
  auto it = this->orders.find(order_ref);
  if (it == this->orders.end())
    throw std::runtime_error(std::format("unknown order_ref {}.", order_ref));
  if (qty == 0)
    throw std::runtime_error(std::format("{} quantity must be greater than 0.", action));
  if (qty > it->second.qty)
    throw std::runtime_error(std::format("Cannot {} {} shares from order_ref {}, only {} remain.", action, qty, order_ref, it->second.qty));
  if (qty == it->second.qty)
  {
    this->orders.erase(it);
    return;
  }
  it->second.qty -= qty;
}

void LOB::deleteOrder(std::uint64_t order_ref)
{
  auto it = this->orders.find(order_ref);
  if (it == this->orders.end())
    throw std::runtime_error(std::format("unknown order_ref {}.", order_ref));
  this->orders.erase(it);
}

void LOB::replaceOrder(std::uint64_t order_ref, std::uint64_t new_order_ref, std::uint32_t qty, std::uint32_t price)
{
  auto it = this->orders.find(order_ref);
  if (it == this->orders.end())
    throw std::runtime_error(std::format("unknown order_ref {}.", order_ref));
  if (this->orders.find(new_order_ref) != this->orders.end())
    throw std::runtime_error(std::format("duplicate order_ref {}.", new_order_ref));
  if (qty == 0)
    throw std::runtime_error("replace quantity must be greater than 0.");

  Order replacement = it->second;
  replacement.qty = qty;
  replacement.price_raw = price;
  this->orders.erase(it);
  this->orders.insert({new_order_ref, replacement});
}

std::vector<std::pair<std::uint64_t, Order>> LOB::snapshot() const
{
  std::vector<std::pair<std::uint64_t, Order>> rows(this->orders.begin(), this->orders.end());
  std::sort(rows.begin(), rows.end(), [](const auto &lhs, const auto &rhs) {
    return lhs.first < rhs.first;
  });
  return rows;
}

std::ostream &operator<<(std::ostream &out, const Order &order)
{
  out << order.stock_locate << ' ';
  for (char ch : order.stock)
  {
    if (ch >= 'A' && ch <= 'Z')
      out << ch;
    else
      break;
  }
  out << ' ' << (order.side == Side::SELL ? 'S' : 'B') << ' ' << order.qty << ' ';
  out << std::fixed << std::setprecision(4) << static_cast<double>(order.price_raw) / 10000;
  return out;
}
