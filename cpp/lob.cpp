#include "lob.hpp"
#include <format>

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
  this->orders.insert({ev.order_ref, Order{ev.stock_locate, ev.stock, *ev.side, ev.qty, ev.price}});
}

void LOB::reduceOrder(uint64_t order_ref, uint32_t qty, const std::string &action)
{
  auto it = this->orders.find(order_ref);
  if (it == this->orders.end())
    throw std::runtime_error(std::format("unknown order_ref {}.", order_ref));
  if (qty > it->second.qty)
    throw std::runtime_error(std::format("Cannot {} {} shares from order_ref {}, only {} remain.", action, qty, order_ref, it->second.qty));
  if (qty == it->second.qty)
    this->deleteOrder(order_ref);
  it->second.qty -= qty;
}

void LOB::deleteOrder(uint64_t order_ref)
{
  auto it = this->orders.find(order_ref);
  if (it == this->orders.end())
    throw std::runtime_error(std::format("unknown order_ref {}.", order_ref));
  this->orders.erase(it);
}

void LOB::replaceOrder(uint64_t order_ref, uint64_t new_order_ref, uint32_t qty, uint32_t price)
{
  auto it = this->orders.find(order_ref);
  if (it == this->orders.end())
    throw std::runtime_error(std::format("unknown order_ref {}.", order_ref));
  if (this->orders.find(new_order_ref) != this->orders.end())
    throw std::runtime_error(std::format("duplicate order_ref {}.", new_order_ref));
  it->second.qty = qty;
  it->second.price_raw = price;
}