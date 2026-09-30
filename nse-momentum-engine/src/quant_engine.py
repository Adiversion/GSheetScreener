#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
quant_engine.py — Serverless Quantitative Momentum Engine for Indian Equities
=============================================================================
Powered by DuckDB, Parquet, and GitHub Actions (100% Free, Zero Google Limits).

Strategy:
  - Mark Minervini SEPA Trend Template + Andreas Clenow Market Regime Filter
  - Regime Filter: Nifty 50 > 50-SMA and 200-SMA. If false -> 100% CASH preservation.
  - Stage-2 Filters: CMP > 50 SMA > 150 SMA > 200 SMA, 200 SMA rising 1M+,
                     within 25% of 52W High, > 30% above 52W Low, Vol >= 500k, 45 <= RSI <= 70.
  - Position Sizing: Dynamic capital base (₹1,000 to ₹100,000+)
  - Output: app/data/signal.json, app/data/screener.json, app/data/signal.csv
"""

import os
import sys
import json
import math
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
import yfinance as yf

# Windows console UTF-8 fix
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

IST = ZoneInfo("Asia/Kolkata")
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT_DIR, "data")
APP_DATA_DIR = os.path.join(ROOT_DIR, "app", "data")
PARQUET_FILE = os.path.join(DATA_DIR, "nse_history.parquet")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(APP_DATA_DIR, exist_ok=True)

# Broad high-volume NSE universe representing momentum pool across large, mid & small
UNIVERSE = [
    "TATAPOWER.NS", "BEL.NS", "BHEL.NS", "HAL.NS", "RECLTD.NS", "PFC.NS",
    "NTPC.NS", "POWERGRID.NS", "SUZLON.NS", "NHPC.NS", "SJVN.NS", "IREDA.NS",
    "MAZDOCK.NS", "COCHINSHIP.NS", "RVNL.NS", "IRFC.NS", "RAILTEL.NS", "TITAGARH.NS",
    "NMDC.NS", "SAIL.NS", "TATASTEEL.NS", "HINDALCO.NS", "JINDALSTEL.NS", "VEDL.NS",
    "COALINDIA.NS", "CANBK.NS", "PNB.NS", "BANKBARODA.NS", "FEDERALBNK.NS", "IDFCFIRSTB.NS",
    "TRENT.NS", "VBL.NS", "DIXON.NS", "POLYCAB.NS", "ASHOKLEY.NS",
    "PERSISTENT.NS", "KPITTECH.NS", "CHOLAFIN.NS", "EXIDEIND.NS", "AMBUJACEM.NS",
    "APOLLOTYRE.NS", "BHARTIARTL.NS", "INDHOTEL.NS", "OBEROIRLTY.NS", "MOTHERSON.NS",
    "KALYANKJIL.NS", "PRESTIGE.NS", "HUDCO.NS", "NBCC.NS", "IOB.NS", "UNIONBANK.NS"
]

# Risk & Capital parameters
DEFAULT_CAPITAL = 1000.0
MIN_PRICE = 100.0
BUFFER = 26.0
MIN_AVG_VOLUME = 500000
STOP_PCT = 0.07       # -7% Hard stop
M1_PCT = 0.15         # +15% Target
M1_STOP_PCT = 0.025   # +2.5% Breakeven floor
M2_PCT = 0.30         # +30% Target
M2_STOP_PCT = 0.15    # +15% Profit lock
M3_PCT = 0.50         # +50% Ultimate Target

def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    h, l, c = df["High"], df["Low"], df["Close"]
    pc = c.shift(1)
    tr = pd.concat([(h - l), (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.rolling(period).mean()

def load_or_update_parquet() -> pd.DataFrame:
    """Loads 2-year rolling daily history from Parquet or bootstraps it via yfinance."""
    print("=" * 65)
    print("🚀 QUANT ENGINE — DUCKDB & PARQUET DATA PIPELINE")
    print("=" * 65)

    dfs = []
    print(f"Syncing daily OHLCV for {len(UNIVERSE)} liquid symbols...")
    for sym in UNIVERSE:
        try:
            df = yf.download(sym, period="2y", interval="1d", progress=False)
            if df is not None and len(df) >= 150:
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                df = df.reset_index()
                # Normalize column names
                date_col = "Date" if "Date" in df.columns else df.columns[0]
                df["Date"] = pd.to_datetime(df[date_col]).dt.tz_localize(None)
                df["Symbol"] = sym.replace(".NS", "")
                df = df[["Date", "Symbol", "Open", "High", "Low", "Close", "Volume"]]
                dfs.append(df)
        except Exception as e:
            continue

    if not dfs:
        raise RuntimeError("Failed to fetch market data.")

    combined_df = pd.concat(dfs, ignore_index=True)
    # Save to Parquet with Snappy/ZSTD compression
    table = pa.Table.from_pandas(combined_df)
    pq.write_table(table, PARQUET_FILE, compression="zstd")
    print(f"✅ Stored {len(combined_df):,} rows in {os.path.basename(PARQUET_FILE)} ({os.path.getsize(PARQUET_FILE)/1024:.1f} KB)")
    return combined_df

def check_market_regime() -> dict:
    """Evaluates Nifty 50 benchmark to determine Bullish vs Defensive Cash regime."""
    print("\n🔍 EVALUATING BROAD MARKET REGIME (NIFTY 50)...")
    nifty = yf.download("^NSEI", period="1y", interval="1d", progress=False)
    if isinstance(nifty.columns, pd.MultiIndex):
        nifty.columns = nifty.columns.get_level_values(0)

    nifty["SMA50"] = nifty["Close"].rolling(50).mean()
    nifty["SMA200"] = nifty["Close"].rolling(200).mean()

    cmp = float(nifty["Close"].iloc[-1])
    sma50 = float(nifty["SMA50"].iloc[-1])
    sma200 = float(nifty["SMA200"].iloc[-1])

    is_bull = (cmp > sma50) and (cmp > sma200)
    is_caution = (cmp > sma200) and (cmp <= sma50)

    if is_bull:
        regime = "BULL_MARKET"
        description = "Nifty 50 in confirmed uptrend (Above 50 & 200 SMA). Aggressive momentum active."
    elif is_caution:
        regime = "CORRECTION_WATCH"
        description = "Nifty 50 in pullback (Above 200 SMA, Below 50 SMA). Selective Stage-2 entries only."
    else:
        regime = "DEFENSIVE_CASH"
        description = "Nifty 50 in bear/correction (Below 200 SMA). 100% Capital preserved in CASH."

    print(f"   • Nifty 50 CMP : {cmp:,.2f}")
    print(f"   • 50-Day SMA   : {sma50:,.2f} ({'+' if cmp >= sma50 else ''}{(cmp - sma50)/sma50*100:.2f}%)")
    print(f"   • 200-Day SMA  : {sma200:,.2f} ({'+' if cmp >= sma200 else ''}{(cmp - sma200)/sma200*100:.2f}%)")
    print(f"   • Regime State : {regime}")
    print(f"   • Status Note  : {description}")

    return {
        "regime": regime,
        "is_bull": is_bull,
        "is_caution": is_caution,
        "nifty_cmp": round(cmp, 2),
        "nifty_sma50": round(sma50, 2),
        "nifty_sma200": round(sma200, 2),
        "description": description
    }

def run_screener(capital: float = DEFAULT_CAPITAL):
    now_ist = datetime.now(IST).strftime("%Y-%m-%d %H:%M IST")
    max_price = capital - BUFFER

    # 1. Update / Load Parquet
    df_raw = load_or_update_parquet()

    # 2. Check Market Regime
    regime_info = check_market_regime()

    # 3. DuckDB SQL Analytical Processing
    con = duckdb.connect()
    con.register("raw_market", df_raw)

    print("\n⚡ RUNNING MINERVINI SEPA STAGE-2 SCREENER (DUCKDB)...")
    symbols = con.execute("SELECT DISTINCT Symbol FROM raw_market").fetchall()
    candidates = []

    for (sym,) in symbols:
        df_sym = con.execute(f"""
            SELECT Date, Open, High, Low, Close, Volume 
            FROM raw_market 
            WHERE Symbol = '{sym}' 
            ORDER BY Date ASC
        """).df()

        if len(df_sym) < 200:
            continue

        cmp = float(df_sym["Close"].iloc[-1])
        if not (MIN_PRICE <= cmp <= max_price):
            continue

        close = df_sym["Close"]
        sma50 = float(close.rolling(50).mean().iloc[-1])
        sma150 = float(close.rolling(150).mean().iloc[-1])
        sma200 = float(close.rolling(200).mean().iloc[-1])
        sma200_prev = float(close.rolling(200).mean().iloc[-22])

        # Minervini SEPA Condition 1: Stage-2 Alignment (CMP > 50 > 150 > 200)
        if not (cmp > sma50 > sma150 > sma200):
            continue

        # Minervini SEPA Condition 2: 200-SMA trending up for at least 1 month
        if sma200 <= sma200_prev:
            continue

        # Minervini SEPA Condition 3: Range Limits
        high52 = float(df_sym["High"].rolling(min(len(df_sym), 252)).max().iloc[-1])
        low52 = float(df_sym["Low"].rolling(min(len(df_sym), 252)).min().iloc[-1])

        dist52_high = (cmp - high52) / high52
        dist52_low = (cmp - low52) / low52

        # Within 25% of 52W High and at least 30% above 52W Low
        if dist52_high < -0.25 or dist52_low < 0.30:
            continue

        # Volume Floor
        vol20 = float(df_sym["Volume"].rolling(20).mean().iloc[-1])
        if vol20 < MIN_AVG_VOLUME:
            continue

        # RSI Guard
        rsi_series = compute_rsi(close)
        rsi_val = float(rsi_series.iloc[-1])
        if not (45 <= rsi_val <= 72):
            continue

        # Rate of Change
        roc_1m = ((cmp - close.iloc[-21]) / close.iloc[-21]) * 100
        roc_2m = ((cmp - close.iloc[-41]) / close.iloc[-41]) * 100
        roc_3m = ((cmp - close.iloc[-61]) / close.iloc[-61]) * 100

        # Anti-downfall check
        if roc_1m < -3.0 or roc_2m <= 0:
            continue

        # ATR & CMS Ranking
        atr_series = compute_atr(df_sym)
        atr_val = float(atr_series.iloc[-1])
        prox_score = (1 - abs(dist52_high)) * 100
        v5 = float(df_sym["Volume"].iloc[-5:].mean())
        v50 = float(df_sym["Volume"].iloc[-50:].mean())
        raw_vr = (v5 / v50) if v50 > 0 else 1.0
        vol_score = min(max((raw_vr - 0.5) / 2.5, 0), 1) * 100

        cms = 0.50 * roc_3m + 0.30 * prox_score + 0.20 * vol_score

        # Position Sizing
        shares = int((capital - BUFFER) // cmp)
        if shares < 1:
            continue

        init_stop = max(round(cmp * (1 - STOP_PCT), 2), round(cmp - 2 * atr_val, 2))
        m1 = round(cmp * (1 + M1_PCT), 2)
        m1_stop = round(cmp * (1 + M1_STOP_PCT), 2)
        m2 = round(cmp * (1 + M2_PCT), 2)
        m2_stop = round(cmp * (1 + M2_STOP_PCT), 2)
        m3 = round(cmp * (1 + M3_PCT), 2)

        candidates.append({
            "SYMBOL": sym,
            "CMP": round(cmp, 2),
            "CMS_SCORE": round(cms, 2),
            "ROC_1M": f"{roc_1m:+.2f}%",
            "ROC_2M": f"{roc_2m:+.2f}%",
            "ROC_3M": f"{roc_3m:+.2f}%",
            "RSI_14": round(rsi_val, 1),
            "SMA_50": round(sma50, 2),
            "SMA_150": round(sma150, 2),
            "SMA_200": round(sma200, 2),
            "ATR_14": round(atr_val, 2),
            "HIGH_52W": round(high52, 2),
            "LOW_52W": round(low52, 2),
            "SHARES": shares,
            "CAPITAL_REQUIRED": round(shares * cmp, 2),
            "INITIAL_STOP": init_stop,
            "M1_TARGET": m1,
            "M1_STOP": m1_stop,
            "M2_TARGET": m2,
            "M2_STOP": m2_stop,
            "M3_TARGET": m3,
            "CAPITAL_BASE": capital
        })

    # Sort by CMS descending
    candidates.sort(key=lambda x: x["CMS_SCORE"], reverse=True)
    total_qualified = len(candidates)
    print(f"✅ Found {total_qualified} institutional Stage-2 candidates.")

    # Apply Market Regime Gate
    if regime_info["regime"] == "DEFENSIVE_CASH":
        status = "CASH"
        signal_reason = f"Preserve 100% Cash: {regime_info['description']}"
    elif total_qualified == 0:
        status = "CASH"
        signal_reason = f"No stocks meet Minervini Stage-2 criteria under ₹{capital:,.2f}."
    else:
        status = "ACTIVE_SIGNAL"
        signal_reason = f"Stage-2 Momentum Breakout in confirmed Bull Market."

    # Build Signal Payload
    winner = candidates[0] if (status == "ACTIVE_SIGNAL" and candidates) else None
    alternates = candidates[1:4] if (status == "ACTIVE_SIGNAL" and len(candidates) > 1) else []

    signal_rows = []
    headers = [
        "STATUS", "TIMESTAMP", "SYMBOL", "CMP", "CMS_SCORE", "ROC_1M", "ROC_2M", "ROC_3M",
        "RSI_14", "SMA_50", "SMA_200", "ATR_14", "HIGH_52W", "SHARES", "CAPITAL_REQUIRED",
        "INITIAL_STOP", "M1_TARGET", "M1_STOP", "M2_TARGET", "M2_STOP", "M3_TARGET",
        "CAPITAL_BASE", "TOTAL_QUALIFIED"
    ]

    if status == "ACTIVE_SIGNAL" and winner:
        # Winner Row
        w_row = {col: winner.get(col, "") for col in headers}
        w_row["STATUS"] = "ACTIVE_SIGNAL"
        w_row["TIMESTAMP"] = now_ist
        w_row["TOTAL_QUALIFIED"] = total_qualified
        signal_rows.append(w_row)

        # Alternate Rows
        for alt in alternates:
            a_row = {col: alt.get(col, "") for col in headers}
            a_row["STATUS"] = "ALTERNATE"
            a_row["TIMESTAMP"] = now_ist
            a_row["TOTAL_QUALIFIED"] = total_qualified
            signal_rows.append(a_row)
    else:
        # Cash Row
        cash_row = {col: "—" for col in headers}
        cash_row["STATUS"] = "CASH"
        cash_row["TIMESTAMP"] = now_ist
        cash_row["CAPITAL_BASE"] = capital
        cash_row["TOTAL_QUALIFIED"] = total_qualified
        signal_rows.append(cash_row)

    # 4. Export JSON & CSV to app/data
    signal_json = {
        "status": status,
        "timestamp": now_ist,
        "capital_base": capital,
        "regime": regime_info,
        "reason": signal_reason,
        "total_qualified": total_qualified,
        "winner": winner,
        "alternates": alternates,
        "rows": signal_rows
    }

    json_path = os.path.join(APP_DATA_DIR, "signal.json")
    screener_path = os.path.join(APP_DATA_DIR, "screener.json")
    csv_path = os.path.join(APP_DATA_DIR, "signal.csv")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(signal_json, f, indent=2)

    with open(screener_path, "w", encoding="utf-8") as f:
        json.dump(candidates, f, indent=2)

    # Export CSV for optional Google Sheet =IMPORTDATA()
    df_sig = pd.DataFrame(signal_rows)
    df_sig.to_csv(csv_path, index=False)

    print("\n" + "=" * 65)
    print("📊  LIVE SCRENER OUTPUT REPORT")
    print("=" * 65)
    print(f"⏰ Timestamp       : {now_ist}")
    print(f"💰 Capital Base    : ₹{capital:,.2f}")
    print(f"🛡️ Market Regime   : {regime_info['regime']} ({regime_info['description']})")
    print(f"🎯 Final Signal    : {status}")

    if status == "ACTIVE_SIGNAL" and winner:
        print(f"\n🏆 WINNER: {winner['SYMBOL']} @ ₹{winner['CMP']}")
        print(f"   • Minervini Trend : CMP (₹{winner['CMP']}) > 50-SMA (₹{winner['SMA_50']}) > 200-SMA (₹{winner['SMA_200']})")
        print(f"   • CMS Score       : {winner['CMS_SCORE']} | RSI: {winner['RSI_14']} | ATR: ₹{winner['ATR_14']}")
        print(f"   • Position Sizing : Buy {winner['SHARES']} share(s) = ₹{winner['CAPITAL_REQUIRED']}")
        print(f"   • Hard Stop (-7%) : ₹{winner['INITIAL_STOP']}")
        print(f"   • M1 Target (+15%): ₹{winner['M1_TARGET']} (Ratchet stop to ₹{winner['M1_STOP']})")
        print(f"   • M2 Target (+30%): ₹{winner['M2_TARGET']} (Ratchet stop to ₹{winner['M2_STOP']})")
        print(f"   • M3 Target (+50%): ₹{winner['M3_TARGET']}")

        if alternates:
            print(f"\n📋 Alternates:")
            for idx, a in enumerate(alternates, 1):
                print(f"   {idx}. {a['SYMBOL']:12s} @ ₹{a['CMP']:7.2f} (CMS: {a['CMS_SCORE']}, RSI: {a['RSI_14']})")
    else:
        print(f"\n🛡️ HOLD CASH: {signal_reason}")

    print(f"\n📁 Static JSON API saved to: {json_path}")
    print(f"📁 Static CSV Feed saved to: {csv_path}")
    print("=" * 65)

if __name__ == "__main__":
    cap = DEFAULT_CAPITAL
    if len(sys.argv) > 1:
        try:
            cap = float(sys.argv[1])
        except ValueError:
            pass
    run_screener(cap)
