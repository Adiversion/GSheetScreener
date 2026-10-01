"""
test_maninds_ftf.py — Empirical Test of Pivot Lifecycle Management on MANINDS
=============================================================================
Tests the pivot lifecycle resolution identified in MANINDS.txt:
  1. On 10-Sep: High-volume rejection at ₹944.
  2. On 23-Sep: Breakout clears ₹944 reaching ₹1,005 on 10.69M volume.
  3. On 25-Sep: New peak ₹1,039.70.
  4. On 30-Sep: Price pulls back to ₹907.35.
     - The engine MUST recognize ₹944 was already cleared (not an unbroken ceiling).
     - The pivot resistance MUST be promoted to ₹1,039.70 (new ATH), not stale ₹944.
     - The state MUST be FAILED_BREAKOUT or POST_BREAKOUT_RETEST, NEVER RESISTANCE_PROBE.
"""

import sys
import os
import unittest
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from failure_to_fail import compute_failure_to_fail


class TestManindsFailureToFail(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        import yfinance as yf
        df = yf.download("MANINDS.NS", period="3mo", interval="1d", progress=False)
        if hasattr(df.columns, 'levels') and len(df.columns.levels) > 1:
            df.columns = df.columns.get_level_values(0)
        df = df.reset_index()
        df["Date"] = pd.to_datetime(df["Date"]).dt.strftime("%Y-%m-%d")
        cls.df = df

    def test_30_sep_pivot_lifecycle_not_stale_probe(self):
        """As of 30-Sep-2026, 944 was already cleared; state must not be RESISTANCE_PROBE."""
        df_30 = self.df[self.df["Date"] <= "2026-09-30"].copy()
        self.assertGreaterEqual(len(df_30), 20)

        result = compute_failure_to_fail(df_30)

        print("\n" + "=" * 65)
        print("[EMPIRICAL TEST: MANINDS AS OF 30-SEP-2026]")
        print("=" * 65)
        print(f"State Output           : {result['state']}")
        print(f"Prior Rejection High   : INR {result['rejection_high']}")
        print(f"Promoted Pivot Peak    : INR {result['pivot_resistance']}")
        print(f"Diagnostic             : {result['diagnostic']}")
        print("=" * 65)

        self.assertNotEqual(result["state"], "RESISTANCE_PROBE", "Cannot be RESISTANCE_PROBE when 944 was already cleared!")
        self.assertIn(result["state"], ["FAILED_BREAKOUT", "POST_BREAKOUT_RETEST"])
        self.assertGreaterEqual(result["pivot_resistance"], 1030.0, "Pivot resistance must be updated to new high ~1039.70")


if __name__ == "__main__":
    unittest.main()
