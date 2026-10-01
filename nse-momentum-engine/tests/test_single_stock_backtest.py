#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_single_stock_backtest.py — Offline verification for the credibility
backtester and the fixed-target rotation exit.

All tests build synthetic OHLC series, so they never touch the network.
"""

import json
import os
import sys
import unittest

import pandas as pd

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (ROOT_DIR, os.path.join(ROOT_DIR, "src")):
    if p not in sys.path:
        sys.path.insert(0, p)

from scripts.single_stock_backtest import (  # noqa: E402
    analyse, forward_outcome_study, compounding_sim, stop_distance_pct,
    build_verdict, DEFAULTS, pace_of, index_entry, build_index,
)
from trade_lifecycle import (  # noqa: E402
    TradeLifecycleManager, TradeState, OrderAction, ExitReason, Position, MarketBar,
)


def make_df(closes):
    """Build a synthetic OHLC frame with a business-day index."""
    idx = pd.date_range("2022-01-03", periods=len(closes), freq="B")
    close = pd.Series(closes, index=idx, dtype=float)
    high = close * 1.004
    low = close * 0.996
    open_ = close.shift(1).fillna(close.iloc[0])
    return pd.DataFrame({"Open": open_, "High": high, "Low": low,
                         "Close": close, "Volume": 1_000_000.0}, index=idx)


def uptrend_closes(n=400, up=0.012, down=-0.004, start=100.0):
    """Alternating up/down drift keeps RSI in the 45–82 sweet zone while rising."""
    out = [start]
    for t in range(1, n):
        r = up if t % 2 == 0 else down
        out.append(out[-1] * (1 + r))
    return out


class TestIndicators(unittest.TestCase):
    def test_stop_distance_clamped(self):
        p = dict(DEFAULTS)
        self.assertAlmostEqual(stop_distance_pct(100.0, 0.0, p), 0.05, places=6)
        self.assertAlmostEqual(stop_distance_pct(100.0, 999.0, p), 0.07, places=6)
        # 2 x ATR / entry inside the band
        self.assertAlmostEqual(stop_distance_pct(100.0, 3.0, p), 0.06, places=6)


class TestForwardStudy(unittest.TestCase):
    def test_uptrend_mostly_hits_target(self):
        df = make_df(uptrend_closes(400))
        s = forward_outcome_study(df, dict(DEFAULTS))
        self.assertGreater(s["observations"], 20)
        self.assertGreater(s["target_hit_rate_pct"], 70.0)
        self.assertGreater(s["expectancy_pct"], 0.0)

    def test_break_after_uptrend_produces_stops(self):
        closes = uptrend_closes(305)
        for _ in range(30):
            closes.append(closes[-1] * 0.97)  # sharp trend break
        df = make_df(closes)
        s = forward_outcome_study(df, dict(DEFAULTS))
        self.assertGreater(s["stop_hits"], 0)

    def test_no_signals_returns_zeroed_study(self):
        closes = [100.0 - i * 0.5 for i in range(300)]  # pure downtrend
        s = forward_outcome_study(make_df(closes), dict(DEFAULTS))
        self.assertEqual(s["observations"], 0)
        self.assertEqual(s["target_hit_rate_pct"], 0.0)


class TestTimeToTarget(unittest.TestCase):
    def test_distribution_present_and_ordered(self):
        df = make_df(uptrend_closes(400))
        s = forward_outcome_study(df, dict(DEFAULTS))
        tt = s["time_to_target"]
        self.assertIsNotNone(tt)
        self.assertGreater(tt["target_count"], 0)
        td = tt["trading_days"]
        self.assertLessEqual(td["p25"], td["median"])
        self.assertLessEqual(td["median"], td["p75"])
        self.assertIn("0-2d", tt["buckets_trading_days"])
        # calendar days must be >= trading days
        self.assertGreaterEqual(tt["calendar_days"]["median"], td["median"])

    def test_analyse_strips_raw_samples_for_compact_json(self):
        df = make_df(uptrend_closes(400))
        report = analyse(df, "TEST", {"capital": 1000.0, "target_pct": 0.15})
        self.assertIn("time_to_target", report["study"])
        self.assertNotIn("_target_trading_days", report["study"])
        self.assertNotIn("_target_calendar_days", report["study"])
        self.assertNotIn("_raw_time_to_target", report)
        json.dumps(report)

    def test_analyse_can_keep_raw_samples(self):
        df = make_df(uptrend_closes(400))
        report = analyse(df, "TEST", {"capital": 1000.0, "target_pct": 0.15}, keep_raw=True)
        raw = report["_raw_time_to_target"]
        self.assertIn("trading", raw)
        self.assertGreater(len(raw["trading"]), 0)
        self.assertEqual(len(raw["trading"]), len(raw["calendar"]))


class TestPaceAndIndex(unittest.TestCase):
    def test_pace_classification(self):
        self.assertEqual(pace_of(5), "fast")
        self.assertEqual(pace_of(10), "fast")
        self.assertEqual(pace_of(18), "medium")
        self.assertEqual(pace_of(25), "medium")
        self.assertEqual(pace_of(40), "slow")
        self.assertEqual(pace_of(None), "unknown")

    def test_index_entry_is_compact_and_json_safe(self):
        df = make_df(uptrend_closes(400))
        report = analyse(df, "TEST", {"capital": 1000.0, "target_pct": 0.15})
        entry = index_entry(report)
        self.assertEqual(entry["symbol"], "TEST")
        for key in ("credible", "score", "pace", "target_hit_rate_pct",
                    "stop_hit_rate_pct", "expectancy_pct", "median_days_to_target",
                    "median_calendar_days_to_target", "avg_cycle_days", "total_return_pct"):
            self.assertIn(key, entry)
        json.dumps(entry)

    def test_build_index_sorts_best_score_first(self):
        mk = lambda sym, score: {
            "symbol": sym, "pace": "fast",
            "study": {"target_hit_rate_pct": 60.0, "stop_hit_rate_pct": 20.0,
                      "expectancy_pct": 2.0, "time_to_target": {}},
            "simulation": {}, "verdict": {"credible": True, "score": score},
        }
        index = build_index([mk("AAA", 40.0), mk("BBB", 90.0), mk("CCC", None)])
        self.assertEqual(index["count"], 3)
        self.assertEqual([e["symbol"] for e in index["entries"]], ["BBB", "AAA", "CCC"])
        json.dumps(index)


class TestCompoundingSim(unittest.TestCase):
    def test_capital_compounds_above_start(self):
        df = make_df(uptrend_closes(400))
        sim = compounding_sim(df, dict(DEFAULTS))
        self.assertGreater(sim["cycles"], 0)
        self.assertGreater(sim["final_capital"], DEFAULTS["capital"])
        self.assertGreater(sim["total_return_pct"], 0.0)

    def test_cycles_never_overlap(self):
        df = make_df(uptrend_closes(400))
        sim = compounding_sim(df, dict(DEFAULTS))
        dates = [(t["entry_date"], t["exit_date"], t["hold_days"]) for t in sim["trades"]]
        for entry, exit_, hold in dates:
            self.assertLess(entry, exit_)
            self.assertGreaterEqual(hold, 0)


class TestVerdict(unittest.TestCase):
    def test_insufficient_data(self):
        v = build_verdict({"observations": 3}, {})
        self.assertFalse(v["credible"])
        self.assertIsNone(v["score"])

    def test_credible_thresholds(self):
        v = build_verdict(
            {"observations": 40, "target_hit_rate_pct": 70.0,
             "stop_hit_rate_pct": 20.0, "expectancy_pct": 3.0},
            {"total_return_pct": 40.0},
        )
        self.assertTrue(v["credible"])
        self.assertGreater(v["score"], 0)

    def test_weak_when_stops_dominate(self):
        v = build_verdict(
            {"observations": 40, "target_hit_rate_pct": 20.0,
             "stop_hit_rate_pct": 75.0, "expectancy_pct": -3.0},
            {"total_return_pct": -30.0},
        )
        self.assertFalse(v["credible"])


class TestReportShape(unittest.TestCase):
    def test_analyse_is_json_serialisable(self):
        df = make_df(uptrend_closes(400))
        report = analyse(df, "test", {"capital": 1000.0, "target_pct": 0.15})
        self.assertEqual(report["symbol"], "TEST")
        for key in ("period", "params", "study", "simulation", "verdict"):
            self.assertIn(key, report)
        # Must serialise without numpy scalar leakage.
        json.dumps(report)


class TestRotationExit(unittest.TestCase):
    def _position(self):
        return Position(
            symbol="ROT", entry_price=100.0, entry_date="2026-09-01",
            total_shares=10, current_shares=10, current_stop=93.0,
            initial_stop_price=93.0, state=TradeState.STATE_0_OPEN,
        )

    def _bar(self, cmp):
        return MarketBar(
            symbol="ROT", cmp=cmp, open=cmp, high=cmp, low=cmp, close=cmp,
            volume=100000, atr_14=3.0, sma_20=cmp, sma_50=cmp, sma_50_prev=cmp,
            sma_150=cmp, sma_200=cmp, ema_20=cmp, vol_sma_20=100000, vol_max_20=100000,
            turnover_20d=80000000.0,
        )

    def test_rotation_mode_exits_full_position_at_target(self):
        mgr = TradeLifecycleManager(portfolio_equity=1000.0, rotation_target_pct=0.15)
        pos = self._position()
        signals = mgr.generate_order_signals(pos, self._bar(115.0))
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0].action, OrderAction.FULL_CLOSE)
        self.assertEqual(signals[0].reason, ExitReason.ROTATION_TARGET)
        self.assertEqual(signals[0].shares, 10)          # whole position, no runner
        self.assertEqual(signals[0].limit_price, 115.0)
        self.assertEqual(signals[0].metadata["action"], "ROTATE_TO_NEXT_LEADER")
        self.assertEqual(pos.state, TradeState.STATE_CLOSED)
        self.assertEqual(pos.current_shares, 0)

    def test_rotation_mode_holds_below_target(self):
        mgr = TradeLifecycleManager(portfolio_equity=1000.0, rotation_target_pct=0.15)
        pos = self._position()
        signals = mgr.generate_order_signals(pos, self._bar(108.0))
        self.assertEqual(signals, [])
        self.assertEqual(pos.state, TradeState.STATE_0_OPEN)

    def test_default_mode_keeps_two_tier_behaviour(self):
        # With rotation disabled, +15% must still mean RISK_FREE, not an exit.
        mgr = TradeLifecycleManager(portfolio_equity=1000.0)
        pos = self._position()
        signals = mgr.generate_order_signals(pos, self._bar(115.0))
        self.assertEqual(signals, [])
        self.assertEqual(pos.state, TradeState.STATE_1_RISK_FREE)


if __name__ == "__main__":
    unittest.main()
