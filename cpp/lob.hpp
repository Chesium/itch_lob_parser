#pragma once

#include "itch_spec.hpp"
#include <unordered_map>

struct Order
{
  uint16_t stock_locate;
  std::array<char, 8> stock;
  Side side;
  uint32_t qty;
  uint32_t price_raw;
};

class LOB
{
public:
  void apply(const ItchEvent &ev);

private:
  void addOrder(const ItchEvent &ev);
  void reduceOrder(uint64_t order_ref, uint32_t qty, const std::string &action);
  void deleteOrder(uint64_t order_ref);
  void replaceOrder(uint64_t order_ref, uint64_t new_order_ref, uint32_t qty, uint32_t price);
  std::unordered_map<uint64_t, Order> orders; // order_ref -> order
};

std::ostream &operator<<(std::ostream &out, const Order &ev);