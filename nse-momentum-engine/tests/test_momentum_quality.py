#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_momentum_quality.py — Unit tests for institutional momentum quality filters
================================================================================
Tests:
  1. VCP ratio calculation, coiling identification, and expanding whipsaw detection.
  2. Volume confirmation, institutional surge detection, and low-volume trap filtering.
  3. Frog-in-the-Pan (FIP) smoothness ratio and discrete jump penalty.
  4. Composite institutional quality evaluation and edge case resilience.
"""

import unittest
import numpy as np
import pandas as pd
import sys
import os

# Add src to path
SRC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from momentum_quality import (
    compute_true_range,
    compute_closing_range,
    compute_up_down_volume_ratio,
    compute_volume_dry_up,
    compute_vcp_ratio,
    compute_volume_confirmation,
    compute_frog_in_the_pan,
    evaluate_institutional_quality
)


class TestMomentumQuality(unittest.TestCase):

    def setUp(self):
        np.random.seed(42)
        n = 100
        dates = pd.date_range("2026-01-01", periods=n, freq="B")
        close = 100.0 + np.cumsum(np.random.normal(0.5, 1.0, n))
        high = close + np.random.uniform(0.5, 2.0, n)
        low = close - np.random.uniform(0.5, 2.0, n)
        volume = np.random.uniform(100000, 500000, n)

        self.df = pd.DataFrame({
            "Open": close - 0.2,
            "High": high,
            "Low": low,
            "Close": close,
            "Volume": volume
        }, index=dates)

    def test_vcp_coiling_and_expansion(self):
        # Create coiling: last 5 bars have very small range
        df_coil = self.df.copy()
        df_coil.iloc[-5:, df_coil.columns.get_loc("High")] = df_coil["Close"].iloc[-5:] + 0.1
        df_coil.iloc[-5:, df_coil.columns.get_loc("Low")] = df_coil["Close"].iloc[-5:] - 0.1
        res = compute_vcp_ratio(df_coil)
        self.assertTrue(res["is_coiled"])
        self.assertLessEqual(res["vcp_ratio"], 1.05)

        # Create expansion: last 5 bars have massive swings
        df_exp = self.df.copy()
        df_exp.iloc[-5:, df_exp.columns.get_loc("High")] = df_exp["Close"].iloc[-5:] + 15.0
        df_exp.iloc[-5:, df_exp.columns.get_loc("Low")] = df_exp["Close"].iloc[-5:] - 15.0
        res_exp = compute_vcp_ratio(df_exp)
        self.assertFalse(res_exp["is_coiled"])
        self.assertEqual(res_exp["vcp_status"], "ERRATIC_EXPANSION")

    def test_volume_confirmation(self):
        # Surge volume
        df_surge = self.df.copy()
        df_surge.iloc[-1, df_surge.columns.get_loc("Volume")] = df_surge["Volume"].tail(20).mean() * 2.5
        res = compute_volume_confirmation(df_surge)
        self.assertTrue(res["is_confirmed"])
        self.assertEqual(res["vol_status"], "INSTITUTIONAL_SURGE")

        # Trap volume (only 0.2x average)
        df_trap = self.df.copy()
        df_trap.iloc[-1, df_trap.columns.get_loc("Volume")] = df_trap["Volume"].tail(20).mean() * 0.2
        res_trap = compute_volume_confirmation(df_trap)
        self.assertFalse(res_trap["is_confirmed"])
        self.assertEqual(res_trap["vol_status"], "LOW_VOLUME_TRAP")

    def test_frog_in_the_pan_smoothness(self):
        # Steady steady upward crawl (high smoothness)
        df_smooth = self.df.copy()
        for i in range(-40, 0):
            df_smooth.iloc[i, df_smooth.columns.get_loc("Close")] = 100.0 + (i * 0.5)
        res = compute_frog_in_the_pan(df_smooth)
        self.assertTrue(res["is_smooth"])
        self.assertGreaterEqual(res["smoothness_pct"], 50.0)

        # Single massive discrete jump followed by flat/down days
        df_jump = self.df.copy()
        df_jump.iloc[-40:-1, df_jump.columns.get_loc("Close")] = 100.0
        df_jump.iloc[-1, df_jump.columns.get_loc("Close")] = 150.0  # +50% single bar
        res_jump = compute_frog_in_the_pan(df_jump)
        self.assertEqual(res_jump["fip_status"], "DISCRETE_JUMP_RISK")

    def test_closing_range(self):
        # Strong bull close (close near high: CR >= 0.70)
        df_strong = self.df.copy()
        df_strong.iloc[-1, df_strong.columns.get_loc("High")] = 110.0
        df_strong.iloc[-1, df_strong.columns.get_loc("Low")] = 100.0
        df_strong.iloc[-1, df_strong.columns.get_loc("Close")] = 108.5  # CR = 8.5 / 10 = 0.85
        res_strong = compute_closing_range(df_strong)
        self.assertTrue(res_strong["is_strong_close"])
        self.assertEqual(res_strong["cr_status"], "STRONG_BULL_CLOSE")
        self.assertAlmostEqual(res_strong["closing_range"], 0.85, places=2)

        # Upthrust trap (close in bottom half: CR < 0.50)
        df_trap = self.df.copy()
        df_trap.iloc[-1, df_trap.columns.get_loc("High")] = 110.0
        df_trap.iloc[-1, df_trap.columns.get_loc("Low")] = 100.0
        df_trap.iloc[-1, df_trap.columns.get_loc("Close")] = 102.0  # CR = 2.0 / 10 = 0.20
        res_trap = compute_closing_range(df_trap)
        self.assertTrue(res_trap["is_upthrust_trap"])
        self.assertEqual(res_trap["cr_status"], "UPTHRUST_TRAP")

    def test_up_down_volume_ratio(self):
        # Heavy up volume
        df_acc = self.df.copy()
        for i in range(-50, 0):
            df_acc.iloc[i, df_acc.columns.get_loc("Close")] = 100.0 + (i * 0.5)
            df_acc.iloc[i, df_acc.columns.get_loc("Volume")] = 1000000.0
        res_acc = compute_up_down_volume_ratio(df_acc)
        self.assertTrue(res_acc["is_accumulating"])
        self.assertGreater(res_acc["up_down_vol_ratio"], 1.0)

    def test_volume_dry_up(self):
        df_vdu = self.df.copy()
        # Set 50-day average volume to 1,000,000
        df_vdu.iloc[-50:, df_vdu.columns.get_loc("Volume")] = 1000000.0
        # Set 5 bars before breakout to 400,000 (0.4x -> dry)
        df_vdu.iloc[-6:-1, df_vdu.columns.get_loc("Volume")] = 400000.0
        res_vdu = compute_volume_dry_up(df_vdu)
        self.assertTrue(res_vdu["is_dry"])
        self.assertEqual(res_vdu["vdu_status"], "VDU_CONFIRMED")

    def test_wyckoff_upthrust_trap_veto(self):
        df_trap = self.df.copy()
        # Heavy volume surge (2.5x)
        df_trap.iloc[-1, df_trap.columns.get_loc("Volume")] = df_trap["Volume"].tail(20).mean() * 2.5
        # Weak close in lower half (CR = 0.20)
        df_trap.iloc[-1, df_trap.columns.get_loc("High")] = 120.0
        df_trap.iloc[-1, df_trap.columns.get_loc("Low")] = 100.0
        df_trap.iloc[-1, df_trap.columns.get_loc("Close")] = 103.0
        res = evaluate_institutional_quality(df_trap)
        self.assertTrue(res["is_trap_veto"])
        self.assertEqual(res["grade"], "TRAP_VETO")
        self.assertLessEqual(res["quality_score"], 35.0)

    def test_evaluate_institutional_quality(self):
        res = evaluate_institutional_quality(self.df)
        self.assertIn("grade", res)
        self.assertIn("quality_score", res)
        self.assertIn("is_institutional_grade", res)
        self.assertIn("is_trap_veto", res)
        self.assertIn("closing_range", res)
        self.assertIn("up_down_vol_ratio", res)
        self.assertIn("warnings", res)

    def test_short_dataframe_graceful(self):
        short_df = self.df.head(5).copy()
        res = evaluate_institutional_quality(short_df)
        self.assertIsNotNone(res["grade"])


if __name__ == "__main__":
    unittest.main()
