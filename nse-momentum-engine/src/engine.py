"""
NSE Momentum Screening Engine — v2.0
=====================================
Author  : nse-momentum-engine
Strategy: Small-capital (₹1,000) weekly trend-following on NSE Cash Delivery.

Key Improvements over v1:
  - Fixed Nifty 500 universe source (NSE official via GitHub mirror)
  - Fixed yfinance v0.2.x multi-ticker download API
  - Added RSI(14) filter (40–70) to avoid overbought/oversold traps
  - Normalized Vol Ratio (z-score capped) to prevent CMS distortion
  - Added ATR-based initial stop as an alternative to fixed -7%
  - Added Milestone 3 (+50%) trailing stop output
  - Top-3 candidates exported alongside rank #1 winner
  - Python 3.12-safe datetime usage
"""

import os
import json
import requests
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime, timezone

# ─────────────────────────────────────────────
# CONFIGURATION  (override via GitHub Secrets / env vars)
# ─────────────────────────────────────────────
CAPITAL_BASE   = float(os.getenv("CAPITAL_BASE", "1000.0"))
MIN_PRICE      = float(os.getenv("MIN_PRICE",    "100.0"))
MAX_PRICE      = float(os.getenv("MAX_PRICE",    "950.0"))
MIN_AVG_VOLUME = int(os.getenv("MIN_AVG_VOLUME", "500000"))

# GTT Ratchet levels
STOP_PCT   = 0.07   # -7% initial hard stop
M1_PCT     = 0.15   # +15% Milestone 1 target
M1_STOP    = 0.025  # +2.5% ratchet after M1
M2_PCT     = 0.30   # +30% Milestone 2 target
M2_STOP    = 0.15   # +15% ratchet after M2
M3_PCT     = 0.50   # +50% Milestone 3 target

# ─────────────────────────────────────────────
# UNIVERSE  — Nifty 500 via reliable public mirror
# ─────────────────────────────────────────────
NIFTY500_URL = (
    "https://raw.githubusercontent.com/theafwan/nifty500/main/nifty500.csv"
)
FALLBACK_SYMBOLS = [
    "BEL", "TATAPOWER", "BHEL", "ASHOKLEY", "FEDERALBNK",
    "NMDC", "SAIL", "HDFCBANK", "ICICIBANK", "SBIN",
    "TATAMOTORS", "BAJFINANCE", "AXISBANK", "INFY", "TCS",
]


def get_nse_universe() -> list[str]:
    """
    Fetches the Nifty 500 symbol list. Returns Yahoo Finance ticker format (.NS).
    Falls back to a curated liquid list if the URL is unavailable.
    """
    try:
        resp = requests.get(NIFTY500_URL, timeout=15)
        resp.raise_for_status()
        df = pd.read_csv(pd.io.common.StringIO(resp.text))
        # Column name varies — try common ones
        col = next((c for c in df.columns if "symbol" in c.lower()), df.columns[0])
        symbols = [f"{s.strip()}.NS" for s in df[col].dropna().unique()]
        print(f"[INFO] Universe loaded: {len(symbols)} symbols from Nifty 500")
        return symbols
    except Exception as exc:
        print(f"[WARN] Universe URL failed ({exc}). Using fallback list.")
        return [f"{s}.NS" for s in FALLBACK_SYMBOLS]


# ─────────────────────────────────────────────
# INDICATOR HELPERS
# ─────────────────────────────────────────────

def compute_rsi(series: pd.Series, period: int = 14) -> float:
    """Returns the latest RSI value for a price series."""
    delta = series.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / loss.replace(0, np.nan)
    rsi   = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1])


def compute_atr(df: pd.DataFrame, period: int = 14) -> float:
    """Returns the latest Average True Range (ATR) value."""
    high, low, close = df['High'], df['Low'], df['Close']
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low  - prev_close).abs(),
    ], axis=1).max(axis=1)
    return float(tr.rolling(period).mean().iloc[-1])


# ─────────────────────────────────────────────
# FILTER + SCORE
# ─────────────────────────────────────────────

def evaluate_ticker(df: pd.DataFrame, cmp: float) -> dict | None:
    """
    Applies all hard filters. Returns a score dict or None if the stock fails.
    Filters (hard disqualifiers):
      1. Anti-downfall  : 20-day ROC > 0  AND  40-day ROC > 0
      2. Trend regime   : CMP > 50-SMA > 200-SMA
      3. 52W proximity  : Within 15% of 52-week high
      4. Volume floor   : 20-day avg volume >= MIN_AVG_VOLUME
      5. RSI window     : 40 <= RSI(14) <= 70  (avoid overbought/oversold)
    """
    # Need at least 250 bars for reliable indicators
    if len(df) < 250:
        return None

    close = df['Close']

    # ── Filter 1: Anti-Downfall ────────────────────────────────────────────
    roc_20 = (cmp - close.iloc[-21]) / close.iloc[-21]
    roc_40 = (cmp - close.iloc[-41]) / close.iloc[-41]
    if roc_20 <= 0 or roc_40 <= 0:
        return None

    # ── Filter 2: Trend Regime (Stage 2 Uptrend) ──────────────────────────
    sma_50  = close.rolling(50).mean().iloc[-1]
    sma_200 = close.rolling(200).mean().iloc[-1]
    if not (cmp > sma_50 > sma_200):
        return None

    # ── Filter 3: 52-Week Proximity ────────────────────────────────────────
    high_52w  = df['High'].iloc[-252:].max()
    dist_52w  = (cmp - high_52w) / high_52w  # negative value; floor = -0.15
    if dist_52w < -0.15:
        return None

    # ── Filter 4: Liquidity ─────────────────────────────────────────────────
    avg_vol_20 = df['Volume'].rolling(20).mean().iloc[-1]
    if avg_vol_20 < MIN_AVG_VOLUME:
        return None

    # ── Filter 5: RSI Guard ─────────────────────────────────────────────────
    rsi = compute_rsi(close)
    if not (40 <= rsi <= 70):
        return None

    # ── CMS Calculation ─────────────────────────────────────────────────────
    # Component A: 3-Month (60-day) ROC — weight 0.50
    roc_60 = ((cmp - close.iloc[-61]) / close.iloc[-61]) * 100

    # Component B: 52-Week Proximity Score (0–100, higher = closer to high) — weight 0.30
    prox_score = (1 - abs(dist_52w)) * 100

    # Component C: Volume Ratio — normalized to 0–100 range via sigmoid-like cap — weight 0.20
    # vol_ratio raw = 5-day mean / 50-day mean
    raw_vol_ratio = df['Volume'].iloc[-5:].mean() / df['Volume'].iloc[-50:].mean()
    # Cap at [0.5x, 3x] → rescale to 0–100
    vol_score = min(max((raw_vol_ratio - 0.5) / 2.5, 0), 1) * 100

    cms = (0.50 * roc_60) + (0.30 * prox_score) + (0.20 * vol_score)

    # ── ATR-based stop ──────────────────────────────────────────────────────
    atr = compute_atr(df)
    atr_stop = cmp - (2.0 * atr)           # 2x ATR below CMP
    fixed_stop = cmp * (1 - STOP_PCT)      # Traditional -7%
    # Use the tighter of the two (higher price = less risk)
    initial_stop = round(max(atr_stop, fixed_stop), 2)

    return {
        "roc_60": roc_60,
        "roc_20": roc_20,
        "roc_40": roc_40,
        "prox_score": prox_score,
        "vol_score": vol_score,
        "rsi": round(rsi, 1),
        "sma_50": round(sma_50, 2),
        "sma_200": round(sma_200, 2),
        "high_52w": round(high_52w, 2),
        "atr": round(atr, 2),
        "initial_stop": initial_stop,
        "cms": cms,
    }


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    symbols = get_nse_universe()

    print(f"[INFO] Downloading data for {len(symbols)} symbols…")
    # yfinance ≥ 0.2.x: use auto_adjust=True; group_by='ticker' for multi-ticker
    raw = yf.download(
        tickers=symbols,
        period="1y",
        interval="1d",
        group_by="ticker",
        auto_adjust=True,
        threads=True,
        progress=False,
    )

    candidates = []
    skipped    = 0

    for sym in symbols:
        try:
            # Multi-ticker download returns MultiIndex columns: (ticker, OHLCV)
            if isinstance(raw.columns, pd.MultiIndex):
                if sym not in raw.columns.get_level_values(0):
                    skipped += 1
                    continue
                df = raw[sym].dropna()
            else:
                # Single-ticker fallback (shouldn't normally happen)
                df = raw.dropna()

            if len(df) < 250:
                skipped += 1
                continue

            cmp = float(df['Close'].iloc[-1])
            if not (MIN_PRICE <= cmp <= MAX_PRICE):
                continue

            result = evaluate_ticker(df, cmp)
            if result is None:
                continue

            shares = int((CAPITAL_BASE - 25) // cmp)  # Reserve ₹25 buffer for taxes & DP charges
            if shares < 1:
                continue

            capital_used = round(shares * cmp, 2)

            candidates.append({
                "symbol"          : sym.replace(".NS", ""),
                "cmp"             : round(cmp, 2),
                "cms_score"       : round(result["cms"], 2),
                # ROC
                "roc_1m_pct"      : f"+{round(result['roc_20']*100, 2)}%",
                "roc_2m_pct"      : f"+{round(result['roc_40']*100, 2)}%",
                "roc_3m_pct"      : f"+{round(result['roc_60'], 2)}%",
                # Indicators
                "rsi_14"          : result["rsi"],
                "sma_50"          : result["sma_50"],
                "sma_200"         : result["sma_200"],
                "atr_14"          : result["atr"],
                "high_52w"        : result["high_52w"],
                # Position sizing
                "shares_to_buy"   : shares,
                "capital_required": capital_used,
                # GTT Levels
                "initial_stop"    : result["initial_stop"],       # Tighter of -7% or 2x ATR
                "m1_target"       : round(cmp * (1 + M1_PCT), 2), # +15%
                "m1_ratchet_stop" : round(cmp * (1 + M1_STOP), 2),# +2.5% after M1
                "m2_target"       : round(cmp * (1 + M2_PCT), 2), # +30%
                "m2_ratchet_stop" : round(cmp * (1 + M2_STOP), 2),# +15% after M2
                "m3_target"       : round(cmp * (1 + M3_PCT), 2), # +50% (trail via 20-DMA)
                "m3_trail_note"   : "Trail via 20-DMA or 2x ATR after M3 hit",
            })

        except Exception as exc:
            print(f"[WARN] {sym}: {exc}")
            continue

    print(f"[INFO] Screened {len(symbols)} symbols. Skipped {skipped}. Qualified: {len(candidates)}")

    os.makedirs("data/signals", exist_ok=True)
    now_iso = datetime.now(timezone.utc).isoformat()

    if not candidates:
        payload = {
            "status"   : "CASH",
            "timestamp": now_iso,
            "message"  : "Market breadth weak. Zero stocks passed all filters. Hold 100% Cash.",
        }
    else:
        candidates.sort(key=lambda x: x["cms_score"], reverse=True)
        winner    = candidates[0]
        top3      = candidates[:3]

        payload = {
            "status"             : "ACTIVE_SIGNAL",
            "timestamp"          : now_iso,
            "capital_base"       : CAPITAL_BASE,
            "total_qualified"    : len(candidates),
            "winner"             : winner,
            "top_3_alternates"   : top3,  # for manual override / fallback
        }

    out_file = "data/signals/latest.json"
    with open(out_file, "w") as f:
        json.dump(payload, f, indent=2)

    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
