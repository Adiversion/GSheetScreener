"""
event_study_engine.py — Empirical Event Study Engine for FTF & AQS State Separation
Validates whether RESISTANCE_PROBE -> CONFIRMED_BREAKOUT separates from FAILED_BREAKOUT
and measures how AQS amplifies forward return expectancy (AGENTS.md compliant).
"""

from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np
from src.failure_to_fail import compute_failure_to_fail
from src.momentum_quality import evaluate_institutional_quality


def compute_sqs(df_window: pd.DataFrame) -> float:
    """Computes Stage-2 Structural Quality Score (SQS: 0-100) on rolling daily window."""
    if len(df_window) < 60:
        return 50.0
    c = df_window["Close"]
    h = df_window["High"]
    cmp = float(c.iloc[-1])
    sma50 = float(c.tail(50).mean())
    sma200 = float(c.tail(200).mean()) if len(c) >= 200 else float(c.mean())
    sma200_prev = float(c.iloc[-22:-2].mean()) if len(c) >= 22 else sma200
    h52w = float(h.tail(250).max()) if len(h) >= 250 else float(h.max())

    score = 0.0
    if cmp > sma50:
        score += 25.0
    if sma50 > sma200:
        score += 25.0
    if sma200 >= sma200_prev:
        score += 25.0
    if h52w > 0 and (cmp / h52w) >= 0.80:
        score += 25.0
    return score


def extract_events_for_series(df: pd.DataFrame, symbol: str) -> List[Dict[str, Any]]:
    """
    Scans a single stock's full history and extracts all RESISTANCE_PROBE and FTF_COILING
    events, recording metrics at T, 3-day resolution, and T+1..T+20 forward returns.
    """
    events: List[Dict[str, Any]] = []
    n = len(df)
    if n < 80:
        return events

    # Required numeric series
    c = df["Close"].values
    h = df["High"].values
    l = df["Low"].values
    v = df["Volume"].values
    dates = df["Date"].astype(str).values

    # Scan from day 60 up to n - 21 (so forward returns T+20 are guaranteed complete)
    last_event_idx = -999
    for t in range(60, n - 21):
        # Prevent clustering: enforce at least 3 days between consecutive probe events
        if (t - last_event_idx) < 3:
            continue

        window = df.iloc[:t + 1]
        h52w = float(df["High"].iloc[max(0, t - 250):t + 1].max())

        # 1. Evaluate failure to fail state
        ftf = compute_failure_to_fail(window, high_52w=h52w)
        init_state = ftf["state"]

        if init_state not in ("RESISTANCE_PROBE", "FTF_COILING"):
            continue

        # 2. Evaluate institutional quality (AQS)
        iq = evaluate_institutional_quality(window)
        sqs = compute_sqs(window)

        p_high = float(ftf["pivot_resistance"]) if ftf["pivot_resistance"] else float(h[t])
        p_low = float(ftf["downside_floor"]) if ftf["downside_floor"] else float(l[t])
        cmp_t = float(c[t])

        # 3. Determine Resolution over T+1 .. T+3
        # Breakout confirmed if stock closes above p_high or reaches high >= 1.01 * p_high on volume
        # Breakdown/failed if stock drops below floor * 0.98
        res_state = "UNRESOLVED"
        res_day_idx = t + 3
        for k in range(1, 4):
            idx = t + k
            day_c = c[idx]
            day_h = h[idx]
            day_v = v[idx]
            avg_v = float(np.mean(v[max(0, idx - 20):idx])) if idx >= 20 else day_v
            v_ratio = day_v / avg_v if avg_v > 0 else 1.0

            if (day_c > p_high and v_ratio >= 1.25) or (day_h >= p_high * 1.015):
                res_state = "CONFIRMED_BREAKOUT"
                res_day_idx = idx
                break
            elif day_c < p_low * 0.98:
                res_state = "FAILED_BREAKOUT"
                res_day_idx = idx
                break

        # 4. Measure Forward Returns from Close at T (%)
        fwd_1d = round(((c[t + 1] - cmp_t) / cmp_t) * 100.0, 2)
        fwd_2d = round(((c[t + 2] - cmp_t) / cmp_t) * 100.0, 2)
        fwd_5d = round(((c[t + 5] - cmp_t) / cmp_t) * 100.0, 2)
        fwd_10d = round(((c[t + 10] - cmp_t) / cmp_t) * 100.0, 2)
        fwd_20d = round(((c[t + 20] - cmp_t) / cmp_t) * 100.0, 2)

        # 5. Measure Forward Return from entry trigger post-resolution (T_res to T+20)
        c_res = float(c[res_day_idx])
        post_res_20d = round(((c[t + 20] - c_res) / c_res) * 100.0, 2)

        event_record = {
            "symbol": symbol,
            "date": dates[t],
            "cmp": round(cmp_t, 2),
            "sqs": sqs,
            "aqs": round(float(iq["quality_score"]), 1),
            "ud_ratio": round(float(iq["up_down_vol_ratio"]), 2),
            "fip_smoothness": round(float(iq["fip_smoothness_pct"]), 1),
            "vcp_ratio": round(float(iq["vcp_ratio"]), 2),
            "vdu_ratio": round(float(iq["vdu_ratio"]), 2),
            "prior_rejection_peak": round(p_high, 2),
            "downside_floor": round(p_low, 2),
            "dist_to_resistance_pct": round(float(ftf["proximity_to_peak_pct"]), 2),
            "cr": round(float(ftf["current_cr"]), 2),
            "volume_ratio": round(float(ftf["current_vol_ratio"]), 2),
            "volume_contraction": round(float(ftf["intermediate_vol_ratio"]), 2),
            "price_retention": round(float(ftf["downside_retention_pct"]), 2),
            "initial_state": init_state,
            "resolution_state": res_state,
            "res_delay_days": res_day_idx - t,
            "fwd_ret_1d": fwd_1d,
            "fwd_ret_2d": fwd_2d,
            "fwd_ret_5d": fwd_5d,
            "fwd_ret_10d": fwd_10d,
            "fwd_ret_20d": fwd_20d,
            "post_res_20d": post_res_20d
        }
        events.append(event_record)
        last_event_idx = t

    return events
