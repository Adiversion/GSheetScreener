#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_trade_lifecycle.py — Verification Suite for Institutional TradeLifecycleManager
"""

import sys
import os
import unittest

# Ensure src is in python path
SRC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from trade_lifecycle import (
    TradeLifecycleManager,
    TradeState,
    OrderAction,
    ExitReason,
    MacroRegime,
    MarketBar,
    Position,
    calculate_theoretical_skewness_edge
)


class TestTradeLifecycleManager(unittest.TestCase):

    def setUp(self):
        self.manager = TradeLifecycleManager(
            portfolio_equity=100000.0,
            risk_per_trade_pct=0.01,
            max_exposure_pct=0.15,
            max_turnover_participation=0.015,
            min_turnover_floor=50000000.0,
            be_buffer_pct=0.015,
            partial_bank_pct=0.40,
            runner_stop_floor_pct=0.10
        )

    def test_position_sizing_standard(self):
        # CMP = 100, ATR14 = 3 (2*ATR = 6% -> within 5% to 7% bounds)
        # R = 100,000 * 0.01 = 1,000 INR
        # Stop distance = 6% of 100 = 6 INR
        # Raw shares = floor(1000 / 6) = 166 shares
        # Exposure cap = 15% of 100,000 = 15,000 INR -> 150 shares
        # Turnover = 10 Cr -> 1.5% is 15 Lakh -> 15,000 shares
        # Final shares should be min(166, 150) = 150 shares
        shares, stop_price, stop_pct, meta = self.manager.calculate_initial_risk_and_size(
            cmp=100.0,
            atr_14=3.0,
            turnover_20d=100000000.0,
            regime=MacroRegime.BULL_MARKET,
            circuit_band_pct=0.20
        )
        self.assertEqual(shares, 150)
        self.assertEqual(stop_price, 94.0)
        self.assertAlmostEqual(stop_pct, 0.06, places=4)
        self.assertTrue(meta["allowed"])

    def test_position_sizing_turnover_floor_rejection(self):
        # Turnover ₹3 Crore < ₹5 Crore floor -> Should be rejected
        shares, _, _, meta = self.manager.calculate_initial_risk_and_size(
            cmp=100.0,
            atr_14=3.0,
            turnover_20d=30000000.0,
            regime=MacroRegime.BULL_MARKET
        )
        self.assertEqual(shares, 0)
        self.assertFalse(meta["allowed"])
        self.assertIn("LIQUIDITY_DISQUALIFIED", meta["reason"])

    def test_position_sizing_circuit_band_rejection(self):
        # Circuit band 5% -> Should be rejected to avoid lower circuit trap
        shares, _, _, meta = self.manager.calculate_initial_risk_and_size(
            cmp=100.0,
            atr_14=2.0,
            turnover_20d=80000000.0,
            regime=MacroRegime.BULL_MARKET,
            circuit_band_pct=0.05
        )
        self.assertEqual(shares, 0)
        self.assertFalse(meta["allowed"])
        self.assertIn("CIRCUIT_BAND_DISQUALIFIED", meta["reason"])

    def test_position_sizing_defensive_cash_rejection(self):
        # In DEFENSIVE_CASH regime, no new entries allowed
        shares, _, _, meta = self.manager.calculate_initial_risk_and_size(
            cmp=100.0,
            atr_14=3.0,
            turnover_20d=100000000.0,
            regime=MacroRegime.DEFENSIVE_CASH
        )
        self.assertEqual(shares, 0)
        self.assertFalse(meta["allowed"])
        self.assertIn("REGIME_FORBIDDEN", meta["reason"])

    def test_circuit_proximity_warnings(self):
        # CMP 98, Lower Circuit 97 (within 1.03% distance <= 1.5%)
        diag = self.manager.check_liquidity_and_circuit(
            cmp=98.0,
            turnover_20d=60000000.0,
            circuit_band_pct=0.10,
            lower_circuit=97.0,
            upper_circuit=110.0
        )
        self.assertTrue(diag["near_lower_circuit"])
        self.assertTrue(diag["execution_risk_flag"])

    def test_state_0_initial_stop_exit(self):
        pos = Position(
            symbol="TEST",
            entry_price=100.0,
            entry_date="2026-09-01",
            total_shares=100,
            current_shares=100,
            current_stop=93.0,
            initial_stop_price=93.0,
            state=TradeState.STATE_0_OPEN
        )
        bar = MarketBar(
            symbol="TEST", cmp=92.5, open=95.0, high=95.0, low=92.0, close=92.5,
            volume=50000, atr_14=3.0, sma_20=98.0, sma_50=96.0, sma_50_prev=95.5,
            sma_150=90.0, sma_200=85.0, ema_20=97.0, vol_sma_20=60000, vol_max_20=100000,
            turnover_20d=70000000.0
        )
        signals = self.manager.generate_order_signals(pos, bar)
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0].action, OrderAction.FULL_CLOSE)
        self.assertEqual(signals[0].reason, ExitReason.INITIAL_STOP)
        self.assertEqual(pos.state, TradeState.STATE_CLOSED)

    def test_state_0_to_state_1_risk_free_transition(self):
        pos = Position(
            symbol="TEST",
            entry_price=100.0,
            entry_date="2026-09-01",
            total_shares=100,
            current_shares=100,
            current_stop=93.0,
            initial_stop_price=93.0,
            state=TradeState.STATE_0_OPEN
        )
        # Price surges to +14% (114.0)
        bar = MarketBar(
            symbol="TEST", cmp=114.0, open=110.0, high=115.0, low=109.0, close=114.0,
            volume=80000, atr_14=3.5, sma_20=102.0, sma_50=98.0, sma_50_prev=97.5,
            sma_150=90.0, sma_200=85.0, ema_20=105.0, vol_sma_20=60000, vol_max_20=100000,
            turnover_20d=70000000.0
        )
        signals = self.manager.generate_order_signals(pos, bar)
        self.assertEqual(len(signals), 0)  # No exit order, position intact
        self.assertEqual(pos.state, TradeState.STATE_1_RISK_FREE)
        self.assertEqual(pos.current_stop, 101.5)  # +1.5% Breakeven buffer

    def test_state_1_breakeven_stop_exit(self):
        pos = Position(
            symbol="TEST",
            entry_price=100.0,
            entry_date="2026-09-01",
            total_shares=100,
            current_shares=100,
            current_stop=101.5,
            initial_stop_price=93.0,
            state=TradeState.STATE_1_RISK_FREE
        )
        # Price drops to 101.0 (below 101.5 breakeven)
        bar = MarketBar(
            symbol="TEST", cmp=101.0, open=103.0, high=103.0, low=100.5, close=101.0,
            volume=60000, atr_14=3.0, sma_20=102.0, sma_50=98.0, sma_50_prev=97.5,
            sma_150=90.0, sma_200=85.0, ema_20=103.0, vol_sma_20=60000, vol_max_20=100000,
            turnover_20d=70000000.0
        )
        signals = self.manager.generate_order_signals(pos, bar)
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0].action, OrderAction.FULL_CLOSE)
        self.assertEqual(signals[0].reason, ExitReason.BREAKEVEN_STOP)
        self.assertEqual(pos.state, TradeState.STATE_CLOSED)

    def test_state_1_to_state_2_bank_and_trail(self):
        pos = Position(
            symbol="TEST",
            entry_price=100.0,
            entry_date="2026-09-01",
            total_shares=100,
            current_shares=100,
            current_stop=101.5,
            initial_stop_price=93.0,
            state=TradeState.STATE_1_RISK_FREE
        )
        # Price surges to +22% (122.0) -> triggers 40% partial exit
        bar = MarketBar(
            symbol="TEST", cmp=122.0, open=118.0, high=123.0, low=117.0, close=122.0,
            volume=90000, atr_14=3.8, sma_20=108.0, sma_50=100.0, sma_50_prev=99.0,
            sma_150=92.0, sma_200=86.0, ema_20=112.0, vol_sma_20=60000, vol_max_20=100000,
            turnover_20d=80000000.0
        )
        signals = self.manager.generate_order_signals(pos, bar)
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0].action, OrderAction.PARTIAL_PROFIT)
        self.assertEqual(signals[0].shares, 40)
        self.assertEqual(pos.state, TradeState.STATE_2_BANK_AND_TRAIL)
        self.assertEqual(pos.current_shares, 60)
        self.assertEqual(pos.banked_shares, 40)
        self.assertEqual(pos.current_stop, 110.0)  # +10% profit locked on 60% runner

    def test_state_2_to_state_3_power_runner(self):
        pos = Position(
            symbol="TEST",
            entry_price=100.0,
            entry_date="2026-09-01",
            total_shares=100,
            current_shares=60,
            banked_shares=40,
            current_stop=110.0,
            initial_stop_price=93.0,
            state=TradeState.STATE_2_BANK_AND_TRAIL
        )
        # Runner reaches +30% (130.0) -> transitions to POWER_RUNNER
        bar = MarketBar(
            symbol="TEST", cmp=130.0, open=125.0, high=132.0, low=124.0, close=130.0,
            volume=110000, atr_14=4.0, sma_20=114.0, sma_50=104.0, sma_50_prev=103.0,
            sma_150=94.0, sma_200=87.0, ema_20=118.0, vol_sma_20=70000, vol_max_20=120000,
            turnover_20d=90000000.0
        )
        signals = self.manager.generate_order_signals(pos, bar)
        self.assertEqual(len(signals), 0)
        self.assertEqual(pos.state, TradeState.STATE_3_POWER_RUNNER)

    def test_power_runner_50sma_grace_period(self):
        # Entry at 80.0 -> +10% floor is 88.0. Current 50 SMA is 100.0.
        pos = Position(
            symbol="TEST",
            entry_price=80.0,
            entry_date="2026-09-01",
            total_shares=100,
            current_shares=60,
            banked_shares=40,
            current_stop=88.0,
            state=TradeState.STATE_3_POWER_RUNNER
        )
        # Day 1: Close below rising 50 SMA (99 < 100), but volume 40k < 60k average
        # 99.0 > 88.0 (+10% floor not hit), so 50 SMA grace rule applies
        bar_day1 = MarketBar(
            symbol="TEST", cmp=99.0, open=102.0, high=102.0, low=98.5, close=99.0,
            volume=40000, atr_14=3.5, sma_20=105.0, sma_50=100.0, sma_50_prev=99.5,
            sma_150=92.0, sma_200=85.0, ema_20=104.0, vol_sma_20=60000, vol_max_20=100000,
            turnover_20d=80000000.0
        )
        signals1 = self.manager.generate_order_signals(pos, bar_day1)
        self.assertEqual(len(signals1), 0)  # Grace period applied!
        self.assertEqual(pos.days_below_sma50, 1)

        # Day 2: Still below 50 SMA -> Grace period expires, immediate exit
        bar_day2 = MarketBar(
            symbol="TEST", cmp=98.0, open=99.0, high=99.5, low=97.5, close=98.0,
            volume=45000, atr_14=3.5, sma_20=104.0, sma_50=100.0, sma_50_prev=99.8,
            sma_150=92.0, sma_200=85.0, ema_20=103.0, vol_sma_20=60000, vol_max_20=100000,
            turnover_20d=80000000.0
        )
        signals2 = self.manager.generate_order_signals(pos, bar_day2)
        self.assertEqual(len(signals2), 1)
        self.assertEqual(signals2[0].action, OrderAction.FULL_CLOSE)
        self.assertEqual(signals2[0].reason, ExitReason.PRIMARY_TREND_50SMA)
        self.assertEqual(pos.state, TradeState.STATE_CLOSED)

    def test_power_runner_climax_exit(self):
        # Entry at 100.0, peak was 140.0. 50 SMA is 100.0 (140 / 100 = 1.40x > 1.35x)
        pos = Position(
            symbol="TEST",
            entry_price=100.0,
            entry_date="2026-09-01",
            total_shares=100,
            current_shares=60,
            banked_shares=40,
            current_stop=110.0,
            peak_price=140.0,
            state=TradeState.STATE_3_POWER_RUNNER
        )
        # Close drops below 20 EMA (124 < 125) while remaining above 110 stop
        bar = MarketBar(
            symbol="TEST", cmp=124.0, open=135.0, high=140.0, low=123.0, close=124.0,
            volume=80000, atr_14=5.0, sma_20=128.0, sma_50=100.0, sma_50_prev=99.0,
            sma_150=90.0, sma_200=80.0, ema_20=125.0, vol_sma_20=70000, vol_max_20=100000,
            turnover_20d=80000000.0
        )
        signals = self.manager.generate_order_signals(pos, bar)
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0].action, OrderAction.FULL_CLOSE)
        self.assertEqual(signals[0].reason, ExitReason.CLIMAX_MEAN_REVERSION_20EMA)

    def test_power_runner_blowoff_exhaustion_exit(self):
        pos = Position(
            symbol="TEST",
            entry_price=100.0,
            entry_date="2026-09-01",
            total_shares=100,
            current_shares=60,
            banked_shares=40,
            current_stop=110.0,
            state=TradeState.STATE_3_POWER_RUNNER
        )
        # CMP 200, 200 SMA 110 -> CMP / 200 SMA = 1.81 (> 1.70x)
        # Range = 215 - 195 = 20 > 3 * ATR (3 * 5 = 15)
        # Volume = 500,000 == 20-day high (vol_max_20 = 500,000)
        bar = MarketBar(
            symbol="TEST", cmp=205.0, open=198.0, high=215.0, low=195.0, close=205.0,
            volume=500000, atr_14=5.0, sma_20=170.0, sma_50=140.0, sma_50_prev=138.0,
            sma_150=120.0, sma_200=110.0, ema_20=175.0, vol_sma_20=150000, vol_max_20=500000,
            turnover_20d=150000000.0
        )
        signals = self.manager.generate_order_signals(pos, bar)
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0].action, OrderAction.FULL_CLOSE)
        self.assertEqual(signals[0].reason, ExitReason.BLOWOFF_EXHAUSTION)

    def test_circuit_lock_amo_fallback(self):
        pos = Position(
            symbol="TEST",
            entry_price=100.0,
            entry_date="2026-09-01",
            total_shares=100,
            current_shares=100,
            current_stop=93.0,
            state=TradeState.STATE_0_OPEN
        )
        # Stock gaps down locked at lower circuit (90.0) with zero range (high == low)
        bar = MarketBar(
            symbol="TEST", cmp=90.0, open=90.0, high=90.0, low=90.0, close=90.0,
            volume=1000, atr_14=4.0, sma_20=98.0, sma_50=95.0, sma_50_prev=94.5,
            sma_150=90.0, sma_200=85.0, ema_20=97.0, vol_sma_20=80000, vol_max_20=120000,
            turnover_20d=60000000.0, lower_circuit=90.0, upper_circuit=110.0, circuit_band_pct=0.10
        )
        signals = self.manager.generate_order_signals(pos, bar)
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0].action, OrderAction.AMO_FALLBACK)
        self.assertEqual(signals[0].urgency, "PRE_MARKET_AMO")
        self.assertTrue(pos.is_circuit_locked)
        self.assertTrue(pos.queued_amo)

    def test_theoretical_skewness_edge(self):
        res = calculate_theoretical_skewness_edge()
        self.assertTrue(res["positive_skewness_unlocked"])
        self.assertGreater(res["dynamic_expected_return_per_trade_pct"], res["fixed_expected_return_per_trade_pct"])
        self.assertGreater(res["expected_edge_lift_pct"], 0.0)


if __name__ == "__main__":
    unittest.main()
