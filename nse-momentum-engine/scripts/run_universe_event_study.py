#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_universe_event_study.py — Executes Large-Scale Universe Separation Study (AGENTS.md)
Answers: Does RESISTANCE_PROBE -> CONFIRMED_BREAKOUT separate from FAILED_BREAKOUT,
and does AQS enhance that predictive separation across the liquid NSE universe?
"""

import sys
import os
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.event_study_engine import extract_events_for_series


def compute_group_stats(df_group: pd.DataFrame, label: str) -> dict:
    """Computes comprehensive statistical expectancy for an event cohort."""
    n = len(df_group)
    if n == 0:
        return {"cohort": label, "count": 0}

    horizons = ["fwd_ret_1d", "fwd_ret_2d", "fwd_ret_5d", "fwd_ret_10d", "fwd_ret_20d", "post_res_20d"]
    stats = {"cohort": label, "count": n}

    for h in horizons:
        s = df_group[h].dropna()
        mean_v = round(float(s.mean()), 2) if len(s) > 0 else 0.0
        med_v = round(float(s.median()), 2) if len(s) > 0 else 0.0
        win_rate = round(float((s > 0).sum() / len(s) * 100.0), 1) if len(s) > 0 else 0.0
        pos_sum = float(s[s > 0].sum())
        neg_sum = float(s[s < 0].abs().sum())
        pf = round(pos_sum / neg_sum, 2) if neg_sum > 0 else (99.0 if pos_sum > 0 else 1.0)

        stats[f"{h}_mean"] = mean_v
        stats[f"{h}_median"] = med_v
        stats[f"{h}_winrate"] = win_rate
        stats[f"{h}_pf"] = pf

    return stats


def print_comparison_table(stats_list: list):
    """Prints clean markdown-style tables of forward return distributions."""
    print("\n" + "=" * 95)
    print("EMPIRICAL SEPARATION RESULTS: FORWARD RETURN EXPECTANCY (%)")
    print("=" * 95)
    header = f"{'Cohort':<36} | {'N':>4} | {'T+1 Mean':>8} | {'T+2 Mean':>8} | {'T+5 Mean':>8} | {'T+10 Mean':>9} | {'T+20 Mean':>9} | {'WinRate%':>8} | {'PF':>5}"
    print(header)
    print("-" * 95)
    for s in stats_list:
        if s["count"] == 0:
            continue
        c = s["cohort"]
        cnt = s["count"]
        m1 = f"{s.get('fwd_ret_1d_mean', 0.0):+.2f}%"
        m2 = f"{s.get('fwd_ret_2d_mean', 0.0):+.2f}%"
        m5 = f"{s.get('fwd_ret_5d_mean', 0.0):+.2f}%"
        m10 = f"{s.get('fwd_ret_10d_mean', 0.0):+.2f}%"
        m20 = f"{s.get('fwd_ret_20d_mean', 0.0):+.2f}%"
        wr = f"{s.get('fwd_ret_20d_winrate', 0.0):.1f}%"
        pf = f"{s.get('fwd_ret_20d_pf', 0.0):.2f}"
        print(f"{c:<36} | {cnt:>4} | {m1:>8} | {m2:>8} | {m5:>8} | {m10:>9} | {m20:>9} | {wr:>8} | {pf:>5}")
    print("=" * 95)


def run_study(data_parquet: Path, output_dir: Path):
    """Executes full empirical event study across universe parquet."""
    print(f"Loading universe history from {data_parquet}...")
    df_raw = pd.read_parquet(data_parquet)
    print(f"Loaded {len(df_raw)} bars across {df_raw['Symbol'].nunique()} symbols.")

    all_events = []
    symbols = sorted(df_raw["Symbol"].unique())
    for idx, sym in enumerate(symbols, 1):
        df_sym = df_raw[df_raw["Symbol"] == sym].sort_values("Date").copy()
        events = extract_events_for_series(df_sym, sym)
        all_events.extend(events)

    df_events = pd.DataFrame(all_events)
    print(f"Discovered {len(df_events)} qualifying events across the universe.")

    # Save event dataset
    output_dir.mkdir(parents=True, exist_ok=True)
    events_pq = output_dir / "universe_events.parquet"
    events_csv = output_dir / "universe_events.csv"
    df_events.to_parquet(events_pq, index=False)
    df_events.to_csv(events_csv, index=False)
    print(f"Saved event dataset to {events_pq} and {events_csv}")

    # Core Resolution Subsets
    probe_cb = df_events[(df_events["initial_state"] == "RESISTANCE_PROBE") & (df_events["resolution_state"] == "CONFIRMED_BREAKOUT")]
    probe_fb = df_events[(df_events["initial_state"] == "RESISTANCE_PROBE") & (df_events["resolution_state"] == "FAILED_BREAKOUT")]
    probe_un = df_events[(df_events["initial_state"] == "RESISTANCE_PROBE") & (df_events["resolution_state"] == "UNRESOLVED")]

    coiling_cb = df_events[(df_events["initial_state"] == "FTF_COILING") & (df_events["resolution_state"] == "CONFIRMED_BREAKOUT")]
    coiling_fb = df_events[(df_events["initial_state"] == "FTF_COILING") & (df_events["resolution_state"] == "FAILED_BREAKOUT")]

    # AQS Stratification Subsets
    cb_high_aqs = df_events[(df_events["resolution_state"] == "CONFIRMED_BREAKOUT") & (df_events["aqs"] >= 75)]
    cb_mid_aqs = df_events[(df_events["resolution_state"] == "CONFIRMED_BREAKOUT") & (df_events["aqs"] >= 60) & (df_events["aqs"] < 75)]
    cb_low_aqs = df_events[(df_events["resolution_state"] == "CONFIRMED_BREAKOUT") & (df_events["aqs"] < 60)]

    fb_high_aqs = df_events[(df_events["resolution_state"] == "FAILED_BREAKOUT") & (df_events["aqs"] >= 75)]
    fb_low_aqs = df_events[(df_events["resolution_state"] == "FAILED_BREAKOUT") & (df_events["aqs"] < 60)]

    stats = [
        compute_group_stats(df_events, "ALL EVENTS AT T (BASELINE)"),
        compute_group_stats(probe_cb, "RESISTANCE_PROBE -> CONFIRMED_BREAKOUT"),
        compute_group_stats(probe_fb, "RESISTANCE_PROBE -> FAILED_BREAKOUT"),
        compute_group_stats(probe_un, "RESISTANCE_PROBE -> UNRESOLVED"),
        compute_group_stats(coiling_cb, "FTF_COILING -> CONFIRMED_BREAKOUT"),
        compute_group_stats(coiling_fb, "FTF_COILING -> FAILED_BREAKOUT"),
        compute_group_stats(cb_high_aqs, "CONFIRMED_BREAKOUT + AQS >= 75 (PRIME)"),
        compute_group_stats(cb_mid_aqs, "CONFIRMED_BREAKOUT + 60 <= AQS < 75"),
        compute_group_stats(cb_low_aqs, "CONFIRMED_BREAKOUT + AQS < 60 (WEAK)"),
        compute_group_stats(fb_high_aqs, "FAILED_BREAKOUT + AQS >= 75 (HIGH)"),
        compute_group_stats(fb_low_aqs, "FAILED_BREAKOUT + AQS < 60 (LOW)"),
    ]

    print_comparison_table(stats)

    # Calculate and output clear separation answer
    if len(probe_cb) > 0 and len(probe_fb) > 0:
        spread_20d = probe_cb["fwd_ret_20d"].mean() - probe_fb["fwd_ret_20d"].mean()
        spread_5d = probe_cb["fwd_ret_5d"].mean() - probe_fb["fwd_ret_5d"].mean()
        print(f"\n🎯 CORE HYPOTHESIS ANSWER:")
        print(f"1. Separation Spread at T+5 : {spread_5d:+.2f}%")
        print(f"2. Separation Spread at T+20: {spread_20d:+.2f}%")
        print(f"   • Confirmed Breakouts deliver +{probe_cb['fwd_ret_20d'].mean():.2f}% (Win Rate: {(probe_cb['fwd_ret_20d'] > 0).mean()*100:.1f}%)")
        print(f"   • Failed Breakouts deliver    {probe_fb['fwd_ret_20d'].mean():.2f}% (Win Rate: {(probe_fb['fwd_ret_20d'] > 0).mean()*100:.1f}%)")

    if len(cb_high_aqs) > 0 and len(cb_low_aqs) > 0:
        aqs_alpha = cb_high_aqs["fwd_ret_20d"].mean() - cb_low_aqs["fwd_ret_20d"].mean()
        print(f"\n🚀 AQS VALUE-ADD ANSWER:")
        print(f"   • High-AQS Breakouts (>=75) average : +{cb_high_aqs['fwd_ret_20d'].mean():.2f}% (PF: {compute_group_stats(cb_high_aqs, '')['fwd_ret_20d_pf']})")
        print(f"   • Low-AQS Breakouts (<60) average   : +{cb_low_aqs['fwd_ret_20d'].mean():.2f}% (PF: {compute_group_stats(cb_low_aqs, '')['fwd_ret_20d_pf']})")
        print(f"   • Net AQS Alpha Spread              : {aqs_alpha:+.2f}% extra gain per trade")


if __name__ == "__main__":
    base_dir = Path(__file__).resolve().parent.parent
    pq_path = base_dir / "data" / "universe_event_history.parquet"
    out_dir = base_dir / "data"
    run_study(pq_path, out_dir)
