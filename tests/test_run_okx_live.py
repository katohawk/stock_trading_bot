import unittest

from run_okx_live import sync_exchange_position_state


class SyncExchangePositionStateTest(unittest.TestCase):
    def test_initializes_reference_price_for_existing_exchange_position(self):
        ref_price, avg_cost, position_qty, changed = sync_exchange_position_state(
            symbol="BTC/USDT",
            price=71455.0,
            exchange_qty=0.00071792634,
            reference_price=None,
            avg_cost=70544.30,
            position_qty=0.0,
        )

        self.assertTrue(changed)
        self.assertEqual(position_qty, 0.00071792634)
        self.assertEqual(avg_cost, 70544.30)
        self.assertEqual(ref_price, 70544.30)

    def test_preserves_existing_reference_price(self):
        ref_price, avg_cost, position_qty, changed = sync_exchange_position_state(
            symbol="BTC/USDT",
            price=71455.0,
            exchange_qty=0.00071792634,
            reference_price=71000.0,
            avg_cost=70544.30,
            position_qty=0.00071792634,
        )

        self.assertFalse(changed)
        self.assertEqual(position_qty, 0.00071792634)
        self.assertEqual(avg_cost, 70544.30)
        self.assertEqual(ref_price, 71000.0)


if __name__ == "__main__":
    unittest.main()
