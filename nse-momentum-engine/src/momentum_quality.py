#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
momentum_quality.py — Institutional Momentum Quality & Low-Probability Defense
=============================================================================
Pure domain module implementing three canonical institutional defense filters:
  1. Minervini Volume Surge Confirmation (Breakout volume vs. 20d average)
  2. Volatility Contraction Pattern (VCP) Ratio (ATR5 / ATR20 coiling)
  3. "Frog-in-the-Pan" (FIP) Information Discreteness (Smoothness vs. discrete spike)

Strictly adheres to AGENTS.md: pure functions, immutable inputs, typed outputs.
"""

from __future__ import annotations
import math
from typing import Dict, Any, List, Optional
import numpy as np
import pandas as pd


def compute_true_range(df: pd.DataFrame) -> pd.Series:
    """Computes True Range (TR) across High, Low, and Close."""
    h = df["High"]
    l = df["Low"]
    c = df["Close"]
    pc = c.shift(1)
    tr = pd.concat([(h - l), (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr


def compute_vcp_ratio(df: pd.DataFrame, fast: int = 5, slow: int = 20) -> Dict[str, Any]:
    """
    Computes Volatility Contraction Pattern (VCP) ratio.
    Coiling occurs when short-term range (ATR5) dampens relative to medium-term (ATR20).
    VCP ratio <= 1.05 indicates coiling; > 1.25 indicates expanding volatility whipsaw.
    """
    if len(df) < slow + 2:
        return {"vcp_ratio": 1.0, "is_coiled": True, "vcp_status": "NEUTRAL"}

    tr = compute_true_range(df)
    atr_fast = float(tr.rolling(fast).mean().iloc[-1])
    atr_slow = float(tr.rolling(slow).mean().iloc[-1])

    if atr_slow <= 0 or math.isnan(atr_slow):
        ratio = 1.0
    else:
        ratio = round(atr_fast / atr_slow, 2)

    is_coiled = ratio <= 1.05
    if ratio <= 0.90:
        status = "TIGHT_COIL"
    elif ratio <= 1.05:
        status = "NORMAL_CONTRACTION"
    elif ratio <= 1.25:
        status = "NEUTRAL"
    else:
        status = "ERRATIC_EXPANSION"

    return {
        "vcp_ratio": ratio,
        "is_coiled": is_coiled,
        "vcp_status": status
    }


def compute_volume_confirmation(df: pd.DataFrame, period: int = 20) -> Dict[str, Any]:
    """
    Computes volume confirmation on setup/breakout day.
    Institutional accumulation requires volume >= 1.0x (ideally >= 1.2x) 20-day average.
    Volume < 0.70x indicates low-volume retail fakeout.
    """
    if len(df) < period + 1:
        return {"vol_ratio": 1.0, "is_confirmed": True, "vol_status": "NEUTRAL"}

    v = df["Volume"]
    vol_latest = float(v.iloc[-1])
    vol_avg = float(v.tail(period).mean())

    if vol_avg <= 0 or math.isnan(vol_avg):
        ratio = 1.0
    else:
        ratio = round(vol_latest / vol_avg, 2)

    is_confirmed = ratio >= 1.0
    if ratio >= 1.50:
        status = "INSTITUTIONAL_SURGE"
    elif ratio >= 1.0:
        status = "VOLUME_CONFIRMED"
    elif ratio >= 0.70:
        status = "SUB_AVERAGE"
    else:
        status = "LOW_VOLUME_TRAP"

    return {
        "vol_ratio": ratio,
        "is_confirmed": is_confirmed,
        "vol_status": status
    }


def compute_frog_in_the_pan(df: pd.DataFrame, lookback: int = 40) -> Dict[str, Any]:
    """
    Computes 'Frog-in-the-Pan' (FIP) Information Discreteness.
    Measures price path smoothness (frequent steady increments vs. single discrete jump).
    Returns smoothness percentage and maximum 1-day jump share.
    """
    if len(df) < lookback + 1:
        return {"smoothness_pct": 50.0, "max_jump_pct": 20.0, "is_smooth": True, "fip_status": "NEUTRAL"}

    c = df["Close"]
    ret = c.pct_change()
    recent_ret = ret.tail(lookback).dropna()

    pos_count = int((recent_ret > 0).sum())
    neg_count = int((recent_ret < 0).sum())
    total_active = pos_count + neg_count

    smoothness_pct = round((pos_count / total_active * 100.0), 1) if total_active > 0 else 50.0

    # Robust FIP: Max single-day price gain as % of total cumulative positive gains
    diffs = (c - c.shift(1)).tail(lookback)
    pos_gains = diffs.clip(lower=0)
    sum_pos_gains = float(pos_gains.sum())
    max_1d_gain = float(pos_gains.max())

    if sum_pos_gains > 0 and max_1d_gain > 0:
        max_jump_pct = round((max_1d_gain / sum_pos_gains) * 100.0, 1)
    else:
        max_jump_pct = 0.0

    # Smoothness >= 50% and no single day accounts for > 40% of total gains
    is_smooth = (smoothness_pct >= 50.0) and (max_jump_pct <= 40.0)

    if smoothness_pct >= 55.0 and max_jump_pct <= 25.0:
        status = "STEADY_ACCUMULATION"
    elif is_smooth:
        status = "MODERATE_SMOOTHNESS"
    else:
        status = "DISCRETE_JUMP_RISK"

    return {
        "smoothness_pct": smoothness_pct,
        "max_jump_pct": max_jump_pct,
        "is_smooth": is_smooth,
        "fip_status": status
    }


def evaluate_institutional_quality(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Comprehensive institutional quality gate evaluating all three dimensions.
    Returns composite grade, pass flags, and specific disqualification warnings.
    """
    vcp = compute_vcp_ratio(df)
    vol = compute_volume_confirmation(df)
    fip = compute_frog_in_the_pan(df)

    warnings: List[str] = []
    if not vol["is_confirmed"]:
        warnings.append(f"Low volume breakout ({vol['vol_ratio']}x vs 20d avg) — High fakeout risk")
    if not vcp["is_coiled"]:
        warnings.append(f"Expanding volatility whipsaw (VCP {vcp['vcp_ratio']}) — Stop-out risk")
    if not fip["is_smooth"]:
        warnings.append(f"Erratic discrete jump profile (Smoothness {fip['smoothness_pct']}%) — Mean-reversion risk")

    # Composite Institutional Grade
    passes_count = sum([vol["is_confirmed"], vcp["is_coiled"], fip["is_smooth"]])

    if passes_count == 3:
        grade = "PRIME_INSTITUTIONAL"
        quality_score = 100.0
    elif passes_count == 2:
        grade = "MODERATE_CONVICTION"
        quality_score = 70.0
    elif vol["vol_status"] == "LOW_VOLUME_TRAP" or vcp["vcp_status"] == "ERRATIC_EXPANSION":
        grade = "RETAIL_TRAP"
        quality_score = 30.0
    else:
        grade = "LOW_PROBABILITY"
        quality_score = 45.0

    return {
        "grade": grade,
        "quality_score": quality_score,
        "is_institutional_grade": passes_count >= 2 and vol["vol_ratio"] >= 0.85,
        "vcp_ratio": vcp["vcp_ratio"],
        "vcp_status": vcp["vcp_status"],
        "vol_ratio": vol["vol_ratio"],
        "vol_status": vol["vol_status"],
        "fip_smoothness_pct": fip["smoothness_pct"],
        "fip_status": fip["fip_status"],
        "warnings": warnings
    }
