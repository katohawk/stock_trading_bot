import unittest

from run_okx_live import compute_sell_trigger, get_min_profit_ratio, sync_exchange_position_state


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


class SellTriggerTest(unittest.TestCase):
    def test_sell_trigger_respects_fee_floor_and_reference_wave(self):
        trigger, min_profit_ratio, swing_trigger, cost_trigger = compute_sell_trigger(
            reference_price=70544.30,
            avg_cost=70544.30,
            ratio_pct=0.35,
            fee_compensation_pct=0.15,
            taker_fee_rate=0.001,
            max_slippage=0.001,
        )

        self.assertAlmostEqual(swing_trigger, 70897.0215)
        self.assertAlmostEqual(min_profit_ratio, get_min_profit_ratio(0.001, 0.001))
        self.assertGreater(trigger, cost_trigger)
        self.assertEqual(trigger, swing_trigger)

    def test_sell_trigger_uses_cost_floor_when_reference_is_too_low(self):
        trigger, min_profit_ratio, swing_trigger, cost_trigger = compute_sell_trigger(
            reference_price=70000.0,
            avg_cost=70544.30,
            ratio_pct=0.35,
            fee_compensation_pct=0.15,
            taker_fee_rate=0.001,
            max_slippage=0.001,
        )

        self.assertGreater(cost_trigger, swing_trigger)
        self.assertEqual(trigger, cost_trigger)
        self.assertAlmostEqual(cost_trigger, 70544.30 * (1 + min_profit_ratio))


if __name__ == "__main__":
    unittest.main()
