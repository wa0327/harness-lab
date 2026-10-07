import unittest

from inventory import Inventory


class InventoryTest(unittest.TestCase):
    def setUp(self):
        self.inv = Inventory()
        self.inv.add("apple", 10.0, 5)
        self.inv.add("pear", 4.0, 1)
        self.inv.add("plum", 2.5, 0)

    def test_duplicate_sku_rejected(self):
        with self.assertRaises(ValueError):
            self.inv.add("apple", 1.0)

    def test_restock_adds_to_existing_quantity(self):
        self.assertEqual(self.inv.restock("apple", 3), 8)

    def test_restock_rejects_non_positive(self):
        with self.assertRaises(ValueError):
            self.inv.restock("apple", 0)

    def test_sell_returns_revenue_and_reduces_stock(self):
        self.assertEqual(self.inv.sell("apple", 2), 20.0)
        self.assertEqual(self.inv.items["apple"].quantity, 3)

    def test_cannot_oversell(self):
        with self.assertRaises(ValueError):
            self.inv.sell("pear", 2)
        self.assertEqual(self.inv.items["pear"].quantity, 1)

    def test_total_value_counts_quantity(self):
        self.assertEqual(self.inv.total_value(), 54.0)

    def test_low_stock_at_or_below_threshold(self):
        self.assertEqual(self.inv.low_stock(1), ["pear", "plum"])


if __name__ == "__main__":
    unittest.main()
