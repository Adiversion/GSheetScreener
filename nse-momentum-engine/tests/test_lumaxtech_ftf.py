"""
test_lumaxtech_ftf.py — Empirical Test of LUMAXTECH Price-Volume Structure
==========================================================================
Tests the complete multi-day sequence for LUMAXTECH:
  1. On 23-Sep: Spikes to ATH ₹2,190 with heavy volume rejection wick (CR = 3.3%).
  2. 24-Sep to 30-Sep: Supply dries up (VDU = 0.45x, VCP = 0.90x, AQS = 80.0).
     - Proximity is 5.2% (> 3.5%), so the engine correctly avoids a premature trigger.
  3. On 01-Oct: Heavy volume distribution (1.85x) closes near lows (CR = 0.27).
     - The engine MUST trigger TRAP_VETO and slash AQS to 35.0, forbidding new entry.
"""

import sys
import os
import unittest
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from failure_to_fail import compute_failure_to_fail
from momentum_quality import evaluate_institutional_quality


class TestLumaxtechStructure(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        import yfinance as yf
        df = yf.download("LUMAXTECH.NS", period="1y", interval="1d", progress=False)
        if hasattr(df.columns, 'levels') and len(df.columns.levels) > 1:
            df.columns = df.columns.get_level_values(0)
        df = df.reset_index()
        df["Date"] = pd.to_datetime(df["Date"]).dt.strftime("%Y-%m-%d")
        cls.df = df
        cls.h52w = float(df["High"].max())

    def test_30_sep_healthy_accumulation_but_not_in_trigger_zone(self):
        """As of 30-Sep, AQS is strong (80) but proximity is 5.2% (safely waiting)."""
        df_30 = self.df[self.df["Date"] <= "2026-09-30"].copy()
        ftf_30 = compute_failure_to_fail(df_30, high_52w=self.h52w)
        aqs_30 = evaluate_institutional_quality(df_30)

        print("\n" + "=" * 65)
        print("[EMPIRICAL TEST 1: LUMAXTECH AS OF 30-SEP-2026]")
        print("=" * 65)
        print(f"AQS Score              : {aqs_30['quality_score']}/100 ({aqs_30['grade']})")
        print(f"50D U/D Volume Ratio   : {aqs_30['up_down_vol_ratio']}")
        print(f"Volume Dry-Up (VDU)    : {aqs_30['vdu_ratio']}x ({aqs_30['vdu_status']})")
        print(f"Rejection Peak Pivot   : INR {ftf_30['pivot_resistance']}")
        print(f"Proximity to Peak      : {ftf_30['proximity_to_peak_pct']}% (Threshold <= 3.5%)")
        print(f"FTF State              : {ftf_30['state']}")
        print("=" * 65)

        self.assertGreaterEqual(aqs_30["quality_score"], 75.0, "30-Sep had prime multi-month accumulation")
        self.assertGreater(ftf_30["proximity_to_peak_pct"], 3.5, "Must not trigger prematurely while 5.2% away")
        self.assertIsNone(ftf_30["trigger_guidance"], "No trigger should be issued when > 3.5% away")

    def test_01_oct_trap_veto_defense_activates(self):
        """As of 01-Oct, heavy down-volume with close near lows must trigger TRAP_VETO."""
        df_01 = self.df[self.df["Date"] <= "2026-10-01"].copy()
        ftf_01 = compute_failure_to_fail(df_01, high_52w=self.h52w)
        aqs_01 = evaluate_institutional_quality(df_01)

        print("\n" + "=" * 65)
        print("[EMPIRICAL TEST 2: LUMAXTECH AS OF 01-OCT-2026]")
        print("=" * 65)
        print(f"AQS Score              : {aqs_01['quality_score']}/100 ({aqs_01['grade']})")
        print(f"Is Trap Veto?          : {aqs_01['is_trap_veto']}")
        print(f"Closing Range (CR)     : {aqs_01['closing_range']*100:.1f}% ({aqs_01['cr_status']})")
        print(f"Volume Ratio           : {aqs_01['vol_ratio']}x ({aqs_01['vol_status']})")
        print(f"Triggered Warnings     : {aqs_01['warnings']}")
        print("=" * 65)

        self.assertTrue(aqs_01["is_trap_veto"], "01-Oct must trigger TRAP_VETO on heavy volume drop near session lows!")
        self.assertLessEqual(aqs_01["quality_score"], 35.0, "Quality score must be capped at 35 on trap veto")


if __name__ == "__main__":
    unittest.main()
