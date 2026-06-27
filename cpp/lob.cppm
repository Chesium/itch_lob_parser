export module itch.lob;

import std;
import itch.spec;

export struct Order
{
  std::uint16_t stock_locate;
  std::array<char, 8> stock;
  Side side;
  std::uint32_t qty;
  std::uint32_t price_raw;
};

export class LOB
{
public:
  void apply(const ItchEvent &ev);
  std::vector<std::pair<std::uint64_t, Order>> snapshot() const;

private:
  void addOrder(const ItchEvent &ev);
  void reduceOrder(std::uint64_t order_ref, std::uint32_t qty, const std::string &action);
  void deleteOrder(std::uint64_t order_ref);
  void replaceOrder(std::uint64_t order_ref, std::uint64_t new_order_ref, std::uint32_t qty, std::uint32_t price);
  std::unordered_map<std::uint64_t, Order> orders;
};

export std::ostream &operator<<(std::ostream &out, const Order &order);
