#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
quant_engine.py — Institutional Quant Engine V2 for Indian Equities (NSE)
========================================================================
Implements:
  1. 100% Dynamic NSE Bhavcopy ingestion across all 2,600+ equities.
  2. Institutional Liquidity Filter (20-day average turnover >= ₹5.0 Crore).
  3. Official NSE Circuit Band Awareness (2% and 5% circuit band disqualification).
  4. Nifty 500 Macro Regime Governor (^CRSLDX) with Defensive Cash capital preservation.
  5. Cross-Sectional Percentile Normalized CMS Scoring (0.60 * ROC_3M_Pctile + 0.40 * Prox_Pctile).
  6. Power Breakout RSI sweet zone (45 <= RSI <= 82) and ATR volatility ceiling (<= 6.5%).
  7. Two-Tier Profit Booking & Uncapped Multibagger Trailing State Machine via TradeLifecycleManager:
       - Initial Stop (-5% to -7% ATR-based, tightened to -4% in defensive regimes).
       - M1: Risk-Free (+15%, stop at +1.5% Breakeven buffer).
       - M2: Bank & Trail (+22%, bank 40% at >= 3R, ratchet 60% runner stop to +10%).
       - M3: Power Runner (> +25% unconstrained, dynamically trailed on 50 SMA / 20 EMA / Blow-off).
  8. Synchronizes output with app/data/screener.json, app/data/signal.json, and app/data/signal.csv.
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

# Ensure local module directory is in path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from trade_lifecycle import (
    TradeLifecycleManager,
    TradeState,
    MacroRegime,
    ExitReason,
    OrderAction,
    MarketBar,
    Position,
    calculate_theoretical_skewness_edge
)
from momentum_quality import evaluate_institutional_quality
from failure_to_fail import compute_failure_to_fail


IST = ZoneInfo("Asia/Kolkata")
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT_DIR, "data")
APP_DATA_DIR = os.path.join(ROOT_DIR, "app", "data")
HISTORY_DIR = os.path.join(APP_DATA_DIR, "history")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(APP_DATA_DIR, exist_ok=True)
os.makedirs(HISTORY_DIR, exist_ok=True)

# ─── PARAMETERS ──────────────────────────────────────────────────────────────
MIN_TURNOVER_FLOOR = 50000000.0          # ₹5.0 Crore minimum average daily turnover
MAX_TURNOVER_PARTICIPATION = 0.015       # Max 1.5% turnover participation
MAX_POSITION_EXPOSURE = 0.15             # Max 15% portfolio equity per position
PORTFOLIO_RISK_PCT = 0.01                # 1% portfolio risk model ($R = Portfolio * 0.01)

# Asymmetric Two-Tier Profit Targets
M1_PCT = 0.15                            # +15% Target (State 1: RISK_FREE)
M1_STOP_BE_BUFFER = 0.015                # +1.5% Breakeven floor covering STT, turnover charges, taxes
M2_PCT = 0.22                            # +22% Target (State 2: BANK_AND_TRAIL, Bank 40% at >= 3R)
M2_RUNNER_STOP = 0.10                    # +10% Profit lock floor on remaining 60% runner
M3_REF_PCT = 0.50                        # +50% Reference milestone (State 3: POWER_RUNNER unconstrained)
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
                df_eq["TURNOVER"] = pd.to_numeric(df_eq["TtlTrfVal"], errors="coerce").fillna(0)
                df_eq["PREV_CLOSE"] = pd.to_numeric(df_eq["PrvsClsgPric"], errors="coerce").fillna(df_eq["CMP"])
                df_eq["SYMBOL"] = df_eq["TckrSymb"].astype(str).str.strip().str.upper()
                df_eq = df_eq.dropna(subset=["CMP", "SYMBOL"])
                print(f"✅ Successfully loaded official NSE Bhavcopy for {dt.strftime('%d-%b-%Y')}")
                print(f"   • Total Active EQ Equities: {len(df_eq):,}")
                return df_eq, dt.strftime("%Y-%m-%d"), dt
        except Exception:
            continue

    raise RuntimeError(f"Could not download NSE Bhavcopy from archives. Target: {target_date_str or 'recent'}")


def download_nse_circuit_bands():
    """
    Downloads official NSE price band & security list from archives.nseindia.com.
    Returns mapping of symbol -> circuit_band_str (e.g. '2', '5', '10', '20', 'No Band').
    """
    url = "https://archives.nseindia.com/content/equities/sec_list.csv"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "*/*",
        "Referer": "https://www.nseindia.com/"
    }
    bands = {}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200 and len(r.content) > 10000:
            df = pd.read_csv(io.StringIO(r.text))
            sym_col = next((c for c in df.columns if "symbol" in c.lower()), "Symbol")
            band_col = next((c for c in df.columns if "band" in c.lower()), "Band")
            for _, row in df.iterrows():
                s = str(row[sym_col]).strip().upper()
                b = str(row[band_col]).strip()
                bands[s] = b
            print(f"📋 Loaded official NSE price bands for {len(bands):,} securities.")
    except Exception as e:
        print(f"⚠️ Note on loading NSE price band list: {e}")
    return bands


def get_nifty_regime():
    """
    Inspects Nifty 500 (^CRSLDX) moving averages to provide institutional market breadth context.
    Falls back to Nifty 50 (^NSEI) if ^CRSLDX is unreachable.
    When benchmark < SMA200, triggers DEFENSIVE_CASH regime:
      - Forbids all new entries
      - Tightens existing State 0 stops from -7% to -4%
      - Preserves cash
    """
    for ticker_symbol, display_name in [("^CRSLDX", "Nifty 500"), ("^NSEI", "Nifty 50")]:
        try:
            nifty = yf.Ticker(ticker_symbol).history(period="1y")
            if len(nifty) >= 200:
                c = nifty["Close"]
                cmp = float(c.iloc[-1])
                sma50 = float(c.rolling(50).mean().iloc[-1])
                sma200 = float(c.rolling(200).mean().iloc[-1])
                if cmp > sma50 > sma200:
                    return {
                        "benchmark": display_name,
                        "ticker": ticker_symbol,
                        "regime": "BULL_MARKET",
                        "nifty_cmp": round(cmp, 2),
                        "sma_50": round(sma50, 2),
                        "sma_200": round(sma200, 2),
                        "allow_new_entries": True,
                        "state_0_stop_pct": 0.07,
                        "description": f"{display_name} in confirmed uptrend (Price > SMA50 > SMA200). Aggressive momentum active."
                    }
                elif cmp > sma200:
                    return {
                        "benchmark": display_name,
                        "ticker": ticker_symbol,
                        "regime": "CORRECTION_WATCH",
                        "nifty_cmp": round(cmp, 2),
                        "sma_50": round(sma50, 2),
                        "sma_200": round(sma200, 2),
                        "allow_new_entries": True,
                        "state_0_stop_pct": 0.07,
                        "description": f"{display_name} consolidating above 200 SMA. Stage-2 breakout candidates active with dynamic stops."
                    }
                else:
                    return {
                        "benchmark": display_name,
                        "ticker": ticker_symbol,
                        "regime": "DEFENSIVE_CASH",
                        "nifty_cmp": round(cmp, 2),
                        "sma_50": round(sma50, 2),
                        "sma_200": round(sma200, 2),
                        "allow_new_entries": False,
                        "state_0_stop_pct": 0.04,
                        "description": f"{display_name} below 200 SMA. Macro regime is DEFENSIVE_CASH; new entries forbidden, State 0 stops tightened to -4%."
                    }
        except Exception as e:
            print(f"⚠️ {display_name} lookup note ({ticker_symbol}): {e}")
            continue

    return {
        "benchmark": "Nifty 500",
        "ticker": "^CRSLDX",
        "regime": "BULL_MARKET",
        "allow_new_entries": True,
        "state_0_stop_pct": 0.07,
        "description": "Standard market regime fallback. Minervini Stage-2 criteria applied."
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
    print(f"📡 INSTITUTIONAL QUANT ENGINE V2 — TARGET DATE: {target_date_str or 'LATEST'}")
    print("=" * 65)

    # 1. Download official NSE Bhavcopy
    df_bhav, trade_date, dt_obj = download_nse_bhavcopy(target_date_str)
    is_today = (trade_date == today_str)
    bhavcopy_status = "CURRENT_SESSION" if is_today else ("LATEST_CONFIRMED" if is_latest else "HISTORICAL_ARCHIVE")

    # 2. Download official NSE Circuit Bands
    circuit_bands = download_nse_circuit_bands()

    # 3. Fetch Macro Regime via Nifty 500
    regime_info = get_nifty_regime()
    macro_regime_enum = (
        MacroRegime.DEFENSIVE_CASH if regime_info["regime"] == "DEFENSIVE_CASH"
        else (MacroRegime.CORRECTION_WATCH if regime_info["regime"] == "CORRECTION_WATCH"
              else MacroRegime.BULL_MARKET)
    )
    print(f"🌐 Macro Regime: {regime_info['benchmark']} -> {regime_info['regime']} (Allow Buys: {regime_info['allow_new_entries']})")

    # 4. Filter liquid active equities:
    # CMP >= ₹50, Volume >= 100,000, Single-day Turnover >= ₹2.0 Cr for broad pool;
    # 20-day average daily turnover will strictly enforce >= ₹5.0 Cr.
    # Exclude 2% and 5% circuit bands from initial entry to prevent lower-circuit lockups.
    cands_df = df_bhav[
        (df_bhav["CMP"] >= 50.0) & 
        (df_bhav["VOLUME"] >= 100000) &
        (df_bhav["TURNOVER"] >= 20000000.0)
    ].copy()

    # Filter out 2% and 5% circuit bands
    def is_narrow_circuit_band(sym):
        b = str(circuit_bands.get(sym, "")).strip()
        return b in ("2", "5", "0.02", "0.05")

    cands_df = cands_df[~cands_df["SYMBOL"].apply(is_narrow_circuit_band)].copy()
    cands_df = cands_df.sort_values(by="TURNOVER", ascending=False)
    dynamic_symbols = cands_df.head(500)["SYMBOL"].unique().tolist()
    print(f"🔍 Discovered {len(dynamic_symbols)} high-liquidity, non-circuit-locked active equities.")

    # 5. Batch fetch 1-year historical daily bars
    tickers = [f"{s}.NS" for s in dynamic_symbols]
    print(f"⚡ Batch downloading historical daily data for {len(tickers)} symbols...")
    batch_data = yf.download(tickers, period="1y", interval="1d", progress=False, group_by="ticker", threads=True)

    # 6. Initialize TradeLifecycleManager
    capital_default = float(capital_override) if capital_override else 1000.0
    # Portfolio equity reference for institutional sizing: use user capital or default ₹100k
    equity_reference = max(capital_default, 100000.0)
    lifecycle_mgr = TradeLifecycleManager(
        portfolio_equity=equity_reference,
        risk_per_trade_pct=PORTFOLIO_RISK_PCT,
        max_exposure_pct=MAX_POSITION_EXPOSURE,
        max_turnover_participation=MAX_TURNOVER_PARTICIPATION,
        min_turnover_floor=MIN_TURNOVER_FLOOR,
        be_buffer_pct=M1_STOP_BE_BUFFER,
        partial_bank_pct=0.40,
        runner_stop_floor_pct=M2_RUNNER_STOP
    )

    stage2_candidates = []

    # Calculate Universe 12-Month Performance & Relative Strength (RS Rating 0-99)
    perf_12m = {}
    for sym in dynamic_symbols:
        tick = f"{sym}.NS"
        if tick in batch_data:
            df_sym = batch_data[tick].dropna(subset=["Close"])
            if len(df_sym) >= 120:
                p_curr = float(df_sym["Close"].iloc[-1])
                p_past = float(df_sym["Close"].iloc[-min(len(df_sym), 250)])
                if p_past > 0:
                    perf_12m[sym] = (p_curr / p_past - 1.0) * 100.0

    rs_ratings = {}
    if perf_12m:
        s_perf = pd.Series(perf_12m)
        s_rank = (s_perf.rank(pct=True) * 99.0).round(1)
        rs_ratings = s_rank.to_dict()

    for sym in dynamic_symbols:
        tick = f"{sym}.NS"
        if tick not in batch_data:
            continue
        df_s = batch_data[tick].dropna(subset=["Close"])
        if trade_date:
            df_s = df_s[df_s.index <= pd.Timestamp(trade_date)]
        if len(df_s) < 180:
            continue

        c = df_s["Close"]
        cmp = float(c.iloc[-1])
        if cmp <= 0 or math.isnan(cmp):
            continue

        # Liquidity Check: 20-day Average Daily Turnover >= ₹5.0 Crore
        turnover_20d = float((df_s["Close"] * df_s["Volume"]).tail(20).mean())
        if turnover_20d < MIN_TURNOVER_FLOOR:
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

        # RSI Sweet Zone: Power Trends Allowed up to 82 (45 <= RSI <= 82)
        rsi_series = compute_rsi(c)
        rsi_val = float(rsi_series.iloc[-1])
        if not (45.0 <= rsi_val <= 82.0):
            continue

        # ROC Anti-Downfall
        roc_1m = ((cmp - c.iloc[-21]) / c.iloc[-21]) * 100
        roc_2m = ((cmp - c.iloc[-41]) / c.iloc[-41]) * 100
        roc_3m = ((cmp - c.iloc[-60]) / c.iloc[-60]) * 100

        if roc_1m < -3.0 or roc_2m <= 0:
            continue

        atr_series = compute_atr(df_s)
        atr_val = float(atr_series.iloc[-1])

        # Metrics for percentile CMS and quality
        dist_50 = ((cmp - sma50) / sma50) * 100
        atr_pct = (atr_val / cmp) * 100
        vol_20 = float(df_s["Volume"].tail(20).mean())
        vol_latest = float(df_s["Volume"].iloc[-1])
        vol_ratio = round(vol_latest / vol_20, 2) if vol_20 > 0 else 1.0

        # ATR Volatility Ceiling: Expanded to 6.5% for Midcap Breakout Fit
        is_prime = (dist_50 <= 25.0) and (atr_pct <= 6.5)
        setup_quality = "PRIME_LOW_RISK" if is_prime else ("OVER_EXTENDED" if dist_50 > 25.0 else "HIGH_VOLATILITY")

        # Evaluate Institutional Quality (Volume Surge, VCP Coiling, Frog-in-the-Pan Smoothness)
        inst_quality = evaluate_institutional_quality(df_s)
        ftf_state = compute_failure_to_fail(df_s, high_52w=h52)

        # Circuit band metadata
        band_raw = circuit_bands.get(sym, "Dynamic")
        band_pct_val = None
        if band_raw in ("10", "20"):
            band_pct_val = float(band_raw) / 100.0

        # Calculate Lower Circuit and check proximity
        prev_row = df_bhav[df_bhav["SYMBOL"] == sym]
        prev_close = float(prev_row["PREV_CLOSE"].iloc[0]) if len(prev_row) > 0 else cmp
        lower_circuit = round(prev_close * (1.0 - band_pct_val), 2) if band_pct_val else None
        upper_circuit = round(prev_close * (1.0 + band_pct_val), 2) if band_pct_val else None

        circuit_diag = lifecycle_mgr.check_liquidity_and_circuit(
            cmp=cmp,
            turnover_20d=turnover_20d,
            circuit_band_pct=band_pct_val,
            lower_circuit=lower_circuit,
            upper_circuit=upper_circuit,
            is_fno=(band_raw.lower() == "no band")
        )

        stage2_candidates.append({
            "SYMBOL": sym,
            "CMP": round(cmp, 2),
            "HIGH_52W": round(h52, 2),
            "LOW_52W": round(l52, 2),
            "ROC_1M": roc_1m,
            "ROC_2M": roc_2m,
            "ROC_3M": roc_3m,
            "RSI_14": round(rsi_val, 1),
            "SMA_50": round(sma50, 2),
            "SMA_150": round(sma150, 2),
            "SMA_200": round(sma200, 2),
            "ATR_14": round(atr_val, 2),
            "ATR_PCT": round(atr_pct, 1),
            "DIST_50SMA": round(dist_50, 1),
            "VOL_RATIO": vol_ratio,
            "TURNOVER_20D": turnover_20d,
            "TURNOVER_CRORES": round(turnover_20d / 10000000.0, 2),
            "CIRCUIT_BAND": band_raw,
            "LOWER_CIRCUIT": lower_circuit,
            "UPPER_CIRCUIT": upper_circuit,
            "CIRCUIT_DIAG": circuit_diag,
            "IS_PRIME": is_prime,
            "SETUP_QUALITY": setup_quality,
            "AQS_SCORE": inst_quality["quality_score"],
            "AQS_GRADE": inst_quality["grade"],
            "IS_TRAP_VETO": inst_quality["is_trap_veto"],
            "CLOSING_RANGE": inst_quality["closing_range"],
            "CR_STATUS": inst_quality["cr_status"],
            "UP_DOWN_VOL": inst_quality["up_down_vol_ratio"],
            "UD_STATUS": inst_quality["ud_status"],
            "VDU_RATIO": inst_quality["vdu_ratio"],
            "VDU_STATUS": inst_quality["vdu_status"],
            "RS_12M": rs_ratings.get(sym, 50.0),
            "INSTITUTIONAL_GRADE": inst_quality["grade"],
            "INSTITUTIONAL_SCORE": inst_quality["quality_score"],
            "VCP_RATIO": inst_quality["vcp_ratio"],
            "VCP_STATUS": inst_quality["vcp_status"],
            "VOL_SURGE_RATIO": inst_quality["vol_ratio"],
            "VOL_STATUS": inst_quality["vol_status"],
            "FIP_SMOOTHNESS": inst_quality["fip_smoothness_pct"],
            "FIP_STATUS": inst_quality["fip_status"],
            "INSTITUTIONAL_WARNINGS": inst_quality["warnings"],
            "IS_INSTITUTIONAL": inst_quality["is_institutional_grade"],
            "FTF_STATE": ftf_state["state"],
            "FTF_TRIGGER": ftf_state.get("trigger_guidance"),
            "FTF_DIAGNOSTIC": ftf_state.get("diagnostic"),
            "PIVOT_RESISTANCE": ftf_state.get("pivot_resistance"),
            "DOWNSIDE_FLOOR": ftf_state.get("downside_floor"),
            "FLOOR_STATUS": ftf_state.get("floor_status", "INTACT"),
        })

    # 7. Cross-Sectional Percentile Normalization for CMS Score
    qualified_stocks = []
    if stage2_candidates:
        df_cands = pd.DataFrame(stage2_candidates)
        df_cands["ROC_3M_PCTILE"] = df_cands["ROC_3M"].rank(pct=True) * 100.0
        df_cands["PROX_PCTILE"] = (df_cands["CMP"] / df_cands["HIGH_52W"]).rank(pct=True) * 100.0
        df_cands["CMS_SCORE"] = round(0.60 * df_cands["ROC_3M_PCTILE"] + 0.40 * df_cands["PROX_PCTILE"], 1)

        for _, row in df_cands.iterrows():
            sym = row["SYMBOL"]
            cmp = row["CMP"]
            atr_val = row["ATR_14"]
            turnover_20d = row["TURNOVER_20D"]

            # Calculate Initial Stop & Sizing using TradeLifecycleManager
            shares, init_stop, stop_dist_pct, size_meta = lifecycle_mgr.calculate_initial_risk_and_size(
                cmp=cmp,
                atr_14=atr_val,
                turnover_20d=turnover_20d,
                regime=macro_regime_enum,
                circuit_band_pct=float(row["CIRCUIT_BAND"]) / 100.0 if str(row["CIRCUIT_BAND"]).isdigit() else None,
                is_fno=(str(row["CIRCUIT_BAND"]).lower() == "no band")
            )

            if stop_dist_pct <= 0:
                atr_pct_val = (2.0 * atr_val) / cmp if cmp > 0 else 0.06
                stop_dist_pct = 0.04 if macro_regime_enum == MacroRegime.DEFENSIVE_CASH else min(0.07, max(0.05, atr_pct_val))
                init_stop = round(cmp * (1.0 - stop_dist_pct), 2)

            # Two-Tier GTT Targets
            m1 = round(cmp * (1.0 + M1_PCT), 2)
            m1_stop = round(cmp * (1.0 + M1_STOP_BE_BUFFER), 2)
            m2 = round(cmp * (1.0 + M2_PCT), 2)
            m2_stop = round(cmp * (1.0 + M2_RUNNER_STOP), 2)
            m3_ref = round(cmp * (1.0 + M3_REF_PCT), 2)

            qualified_stocks.append({
                "SYMBOL": sym,
                "CMP": cmp,
                "CMS_SCORE": row["CMS_SCORE"],
                "ROC_1M": f"{row['ROC_1M']:+.2f}%",
                "ROC_2M": f"{row['ROC_2M']:+.2f}%",
                "ROC_3M": f"{row['ROC_3M']:+.2f}%",
                "RSI_14": row["RSI_14"],
                "SMA_50": row["SMA_50"],
                "SMA_150": row["SMA_150"],
                "SMA_200": row["SMA_200"],
                "ATR_14": row["ATR_14"],
                "ATR_PCT": row["ATR_PCT"],
                "DIST_50SMA": row["DIST_50SMA"],
                "VOL_RATIO": row["VOL_RATIO"],
                "TURNOVER_CRORES": row["TURNOVER_CRORES"],
                "CIRCUIT_BAND": row["CIRCUIT_BAND"],
                "IS_PRIME": row["IS_PRIME"],
                "SETUP_QUALITY": row["SETUP_QUALITY"],
                "HIGH_52W": row["HIGH_52W"],
                "LOW_52W": row["LOW_52W"],
                "INITIAL_STOP": init_stop,
                "INITIAL_STOP_PCT": round(stop_dist_pct * 100, 1),
                "M1_TARGET": m1,
                "M1_STOP": m1_stop,
                "M2_TARGET": m2,
                "M2_STOP": m2_stop,
                "M3_TARGET": m3_ref,
                "M3_RUNNER_RULE": "Power Runner: Dynamic 50 SMA / 20 EMA / Blow-off trail (Ceiling removed)",
                "SIZING_META": size_meta,
                "CIRCUIT_RISK": row["CIRCUIT_DIAG"]["execution_risk_flag"],
                "AQS_SCORE": row["AQS_SCORE"],
                "AQS_GRADE": row["AQS_GRADE"],
                "IS_TRAP_VETO": row["IS_TRAP_VETO"],
                "CLOSING_RANGE": row["CLOSING_RANGE"],
                "CR_STATUS": row["CR_STATUS"],
                "UP_DOWN_VOL": row["UP_DOWN_VOL"],
                "UD_STATUS": row["UD_STATUS"],
                "VDU_RATIO": row["VDU_RATIO"],
                "VDU_STATUS": row["VDU_STATUS"],
                "RS_12M": row["RS_12M"],
                "INSTITUTIONAL_GRADE": row["INSTITUTIONAL_GRADE"],
                "INSTITUTIONAL_SCORE": row["INSTITUTIONAL_SCORE"],
                "VCP_RATIO": row["VCP_RATIO"],
                "VCP_STATUS": row["VCP_STATUS"],
                "VOL_SURGE_RATIO": row["VOL_SURGE_RATIO"],
                "VOL_STATUS": row["VOL_STATUS"],
                "FIP_SMOOTHNESS": row["FIP_SMOOTHNESS"],
                "FIP_STATUS": row["FIP_STATUS"],
                "INSTITUTIONAL_WARNINGS": row["INSTITUTIONAL_WARNINGS"],
                "IS_INSTITUTIONAL": row["IS_INSTITUTIONAL"],
                "FTF_STATE": str(row["FTF_STATE"]) if pd.notna(row["FTF_STATE"]) else "NORMAL_TREND",
                "FTF_TRIGGER": str(row["FTF_TRIGGER"]) if pd.notna(row["FTF_TRIGGER"]) else None,
                "FTF_DIAGNOSTIC": str(row["FTF_DIAGNOSTIC"]) if pd.notna(row["FTF_DIAGNOSTIC"]) else None,
                "PIVOT_RESISTANCE": float(row["PIVOT_RESISTANCE"]) if pd.notna(row["PIVOT_RESISTANCE"]) else None,
                "DOWNSIDE_FLOOR": float(row["DOWNSIDE_FLOOR"]) if pd.notna(row["DOWNSIDE_FLOOR"]) else None,
                "FLOOR_STATUS": str(row["FLOOR_STATUS"]) if pd.notna(row.get("FLOOR_STATUS")) else "INTACT",
            })

    # Sort: Anti-Trap Vetoes suppressed, then AQS Grade, then AQS Score, then CMS
    grade_weights = {
        "PRIME_ACCUMULATION": 5,
        "CONFIRMED_DEMAND": 4,
        "PRIME_INSTITUTIONAL": 4,
        "MODERATE_CONVICTION": 3,
        "NEUTRAL_QUALITY": 2,
        "LOW_PROBABILITY": 1,
        "SPECULATIVE_CHURN": 0,
        "TRAP_VETO": -1,
        "RETAIL_TRAP": -1
    }
    qualified_stocks.sort(
        key=lambda x: (
            not x.get("IS_TRAP_VETO", False),
            grade_weights.get(x.get("AQS_GRADE", ""), 0),
            x.get("AQS_SCORE", 0.0),
            x["IS_PRIME"],
            x["CMS_SCORE"]
        ),
        reverse=True
    )
    total_qualified = len(qualified_stocks)
    print(f"\n🏆 INSTITUTIONAL STAGE-2 QUALIFIED LEADERS (₹5 Cr+ Turnover): {total_qualified}")

    # Determine Active Signal vs. Cash based on Macro Regime
    is_cash_regime = (macro_regime_enum == MacroRegime.DEFENSIVE_CASH)

    if is_cash_regime:
        status = "CASH"
        winner_sized = None
        alternates = []
        print(f"🛑 CASH REGIME ENFORCED: {regime_info['benchmark']} is below its 200 SMA. No new positions permitted.")
    else:
        # Sizing winner: Only candidates meeting institutional quality grade are eligible
        eligible_leaders = [s for s in qualified_stocks if s.get("IS_INSTITUTIONAL", False)]
        cands_under_default = [s for s in eligible_leaders if s["CMP"] <= (capital_default - BUFFER)]
        winner = cands_under_default[0] if cands_under_default else (eligible_leaders[0] if eligible_leaders else (qualified_stocks[0] if qualified_stocks else None))
        alternates = [s for s in eligible_leaders if s != winner][:3] if eligible_leaders else qualified_stocks[1:4]
        status = "ACTIVE_SIGNAL" if winner else "CASH"

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

    # Theoretical skewness edge calculations
    skewness_proof = calculate_theoretical_skewness_edge()

    # Build Signal Payload
    signal_payload = {
        "status": status,
        "timestamp": now_ist,
        "trade_date": trade_date,
        "trade_date_display": dt_obj.strftime("%d-%b-%Y"),
        "is_today": is_today,
        "is_latest_session": is_latest,
        "bhavcopy_status": bhavcopy_status,
        "capital_base": capital_default,
        "total_qualified": total_qualified,
        "regime": regime_info,
        "winner": winner_sized,
        "alternates": alternates,
        "rows": signal_rows,
        "all_qualified": qualified_stocks,
        "skewness_proof": skewness_proof
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
        "is_latest": is_latest,
        "winner": winner_sized["SYMBOL"] if winner_sized else "CASH",
        "cmp": winner_sized["CMP"] if winner_sized else 0,
        "cms": winner_sized["CMS_SCORE"] if winner_sized else 0,
        "total_qualified": total_qualified,
        "regime": regime_info.get("regime", "UNKNOWN")
    })
    manifest = sorted(manifest, key=lambda x: x["date"], reverse=True)
    for idx, m in enumerate(manifest):
        m["is_latest"] = (idx == 0)
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    signal_payload["history_manifest"] = manifest

    if is_latest:
        screener_payload = {
            "timestamp": now_ist,
            "trade_date": trade_date,
            "total_screened": len(dynamic_symbols),
            "total_qualified": total_qualified,
            "regime": regime_info,
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
    print(f"🎯  TOP MOMENTUM LEADERS (TWO-TIER GTT) FOR {dt_obj.strftime('%d-%b-%Y')}:")
    for idx, s in enumerate(qualified_stocks[:10], 1):
        print(
            f"{idx:2d}. {s['SYMBOL']:12s} | CMP: ₹{s['CMP']:7.2f} | CMS: {s['CMS_SCORE']:5.1f} | "
            f"Grade: {s.get('INSTITUTIONAL_GRADE', 'N/A'):20s} | Vol: {s.get('VOL_SURGE_RATIO', 1.0):4.2f}x | "
            f"VCP: {s.get('VCP_RATIO', 1.0):4.2f} | Stop: ₹{s['INITIAL_STOP']:7.2f} (-{s['INITIAL_STOP_PCT']}%)"
        )
    print("=" * 65)

    return signal_payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NSE Momentum Quant Engine V2")
    parser.add_argument("capital", nargs="?", default="1000", help="Capital base (default 1000)")
    parser.add_argument("--date", help="Specific trade date (YYYY-MM-DD)")
    parser.add_argument("--backfill", type=int, default=0, help="Number of previous trading days to backfill into history")
    args = parser.parse_args()

    cap = float(args.capital) if args.capital else 1000.0

    if args.date:
        run_screener(capital_override=cap, target_date_str=args.date, is_latest=False)
    else:
        run_screener(capital_override=cap, is_latest=True)

        if args.backfill > 0:
            dates = get_recent_trading_dates(limit=args.backfill + 2)
            for dt in dates[1:1 + args.backfill]:
                dt_str = dt.strftime("%Y-%m-%d")
                print(f"\n⏳ Backfilling historical screener for {dt_str}...")
                try:
                    run_screener(capital_override=cap, target_date_str=dt_str, is_latest=False)
                except Exception as e:
                    print(f"⚠️ Failed backfill for {dt_str}: {e}")
