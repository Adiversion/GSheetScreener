"""
test_tdpowersys_ftf.py — Empirical Test of the Failure-to-Fail & AQS Engine on TDPOWERSYS
========================================================================================
Validates the quantitative state machine on TDPOWERSYS:
  1. 01-Oct Snapshot (Close = ₹792.15, CR = 48%, Vol = 2.06x):
     - Must NOT be classified as TRAP_VETO.
     - Must retain strong structural accumulation score (AQS >= 75 / PRIME_ACCUMULATION).
     - Must be classified as RESISTANCE_PROBE (Breakout Attempt Unconfirmed) near 52W high (₹817.55).
     - Generates conditional trigger: Buy Stop @ ₹819.19 on Volume >= 1.5x.
  2. 01-Oct Final EOD Candle (Close = ₹809.70, High = ₹811.95, Low = ₹773.55):
     - Closing Range is ~94% (Bull close).
     - Trap Veto is False.
     - AQS is >= 85 (PRIME_ACCUMULATION).
"""

import sys
import os
import unittest
import pandas as pd
import numpy as np

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from failure_to_fail import compute_failure_to_fail
from momentum_quality import evaluate_institutional_quality


class TestTDPowerSysFTF(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        import yfinance as yf
        df = yf.download("TDPOWERSYS.NS", period="3mo", interval="1d", progress=False)
        if hasattr(df.columns, 'levels') and len(df.columns.levels) > 1:
            df.columns = df.columns.get_level_values(0)
        df = df.reset_index()
        df["Date"] = pd.to_datetime(df["Date"]).dt.strftime("%Y-%m-%d")
        cls.df = df
        cls.high_52w = 817.55

    def test_01_oct_snapshot_is_resistance_probe_not_trap(self):
        """01-Oct snapshot (CMP ₹792.15) must be RESISTANCE_PROBE, NOT TRAP_VETO."""
        df_snap = self.df[self.df["Date"] <= "2026-10-01"].copy()
        self.assertGreaterEqual(len(df_snap), 25, "Must have at least 25 bars up to 01-Oct")

        # Evaluate quality and FTF
        q_res = evaluate_institutional_quality(df_snap)
        ftf_res = compute_failure_to_fail(df_snap, high_52w=self.high_52w)

        print("\n" + "=" * 65)
        print("[EMPIRICAL TEST 1: TDPOWERSYS 01-OCT SNAPSHOT (CMP INR 792.15)]")
        print("=" * 65)
        print(f"AQS Score              : {q_res['quality_score']}/100 ({q_res['grade']})")
        print(f"Is Trap Veto?          : {q_res['is_trap_veto']} (Must be False!)")
        print(f"50D Up/Down Volume     : {q_res['up_down_vol_ratio']} ({q_res['ud_status']})")
        print(f"Wyckoff Closing Range  : {q_res['closing_range']*100:.1f}%")
        print(f"FTF State              : {ftf_res['state']}")
        print(f"Pivot Resistance       : INR {ftf_res['pivot_resistance']}")
        print(f"Downside Floor         : INR {ftf_res['downside_floor']}")
        print(f"Trigger Guidance       : {ftf_res['trigger_guidance']}")
        print(f"Diagnostic             : {ftf_res['diagnostic']}")
        print("=" * 65)

        # Assertions
        self.assertFalse(q_res["is_trap_veto"], "TDPOWERSYS must NOT be flagged as TRAP_VETO!")
        self.assertGreaterEqual(q_res["quality_score"], 75.0, "AQS must reflect strong accumulation (>= 75)")
        self.assertEqual(q_res["grade"], "PRIME_ACCUMULATION")
        self.assertEqual(ftf_res["state"], "RESISTANCE_PROBE")
        self.assertIn("Buy Stop", ftf_res["trigger_guidance"])
        self.assertAlmostEqual(ftf_res["pivot_resistance"], self.high_52w, delta=0.5)

    def test_01_oct_eod_completed_candle(self):
        """Final completed EOD candle with Close INR 809.70 must show CR ~94% and Prime AQS."""
        df_eod = self.df[self.df["Date"] <= "2026-10-01"].copy()
        last_idx = df_eod.index[-1]
        df_eod.loc[last_idx, "High"] = 811.95
        df_eod.loc[last_idx, "Low"] = 773.55
        df_eod.loc[last_idx, "Close"] = 809.70

        q_res = evaluate_institutional_quality(df_eod)

        print("\n" + "=" * 65)
        print("[EMPIRICAL TEST 2: TDPOWERSYS 01-OCT COMPLETED EOD (CLOSE INR 809.70)]")
        print("=" * 65)
        print(f"AQS Score              : {q_res['quality_score']}/100 ({q_res['grade']})")
        print(f"Is Trap Veto?          : {q_res['is_trap_veto']}")
        print(f"Closing Range (CR)     : {q_res['closing_range']*100:.1f}% ({q_res['cr_status']})")
        print("=" * 65)

        self.assertFalse(q_res["is_trap_veto"])
        self.assertGreaterEqual(q_res["closing_range"], 0.90)
        self.assertEqual(q_res["cr_status"], "STRONG_BULL_CLOSE")
        self.assertGreaterEqual(q_res["quality_score"], 85.0)


if __name__ == "__main__":
    unittest.main()
