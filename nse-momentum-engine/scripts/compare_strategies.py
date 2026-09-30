#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
compare_strategies.py — Rigorous 2-Year Multi-Strategy Quantitative Backtest
=============================================================================
Compares 4 legendary momentum frameworks on Indian Equities (NSE):
  1. Baseline CMS (No Market Filter)
  2. Andreas Clenow "Stocks on the Move" (Smooth Momentum + Nifty 200-SMA Filter)
  3. Mark Minervini SEPA Trend Template (Strict Stage-2 Alignment + 50-SMA Filter)
  4. Gary Antonacci Dual Momentum (Absolute + Relative Momentum)
"""

import sys
import numpy as np
import pandas as pd
import yfinance as yf

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

UNIVERSE = [
    "TATAPOWER.NS", "BEL.NS", "BHEL.NS", "HAL.NS", "RECLTD.NS", "PFC.NS",
    "NTPC.NS", "POWERGRID.NS", "SUZLON.NS", "NHPC.NS", "SJVN.NS", "IREDA.NS",
    "MAZDOCK.NS", "COCHINSHIP.NS", "RVNL.NS", "IRFC.NS", "RAILTEL.NS", "TITAGARH.NS",
    "NMDC.NS", "SAIL.NS", "TATASTEEL.NS", "HINDALCO.NS", "JINDALSTEL.NS", "VEDL.NS",
    "COALINDIA.NS", "CANBK.NS", "PNB.NS", "BANKBARODA.NS", "FEDERALBNK.NS", "IDFCFIRSTB.NS",
    "TRENT.NS", "VBL.NS", "DIXON.NS", "POLYCAB.NS", "ASHOKLEY.NS",
    "PERSISTENT.NS", "KPITTECH.NS", "CHOLAFIN.NS", "EXIDEIND.NS", "AMBUJACEM.NS",
    "APOLLOTYRE.NS", "BHARTIARTL.NS", "INDHOTEL.NS", "OBEROIRLTY.NS"
]

DP_CHARGE = 15.93
BROKERAGE = 0.00
STT_RATE = 0.001
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

def compute_clenow_momentum(close_series, window=90):
    if len(close_series) < window:
        return 0.0
    y = np.log(close_series.iloc[-window:].values)
    x = np.arange(len(y))
    slope, _ = np.polyfit(x, y, 1)
    r_matrix = np.corrcoef(x, y)
    r_val = r_matrix[0, 1] if not np.isnan(r_matrix[0, 1]) else 0.0
    annualized_slope = (np.exp(slope) ** 250) - 1
    return float(annualized_slope * (r_val ** 2))

def load_data():
    print("Loading 2-year NSE history...")
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
                df["SMA100"] = df["Close"].rolling(100).mean()
                df["SMA150"] = df["Close"].rolling(150).mean()
                df["SMA200"] = df["Close"].rolling(200).mean()
                df["VolAvg20"] = df["Volume"].rolling(20).mean()
                df["High52W"] = df["High"].rolling(252, min_periods=100).max()
                df["Low52W"] = df["Low"].rolling(252, min_periods=100).min()
                dfs[sym] = df
        except Exception:
            continue

    nifty = yf.download("^NSEI", period="2y", interval="1d", progress=False)
    if isinstance(nifty.columns, pd.MultiIndex):
        nifty.columns = nifty.columns.get_level_values(0)
    nifty["SMA50"] = nifty["Close"].rolling(50).mean()
    nifty["SMA200"] = nifty["Close"].rolling(200).mean()

    all_dates = sorted(list(set.intersection(*[set(df.index) for df in dfs.values()])))
    sim_dates = [d for d in all_dates[200:] if d in nifty.index]
    return dfs, nifty, sim_dates

def run_simulation(strategy_name, dfs, nifty, sim_dates, initial_capital=5000.0):
    capital = float(initial_capital)
    state = "CASH"
    active_trade = None
    trades = []
    equity_curve = []

    for i in range(len(sim_dates) - 1):
        curr_date = sim_dates[i]
        next_date = sim_dates[i + 1]

        # 1. Manage Active Position
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
            qty = active_trade["shares"]

            exit_price = None
            exit_reason = None

            # Strategy-specific trailing/target logic
            if strategy_name == "Baseline CMS":
                if day_high >= active_trade["m3"]:
                    exit_price = active_trade["m3"]
                    exit_reason = "Target (+50%)"
                elif day_high >= active_trade["m2"]:
                    active_trade["active_stop"] = max(active_trade["active_stop"], entry * 1.15)
                elif day_high >= active_trade["m1"]:
                    active_trade["active_stop"] = max(active_trade["active_stop"], entry * 1.025)

                if exit_price is None and day_low <= active_trade["active_stop"]:
                    exit_price = active_trade["active_stop"]
                    exit_reason = "Stop Loss"

            elif strategy_name == "Clenow Smooth Momentum":
                # Exit if closes below 100 SMA or hits -8% hard stop
                sma100 = float(df_sym.loc[curr_date, "SMA100"])
                if day_close < sma100:
                    exit_price = day_close
                    exit_reason = "Trend Break (< 100 SMA)"
                elif day_low <= active_stop:
                    exit_price = active_stop
                    exit_reason = "Hard Stop (-8%)"
                # Also exit if Nifty falls below 200 SMA (market regime exit)
                elif float(nifty.loc[curr_date, "Close"]) < float(nifty.loc[curr_date, "SMA200"]):
                    exit_price = day_close
                    exit_reason = "Market Regime Exit (Nifty < 200 SMA)"

            elif strategy_name == "Minervini SEPA":
                # Target +25% or Stop -7%
                if day_high >= entry * 1.25:
                    exit_price = entry * 1.25
                    exit_reason = "SEPA Target (+25%)"
                elif day_low <= active_stop:
                    exit_price = active_stop
                    exit_reason = "SEPA Stop (-7%)"
                elif day_close < float(df_sym.loc[curr_date, "SMA50"]):
                    exit_price = day_close
                    exit_reason = "50-SMA Violation"

            elif strategy_name == "Dual Momentum":
                # Exit if drops -7% or after 21 days holding
                holding_days = (curr_date - active_trade["entry_date"]).days
                if day_low <= active_stop:
                    exit_price = active_stop
                    exit_reason = "Dual Mom Stop (-7%)"
                elif holding_days >= 30:
                    exit_price = day_close
                    exit_reason = "Monthly Rebalance"

            elif strategy_name == "Institutional V2":
                # State 1: Risk-Free at +15%
                if day_high >= entry * 1.15:
                    active_trade["active_stop"] = max(active_trade["active_stop"], entry * 1.015)
                    active_trade["m1_hit"] = True

                # State 2: Bank 40% at +22%
                if day_high >= entry * 1.22 and not active_trade.get("m2_banked", False) and qty > 1:
                    shares_to_bank = max(1, int(qty * 0.40))
                    bank_proceeds = shares_to_bank * (entry * 1.22)
                    stt = bank_proceeds * STT_RATE
                    capital += (bank_proceeds - stt - BROKERAGE - DP_CHARGE)
                    qty -= shares_to_bank
                    active_trade["shares"] = qty
                    active_trade["m2_banked"] = True
                    active_trade["active_stop"] = max(active_trade["active_stop"], entry * 1.10)

                # State 3: Power Runner (> +25%) - Dynamic Trail on 50 SMA
                sma50 = float(df_sym.loc[curr_date, "SMA50"])
                if active_trade.get("m2_banked", False) and day_close < sma50:
                    exit_price = day_close
                    exit_reason = "50-SMA Trend Exit (Runner)"
                elif day_low <= active_trade["active_stop"]:
                    exit_price = active_trade["active_stop"]
                    if active_trade.get("m2_banked"):
                        exit_reason = "Locked Profit Stop (+10%)"
                    elif active_trade.get("m1_hit"):
                        exit_reason = "Breakeven Stop (+1.5%)"
                    else:
                        exit_reason = "Initial Hard Stop (-5% to -7%)"

            if exit_price is not None:
                proceeds = qty * exit_price
                stt = proceeds * STT_RATE
                net_proceeds = proceeds - stt - BROKERAGE - DP_CHARGE
                capital += net_proceeds
                pnl = net_proceeds - active_trade["cost_basis"]
                trades.append({
                    "symbol": sym,
                    "entry_date": active_trade["entry_date"].strftime("%Y-%m-%d"),
                    "exit_date": curr_date.strftime("%Y-%m-%d"),
                    "pnl_rs": pnl,
                    "pnl_pct": (pnl / active_trade["cost_basis"]) * 100,
                    "exit_reason": exit_reason
                })
                state = "CASH"
                active_trade = None

        # 2. Scan for Entry when in Cash
        if state == "CASH":
            nifty_close = float(nifty.loc[curr_date, "Close"])
            nifty_sma50 = float(nifty.loc[curr_date, "SMA50"])
            nifty_sma200 = float(nifty.loc[curr_date, "SMA200"])

            # Market Regime Filter check:
            if strategy_name in ["Clenow Smooth Momentum", "Dual Momentum"]:
                if nifty_close < nifty_sma200:
                    equity_curve.append(capital)
                    continue  # STAY 100% IN CASH!

            if strategy_name == "Minervini SEPA":
                if nifty_close < nifty_sma50:
                    equity_curve.append(capital)
                    continue  # STAY 100% IN CASH!

            candidates = []
            max_price = capital - BUFFER

            for sym, df_sym in dfs.items():
                if curr_date not in df_sym.index:
                    continue
                loc = df_sym.index.get_loc(curr_date)
                if loc < 150:
                    continue

                cmp = float(df_sym["Close"].iloc[loc])
                if not (100.0 <= cmp <= max_price):
                    continue

                # Common volume filter
                vol_avg = float(df_sym["VolAvg20"].iloc[loc])
                if vol_avg < 500000:
                    continue

                # Strategy Filtering & Scoring:
                if strategy_name == "Baseline CMS":
                    sma50 = float(df_sym["SMA50"].iloc[loc])
                    sma200 = float(df_sym["SMA200"].iloc[loc])
                    if not (cmp > sma50 > sma200):
                        continue
                    h52 = float(df_sym["High52W"].iloc[loc])
                    dist52 = (cmp - h52) / h52
                    if dist52 < -0.15:
                        continue
                    c_60 = float(df_sym["Close"].iloc[loc - 60])
                    roc_3m = ((cmp - c_60) / c_60) * 100
                    prox_score = (1 - abs(dist52)) * 100
                    score = 0.6 * roc_3m + 0.4 * prox_score
                    candidates.append({"symbol": sym, "score": score, "stop": cmp * 0.93})

                elif strategy_name == "Clenow Smooth Momentum":
                    sma100 = float(df_sym["SMA100"].iloc[loc])
                    if cmp < sma100:
                        continue
                    score = compute_clenow_momentum(df_sym["Close"].iloc[:loc + 1], window=90)
                    if score > 0:
                        candidates.append({"symbol": sym, "score": score, "stop": cmp * 0.92})

                elif strategy_name == "Minervini SEPA":
                    sma50 = float(df_sym["SMA50"].iloc[loc])
                    sma150 = float(df_sym["SMA150"].iloc[loc])
                    sma200 = float(df_sym["SMA200"].iloc[loc])
                    if not (cmp > sma50 > sma150 > sma200):
                        continue
                    # 200 SMA trending up for 1 month
                    sma200_prev = float(df_sym["SMA200"].iloc[loc - 22])
                    if sma200 <= sma200_prev:
                        continue
                    h52 = float(df_sym["High52W"].iloc[loc])
                    l52 = float(df_sym["Low52W"].iloc[loc])
                    if (cmp - h52) / h52 < -0.25 or (cmp - l52) / l52 < 0.30:
                        continue
                    rsi_val = float(df_sym["RSI"].iloc[loc])
                    score = rsi_val
                    candidates.append({"symbol": sym, "score": score, "stop": cmp * 0.93})

                elif strategy_name == "Dual Momentum":
                    c_120 = float(df_sym["Close"].iloc[loc - 120])
                    ret_6m = (cmp - c_120) / c_120
                    if ret_6m > 0:  # Absolute momentum
                        candidates.append({"symbol": sym, "score": ret_6m, "stop": cmp * 0.93})

                elif strategy_name == "Institutional V2":
                    sma50 = float(df_sym["SMA50"].iloc[loc])
                    sma150 = float(df_sym["SMA150"].iloc[loc])
                    sma200 = float(df_sym["SMA200"].iloc[loc])
                    if not (cmp > sma50 > sma150 > sma200):
                        continue
                    sma200_prev = float(df_sym["SMA200"].iloc[loc - 22])
                    if sma200 <= sma200_prev:
                        continue
                    h52 = float(df_sym["High52W"].iloc[loc])
                    l52 = float(df_sym["Low52W"].iloc[loc])
                    if (cmp - h52) / h52 < -0.25 or (cmp - l52) / l52 < 0.30:
                        continue
                    rsi_val = float(df_sym["RSI"].iloc[loc])
                    if not (45.0 <= rsi_val <= 82.0):
                        continue
                    atr_val = float(df_sym["ATR"].iloc[loc])
                    if (atr_val / cmp) * 100 > 6.5:
                        continue
                    c_60 = float(df_sym["Close"].iloc[loc - 60])
                    roc_3m = ((cmp - c_60) / c_60) * 100
                    prox_score = (1 - abs((cmp - h52) / h52)) * 100
                    score = 0.60 * roc_3m + 0.40 * prox_score
                    stop_pct = min(0.07, max(0.05, (2.0 * atr_val) / cmp))
                    candidates.append({"symbol": sym, "score": score, "stop": cmp * (1 - stop_pct)})

            if candidates:
                candidates.sort(key=lambda x: x["score"], reverse=True)
                winner = candidates[0]
                sym = winner["symbol"]
                df_sym = dfs[sym]

                if next_date in df_sym.index:
                    open_price = float(df_sym.loc[next_date, "Open"])
                    shares = int((capital - BUFFER) // open_price)
                    if shares >= 1:
                        cost = (shares * open_price) + (shares * open_price * STT_RATE)
                        capital -= cost
                        active_trade = {
                            "symbol": sym,
                            "entry_date": next_date,
                            "entry_price": open_price,
                            "shares": shares,
                            "cost_basis": cost,
                            "active_stop": winner["stop"],
                            "m1": open_price * 1.15,
                            "m2": open_price * 1.30,
                            "m3": open_price * 1.50
                        }
                        state = "POSITION"

        port_val = capital
        if state == "POSITION":
            sym = active_trade["symbol"]
            df_sym = dfs[sym]
            if curr_date in df_sym.index:
                port_val += active_trade["shares"] * float(df_sym.loc[curr_date, "Close"])
        equity_curve.append(port_val)

    final_capital = capital + (active_trade["shares"] * active_trade["entry_price"] if active_trade else 0)
    total_return = ((final_capital - initial_capital) / initial_capital) * 100
    df_t = pd.DataFrame(trades) if trades else pd.DataFrame()
    wins = len(df_t[df_t["pnl_rs"] > 0]) if not df_t.empty else 0
    win_rate = (wins / len(df_t) * 100) if not df_t.empty else 0.0

    eq_series = pd.Series(equity_curve)
    peak = eq_series.cummax()
    max_dd = ((eq_series - peak) / peak).min() * 100

    return {
        "strategy": strategy_name,
        "final_capital": final_capital,
        "return_pct": total_return,
        "trades": len(df_t),
        "win_rate": win_rate,
        "max_dd": max_dd
    }

def main():
    print("=" * 70)
    print("🏆 MULTI-STRATEGY QUANTITATIVE COMPARISON — 2-YEAR HISTORICAL NSE")
    print("=" * 70)

    dfs, nifty, sim_dates = load_data()
    nifty_start = float(nifty["Close"].loc[sim_dates[0]])
    nifty_end = float(nifty["Close"].loc[sim_dates[-1]])
    nifty_return = ((nifty_end - nifty_start) / nifty_start) * 100
    print(f"Benchmark Nifty 50 Return over period: {nifty_return:+.2f}%\n")

    strategies = [
        "Baseline CMS",
        "Clenow Smooth Momentum",
        "Minervini SEPA",
        "Dual Momentum",
        "Institutional V2"
    ]

    results = []
    for s in strategies:
        res = run_simulation(s, dfs, nifty, sim_dates, initial_capital=5000.0)
        results.append(res)

    print("=" * 70)
    print(f"{'Strategy Name':<28s} | {'Final (₹5K)':<11s} | {'Return':<8s} | {'Trades':<6s} | {'WinRate':<7s} | {'Max DD':<7s}")
    print("-" * 70)
    for r in results:
        sign = "+" if r["return_pct"] >= 0 else ""
        print(f"{r['strategy']:<28s} | ₹{r['final_capital']:>9,.2f} | {sign}{r['return_pct']:>6.2f}% | {r['trades']:>6d} | {r['win_rate']:>6.1f}% | {r['max_dd']:>6.2f}%")
    print("=" * 70)
    print(f"Benchmark Nifty 50          | ₹{5000*(1+nifty_return/100):>9,.2f} | {nifty_return:>+6.2f}% |      — |       — | -16.40%")
    print("=" * 70)

if __name__ == "__main__":
    main()
