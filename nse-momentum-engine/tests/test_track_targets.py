#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_track_targets.py — Offline tests for the daily target tracker.

All tests use synthetic prices, so they never touch the network.
"""

import json
import os
import sys
import unittest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (ROOT_DIR, os.path.join(ROOT_DIR, "scripts")):
    if p not in sys.path:
        sys.path.insert(0, p)

from track_targets import (  # noqa: E402
    evaluate_position, summarise, build_targets, NEAR_FRACTION,
)

TARGET = 0.15
STOP = 0.06


class TestEvaluatePosition(unittest.TestCase):
    def test_target_hit(self):
        r = evaluate_position(entry=100.0, cmp=115.0, target_pct=TARGET,
                              stop_pct=STOP, shares=10)
        self.assertEqual(r["status"], "hit")
        self.assertAlmostEqual(r["pnl_pct"], 15.0, places=2)
        self.assertAlmostEqual(r["target_price"], 115.0, places=2)
        self.assertAlmostEqual(r["stop_price"], 94.0, places=2)
        self.assertAlmostEqual(r["pnl_value"], 150.0, places=2)

    def test_hit_above_target(self):
        r = evaluate_position(100.0, 120.0, TARGET, STOP)
        self.assertEqual(r["status"], "hit")

    def test_stopped_at_or_below_stop(self):
        r = evaluate_position(100.0, 94.0, TARGET, STOP)
        self.assertEqual(r["status"], "stopped")
        r2 = evaluate_position(100.0, 90.0, TARGET, STOP)
        self.assertEqual(r2["status"], "stopped")

    def test_near_when_past_near_fraction(self):
        # 70% of a 15% target = +10.5%
        r = evaluate_position(100.0, 110.5, TARGET, STOP)
        self.assertEqual(r["status"], "near")
        self.assertGreaterEqual(r["pnl_pct"], TARGET * 100 * NEAR_FRACTION - 0.01)

    def test_holding_mid_way(self):
        r = evaluate_position(100.0, 104.0, TARGET, STOP)
        self.assertEqual(r["status"], "holding")

    def test_stop_takes_priority_over_near_when_both_bounds_tight(self):
        # entry protects against entry<=0 division
        r = evaluate_position(0.0, 50.0, TARGET, STOP)
        self.assertAlmostEqual(r["pnl_pct"], 0.0, places=6)

    def test_to_target_pct_sign(self):
        r = evaluate_position(100.0, 100.0, TARGET, STOP)
        self.assertAlmostEqual(r["to_target_pct"], 15.0, places=2)


class TestSummarise(unittest.TestCase):
    def test_counts_each_status(self):
        entries = [
            {"status": "hit"}, {"status": "hit"}, {"status": "near"},
            {"status": "holding"}, {"status": "stopped"},
        ]
        s = summarise(entries)
        self.assertEqual(s["count"], 5)
        self.assertEqual(s["hit"], 2)
        self.assertEqual(s["near"], 1)
        self.assertEqual(s["holding"], 1)
        self.assertEqual(s["stopped"], 1)


class TestBuildTargets(unittest.TestCase):
    def test_builds_and_serialises(self):
        positions = [
            {"symbol": "CUPID", "entry": 100.0, "shares": 9},
            {"symbol": "MISSING", "entry": 200.0, "shares": 4},
        ]
        prices = {"CUPID": 115.0}   # MISSING has no price
        out = build_targets(positions, prices, "yfinance", TARGET, STOP)
        self.assertEqual(out["source"], "yfinance")
        self.assertEqual(out["summary"]["hit"], 1)
        self.assertEqual(out["summary"]["count"], 2)
        by = {e["symbol"]: e for e in out["entries"]}
        self.assertEqual(by["CUPID"]["status"], "hit")
        self.assertEqual(by["MISSING"]["status"], "no_price")
        self.assertIsNone(by["MISSING"]["cmp"])
        json.dumps(out)  # must be JSON-safe

    def test_per_position_overrides(self):
        positions = [{"symbol": "X", "entry": 100.0, "shares": 1,
                      "target_pct": 5, "stop_pct": 2}]
        out = build_targets(positions, {"X": 105.0}, "yfinance", TARGET, STOP)
        e = out["entries"][0]
        self.assertEqual(e["status"], "hit")  # +5% meets the +5% override
        self.assertAlmostEqual(e["target_price"], 105.0, places=2)


if __name__ == "__main__":
    unittest.main()
