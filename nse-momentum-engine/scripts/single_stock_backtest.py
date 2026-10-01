#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
single_stock_backtest.py — Single-stock credibility study + compounding rotation backtest
========================================================================================
Answers one question the trader asks before deploying capital:

    "If I take THIS stock under my fixed-target rotation rules, how often does it
     reach +15% before my stop takes me out?"

Two independent analyses are produced per symbol:

  1. Forward-outcome study
     Every historical bar where the stock satisfied the Stage-2 entry stack is
     treated as a hypothetical entry (next-day open). The forward path is then
     walked until the first of: +15% target, initial stop, or a holding deadline.
     This yields the per-entry hit rates — the stock's "credibility".

  2. Compounding rotation simulation
     A single ₹capital slot rotated sequentially: enter the next qualifying day,
     exit at target / stop / deadline, then redeploy the whole principal + profit
     into the next qualifying entry. No external capital is ever added.

The quant engine (src/quant_engine.py) is used purely as a REFERENCE for the
indicator and filter definitions; this script never imports or mutates it.

Usage
-----
    python scripts/single_stock_backtest.py --symbol CUPID
    python scripts/single_stock_backtest.py --symbol CUPID --years 3 --capital 1000
    python scripts/single_stock_backtest.py --all          # every leader in signal.json
    python scripts/single_stock_backtest.py --symbol CUPID --out-dir app/data/backtests
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

# Windows console UTF-8 guard (emoji / rupee symbols)
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DATA_DIR = os.path.join(ROOT_DIR, "app", "data")
DEFAULT_OUT_DIR = os.path.join(APP_DATA_DIR, "backtests")
SIGNAL_JSON = os.path.join(APP_DATA_DIR, "signal.json")

# Strategy parameters (defaults mirror the rotation plan: +15% take-profit).
DEFAULTS = {
    "capital": 1000.0,
    "target_pct": 0.15,        # rotation take-profit
    "stop_floor_pct": 0.05,    # initial stop is clamped between 5% and 7%
    "stop_cap_pct": 0.07,
    "stop_atr_mult": 2.0,      # 2 x ATR14
    "max_hold_days": 60,       # deadline if neither target nor stop is hit
    "rsi_min": 45.0,
    "rsi_max": 82.0,
    "stt_rate": 0.001,         # 0.1% securities transaction tax, each side
    "dp_charge": 15.93,        # flat depository charge per sell
    "buffer": 26.0,            # DP + taxes + rounding headroom
}

WARMUP_BARS = 200


# ─────────────────────────────────────────────────────────────────────────────
# Indicators (reference implementations matching the quant engine)
# ─────────────────────────────────────────────────────────────────────────────
def _flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df


def compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period, min_periods=period).mean()
    avg_loss = loss.rolling(period, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    for col in ("High", "Low", "Close"):
        if col not in df.columns:
            raise KeyError(f"backtest requires a '{col}' column")
    h, l, c = df["High"], df["Low"], df["Close"]
    pc = c.shift(1)
    tr = pd.concat([(h - l), (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def prepare(df: pd.DataFrame) -> pd.DataFrame:
    """Returns a copy with the indicator columns the strategy needs."""
    d = _flatten_columns(df.copy())
    d = d.dropna(subset=["Close"])
    d["RSI"] = compute_rsi(d["Close"])
    d["ATR"] = compute_atr(d)
    d["SMA50"] = d["Close"].rolling(50).mean()
    d["SMA200"] = d["Close"].rolling(200).mean()
    d["ROC_2M"] = (d["Close"] / d["Close"].shift(40) - 1.0) * 100.0
    d["ROC_3M"] = (d["Close"] / d["Close"].shift(60) - 1.0) * 100.0
    return d


def stop_distance_pct(entry: float, atr: float, p: dict) -> float:
    atr_pct = (p["stop_atr_mult"] * atr) / entry if entry > 0 else p["stop_cap_pct"]
    return min(p["stop_cap_pct"], max(p["stop_floor_pct"], atr_pct))


def _qualifies(row) -> bool:
    """Stage-2 entry stack, evaluated with values known on the signal day."""
    try:
        cmp = float(row["Close"])
        sma50 = float(row["SMA50"])
        sma200 = float(row["SMA200"])
        rsi = float(row["RSI"])
        roc2 = float(row["ROC_2M"])
    except (TypeError, ValueError):
        return False
    if not (cmp > 0 and math.isfinite(cmp)):
        return False
    if not (cmp > sma50 > sma200):
        return False
    if not (40.0 <= rsi <= 82.0):
        return False
    if roc2 <= 0:
        return False
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Time-to-target helpers
# ─────────────────────────────────────────────────────────────────────────────
def _dist(values):
    """Small percentile summary, tolerant of empty input."""
    if not values:
        return None
    s = sorted(float(v) for v in values)

    def q(p):
        idx = min(len(s) - 1, max(0, int(round(p * (len(s) - 1)))))
        return s[idx]

    return {
        "count": len(s),
        "min": round(s[0], 1), "p25": round(q(0.25), 1), "median": round(q(0.5), 1),
        "p75": round(q(0.75), 1), "p90": round(q(0.90), 1), "max": round(s[-1], 1),
    }


def _buckets(trading_days):
    """How the winning cycles spread across days / weeks / months."""
    b = {
        "0-2d": 0, "3-5d (\u22641 week)": 0, "6-10d (\u22642 weeks)": 0,
        "11-21d (\u22641 month)": 0, "22-42d (\u22642 months)": 0, ">42d (slow)": 0,
    }
    for d in trading_days:
        if d <= 2: b["0-2d"] += 1
        elif d <= 5: b["3-5d (\u22641 week)"] += 1
        elif d <= 10: b["6-10d (\u22642 weeks)"] += 1
        elif d <= 21: b["11-21d (\u22641 month)"] += 1
        elif d <= 42: b["22-42d (\u22642 months)"] += 1
        else: b[">42d (slow)"] += 1
    return b


# ─────────────────────────────────────────────────────────────────────────────
# 1. Forward-outcome study — per-entry credibility
# ─────────────────────────────────────────────────────────────────────────────
def forward_outcome_study(df: pd.DataFrame, p: dict) -> dict:
    d = prepare(df)
    n = len(d)
    highs = d["High"].to_numpy(dtype=float)
    lows = d["Low"].to_numpy(dtype=float)
    closes = d["Close"].to_numpy(dtype=float)
    opens = d["Open"].to_numpy(dtype=float) if "Open" in d.columns else closes

    outcomes = []
    target_pct = p["target_pct"]
    for i in range(WARMUP_BARS, n - 1):
        if not _qualifies(d.iloc[i]):
            continue
        entry = float(opens[i + 1])
        if not (entry > 0 and math.isfinite(entry)):
            continue
        stop_pct = stop_distance_pct(entry, float(d["ATR"].iloc[i]), p)
        stop = entry * (1.0 - stop_pct)
        target = entry * (1.0 + target_pct)

        end = min(i + 1 + p["max_hold_days"], n - 1)
        outcome = "timeout"
        exit_price = close_price = float(closes[end])
        hold = end - (i + 1)
        for j in range(i + 1, end + 1):
            # Conservative ordering: if a bar straddles both levels, the stop is
            # assumed to fill first.
            if lows[j] <= stop:
                outcome, exit_price, hold = "stop", stop, j - (i + 1)
                break
            if highs[j] >= target:
                outcome, exit_price, hold = "target", target, j - (i + 1)
                break

        exit_bar = min(i + 1 + hold, n - 1)
        try:
            cal_days = int((d.index[exit_bar] - d.index[i + 1]).days)
        except Exception:
            cal_days = int(round(hold * 7.0 / 5.0))
        gross = (exit_price / entry) - 1.0
        outcomes.append({
            "outcome": outcome,
            "gross_pct": gross * 100.0,
            "hold_days": int(hold),
            "calendar_days": cal_days,
            "stop_pct": stop_pct * 100.0,
        })

    if not outcomes:
        return {
            "observations": 0, "target_hits": 0, "stop_hits": 0, "timeouts": 0,
            "target_hit_rate_pct": 0.0, "stop_hit_rate_pct": 0.0,
            "expectancy_pct": 0.0, "avg_hold_to_target_days": None,
            "avg_hold_to_stop_days": None, "median_return_pct": 0.0,
            "p10_return_pct": 0.0, "p90_return_pct": 0.0,
            "time_to_target": None,
            "_target_trading_days": [], "_target_calendar_days": [],
        }

    df_o = pd.DataFrame(outcomes)
    target_hits = int((df_o["outcome"] == "target").sum())
    stop_hits = int((df_o["outcome"] == "stop").sum())
    timeouts = int((df_o["outcome"] == "timeout").sum())
    total = len(df_o)

    tgt = df_o[df_o["outcome"] == "target"]
    stp = df_o[df_o["outcome"] == "stop"]

    return {
        "observations": total,
        "target_hits": target_hits,
        "stop_hits": stop_hits,
        "timeouts": timeouts,
        "target_hit_rate_pct": round(target_hits / total * 100.0, 1),
        "stop_hit_rate_pct": round(stop_hits / total * 100.0, 1),
        "expectancy_pct": round(float(df_o["gross_pct"].mean()), 2),
        "avg_hold_to_target_days": round(float(tgt["hold_days"].mean()), 1) if len(tgt) else None,
        "avg_hold_to_stop_days": round(float(stp["hold_days"].mean()), 1) if len(stp) else None,
        "median_return_pct": round(float(df_o["gross_pct"].median()), 2),
        "p10_return_pct": round(float(df_o["gross_pct"].quantile(0.10)), 2),
        "p90_return_pct": round(float(df_o["gross_pct"].quantile(0.90)), 2),
        "avg_stop_distance_pct": round(float(df_o["stop_pct"].mean()), 2),
        "time_to_target": _time_to_target(tgt),
        "_target_trading_days": [int(x) for x in tgt["hold_days"].tolist()],
        "_target_calendar_days": [int(x) for x in tgt["calendar_days"].tolist()],
    }


def _time_to_target(tgt: pd.DataFrame) -> dict:
    """Distribution of how long a winning cycle took to reach +15%."""
    if tgt is None or len(tgt) == 0:
        return {"target_count": 0, "trading_days": None, "calendar_days": None,
                "buckets_trading_days": _buckets([])}
    trading = [int(x) for x in tgt["hold_days"].tolist()]
    calendar = [int(x) for x in tgt["calendar_days"].tolist()]
    return {
        "target_count": len(trading),
        "trading_days": _dist(trading),
        "calendar_days": _dist(calendar),
        "buckets_trading_days": _buckets(trading),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 2. Compounding rotation simulation — one capital slot, sequential
# ─────────────────────────────────────────────────────────────────────────────
def compounding_sim(df: pd.DataFrame, p: dict) -> dict:
    d = prepare(df)
    n = len(d)
    highs = d["High"].to_numpy(dtype=float)
    lows = d["Low"].to_numpy(dtype=float)
    closes = d["Close"].to_numpy(dtype=float)
    opens = d["Open"].to_numpy(dtype=float) if "Open" in d.columns else closes

    capital = float(p["capital"])
    initial = capital
    equity_curve = [capital]
    trades = []
    target_pct = p["target_pct"]
    first_entry_idx = None
    last_exit_idx = None

    i = WARMUP_BARS
    while i < n - 1:
        if not _qualifies(d.iloc[i]):
            i += 1
            continue
        entry = float(opens[i + 1])
        if not (entry > 0 and math.isfinite(entry)):
            i += 1
            continue
        affordable = math.floor((capital - p["buffer"]) / entry)
        if affordable < 1:
            # Capital can no longer afford a single share of this name; in the
            # real rotation the trader would pick the next leader, so skip ahead.
            i += 1
            continue

        shares = int(affordable)
        if first_entry_idx is None:
            first_entry_idx = i + 1
        stop_pct = stop_distance_pct(entry, float(d["ATR"].iloc[i]), p)
        stop = entry * (1.0 - stop_pct)
        target = entry * (1.0 + target_pct)

        capital -= shares * entry
        capital -= shares * entry * p["stt_rate"]  # STT on buy

        end = min(i + 1 + p["max_hold_days"], n - 1)
        exit_price, reason, exit_idx = float(closes[end]), "deadline", end
        for j in range(i + 1, end + 1):
            if lows[j] <= stop:
                exit_price, reason, exit_idx = stop, "stop", j
                break
            if highs[j] >= target:
                exit_price, reason, exit_idx = target, "target", j
                break

        gross_before = shares * exit_price
        net_proceeds = gross_before - gross_before * p["stt_rate"] - p["dp_charge"]
        capital += net_proceeds

        cost_basis = shares * entry + shares * entry * p["stt_rate"]
        pnl = net_proceeds - cost_basis
        trades.append({
            "entry_date": str(d.index[i + 1].date()) if hasattr(d.index[i + 1], "date") else str(d.index[i + 1]),
            "exit_date": str(d.index[exit_idx].date()) if hasattr(d.index[exit_idx], "date") else str(d.index[exit_idx]),
            "entry_price": round(entry, 2),
            "exit_price": round(exit_price, 2),
            "shares": shares,
            "pnl": round(pnl, 2),
            "pnl_pct": round((pnl / cost_basis) * 100.0, 2) if cost_basis > 0 else 0.0,
            "hold_days": int(exit_idx - (i + 1)),
            "reason": reason,
            "capital_after": round(capital, 2),
        })
        equity_curve.append(capital)
        last_exit_idx = exit_idx
        i = exit_idx + 1

    if not trades:
        return {
            "cycles": 0, "final_capital": round(initial, 2),
            "total_return_pct": 0.0, "win_rate_pct": 0.0, "profit_factor": 0.0,
            "max_drawdown_pct": 0.0, "avg_cycle_days": None, "trades": [],
        }

    pf = pd.DataFrame(trades)
    wins = pf[pf["pnl"] > 0]
    losses = pf[pf["pnl"] <= 0]
    gross_profit = float(wins["pnl"].sum()) if len(wins) else 0.0
    gross_loss = abs(float(losses["pnl"].sum())) if len(losses) else 0.0

    eq = pd.Series(equity_curve)
    peak = eq.cummax()
    dd = ((eq - peak) / peak).min() * 100.0

    # Annualised return from the first entry bar to the last exit bar.
    span_days = 0
    if first_entry_idx is not None and last_exit_idx is not None:
        try:
            span_days = (d.index[last_exit_idx] - d.index[first_entry_idx]).days
        except Exception:
            span_days = 0
    years = span_days / 365.25
    cagr = ((capital / initial) ** (1 / years) - 1.0) * 100.0 if (capital > 0 and years >= 0.25) else None

    return {
        "cycles": len(trades),
        "final_capital": round(capital, 2),
        "total_return_pct": round((capital / initial - 1.0) * 100.0, 2),
        "win_rate_pct": round(len(wins) / len(trades) * 100.0, 1),
        "profit_factor": round(gross_profit / gross_loss, 2) if gross_loss > 0 else None,
        "max_drawdown_pct": round(float(dd), 2),
        "avg_cycle_days": round(float(pf["hold_days"].mean()), 1),
        "cagr_pct": round(cagr, 1) if cagr is not None else None,
        "target_exits": int((pf["reason"] == "target").sum()),
        "stop_exits": int((pf["reason"] == "stop").sum()),
        "deadline_exits": int((pf["reason"] == "deadline").sum()),
        "trades": trades,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Verdict
# ─────────────────────────────────────────────────────────────────────────────
def build_verdict(study: dict, sim: dict) -> dict:
    obs = study.get("observations", 0)
    if obs < 8:
        return {
            "credible": False,
            "score": None,
            "summary": "Not enough historical signals for this stock to judge credibility.",
        }
    hit = study.get("target_hit_rate_pct", 0.0)
    stop = study.get("stop_hit_rate_pct", 0.0)
    exp = study.get("expectancy_pct", 0.0)

    # Score: reward target-hit rate and positive expectancy, penalise stop rate.
    score = max(0.0, min(100.0, hit * 0.8 + (exp + 7.0) * 1.5 - stop * 0.3))
    credible = hit >= 55.0 and exp > 0.0
    if credible and score >= 70:
        summary = f"Strong edge: reached +15% before the stop in {hit:.0f}% of signals."
    elif credible:
        summary = f"Positive edge: +15% hit before the stop in {hit:.0f}% of signals."
    elif hit >= 45.0:
        summary = f"Marginal: only {hit:.0f}% of signals reached +15% before the stop."
    else:
        summary = f"Weak: stops dominate ({stop:.0f}% stopped, {hit:.0f}% reached target)."
    return {"credible": bool(credible), "score": round(score, 1), "summary": summary}


def pace_of(median_trading_days) -> str:
    """Rough speed class for a winning cycle."""
    if median_trading_days is None:
        return "unknown"
    if median_trading_days <= 10:
        return "fast"
    if median_trading_days <= 25:
        return "medium"
    return "slow"


def analyse(df: pd.DataFrame, symbol: str, params: dict, keep_raw: bool = False) -> dict:
    p = {**DEFAULTS, **params}
    study = forward_outcome_study(df, p)
    raw = {
        "trading": study.pop("_target_trading_days", []) or [],
        "calendar": study.pop("_target_calendar_days", []) or [],
    }
    sim = compounding_sim(df, p)
    verdict = build_verdict(study, sim)
    prep = prepare(df)
    period = {
        "start": str(prep.index[0].date()) if hasattr(prep.index[0], "date") else str(prep.index[0]),
        "end": str(prep.index[-1].date()) if hasattr(prep.index[-1], "date") else str(prep.index[-1]),
        "bars": int(len(prep)),
    }
    tt = study.get("time_to_target") or {}
    median_td = (tt.get("trading_days") or {}).get("median")
    report = {
        "symbol": symbol.upper(),
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "period": period,
        "pace": pace_of(median_td),
        "params": {
            "capital": p["capital"],
            "target_pct": round(p["target_pct"] * 100, 1),
            "stop_floor_pct": round(p["stop_floor_pct"] * 100, 1),
            "stop_cap_pct": round(p["stop_cap_pct"] * 100, 1),
            "stop_atr_mult": p["stop_atr_mult"],
            "max_hold_days": p["max_hold_days"],
        },
        "study": study,
        "simulation": sim,
        "verdict": verdict,
    }
    if keep_raw:
        report["_raw_time_to_target"] = raw
    return report


def index_entry(report: dict) -> dict:
    """Compact per-symbol summary for the app's screener ranking."""
    s, sim, v = report.get("study", {}), report.get("simulation", {}), report.get("verdict", {})
    tt = s.get("time_to_target") or {}
    td = tt.get("trading_days") or {}
    cd = tt.get("calendar_days") or {}
    median_td = td.get("median")
    # Older reports predate the "pace" field; derive it from the median instead.
    pace = report.get("pace") if report.get("pace") not in (None, "unknown") else pace_of(median_td)
    return {
        "symbol": report.get("symbol"),
        "credible": v.get("credible", False),
        "score": v.get("score"),
        "pace": pace,
        "target_hit_rate_pct": s.get("target_hit_rate_pct"),
        "stop_hit_rate_pct": s.get("stop_hit_rate_pct"),
        "expectancy_pct": s.get("expectancy_pct"),
        "median_days_to_target": td.get("median"),
        "median_calendar_days_to_target": cd.get("median"),
        "avg_cycle_days": sim.get("avg_cycle_days"),
        "total_return_pct": sim.get("total_return_pct"),
    }


def build_index(reports: list) -> dict:
    """Aggregate compact entries from many per-symbol reports, best-first."""
    entries = [index_entry(r) for r in reports if isinstance(r, dict) and r.get("symbol")]

    def _key(e):
        s = e.get("score")
        return (s is None, -(s if s is not None else 0.0), str(e.get("symbol")))

    entries.sort(key=_key)
    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "count": len(entries),
        "entries": entries,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Data fetching + CLI
# ─────────────────────────────────────────────────────────────────────────────
def fetch_history(symbol: str, years: int = 3) -> pd.DataFrame:
    import yfinance as yf

    ticker = symbol if symbol.endswith(".NS") else f"{symbol}.NS"
    df = yf.download(ticker, period=f"{years}y", interval="1d", progress=False, auto_adjust=False)
    if df is None or len(df) == 0:
        raise RuntimeError(f"No data returned for {ticker}")
    return _flatten_columns(df)


def fetch_batch(symbols: list[str], years: int = 3) -> dict:
    import yfinance as yf

    tickers = [s if s.endswith(".NS") else f"{s}.NS" for s in symbols]
    data = yf.download(tickers, period=f"{years}y", interval="1d", progress=False,
                       group_by="ticker", threads=True, auto_adjust=False)
    out = {}
    for s, t in zip(symbols, tickers):
        try:
            sub = data[t] if isinstance(data.columns, pd.MultiIndex) else data
            sub = _flatten_columns(sub.copy()).dropna(subset=["Close"])
            if len(sub):
                out[s.upper()] = sub
        except Exception:
            continue
    return out


def pooled_time_analysis(symbols: list, years: int, params: dict) -> dict:
    """Pools every winning cycle across all leaders to answer
    'how long does \u20b91,000 take to reach +15%?'."""
    data = fetch_batch(symbols, years) if symbols else {}
    trading, calendar, per_stock = [], [], {}
    for sym in symbols:
        df = data.get(sym.upper())
        if df is None:
            continue
        study = forward_outcome_study(df, {**DEFAULTS, **params})
        trading += study.get("_target_trading_days", [])
        calendar += study.get("_target_calendar_days", [])
        tt = study.get("time_to_target") or {}
        per_stock[sym.upper()] = {
            "target_hit_rate_pct": study.get("target_hit_rate_pct"),
            "median_trading_days_to_target": (tt.get("trading_days") or {}).get("median"),
            "median_calendar_days_to_target": (tt.get("calendar_days") or {}).get("median"),
        }
    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "symbols": len(per_stock),
        "target_observations": len(trading),
        "trading_days": _dist(trading),
        "calendar_days": _dist(calendar),
        "buckets_trading_days": _buckets(trading),
        "per_stock": per_stock,
    }


def _write_report(report: dict, out_dir: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{report['symbol']}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    return path


def write_index(reports: list, out_dir: str) -> str:
    index = build_index(reports)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "_index.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2)
    return path


def rebuild_index_from_dir(out_dir: str) -> str:
    """Rebuild _index.json from the per-symbol reports already on disk.

    Lets the app get a fresh credibility index without re-downloading 3 years
    of history for every leader.
    """
    reports = []
    if os.path.isdir(out_dir):
        for name in sorted(os.listdir(out_dir)):
            if not name.endswith(".json") or name.startswith("_"):
                continue
            try:
                with open(os.path.join(out_dir, name), "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict) and data.get("symbol"):
                    reports.append(data)
            except Exception:
                continue
    return write_index(reports, out_dir)


def _print_report(report: dict) -> None:
    s, sim, v = report["study"], report["simulation"], report["verdict"]
    print("=" * 68)
    print(f"📊  CREDIBILITY REPORT — {report['symbol']}   ({report['period']['start']} → {report['period']['end']})")
    print("=" * 68)
    print(f"  Historical signals simulated : {s['observations']}")
    print(f"  Reached +15% before stop     : {s['target_hit_rate_pct']}%")
    print(f"  Stopped out first            : {s['stop_hit_rate_pct']}%")
    print(f"  Deadline exits               : {s['timeouts']}")
    print(f"  Expectancy per signal        : {s['expectancy_pct']:+.2f}%")
    print(f"  Avg hold to target / stop    : {s['avg_hold_to_target_days']}d / {s['avg_hold_to_stop_days']}d")
    print(f"  Median / 10–90th percentile  : {s['median_return_pct']:+.1f}%  ({s['p10_return_pct']:+.1f}% … {s['p90_return_pct']:+.1f}%)")
    print("-" * 68)
    print(f"🧮  Rotation sim  start ₹{report['params']['capital']:,.0f} → ₹{sim['final_capital']:,.2f}  ({sim['total_return_pct']:+.1f}%)")
    print(f"    Cycles: {sim['cycles']}   Win rate: {sim['win_rate_pct']}%   Profit factor: {sim['profit_factor']}   Max DD: {sim['max_drawdown_pct']}%")
    print(f"    Exits: {sim['target_exits']} target · {sim['stop_exits']} stop · {sim['deadline_exits']} deadline   Avg cycle: {sim['avg_cycle_days']}d")
    print("-" * 68)
    flag = "✅ CREDIBLE" if v["credible"] else "⚠️  LOW CREDIBILITY"
    print(f"  VERDICT: {flag}  (score {v['score']})")
    print(f"  {v['summary']}")
    print("=" * 68)


def _print_time_analysis(a: dict) -> None:
    td = a.get("trading_days") or {}
    cd = a.get("calendar_days") or {}
    print("=" * 68)
    print("\u23f1\ufe0f  TIME TO +15%  (pooled across every leader)")
    print("=" * 68)
    print(f"  Winning cycles analysed : {a['target_observations']}  across {a['symbols']} stocks")
    print(f"  Trading days   median {td.get('median')}d   p25 {td.get('p25')}  p75 {td.get('p75')}  p90 {td.get('p90')}  max {td.get('max')}")
    print(f"  Calendar days  median {cd.get('median')}d   p25 {cd.get('p25')}  p75 {cd.get('p75')}  p90 {cd.get('p90')}")
    print("  Winning cycles by duration (trading days):")
    for k, v in (a.get("buckets_trading_days") or {}).items():
        print(f"    {k:22s} {v}")
    print("=" * 68)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Single-stock credibility study & rotation backtest")
    ap.add_argument("--symbol", help="NSE symbol, e.g. CUPID")
    ap.add_argument("--all", action="store_true", help="Run for every leader in app/data/signal.json")
    ap.add_argument("--time-analysis", action="store_true",
                    help="Pool every winning cycle to measure how long the +15 percent target takes")
    ap.add_argument("--rebuild-index", action="store_true",
                    help="Rebuild _index.json from the per-symbol reports already on disk (offline)")
    ap.add_argument("--years", type=int, default=3, help="History depth in years (default 3)")
    ap.add_argument("--capital", type=float, default=DEFAULTS["capital"])
    ap.add_argument("--target", type=float, default=DEFAULTS["target_pct"], help="Rotation target as a decimal (0.15)")
    ap.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    args = ap.parse_args(argv)

    params = {"capital": args.capital, "target_pct": args.target}

    if args.rebuild_index:
        path = rebuild_index_from_dir(args.out_dir)
        with open(path, "r", encoding="utf-8") as f:
            n = json.load(f).get("count", 0)
        print(f"\U0001f4be Rebuilt credibility index: {path}  ({n} symbols)")
        return 0

    if args.time_analysis:
        symbols = []
        if os.path.exists(SIGNAL_JSON):
            with open(SIGNAL_JSON, "r", encoding="utf-8") as f:
                payload = json.load(f)
            symbols = [s["SYMBOL"] for s in payload.get("all_qualified", [])]
        if not symbols:
            print("No symbols found in signal.json (or file missing).")
            return 1
        print(f"Pooling winning cycles across {len(symbols)} leaders…")
        summary = pooled_time_analysis(symbols, args.years, params)
        _print_time_analysis(summary)
        os.makedirs(args.out_dir, exist_ok=True)
        path = os.path.join(args.out_dir, "_aggregate.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
        print(f"💾 Saved: {path}")
        return 0

    if args.all:
        symbols = []
        if os.path.exists(SIGNAL_JSON):
            with open(SIGNAL_JSON, "r", encoding="utf-8") as f:
                payload = json.load(f)
            symbols = [s["SYMBOL"] for s in payload.get("all_qualified", [])]
        if not symbols:
            print("No symbols found in signal.json (or file missing).")
            return 1
        print(f"Running credibility study for {len(symbols)} leaders…")
        data = fetch_batch(symbols, years=args.years)
        reports, written = [], []
        for sym in symbols:
            if sym.upper() not in data:
                print(f"  · {sym}: no history, skipped")
                continue
            report = analyse(data[sym.upper()], sym, params)
            reports.append(report)
            written.append(_write_report(report, args.out_dir))
            v = report["verdict"]
            print(f"  · {sym:12s} target-hit {report['study']['target_hit_rate_pct']:5.1f}%  "
                  f"expectancy {report['study']['expectancy_pct']:+6.2f}%  "
                  f"{'✅' if v['credible'] else '⚠️ '} score {v['score']}")
        index_path = write_index(reports, args.out_dir)
        print(f"\nWrote {len(written)} reports to {args.out_dir}")
        print(f"\U0001f4be Credibility index: {index_path}  ({len(reports)} symbols)")
        return 0

    if not args.symbol:
        ap.error("provide --symbol SYMBOL or --all")

    df = fetch_history(args.symbol, years=args.years)
    report = analyse(df, args.symbol, params)
    _print_report(report)
    path = _write_report(report, args.out_dir)
    print(f"💾 Saved: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
