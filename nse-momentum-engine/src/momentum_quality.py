#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""momentum_quality.py — Institutional Accumulation Quality (AQS) & Anti-Trap Defense (AGENTS.md compliant)."""

from __future__ import annotations
import math
from typing import Dict, Any, List
import pandas as pd


def compute_true_range(df: pd.DataFrame) -> pd.Series:
    """Computes True Range (TR) across High, Low, and Close."""
    h, l, c = df["High"], df["Low"], df["Close"]
    pc = c.shift(1)
    return pd.concat([(h - l), (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)


def compute_closing_range(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Computes Wyckoff Closing Range / Internal Bar Strength (IBS):
    CR = (Close - Low) / (High - Low). Range: 0.0 to 1.0.
    CR >= 0.70: Strong institutional close near session highs.
    CR < 0.50: Wyckoff Upthrust / Seller Rejection Trap (sellers overwhelmed buyers).
    """
    if len(df) < 1:
        return {"closing_range": 0.5, "cr_status": "NEUTRAL", "is_strong_close": False, "is_upthrust_trap": False}

    h = float(df["High"].iloc[-1])
    l = float(df["Low"].iloc[-1])
    c = float(df["Close"].iloc[-1])
    bar_range = h - l

    if bar_range <= 0 or math.isnan(bar_range):
        cr = 1.0 if c >= l else 0.5
    else:
        cr = round(max(0.0, min(1.0, (c - l) / bar_range)), 2)

    is_strong = cr >= 0.70
    is_upthrust = cr < 0.50

    if is_strong:
        status = "STRONG_BULL_CLOSE"
    elif cr >= 0.50:
        status = "NEUTRAL_CLOSE"
    else:
        status = "UPTHRUST_TRAP"

    return {
        "closing_range": cr,
        "cr_status": status,
        "is_strong_close": is_strong,
        "is_upthrust_trap": is_upthrust
    }


def compute_up_down_volume_ratio(df: pd.DataFrame, period: int = 50) -> Dict[str, Any]:
    """
    Computes Up/Down Volume Ratio over the lookback window.
    U/D Ratio = Sum(Up-day volume) / Sum(Down-day volume).
    > 1.20: Sustained institutional accumulation.
    < 0.85: Heavy volume distribution / selling into rallies.
    """
    if len(df) < 10:
        return {"up_down_vol_ratio": 1.0, "ud_status": "NEUTRAL", "is_accumulating": True}

    sub = df.tail(period)
    c, v = sub["Close"], sub["Volume"]
    diff = c.diff()

    up_vol = float(v[diff > 0].sum())
    down_vol = float(v[diff < 0].sum())

    if down_vol <= 0 or math.isnan(down_vol):
        ratio = 3.0 if up_vol > 0 else 1.0
    else:
        ratio = round(up_vol / down_vol, 2)

    is_accumulating = ratio >= 1.0
    if ratio >= 1.25:
        status = "STRONG_ACCUMULATION"
    elif ratio >= 1.0:
        status = "MILD_ACCUMULATION"
    elif ratio >= 0.85:
        status = "NEUTRAL"
    else:
        status = "DISTRIBUTION_PRESSURE"

    return {
        "up_down_vol_ratio": ratio,
        "ud_status": status,
        "is_accumulating": is_accumulating
    }


def compute_volume_dry_up(df: pd.DataFrame, pre_bars: int = 5, baseline: int = 50) -> Dict[str, Any]:
    """
    Computes Volume Dry-Up (VDU) in the base prior to the breakout day.
    VDU Ratio = Mean(Volume[-6:-1]) / Mean(Volume[-50:]).
    <= 0.75 indicates supply dried up before the expansion.
    """
    if len(df) < baseline + 1:
        return {"vdu_ratio": 1.0, "is_dry": True, "vdu_status": "NEUTRAL"}

    v = df["Volume"]
    base_avg = float(v.tail(baseline).mean())
    pre_breakout_avg = float(v.iloc[-(pre_bars + 1):-1].mean())

    if base_avg <= 0 or math.isnan(base_avg):
        ratio = 1.0
    else:
        ratio = round(pre_breakout_avg / base_avg, 2)

    is_dry = ratio <= 0.75
    status = "VDU_CONFIRMED" if is_dry else ("MODERATE_VOLUME" if ratio <= 1.0 else "ACTIVE_CHURN")

    return {
        "vdu_ratio": ratio,
        "is_dry": is_dry,
        "vdu_status": status
    }


def compute_vcp_ratio(df: pd.DataFrame, fast: int = 5, slow: int = 20) -> Dict[str, Any]:
    """Computes Volatility Contraction Pattern (VCP) ratio (ATR5 / ATR20)."""
    if len(df) < slow + 2:
        return {"vcp_ratio": 1.0, "is_coiled": True, "vcp_status": "NEUTRAL"}

    tr = compute_true_range(df)
    atr_fast = float(tr.rolling(fast).mean().iloc[-1])
    atr_slow = float(tr.rolling(slow).mean().iloc[-1])

    ratio = round(atr_fast / atr_slow, 2) if (atr_slow > 0 and not math.isnan(atr_slow)) else 1.0
    is_coiled = ratio <= 1.05

    if ratio <= 0.90:
        status = "TIGHT_COIL"
    elif ratio <= 1.05:
        status = "NORMAL_CONTRACTION"
    elif ratio <= 1.25:
        status = "NEUTRAL"
    else:
        status = "ERRATIC_EXPANSION"

    return {"vcp_ratio": ratio, "is_coiled": is_coiled, "vcp_status": status}


def compute_volume_confirmation(df: pd.DataFrame, period: int = 20) -> Dict[str, Any]:
    """Computes volume surge confirmation on breakout day."""
    if len(df) < period + 1:
        return {"vol_ratio": 1.0, "is_confirmed": True, "vol_status": "NEUTRAL"}

    v = df["Volume"]
    vol_latest = float(v.iloc[-1])
    vol_avg = float(v.tail(period).mean())
    ratio = round(vol_latest / vol_avg, 2) if (vol_avg > 0 and not math.isnan(vol_avg)) else 1.0

    is_confirmed = ratio >= 1.0
    if ratio >= 1.50:
        status = "INSTITUTIONAL_SURGE"
    elif ratio >= 1.0:
        status = "VOLUME_CONFIRMED"
    elif ratio >= 0.70:
        status = "SUB_AVERAGE"
    else:
        status = "LOW_VOLUME_TRAP"

    return {"vol_ratio": ratio, "is_confirmed": is_confirmed, "vol_status": status}


def compute_frog_in_the_pan(df: pd.DataFrame, lookback: int = 40) -> Dict[str, Any]:
    """Computes 'Frog-in-the-Pan' (FIP) information discreteness and smoothness."""
    if len(df) < lookback + 1:
        return {"smoothness_pct": 50.0, "max_jump_pct": 20.0, "is_smooth": True, "fip_status": "NEUTRAL"}

    c = df["Close"]
    ret = c.pct_change().tail(lookback).dropna()
    pos_count = int((ret > 0).sum())
    total_active = int((ret != 0).sum())
    smoothness_pct = round((pos_count / total_active * 100.0), 1) if total_active > 0 else 50.0

    diffs = (c - c.shift(1)).tail(lookback).clip(lower=0)
    sum_pos = float(diffs.sum())
    max_1d = float(diffs.max())
    max_jump_pct = round((max_1d / sum_pos) * 100.0, 1) if sum_pos > 0 else 0.0

    is_smooth = (smoothness_pct >= 50.0) and (max_jump_pct <= 40.0)
    if smoothness_pct >= 55.0 and max_jump_pct <= 25.0:
        status = "STEADY_ACCUMULATION"
    elif is_smooth:
        status = "MODERATE_SMOOTHNESS"
    else:
        status = "DISCRETE_JUMP_RISK"

    return {"smoothness_pct": smoothness_pct, "max_jump_pct": max_jump_pct, "is_smooth": is_smooth, "fip_status": status}


def evaluate_institutional_quality(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Evaluates complete Accumulation Quality Score (AQS: 0–100) & Anti-Trap Vetoes:
      - Closing Range (IBS)
      - Up/Down Volume Ratio
      - Volume Dry-Up (VDU)
      - Breakout Volume Surge
      - VCP Volatility Coiling
      - Frog-in-the-Pan (FIP) Smoothness
    """
    cr = compute_closing_range(df)
    ud = compute_up_down_volume_ratio(df)
    vdu = compute_volume_dry_up(df)
    vol = compute_volume_confirmation(df)
    vcp = compute_vcp_ratio(df)
    fip = compute_frog_in_the_pan(df)

    warnings: List[str] = []
    is_trap_veto = False

    # 1. Hard Anti-Trap Veto: Wyckoff Upthrust without underlying accumulation (CR <= 0.30 and Vol >= 1.50)
    if cr["closing_range"] <= 0.30 and vol["vol_ratio"] >= 1.50 and ud["up_down_vol_ratio"] < 1.05:
        is_trap_veto = True
        warnings.append(f"Wyckoff Upthrust Trap: Volume surged ({vol['vol_ratio']}x) with close in bottom third (CR {cr['closing_range']})")
    elif cr["closing_range"] <= 0.30 and vol["vol_ratio"] >= 1.50:
        is_trap_veto = True
        warnings.append(f"Wyckoff Upthrust Trap: Heavy volume ({vol['vol_ratio']}x) rejected near session lows (CR {cr['closing_range']})")
    elif cr["is_upthrust_trap"]:
        warnings.append(f"Resistance rejection warning: Session closed in lower half (CR {cr['closing_range']}) — Breakout unconfirmed")

    # 2. Hard Anti-Trap Veto: Heavy distribution volume with sub-average breakout
    if ud["ud_status"] == "DISTRIBUTION_PRESSURE" and vol["vol_ratio"] < 0.85:
        is_trap_veto = True
        warnings.append(f"Distribution Trap: Heavy down-volume (U/D {ud['up_down_vol_ratio']}) with weak breakout volume")

    if not vol["is_confirmed"]:
        warnings.append(f"Low breakout volume ({vol['vol_ratio']}x vs 20d avg) — High fakeout risk")
    if not vcp["is_coiled"]:
        warnings.append(f"Expanding volatility whipsaw (VCP {vcp['vcp_ratio']}) — Stop-out risk")
    if not fip["is_smooth"]:
        warnings.append(f"Discrete jump profile (Smoothness {fip['smoothness_pct']}%) — Mean-reversion risk")

    # Composite AQS Points (0 - 100): Preserves multi-month institutional accumulation
    score = 0.0
    score += 25.0 if cr["is_strong_close"] else (15.0 if cr["closing_range"] >= 0.45 else 0.0)
    score += 20.0 if vol["vol_ratio"] >= 1.20 else (10.0 if vol["is_confirmed"] else 0.0)
    score += 20.0 if ud["up_down_vol_ratio"] >= 1.20 else (10.0 if ud["is_accumulating"] else 0.0)
    score += 20.0 if vcp["is_coiled"] else (10.0 if vcp["vcp_ratio"] <= 1.20 else 0.0)
    score += 15.0 if fip["is_smooth"] else 0.0
    if vdu["is_dry"]:
        score = min(100.0, score + 5.0)

    if score >= 80.0:
        structural_grade = "PRIME_ACCUMULATION"
    elif score >= 60.0:
        structural_grade = "CONFIRMED_DEMAND"
    elif score >= 45.0:
        structural_grade = "NEUTRAL_QUALITY"
    else:
        structural_grade = "SPECULATIVE_CHURN"

    grade = "TRAP_VETO" if is_trap_veto else structural_grade

    return {
        "grade": grade,
        "structural_grade": structural_grade,
        "quality_score": round(score, 1),
        "is_institutional_grade": score >= 65.0 and not is_trap_veto,
        "is_trap_veto": is_trap_veto,
        "closing_range": cr["closing_range"],
        "cr_status": cr["cr_status"],
        "up_down_vol_ratio": ud["up_down_vol_ratio"],
        "ud_status": ud["ud_status"],
        "vdu_ratio": vdu["vdu_ratio"],
        "vdu_status": vdu["vdu_status"],
        "vcp_ratio": vcp["vcp_ratio"],
        "vcp_status": vcp["vcp_status"],
        "vol_ratio": vol["vol_ratio"],
        "vol_status": vol["vol_status"],
        "fip_smoothness_pct": fip["smoothness_pct"],
        "fip_status": fip["fip_status"],
        "warnings": warnings
    }
