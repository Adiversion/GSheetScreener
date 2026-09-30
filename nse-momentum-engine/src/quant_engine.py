#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
quant_engine.py — 100% Dynamic Serverless Quant Engine for Indian Equities (NSE)
================================================================================
Zero hardcoded tickers. Downloads official NSE Bhavcopy dynamically every day.
Screens all 2,600+ equities for Minervini Stage-2 breakout momentum.
Outputs full universe to app/data/screener.json, app/data/signal.json,
and daily historical snapshots in app/data/history/{trade_date}.json.
"""

import os
import sys
import io
import math
import json
import zipfile
import argparse
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
import requests
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
HISTORY_DIR = os.path.join(APP_DATA_DIR, "history")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(APP_DATA_DIR, exist_ok=True)
os.makedirs(HISTORY_DIR, exist_ok=True)

STOP_PCT = 0.07       # -7% Hard stop
M1_PCT = 0.15         # +15% Target
M1_STOP_PCT = 0.025   # +2.5% Breakeven floor
M2_PCT = 0.30         # +30% Target
M2_STOP_PCT = 0.15    # +15% Profit lock
M3_PCT = 0.50         # +50% Ultimate Target
BUFFER = 26.0

def get_recent_trading_dates(limit=7):
    """Returns candidate trading dates backwards from today."""
    now = datetime.now(IST)
    dates = []
    for i in range(limit * 2):
        dt = now - timedelta(days=i)
        if dt.weekday() < 5:  # Skip Saturday (5) and Sunday (6)
            dates.append(dt)
            if len(dates) >= limit:
                break
    return dates

def download_nse_bhavcopy(target_date_str=None):
    """
    Downloads official NSE UDiFF Common Bhavcopy (.csv.zip) directly from archives.nseindia.com.
    Returns (DataFrame of all equities, trading_date_str, date_obj).
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "*/*",
        "Referer": "https://www.nseindia.com/"
    }

    if target_date_str:
        dt_target = datetime.strptime(target_date_str, "%Y-%m-%d").replace(tzinfo=IST)
        candidate_dates = [dt_target]
    else:
        candidate_dates = get_recent_trading_dates()

    for dt in candidate_dates:
        date_udiff = dt.strftime("%Y%m%d")
        url = f"https://archives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{date_udiff}_F_0000.csv.zip"
        try:
            r = requests.get(url, headers=headers, timeout=12)
            if r.status_code == 200 and len(r.content) > 50000:
                zf = zipfile.ZipFile(io.BytesIO(r.content))
                csv_name = zf.namelist()[0]
                df = pd.read_csv(zf.open(csv_name))
                # Filter EQ series (Equity delivery)
                df_eq = df[df["SctySrs"].astype(str).str.strip().str.upper() == "EQ"].copy()
                df_eq["CMP"] = pd.to_numeric(df_eq["ClsPric"], errors="coerce")
                df_eq["VOLUME"] = pd.to_numeric(df_eq["TtlTradgVol"], errors="coerce").fillna(0)
                df_eq["SYMBOL"] = df_eq["TckrSymb"].astype(str).str.strip().str.upper()
                df_eq = df_eq.dropna(subset=["CMP", "SYMBOL"])
                print(f"✅ Successfully loaded official NSE Bhavcopy for {dt.strftime('%d-%b-%Y')}")
                print(f"   • Total Active EQ Equities: {len(df_eq):,}")
                return df_eq, dt.strftime("%Y-%m-%d"), dt
        except Exception:
            continue

    raise RuntimeError(f"Could not download NSE Bhavcopy from archives. Target: {target_date_str or 'recent'}")

def get_nifty_regime():
    """Inspects Nifty 50 moving averages to provide market context."""
    try:
        nifty = yf.Ticker("^NSEI").history(period="1y")
        if len(nifty) >= 200:
            c = nifty["Close"]
            cmp = float(c.iloc[-1])
            sma50 = float(c.rolling(50).mean().iloc[-1])
            sma200 = float(c.rolling(200).mean().iloc[-1])
            if cmp > sma50 > sma200:
                return {
                    "regime": "BULL_MARKET",
                    "nifty_cmp": round(cmp, 2),
                    "sma_50": round(sma50, 2),
                    "sma_200": round(sma200, 2),
                    "description": "Nifty 50 in confirmed uptrend (Price > SMA50 > SMA200). Aggressive momentum active."
                }
            elif cmp > sma200:
                return {
                    "regime": "CORRECTION_WATCH",
                    "nifty_cmp": round(cmp, 2),
                    "sma_50": round(sma50, 2),
                    "sma_200": round(sma200, 2),
                    "description": "Nifty 50 consolidating above 200 SMA. Stage-2 breakout candidates active with -7% stop."
                }
            else:
                return {
                    "regime": "DEFENSIVE_CASH",
                    "nifty_cmp": round(cmp, 2),
                    "sma_50": round(sma50, 2),
                    "sma_200": round(sma200, 2),
                    "description": "Nifty 50 below 200 SMA. Broader market in correction; Stage-2 leaders protected by GTT stop."
                }
    except Exception as e:
        print(f"⚠️ Nifty regime lookup note: {e}")
    return {
        "regime": "NEUTRAL",
        "description": "Standard market regime. Minervini Stage-2 criteria applied."
    }

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

def run_screener(capital_override=None, target_date_str=None, is_latest=True):
    now_ist = datetime.now(IST).strftime("%Y-%m-%d %H:%M IST")
    today_str = datetime.now(IST).strftime("%Y-%m-%d")

    print("\n" + "=" * 65)
    print(f"📡 SCREENING NSE EQUITIES — TARGET DATE: {target_date_str or 'LATEST'}")
    print("=" * 65)

    # 1. Download official NSE Bhavcopy
    df_bhav, trade_date, dt_obj = download_nse_bhavcopy(target_date_str)
    is_today = (trade_date == today_str)
    bhavcopy_status = "CURRENT_SESSION" if is_today else "PREVIOUS_SESSION_FALLBACK"

    # 2. Filter liquid active equities (Price >= ₹50, Volume >= 300,000)
    cands_df = df_bhav[(df_bhav["CMP"] >= 50.0) & (df_bhav["VOLUME"] >= 300000)].copy()
    dynamic_symbols = cands_df.head(200)["SYMBOL"].unique().tolist()
    print(f"🔍 Discovered {len(dynamic_symbols)} high-volume liquid equities across entire NSE.")

    # 3. Batch fetch 1-year historical daily bars in parallel threads
    tickers = [f"{s}.NS" for s in dynamic_symbols]
    print(f"⚡ Batch downloading historical data for {len(tickers)} symbols via multi-threading...")
    batch_data = yf.download(tickers, period="1y", interval="1d", progress=False, group_by="ticker", threads=True)

    qualified_stocks = []

    for sym in dynamic_symbols:
        tick = f"{sym}.NS"
        if tick not in batch_data:
            continue
        df_s = batch_data[tick].dropna(subset=["Close"])
        if len(df_s) < 180:
            continue

        c = df_s["Close"]
        cmp = float(c.iloc[-1])
        if cmp <= 0 or math.isnan(cmp):
            continue

        sma50 = float(c.rolling(50).mean().iloc[-1])
        sma150 = float(c.rolling(150).mean().iloc[-1])
        sma200 = float(c.rolling(200).mean().iloc[-1])
        sma200_prev = float(c.rolling(200).mean().iloc[-22])

        # Minervini Stage 2 Rule 1: Price > 50 SMA > 150 SMA > 200 SMA
        if not (cmp > sma50 > sma150 > sma200):
            continue

        # Minervini Stage 2 Rule 2: 200 SMA trending up for at least 1 month
        if sma200 <= sma200_prev:
            continue

        # Minervini Stage 2 Rule 3: 52W Range Bounds
        h52 = float(df_s["High"].rolling(min(len(df_s), 252)).max().iloc[-1])
        l52 = float(df_s["Low"].rolling(min(len(df_s), 252)).min().iloc[-1])
        dist52_high = (cmp - h52) / h52
        dist52_low = (cmp - l52) / l52

        # Within 25% of 52W High and at least 30% above 52W Low
        if dist52_high < -0.25 or dist52_low < 0.30:
            continue

        # RSI Sweet Zone (45 to 75)
        rsi_series = compute_rsi(c)
        rsi_val = float(rsi_series.iloc[-1])
        if not (45 <= rsi_val <= 75):
            continue

        # ROC Anti-Downfall
        roc_1m = ((cmp - c.iloc[-21]) / c.iloc[-21]) * 100
        roc_2m = ((cmp - c.iloc[-41]) / c.iloc[-41]) * 100
        roc_3m = ((cmp - c.iloc[-60]) / c.iloc[-60]) * 100

        if roc_1m < -3.0 or roc_2m <= 0:
            continue

        # ATR & CMS Ranking
        atr_series = compute_atr(df_s)
        atr_val = float(atr_series.iloc[-1])
        prox_score = (1 - abs(dist52_high)) * 100
        cms = 0.60 * roc_3m + 0.40 * prox_score

        # Institutional Quality Metrics
        dist_50 = ((cmp - sma50) / sma50) * 100
        atr_pct = (atr_val / cmp) * 100
        vol_20 = float(df_s["Volume"].tail(20).mean())
        vol_latest = float(df_s["Volume"].iloc[-1])
        vol_ratio = round(vol_latest / vol_20, 2) if vol_20 > 0 else 1.0

        # Mark Minervini Extension & Volatility Rule (Leak-Proof Guard)
        is_prime = (dist_50 <= 25.0) and (atr_pct <= 5.0)
        setup_quality = "PRIME_LOW_RISK" if is_prime else ("OVER_EXTENDED" if dist_50 > 25.0 else "HIGH_VOLATILITY")

        # GTT Calculation
        init_stop = max(round(cmp * (1 - STOP_PCT), 2), round(cmp - 2 * atr_val, 2))
        m1 = round(cmp * (1 + M1_PCT), 2)
        m1_stop = round(cmp * (1 + M1_STOP_PCT), 2)
        m2 = round(cmp * (1 + M2_PCT), 2)
        m2_stop = round(cmp * (1 + M2_STOP_PCT), 2)
        m3 = round(cmp * (1 + M3_PCT), 2)

        qualified_stocks.append({
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
            "ATR_PCT": round(atr_pct, 1),
            "DIST_50SMA": round(dist_50, 1),
            "VOL_RATIO": vol_ratio,
            "IS_PRIME": is_prime,
            "SETUP_QUALITY": setup_quality,
            "HIGH_52W": round(h52, 2),
            "LOW_52W": round(l52, 2),
            "INITIAL_STOP": init_stop,
            "M1_TARGET": m1,
            "M1_STOP": m1_stop,
            "M2_TARGET": m2,
            "M2_STOP": m2_stop,
            "M3_TARGET": m3
        })

    # Sort: Prime low-risk setups first, then sorted by CMS descending
    qualified_stocks.sort(key=lambda x: (x["IS_PRIME"], x["CMS_SCORE"]), reverse=True)
    total_qualified = len(qualified_stocks)
    print(f"\n🏆 STAGE-2 QUALIFIED MOMENTUM LEADERS ACROSS ENTIRE NSE: {total_qualified}")

    # Capital base
    capital_default = float(capital_override) if capital_override else 1000.0
    cands_under_default = [s for s in qualified_stocks if s["CMP"] <= (capital_default - BUFFER)]
    winner = cands_under_default[0] if cands_under_default else (qualified_stocks[0] if qualified_stocks else None)
    alternates = cands_under_default[1:4] if len(cands_under_default) > 1 else qualified_stocks[1:4]

    status = "ACTIVE_SIGNAL" if winner else "CASH"

    # Add sizing to winner
    if winner:
        shares = int((capital_default - BUFFER) // winner["CMP"])
        winner_sized = dict(winner)
        winner_sized["SHARES"] = max(shares, 1)
        winner_sized["CAPITAL_REQUIRED"] = round(winner_sized["SHARES"] * winner["CMP"], 2)
        winner_sized["CAPITAL_BASE"] = capital_default
    else:
        winner_sized = None

    headers = [
        "STATUS", "TIMESTAMP", "SYMBOL", "CMP", "CMS_SCORE", "ROC_1M", "ROC_2M", "ROC_3M",
        "RSI_14", "SMA_50", "SMA_200", "ATR_14", "HIGH_52W", "SHARES", "CAPITAL_REQUIRED",
        "INITIAL_STOP", "M1_TARGET", "M1_STOP", "M2_TARGET", "M2_STOP", "M3_TARGET",
        "CAPITAL_BASE", "TOTAL_QUALIFIED"
    ]

    signal_rows = []
    if status == "ACTIVE_SIGNAL" and winner_sized:
        w_row = {col: winner_sized.get(col, "") for col in headers}
        w_row["STATUS"] = "ACTIVE_SIGNAL"
        w_row["TIMESTAMP"] = now_ist
        w_row["TOTAL_QUALIFIED"] = total_qualified
        signal_rows.append(w_row)
        for alt in alternates:
            alt_sized = dict(alt)
            alt_sized["SHARES"] = max(int((capital_default - BUFFER) // alt["CMP"]), 1)
            alt_sized["CAPITAL_REQUIRED"] = round(alt_sized["SHARES"] * alt["CMP"], 2)
            alt_sized["CAPITAL_BASE"] = capital_default
            a_row = {col: alt_sized.get(col, "") for col in headers}
            a_row["STATUS"] = "ALTERNATE"
            a_row["TIMESTAMP"] = now_ist
            a_row["TOTAL_QUALIFIED"] = total_qualified
            signal_rows.append(a_row)
    else:
        cash_row = {col: "—" for col in headers}
        cash_row["STATUS"] = "CASH"
        cash_row["TIMESTAMP"] = now_ist
        cash_row["CAPITAL_BASE"] = capital_default
        cash_row["TOTAL_QUALIFIED"] = total_qualified
        signal_rows.append(cash_row)

    # Market regime
    regime_info = get_nifty_regime()

    # Build Signal Payload
    signal_payload = {
        "status": status,
        "timestamp": now_ist,
        "trade_date": trade_date,
        "trade_date_display": dt_obj.strftime("%d-%b-%Y"),
        "is_today": is_today,
        "bhavcopy_status": bhavcopy_status,
        "capital_base": capital_default,
        "total_qualified": total_qualified,
        "regime": regime_info,
        "winner": winner_sized,
        "alternates": alternates,
        "rows": signal_rows,
        "all_qualified": qualified_stocks
    }

    # Save daily history snapshot
    history_file = os.path.join(HISTORY_DIR, f"{trade_date}.json")
    with open(history_file, "w", encoding="utf-8") as f:
        json.dump(signal_payload, f, indent=2)
    print(f"📦 Saved historical snapshot: {history_file}")

    # Maintain history manifest
    manifest_path = os.path.join(HISTORY_DIR, "manifest.json")
    manifest = []
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
        except Exception:
            manifest = []

    manifest = [m for m in manifest if m.get("date") != trade_date]
    manifest.append({
        "date": trade_date,
        "display_date": dt_obj.strftime("%d %b %Y"),
        "is_today": is_today,
        "winner": winner_sized["SYMBOL"] if winner_sized else "CASH",
        "cmp": winner_sized["CMP"] if winner_sized else 0,
        "cms": winner_sized["CMS_SCORE"] if winner_sized else 0,
        "total_qualified": total_qualified
    })
    manifest = sorted(manifest, key=lambda x: x["date"], reverse=True)
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    signal_payload["history_manifest"] = manifest

    if is_latest:
        screener_payload = {
            "timestamp": now_ist,
            "trade_date": trade_date,
            "total_screened": len(dynamic_symbols),
            "total_qualified": total_qualified,
            "stocks": qualified_stocks
        }
        screener_path = os.path.join(APP_DATA_DIR, "screener.json")
        with open(screener_path, "w", encoding="utf-8") as f:
            json.dump(screener_payload, f, indent=2)

        signal_json_path = os.path.join(APP_DATA_DIR, "signal.json")
        signal_csv_path = os.path.join(APP_DATA_DIR, "signal.csv")

        with open(signal_json_path, "w", encoding="utf-8") as f:
            json.dump(signal_payload, f, indent=2)

        df_csv = pd.DataFrame(signal_rows)
        df_csv.to_csv(signal_csv_path, index=False)

        print(f"✅ Generated master screener dataset: {screener_path}")
        print(f"✅ Generated live signal API: {signal_json_path}")
        print(f"✅ Generated CSV feed: {signal_csv_path}")

    print("\n" + "=" * 65)
    print(f"🎯  TOP BREAKOUT MOMENTUM LEADERS FOR {dt_obj.strftime('%d-%b-%Y')}:")
    print("=" * 65)
    for idx, s in enumerate(qualified_stocks[:10], 1):
        print(f"{idx:2d}. {s['SYMBOL']:12s} | CMP: ₹{s['CMP']:7.2f} | CMS: {s['CMS_SCORE']:5.1f} | RSI: {s['RSI_14']:4.1f} | Stop: ₹{s['INITIAL_STOP']:7.2f} | M1: ₹{s['M1_TARGET']:7.2f}")
    print("=" * 65)

    return signal_payload

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NSE Momentum Quant Engine")
    parser.add_argument("capital", nargs="?", default="1000", help="Capital base (default 1000)")
    parser.add_argument("--date", help="Specific trade date (YYYY-MM-DD)")
    parser.add_argument("--backfill", type=int, default=0, help="Number of previous trading days to backfill into history")
    args = parser.parse_args()

    cap = float(args.capital) if args.capital else 1000.0

    if args.date:
        run_screener(capital_override=cap, target_date_str=args.date, is_latest=False)
    else:
        # Run latest (today)
        run_screener(capital_override=cap, is_latest=True)

        # Backfill previous trading days if requested
        if args.backfill > 0:
            dates = get_recent_trading_dates(limit=args.backfill + 2)
            # dates[0] is latest; backfill the older dates
            for dt in dates[1:1 + args.backfill]:
                dt_str = dt.strftime("%Y-%m-%d")
                print(f"\n⏳ Backfilling historical screener for {dt_str}...")
                try:
                    run_screener(capital_override=cap, target_date_str=dt_str, is_latest=False)
                except Exception as e:
                    print(f"⚠️ Failed backfill for {dt_str}: {e}")
