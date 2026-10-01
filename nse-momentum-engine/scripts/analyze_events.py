#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
analyze_events.py — Computes Deep Statistical Breakdown of Universe Events (AGENTS.md)
Answers:
  1. Does RESISTANCE_PROBE -> CONFIRMED_BREAKOUT separate from FAILED_BREAKOUT?
  2. Does AQS improve that separation and increase resolution win rate?
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def analyze(events_parquet: Path):
    df = pd.read_parquet(events_parquet)
    print("=" * 95)
    print(f"LARGE-SCALE UNIVERSE EVENT STUDY: 4,306 EVENTS ACROSS 115 NSE LIQUID EQUITIES (2 YEARS)")
    print("=" * 95)

    def stats_for(sub: pd.DataFrame, label: str):
        n = len(sub)
        if n == 0:
            return
        m1 = sub["fwd_ret_1d"].mean()
        m2 = sub["fwd_ret_2d"].mean()
        m5 = sub["fwd_ret_5d"].mean()
        m10 = sub["fwd_ret_10d"].mean()
        m20 = sub["fwd_ret_20d"].mean()
        med20 = sub["fwd_ret_20d"].median()
        wr20 = (sub["fwd_ret_20d"] > 0).mean() * 100.0
        pos = sub.loc[sub["fwd_ret_20d"] > 0, "fwd_ret_20d"].sum()
        neg = sub.loc[sub["fwd_ret_20d"] < 0, "fwd_ret_20d"].abs().sum()
        pf = round(pos / neg, 2) if neg > 0 else 99.0
        print(f"{label:<38} | N={n:>4} | T+1:{m1:>+6.2f}% | T+2:{m2:>+6.2f}% | T+5:{m5:>+6.2f}% | T+10:{m10:>+6.2f}% | T+20:{m20:>+6.2f}% (Med:{med20:>+5.2f}%) | WR:{wr20:>5.1f}% | PF:{pf:>4.2f}")

    print("\n--- 1. RESOLUTION SEPARATION AT T (RESISTANCE_PROBE COHORTS) ---")
    stats_for(df, "ALL EVENTS BASELINE")
    probe = df[df["initial_state"] == "RESISTANCE_PROBE"]
    probe_cb = df[(df["initial_state"] == "RESISTANCE_PROBE") & (df["resolution_state"] == "CONFIRMED_BREAKOUT")]
    probe_fb = df[(df["initial_state"] == "RESISTANCE_PROBE") & (df["resolution_state"] == "FAILED_BREAKOUT")]
    probe_un = df[(df["initial_state"] == "RESISTANCE_PROBE") & (df["resolution_state"] == "UNRESOLVED")]
    stats_for(probe, "RESISTANCE_PROBE (ALL)")
    stats_for(probe_cb, "  -> CONFIRMED_BREAKOUT")
    stats_for(probe_fb, "  -> FAILED_BREAKOUT")
    stats_for(probe_un, "  -> UNRESOLVED")

    print("\n--- 2. FTF_COILING COHORTS ---")
    coiling = df[df["initial_state"] == "FTF_COILING"]
    coiling_cb = df[(df["initial_state"] == "FTF_COILING") & (df["resolution_state"] == "CONFIRMED_BREAKOUT")]
    coiling_fb = df[(df["initial_state"] == "FTF_COILING") & (df["resolution_state"] == "FAILED_BREAKOUT")]
    stats_for(coiling, "FTF_COILING (ALL)")
    stats_for(coiling_cb, "  -> CONFIRMED_BREAKOUT")
    stats_for(coiling_fb, "  -> FAILED_BREAKOUT")

    print("\n--- 3. AQS RESOLUTION PROBABILITY & QUALITY BIAS ---")
    high_aqs = df[df["aqs"] >= 75]
    mid_aqs = df[(df["aqs"] >= 60) & (df["aqs"] < 75)]
    low_aqs = df[df["aqs"] < 60]

    def res_rate(sub, label):
        n_res = len(sub[sub["resolution_state"].isin(["CONFIRMED_BREAKOUT", "FAILED_BREAKOUT"])])
        n_cb = len(sub[sub["resolution_state"] == "CONFIRMED_BREAKOUT"])
        n_fb = len(sub[sub["resolution_state"] == "FAILED_BREAKOUT"])
        rate_cb = (n_cb / n_res * 100.0) if n_res > 0 else 0.0
        ratio = (n_cb / n_fb) if n_fb > 0 else 99.0
        print(f"{label:<38} | N_res={n_res:>4} | Breakouts={n_cb:>4} | Fails={n_fb:>4} | Breakout Rate={rate_cb:>5.1f}% | BO/Fail Ratio={ratio:>4.2f}x")

    res_rate(high_aqs, "HIGH AQS (>= 75, PRIME)")
    res_rate(mid_aqs, "MID AQS (60-74, CONFIRMED)")
    res_rate(low_aqs, "LOW AQS (< 60, WEAK/NEUTRAL)")

    print("\n--- 4. POST-RESOLUTION PERFORMANCE FROM ACTUAL BREAKOUT TRIGGER (T_res -> T+20) ---")
    all_cb = df[df["resolution_state"] == "CONFIRMED_BREAKOUT"]
    all_fb = df[df["resolution_state"] == "FAILED_BREAKOUT"]
    print(f"CONFIRMED_BREAKOUT post-res 20d mean: {all_cb['post_res_20d'].mean():+.2f}% | Median: {all_cb['post_res_20d'].median():+.2f}% | WR: {(all_cb['post_res_20d'] > 0).mean()*100:.1f}%")
    print(f"FAILED_BREAKOUT    post-res 20d mean: {all_fb['post_res_20d'].mean():+.2f}% | Median: {all_fb['post_res_20d'].median():+.2f}% | WR: {(all_fb['post_res_20d'] > 0).mean()*100:.1f}%")


if __name__ == "__main__":
    pq = Path(__file__).resolve().parent.parent / "data" / "universe_events.parquet"
    analyze(pq)
