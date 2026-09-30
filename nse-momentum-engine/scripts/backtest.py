#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backtest.py — Rigorous 2-Year Quantitative Backtest for NSE Momentum Strategy
=============================================================================
Rules Simulated:
  - Starting Capital: ₹1,000 (100% compounding rolling profit + capital)
  - Filters:
      1. Price Band: ₹100 <= CMP <= (Capital - 26)
      2. Trend: CMP > 50-SMA > 200-SMA
      3. Anti-Downfall: 1M ROC > -3% AND 2M ROC > 0%
      4. 52W Proximity: Within 15% of 52-week High
      5. RSI Guard: 40 <= RSI(14) <= 70
      6. Volume: 20-day average >= 500,000 shares
  - Ranking: CMS = 0.50 * 3M_ROC + 0.30 * Prox52W + 0.20 * VolScore
  - Execution:
      - Buy #1 ranked stock next day Open
      - GTT Stop: max(Entry * 0.93, Entry - 2*ATR)
      - M1 (+15%): Stop moves to Entry * 1.025 (+2.5% breakeven)
      - M2 (+30%): Stop moves to Entry * 1.15 (+15% profit lock)
      - M3 (+50%): Target exit
  - Friction:
      - Brokerage: ₹20 per trade (Zerodha)
      - DP Charge: ₹21.83 flat per sell
      - STT: 0.1% on buy & sell
      - Exchange charges & GST
"""

import sys
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta

# Fix Windows console UTF-8 encoding
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Broad liquid universe representing Indian momentum pool
UNIVERSE = [
    "TATAPOWER.NS", "BEL.NS", "BHEL.NS", "HAL.NS", "RECLTD.NS", "PFC.NS",
    "NTPC.NS", "POWERGRID.NS", "SUZLON.NS", "NHPC.NS", "SJVN.NS", "IREDA.NS",
    "MAZDOCK.NS", "COCHINSHIP.NS", "RVNL.NS", "IRFC.NS", "RAILTEL.NS", "TITAGARH.NS",
    "NMDC.NS", "SAIL.NS", "TATASTEEL.NS", "HINDALCO.NS", "JINDALSTEL.NS", "VEDL.NS",
    "COALINDIA.NS", "CANBK.NS", "PNB.NS", "BANKBARODA.NS", "FEDERALBNK.NS", "IDFCFIRSTB.NS",
    "TRENT.NS", "VBL.NS", "ZOMATO.NS", "DIXON.NS", "POLYCAB.NS", "TATAMOTORS.NS",
    "ASHOKLEY.NS", "PERSISTENT.NS", "KPITTECH.NS", "CHOLAFIN.NS", "EXIDEIND.NS",
    "AMBUJACEM.NS", "APOLLOTYRE.NS", "BHARTIARTL.NS", "INDHOTEL.NS", "OBEROIRLTY.NS"
]

DP_CHARGE = 15.93     # CDSL flat DP charge on sell (₹13.50 + 18% GST)
BROKERAGE = 0.00      # Zerodha delivery/CNC is ₹0 flat!
STT_RATE = 0.001      # 0.1% on buy and sell
BUFFER = 26.0

def compute_rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def compute_atr(df, period=14):
    h = df["High"]
    l = df["Low"]
    c = df["Close"].shift(1)
    tr = pd.concat([h - l, (h - c).abs(), (l - c).abs()], axis=1).max(axis=1)
    return tr.rolling(period).mean()

def run_backtest():
    print("=" * 65)
    print("📈  2-YEAR QUANTITATIVE BACKTEST — NSE MOMENTUM ENGINE")
    print("=" * 65)
    print(f"Loading 2-year daily history for {len(UNIVERSE)} liquid symbols ...")

    # Download data with threads=False to avoid sqlite lock
    dfs = {}
    for sym in UNIVERSE:
        try:
            df = yf.download(sym, period="2y", interval="1d", progress=False)
            if df is not None and len(df) > 200:
                # Flatten multi-index columns if present in newer yfinance
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                df["RSI"] = compute_rsi(df["Close"])
                df["ATR"] = compute_atr(df)
                df["SMA50"] = df["Close"].rolling(50).mean()
                df["SMA200"] = df["Close"].rolling(200).mean()
                df["VolAvg20"] = df["Volume"].rolling(20).mean()
                df["High52W"] = df["High"].rolling(252, min_periods=100).max()
                dfs[sym] = df
        except Exception:
            continue

    print(f"Successfully prepared data for {len(dfs)} stocks.")

    # Benchmark: Nifty 50 over same 2 years
    nifty = yf.download("^NSEI", period="2y", interval="1d", progress=False)
    if isinstance(nifty.columns, pd.MultiIndex):
        nifty.columns = nifty.columns.get_level_values(0)
    nifty_start = float(nifty["Close"].iloc[0])
    nifty_end = float(nifty["Close"].iloc[-1])
    nifty_return = ((nifty_end - nifty_start) / nifty_start) * 100

    # Common trading dates (start after 200 days for warm-up)
    all_dates = sorted(list(set.intersection(*[set(df.index) for df in dfs.values()])))
    sim_dates = all_dates[200:]
    print(f"Simulation Trading Days: {len(sim_dates)} (from {sim_dates[0].strftime('%Y-%m-%d')} to {sim_dates[-1].strftime('%Y-%m-%d')})")
    print(f"Benchmark Nifty 50 Return over same period: +{nifty_return:.2f}%\n")

def simulate_portfolio(initial_capital, dfs, sim_dates, nifty_return, verbose=False):
    capital = float(initial_capital)
    state = "CASH"
    active_trade = None
    trades = []
    equity_curve = []

    for i in range(len(sim_dates) - 1):
        curr_date = sim_dates[i]
        next_date = sim_dates[i + 1]

        # 1. If in position: check GTT execution
        if state == "POSITION":
            sym = active_trade["symbol"]
            df_sym = dfs[sym]
            if curr_date not in df_sym.index:
                continue

            day_high = float(df_sym.loc[curr_date, "High"])
            day_low = float(df_sym.loc[curr_date, "Low"])
            day_close = float(df_sym.loc[curr_date, "Close"])

            entry = active_trade["entry_price"]
            active_stop = active_trade["active_stop"]
            m1 = active_trade["m1_target"]
            m2 = active_trade["m2_target"]
            m3 = active_trade["m3_target"]
            qty = active_trade["shares"]

            exit_price = None
            exit_reason = None

            # Check Milestone 3 (+50%)
            if day_high >= m3:
                exit_price = m3
                exit_reason = "Milestone 3 Target (+50%)"
            elif day_high >= m2:
                active_trade["active_stop"] = max(active_trade["active_stop"], entry * 1.15)
                active_trade["m2_hit"] = True
            elif day_high >= m1:
                active_trade["active_stop"] = max(active_trade["active_stop"], entry * 1.025)
                active_trade["m1_hit"] = True

            # Check Stop Loss Trigger
            if exit_price is None and day_low <= active_trade["active_stop"]:
                exit_price = active_trade["active_stop"]
                if active_trade.get("m2_hit"):
                    exit_reason = "Trailing Stop (+15% Lock)"
                elif active_trade.get("m1_hit"):
                    exit_reason = "Breakeven Stop (+2.5% Floor)"
                else:
                    exit_reason = "Initial Hard Stop (-7%)"

            # Execute exit
            if exit_price is not None:
                gross_proceeds = qty * exit_price
                stt = gross_proceeds * STT_RATE
                net_proceeds = gross_proceeds - stt - BROKERAGE - DP_CHARGE
                capital += net_proceeds

                pnl_rs = net_proceeds - active_trade["cost_basis"]
                pnl_pct = (pnl_rs / active_trade["cost_basis"]) * 100

                trades.append({
                    "symbol": sym,
                    "entry_date": active_trade["entry_date"].strftime("%Y-%m-%d"),
                    "exit_date": curr_date.strftime("%Y-%m-%d"),
                    "entry_price": round(entry, 2),
                    "exit_price": round(exit_price, 2),
                    "shares": qty,
                    "pnl_rs": round(pnl_rs, 2),
                    "pnl_pct": round(pnl_pct, 2),
                    "exit_reason": exit_reason,
                    "new_capital": round(capital, 2)
                })
                state = "CASH"
                active_trade = None

        # 2. If in cash: scan for new #1 winner
        if state == "CASH":
            candidates = []
            max_price = capital - BUFFER

            for sym, df_sym in dfs.items():
                if curr_date not in df_sym.index:
                    continue
                loc = df_sym.index.get_loc(curr_date)
                if loc < 65:
                    continue

                cmp = float(df_sym["Close"].iloc[loc])
                if not (100.0 <= cmp <= max_price):
                    continue

                # Anti-downfall
                close_20 = float(df_sym["Close"].iloc[loc - 20])
                close_40 = float(df_sym["Close"].iloc[loc - 40])
                roc_1m = (cmp - close_20) / close_20
                roc_2m = (cmp - close_40) / close_40
                if roc_1m <= -0.03 or roc_2m <= 0:
                    continue

                # Trend regime: CMP > 50-SMA > 200-SMA
                sma50 = float(df_sym["SMA50"].iloc[loc])
                sma200 = float(df_sym["SMA200"].iloc[loc])
                if not (cmp > sma50 > sma200):
                    continue

                # 52W Proximity
                high52 = float(df_sym["High52W"].iloc[loc])
                dist52 = (cmp - high52) / high52
                if dist52 < -0.15:
                    continue

                # Volume
                vol_avg = float(df_sym["VolAvg20"].iloc[loc])
                if vol_avg < 500000:
                    continue

                # RSI Guard
                rsi_val = float(df_sym["RSI"].iloc[loc])
                if not (40 <= rsi_val <= 70):
                    continue

                # CMS Score
                close_60 = float(df_sym["Close"].iloc[loc - 60])
                roc_3m = ((cmp - close_60) / close_60) * 100
                prox_score = (1 - abs(dist52)) * 100
                v5 = float(df_sym["Volume"].iloc[loc - 4:loc + 1].mean())
                v50 = float(df_sym["Volume"].iloc[loc - 49:loc + 1].mean())
                raw_vr = (v5 / v50) if v50 > 0 else 1.0
                vol_score = min(max((raw_vr - 0.5) / 2.5, 0), 1) * 100
                cms = 0.50 * roc_3m + 0.30 * prox_score + 0.20 * vol_score

                atr_val = float(df_sym["ATR"].iloc[loc])
                candidates.append({
                    "symbol": sym,
                    "cmp": cmp,
                    "cms": cms,
                    "atr": atr_val
                })

            if candidates:
                candidates.sort(key=lambda x: x["cms"], reverse=True)
                winner = candidates[0]
                sym = winner["symbol"]
                df_sym = dfs[sym]

                if next_date in df_sym.index:
                    open_price = float(df_sym.loc[next_date, "Open"])
                    shares = int((capital - BUFFER) // open_price)
                    if shares >= 1:
                        cost = (shares * open_price) + BROKERAGE + (shares * open_price * STT_RATE)
                        capital -= cost

                        atr_val = winner["atr"]
                        init_stop = max(round(open_price * 0.93, 2), round(open_price - 2 * atr_val, 2))
                        m1 = round(open_price * 1.15, 2)
                        m2 = round(open_price * 1.30, 2)
                        m3 = round(open_price * 1.50, 2)

                        active_trade = {
                            "symbol": sym,
                            "entry_date": next_date,
                            "entry_price": open_price,
                            "shares": shares,
                            "cost_basis": cost,
                            "active_stop": init_stop,
                            "m1_target": m1,
                            "m2_target": m2,
                            "m3_target": m3,
                            "m1_hit": False,
                            "m2_hit": False,
                        }
                        state = "POSITION"

        port_val = capital
        if state == "POSITION":
            sym = active_trade["symbol"]
            df_sym = dfs[sym]
            if curr_date in df_sym.index:
                port_val += active_trade["shares"] * float(df_sym.loc[curr_date, "Close"])
        equity_curve.append(port_val)

    # Analytics
    if not trades:
        return None

    df_trades = pd.DataFrame(trades)
    wins = df_trades[df_trades["pnl_rs"] > 0]
    losses = df_trades[df_trades["pnl_rs"] <= 0]
    win_rate = (len(wins) / len(trades)) * 100
    final_capital = capital + (active_trade["shares"] * active_trade["entry_price"] if active_trade else 0)
    total_return = ((final_capital - initial_capital) / initial_capital) * 100

    gross_profit = wins["pnl_rs"].sum() if len(wins) > 0 else 0
    gross_loss = abs(losses["pnl_rs"].sum()) if len(losses) > 0 else 1
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else 999

    eq_series = pd.Series(equity_curve)
    peak = eq_series.cummax()
    dd = (eq_series - peak) / peak
    max_dd = dd.min() * 100

    result = {
        "initial_capital": initial_capital,
        "final_capital": final_capital,
        "total_return": total_return,
        "trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "max_dd": max_dd,
        "trade_log": df_trades
    }

    if verbose:
        print("\n" + "=" * 65)
        print(f"📊  PERFORMANCE REPORT — CAPITAL BASE: ₹{initial_capital:,.2f}")
        print("=" * 65)
        print(f"💰 Initial Capital       : ₹{initial_capital:,.2f}")
        print(f"💵 Final Capital         : ₹{final_capital:,.2f}")
        print(f"🚀 Total Return          : {'+' if total_return >= 0 else ''}{total_return:.2f}% (vs Nifty 50: {nifty_return:.2f}%)")
        print(f"🔢 Total Trades          : {len(trades)}")
        print(f"🎯 Win Rate              : {win_rate:.1f}% ({len(wins)} Wins / {len(losses)} Losses)")
        print(f"⚖️ Profit Factor          : {profit_factor:.2f}")
        print(f"🛡️ Max Drawdown          : {max_dd:.2f}%\n")
        print("── Trade-by-Trade Log ────────────────────────────────────────")
        for idx, t in df_trades.iterrows():
            sign = "+" if t["pnl_rs"] >= 0 else ""
            print(f"{idx+1:2d}. {t['symbol']:14s} | {t['entry_date']} -> {t['exit_date']} | "
                  f"₹{t['entry_price']:6.2f} -> ₹{t['exit_price']:6.2f} | "
                  f"{sign}{t['pnl_pct']:6.2f}% ({sign}₹{t['pnl_rs']:6.2f}) | {t['exit_reason']}")

    return result

def run_backtest():
    print("=" * 65)
    print("📈  2-YEAR QUANTITATIVE BACKTEST — NSE MOMENTUM ENGINE")
    print("=" * 65)
    print(f"Loading 2-year daily history for {len(UNIVERSE)} liquid symbols ...")

    dfs = {}
    for sym in UNIVERSE:
        try:
            df = yf.download(sym, period="2y", interval="1d", progress=False)
            if df is not None and len(df) > 200:
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                df["RSI"] = compute_rsi(df["Close"])
                df["ATR"] = compute_atr(df)
                df["SMA50"] = df["Close"].rolling(50).mean()
                df["SMA200"] = df["Close"].rolling(200).mean()
                df["VolAvg20"] = df["Volume"].rolling(20).mean()
                df["High52W"] = df["High"].rolling(252, min_periods=100).max()
                dfs[sym] = df
        except Exception:
            continue

    print(f"Successfully prepared data for {len(dfs)} stocks.")

    nifty = yf.download("^NSEI", period="2y", interval="1d", progress=False)
    if isinstance(nifty.columns, pd.MultiIndex):
        nifty.columns = nifty.columns.get_level_values(0)
    nifty_start = float(nifty["Close"].iloc[0])
    nifty_end = float(nifty["Close"].iloc[-1])
    nifty_return = ((nifty_end - nifty_start) / nifty_start) * 100

    all_dates = sorted(list(set.intersection(*[set(df.index) for df in dfs.values()])))
    sim_dates = all_dates[200:]
    print(f"Simulation Trading Days: {len(sim_dates)} (from {sim_dates[0].strftime('%Y-%m-%d')} to {sim_dates[-1].strftime('%Y-%m-%d')})")
    print(f"Benchmark Nifty 50 Return over same period: {nifty_return:+.2f}%\n")

    # Run for ₹1,000 (with verbose log)
    res_1k = simulate_portfolio(1000.0, dfs, sim_dates, nifty_return, verbose=True)

    # Comparative analysis across capital tiers
    print("\n" + "=" * 65)
    print("🔬 CAPITAL TIER SENSITIVITY ANALYSIS (Friction & Stock Universe Effect)")
    print("=" * 65)
    print(f"{'Capital':>10s} | {'Final Value':>12s} | {'Return':>9s} | {'Trades':>6s} | {'Win Rate':>8s} | {'Max DD':>8s}")
    print("-" * 65)

    for cap in [1000, 2500, 5000, 10000, 25000, 50000]:
        res = simulate_portfolio(cap, dfs, sim_dates, nifty_return, verbose=False)
        if res:
            print(f"₹{cap:>9,d} | ₹{res['final_capital']:>11,.2f} | {res['total_return']:>+8.2f}% | {res['trades']:>6d} | {res['win_rate']:>7.1f}% | {res['max_dd']:>7.2f}%")
    print("=" * 65)

if __name__ == "__main__":
    run_backtest()
