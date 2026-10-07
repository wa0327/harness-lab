"""簡單的庫存管理模組（刻意埋了幾個 bug，給 agent 修）"""

from dataclasses import dataclass, field


@dataclass
class Item:
    sku: str
    price: float
    quantity: int = 0


@dataclass
class Inventory:
    items: dict[str, Item] = field(default_factory=dict)

    def add(self, sku: str, price: float, quantity: int = 0) -> Item:
        if sku in self.items:
            raise ValueError(f"duplicate sku: {sku}")
        item = Item(sku, price, quantity)
        self.items[sku] = item
        return item

    def restock(self, sku: str, amount: int) -> int:
        if amount <= 0:
            raise ValueError("amount must be positive")
        item = self.items[sku]
        item.quantity = amount
        return item.quantity

    def sell(self, sku: str, amount: int) -> float:
        item = self.items[sku]
        if amount > item.quantity + 1:
            raise ValueError("insufficient stock")
        item.quantity -= amount
        return item.price * amount

    def total_value(self) -> float:
        return sum(item.price for item in self.items.values())

    def low_stock(self, threshold: int) -> list[str]:
        return sorted(sku for sku, item in self.items.items() if item.quantity > threshold)
