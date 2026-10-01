"""
failure_to_fail.py — Pure Domain Module for Multi-Day "Failure-to-Fail" (FTF) Engine
===================================================================================
Analyzes multi-day price-volume memory to distinguish:
  1. Low-volume supply test / absorption (FTF_COILING)
  2. Confirmed demand expansion (CONFIRMED_BREAKOUT)
  3. Genuine distribution failure (TRAP_CONFIRMED)

Strictly adheres to AGENTS.md:
  - 100% pure functions (no network/DOM/global mutation)
  - Under 300 lines limit
  - Strictly observable language
"""

import math
from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np


def compute_failure_to_fail(
    df: pd.DataFrame,
    lookback_rejection: int = 15,
    volume_sma_period: int = 20,
    high_52w: Optional[float] = None
) -> Dict[str, Any]:
    """
    Evaluates multi-day Failure-to-Fail (FTF) state across an OHLCV series.
    Returns:
      state: 'CONFIRMED_BREAKOUT' | 'FTF_COILING' | 'TRAP_CONFIRMED' | 'NORMAL_TREND'
      details: diagnostic metrics, rejection pivot, downside floor, trigger guidance
    """
    if len(df) < volume_sma_period + 2:
        return {
            "state": "NORMAL_TREND",
            "is_ftf_coiling": False,
            "is_confirmed_breakout": False,
            "pivot_resistance": None,
            "downside_floor": None,
            "diagnostic": "Insufficient history for FTF lookback"
        }

    # Ensure clean numeric series
    c = df["Close"].astype(float)
    h = df["High"].astype(float)
    l = df["Low"].astype(float)
    o = df["Open"].astype(float)
    v = df["Volume"].astype(float)
    dates = df["Date"].astype(str) if "Date" in df.columns else [str(i) for i in df.index]

    vol_sma = v.rolling(volume_sma_period).mean()

    curr_idx = len(df) - 1
    curr_c = c.iloc[curr_idx]
    curr_h = h.iloc[curr_idx]
    curr_l = l.iloc[curr_idx]
    curr_v = v.iloc[curr_idx]
    curr_sma_v = vol_sma.iloc[curr_idx]
    curr_vol_ratio = round(curr_v / curr_sma_v, 2) if (curr_sma_v and curr_sma_v > 0) else 1.0
    curr_rng = curr_h - curr_l
    curr_cr = round((curr_c - curr_l) / curr_rng, 2) if curr_rng > 0 else 0.50

    # 1. Scan for prior high-volume rejection bar in previous [curr_idx - lookback, curr_idx - 1]
    rejection: Optional[Dict[str, Any]] = None
    start_scan = max(volume_sma_period, curr_idx - lookback_rejection)

    for i in range(curr_idx - 1, start_scan - 1, -1):
        bar_h = h.iloc[i]
        bar_l = l.iloc[i]
        bar_c = c.iloc[i]
        bar_o = o.iloc[i]
        bar_v = v.iloc[i]
        bar_sma_v = vol_sma.iloc[i]

        if not bar_sma_v or bar_sma_v <= 0:
            continue

        bar_vol_ratio = bar_v / bar_sma_v
        bar_rng = bar_h - bar_l
        if bar_rng <= 0:
            continue

        bar_cr = (bar_c - bar_l) / bar_rng
        upper_wick = bar_h - max(bar_o, bar_c)
        upper_wick_pct = upper_wick / bar_rng

        # Rejection signature: Heavy volume (>= 1.3x) AND upper-wick rejection (CR <= 0.45 or Wick >= 35%)
        # and bar touched near the 20-day high
        rolling_20h = h.iloc[max(0, i - 19):i + 1].max()
        near_peak = (rolling_20h - bar_h) / rolling_20h <= 0.02 if rolling_20h > 0 else False

        if bar_vol_ratio >= 1.30 and (bar_cr <= 0.45 or upper_wick_pct >= 0.35) and near_peak:
            rejection = {
                "idx": i,
                "date": dates[i] if i < len(dates) else f"T-{curr_idx - i}",
                "high": round(bar_h, 2),
                "low": round(bar_l, 2),
                "vol_ratio": round(bar_vol_ratio, 2),
                "cr": round(bar_cr, 2),
                "volume": int(bar_v)
            }
            break

    if not rejection:
        peak_ref = float(high_52w) if (high_52w is not None and not math.isnan(high_52w) and high_52w > 0) else float(h.rolling(min(len(df), 252)).max().iloc[-1])
        dist_high_pct = ((peak_ref - curr_h) / peak_ref) * 100.0 if peak_ref > 0 else 999.0

        if dist_high_pct <= 2.5:
            # Probing major resistance (e.g. 52W high)
            if curr_c >= peak_ref * 0.998 and curr_vol_ratio >= 1.40 and curr_cr >= 0.55:
                return {
                    "state": "CONFIRMED_BREAKOUT",
                    "is_ftf_coiling": False,
                    "is_confirmed_breakout": True,
                    "pivot_resistance": round(peak_ref, 2),
                    "downside_floor": round(float(l.tail(5).min()), 2),
                    "rejection_date": None,
                    "rejection_high": round(peak_ref, 2),
                    "rejection_low": round(float(l.tail(5).min()), 2),
                    "rejection_vol_ratio": None,
                    "floor_held": True,
                    "downside_retention_pct": 0.0,
                    "proximity_to_peak_pct": round(max(0.0, ((peak_ref - curr_c) / peak_ref) * 100.0), 1),
                    "intermediate_vol_ratio": 1.0,
                    "current_vol_ratio": curr_vol_ratio,
                    "current_cr": curr_cr,
                    "trigger_guidance": None,
                    "diagnostic": f"Cleared 52W resistance ({peak_ref:.2f}) on {curr_vol_ratio}x volume with {curr_cr*100:.0f}% close."
                }
            else:
                # TDPOWERSYS pattern: Touching resistance without clearance yet
                recent_floor = float(l.iloc[max(0, curr_idx - 3):curr_idx].min()) if curr_idx >= 3 else curr_l
                floor_held = curr_c >= recent_floor * 0.985
                return {
                    "state": "RESISTANCE_PROBE",
                    "is_ftf_coiling": False,
                    "is_confirmed_breakout": False,
                    "pivot_resistance": round(peak_ref, 2),
                    "downside_floor": round(recent_floor, 2),
                    "rejection_date": dates[curr_idx] if curr_idx < len(dates) else "T-0",
                    "rejection_high": round(curr_h, 2),
                    "rejection_low": round(curr_l, 2),
                    "rejection_vol_ratio": curr_vol_ratio,
                    "floor_held": floor_held,
                    "downside_retention_pct": round(((curr_c - recent_floor) / recent_floor) * 100.0, 1) if recent_floor > 0 else 0.0,
                    "proximity_to_peak_pct": round(max(0.0, ((peak_ref - curr_c) / peak_ref) * 100.0), 1),
                    "intermediate_vol_ratio": 1.0,
                    "current_vol_ratio": curr_vol_ratio,
                    "current_cr": curr_cr,
                    "trigger_guidance": f"Buy Stop @ INR {(peak_ref * 1.002):.2f} on Volume >= 1.5x",
                    "diagnostic": (
                        f"Probing major resistance ({peak_ref:.2f}). Rejection wick (CR {curr_cr*100:.0f}%) on {curr_vol_ratio}x volume. "
                        f"Breakout unconfirmed; awaiting clearance above {peak_ref:.2f} or downside retention."
                    )
                }

        return {
            "state": "NORMAL_TREND",
            "is_ftf_coiling": False,
            "is_confirmed_breakout": False,
            "pivot_resistance": None,
            "downside_floor": None,
            "diagnostic": "No prior high-volume rejection or active resistance probe found"
        }

    # 2. Measure intermediate downside follow-through between rejection and current bar
    rej_idx = rejection["idx"]
    inter_closes = c.iloc[rej_idx + 1:curr_idx] if curr_idx > rej_idx + 1 else pd.Series([curr_c])
    inter_lows = l.iloc[rej_idx + 1:curr_idx] if curr_idx > rej_idx + 1 else pd.Series([curr_l])
    min_inter_close = float(inter_closes.min()) if len(inter_closes) > 0 else curr_c
    min_inter_low = float(inter_lows.min()) if len(inter_lows) > 0 else curr_l
    p_low = rejection["low"]
    p_high = rejection["high"]

    # Downside Retention: Following welspun.txt Section 2:
    # ForwardDownside = Close[t] - minimum(Close[t+1:t+3]).
    # Floor is held if closing prices did not break below rejection low (or intraday dip within 3.0% shakeout buffer)
    floor_held = (min_inter_close >= p_low * 0.985) or (min_inter_low >= p_low * 0.970)
    downside_retention_pct = round(((min_inter_close - p_low) / p_low) * 100.0, 1)

    # Ceiling Proximity: How close is current price to the rejection peak?
    proximity_to_peak_pct = round(((p_high - curr_c) / p_high) * 100.0, 1)

    # Intermediate volume dry-up: Did volume contract after the rejection?
    inter_vols = v.iloc[rej_idx + 1:curr_idx] if curr_idx > rej_idx + 1 else pd.Series([curr_v])
    inter_smas = vol_sma.iloc[rej_idx + 1:curr_idx] if curr_idx > rej_idx + 1 else pd.Series([curr_sma_v])
    avg_inter_vol_ratio = round(float((inter_vols / inter_smas).mean()), 2) if len(inter_vols) > 0 else 1.0

    # 3. Determine Multi-Day State Transitions
    is_confirmed_breakout = (curr_c > p_high) and (curr_vol_ratio >= 1.40) and (curr_cr >= 0.55)
    is_ftf_coiling = (
        floor_held and
        (curr_c <= p_high * 1.01) and
        (proximity_to_peak_pct <= 3.5) and
        (not is_confirmed_breakout)
    )
    is_breakdown = (curr_c < p_low * 0.97) and (curr_vol_ratio >= 1.30)
    high_prox_pct = ((p_high - curr_h) / p_high) * 100.0 if p_high > 0 else 999.0
    is_probe = (not is_confirmed_breakout) and (not is_ftf_coiling) and (not is_breakdown) and ((proximity_to_peak_pct <= 3.5) or (high_prox_pct <= 2.0))

    if is_confirmed_breakout:
        state = "CONFIRMED_BREAKOUT"
        diagnostic = f"Cleared prior rejection peak ({p_high}) on {curr_vol_ratio}x volume with {curr_cr*100:.0f}% close."
    elif is_ftf_coiling:
        state = "FTF_COILING"
        diagnostic = (
            f"Prior rejection at {p_high} ({rejection['date']}) absorbed. Floor {p_low} held ({downside_retention_pct}%). "
            f"Retesting resistance on dry volume ({curr_vol_ratio}x). Coiling for expansion."
        )
    elif is_probe:
        state = "RESISTANCE_PROBE"
        recent_floor = float(l.iloc[max(0, curr_idx - 3):curr_idx].min()) if curr_idx >= 3 else curr_l
        p_low = round(recent_floor, 2)
        diagnostic = (
            f"Re-testing prior resistance peak ({p_high} from {rejection['date']}). Breakout unconfirmed (CR {curr_cr*100:.0f}%); "
            f"awaiting clearance above {p_high} or retention above {p_low}."
        )
    elif is_breakdown:
        state = "TRAP_CONFIRMED"
        diagnostic = f"Rejection at {p_high} broke below floor {p_low} on heavy volume. True distribution."
    else:
        state = "NORMAL_TREND"
        diagnostic = "Price drifting within normal trading band."

    has_trigger = is_ftf_coiling or is_probe
    return {
        "state": state,
        "is_ftf_coiling": is_ftf_coiling,
        "is_resistance_probe": is_probe,
        "is_confirmed_breakout": is_confirmed_breakout,
        "pivot_resistance": p_high,
        "downside_floor": p_low,
        "rejection_date": rejection["date"],
        "rejection_high": p_high,
        "rejection_low": p_low,
        "rejection_vol_ratio": rejection["vol_ratio"],
        "floor_held": floor_held,
        "downside_retention_pct": downside_retention_pct,
        "proximity_to_peak_pct": proximity_to_peak_pct,
        "intermediate_vol_ratio": avg_inter_vol_ratio,
        "current_vol_ratio": curr_vol_ratio,
        "current_cr": curr_cr,
        "trigger_guidance": f"Buy Stop @ INR {(p_high * 1.002):.2f} on Volume >= 1.5x" if has_trigger else None,
        "diagnostic": diagnostic
    }
