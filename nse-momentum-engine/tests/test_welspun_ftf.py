"""
test_welspun_ftf.py — Empirical Test of the Failure-to-Fail (FTF) Engine on WELSPUNLIV
======================================================================================
Tests the exact sequence:
  1. As of 30-Sep-2026: Does the engine identify the 23-Sep rejection at ₹233, verify that
     the floor held, and classify 30-Sep as FTF_COILING (NOT a trap)?
  2. As of 01-Oct-2026: Does the engine detect the explosive volume breakout above ₹233
     and upgrade to CONFIRMED_BREAKOUT?
"""

import sys
import os
import unittest
import pandas as pd

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from failure_to_fail import compute_failure_to_fail


class TestWelspunFailureToFail(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Fetch real daily data for WELSPUNLIV.NS
        import yfinance as yf
        df = yf.download("WELSPUNLIV.NS", period="3mo", interval="1d", progress=False)
        if hasattr(df.columns, 'levels') and len(df.columns.levels) > 1:
            df.columns = df.columns.get_level_values(0)
        df = df.reset_index()
        df["Date"] = pd.to_datetime(df["Date"]).dt.strftime("%Y-%m-%d")
        cls.df = df

    def test_30_sep_evaluation_is_coiling_not_trap(self):
        """As of 30-Sep-2026, the stock must NOT be labeled a trap; it must be FTF_COILING."""
        df_30 = self.df[self.df["Date"] <= "2026-09-30"].copy()
        self.assertGreaterEqual(len(df_30), 25, "Must have at least 25 bars up to 30-Sep")

        result = compute_failure_to_fail(df_30)

        print("\n" + "=" * 65)
        print("[EMPIRICAL TEST 1: WELSPUNLIV AS OF 30-SEP-2026 (YESTERDAY)]")
        print("=" * 65)
        print(f"State Output           : {result['state']}")
        print(f"Is FTF Coiling?        : {result['is_ftf_coiling']}")
        print(f"Prior Rejection Date   : {result['rejection_date']}")
        print(f"Rejection Peak Pivot   : INR {result['rejection_high']}")
        print(f"Downside Floor         : INR {result['rejection_low']}")
        print(f"Floor Retained?        : {result['floor_held']} ({result['downside_retention_pct']}%)")
        print(f"Proximity to Peak      : {result['proximity_to_peak_pct']}% from INR {result['rejection_high']}")
        print(f"Retest Volume Ratio    : {result['current_vol_ratio']}x (Supply Dry-up)")
        print(f"Trigger Guidance       : {result['trigger_guidance']}")
        print(f"Diagnostic             : {result['diagnostic']}")
        print("=" * 65)

        # Assertions
        self.assertEqual(result["state"], "FTF_COILING", "30-Sep must be classified as FTF_COILING, never a trap!")
        self.assertTrue(result["is_ftf_coiling"])
        self.assertFalse(result["is_confirmed_breakout"])
        self.assertIn("2026-09-23", result["rejection_date"], "Must identify 23-Sep as the initial high-volume rejection!")
        self.assertEqual(result["rejection_high"], 233.00, "Rejection pivot must be ₹233.00")
        self.assertTrue(result["floor_held"], "Floor must be verified as held")

    def test_01_oct_evaluation_is_confirmed_breakout(self):
        """As of 01-Oct-2026, the stock must transition to CONFIRMED_BREAKOUT on 22.5M volume."""
        df_01 = self.df[self.df["Date"] <= "2026-10-01"].copy()
        result = compute_failure_to_fail(df_01)

        print("\n" + "=" * 65)
        print("[EMPIRICAL TEST 2: WELSPUNLIV AS OF 01-OCT-2026 (TODAY)]")
        print("=" * 65)
        print(f"State Output           : {result['state']}")
        print(f"Is Confirmed Breakout? : {result['is_confirmed_breakout']}")
        print(f"Cleared Pivot          : INR {result['rejection_high']}")
        print(f"Breakout Volume Ratio  : {result['current_vol_ratio']}x (Institutional Surge)")
        print(f"Closing Range (CR)     : {result['current_cr']*100:.1f}%")
        print(f"Diagnostic             : {result['diagnostic']}")
        print("=" * 65)

        # Assertions
        self.assertEqual(result["state"], "CONFIRMED_BREAKOUT", "01-Oct must be CONFIRMED_BREAKOUT!")
        self.assertTrue(result["is_confirmed_breakout"])
        self.assertFalse(result["is_ftf_coiling"])
        self.assertGreaterEqual(result["current_vol_ratio"], 3.0, "Volume ratio must be > 3x")


if __name__ == "__main__":
    unittest.main()
