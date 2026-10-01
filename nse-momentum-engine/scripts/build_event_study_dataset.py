#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_event_study_dataset.py — Universe Data Collector for Empirical Separation Study
Downloads / consolidates 2-year daily OHLCV for ~120 liquid NSE equities (AGENTS.md).
"""

from pathlib import Path
import pandas as pd
import yfinance as yf

# Liquid NSE equities representing large, mid, and momentum universe
EXPANDED_SYMBOLS = [
    # Existing core liquid universe
    "AMBUJACEM", "APOLLOTYRE", "ASHOKLEY", "BANKBARODA", "BEL", "BHARTIARTL", "BHEL",
    "CANBK", "CHOLAFIN", "COALINDIA", "COCHINSHIP", "DIXON", "EXIDEIND", "FEDERALBNK",
    "HAL", "HINDALCO", "HUDCO", "IDFCFIRSTB", "INDHOTEL", "IOB", "IREDA", "IRFC",
    "JINDALSTEL", "KALYANKJIL", "KPITTECH", "MAZDOCK", "MOTHERSON", "NBCC", "NHPC",
    "NMDC", "NTPC", "OBEROIRLTY", "PERSISTENT", "PFC", "PNB", "POLYCAB", "POWERGRID",
    "PRESTIGE", "RAILTEL", "RECLTD", "RVNL", "SAIL", "SJVN", "SUZLON", "TATAPOWER",
    "TATASTEEL", "TITAGARH", "TRENT", "UNIONBANK", "VBL", "VEDL",
    # Additional high-momentum leaders and sector anchors
    "RELIANCE", "TCS", "INFY", "ICICIBANK", "HDFCBANK", "LT", "TATAMOTORS", "TITAN",
    "BAJFINANCE", "SUNPHARMA", "DIVISLAB", "CIPLA", "DRREDDY", "HEROMOTOCO", "BAJAJ-AUTO",
    "MARUTI", "EICHERMOT", "ADANIENT", "ADANIPORTS", "ASIANPAINT", "ULTRACEMCO", "GRASIM",
    "JSWSTEEL", "TECHM", "WIPRO", "HCLTECH", "LTIM", "COFORGE", "MPHASIS", "OFSS",
    "MUTHOOTFIN", "SHRIRAMFIN", "WELSPUNLIV", "TDPOWERSYS", "MANINDS", "KAYNES",
    "BOSCHLTD", "CUMMINSIND", "SIEMENS", "ABB", "CGPOWER", "THERMAX", "KEI", "HAVELLS",
    "VOLTAS", "BLUESTARCO", "ASTRAL", "SUPREMEIND", "PIIND", "DEEPAKNTR", "TATACHEM",
    "COROMANDEL", "UPL", "SRF", "PAGEIND", "DMART", "METROPOLIS", "LALPATHLAB", "FORTIS",
    "APOLLOHOSP", "MAXHEALTH", "GLENMARK", "LUPIN", "AUROPHARMA", "TORNTPHARM", "ZYDUSLIFE"
]


def build_universe_history(output_path: Path, period: str = "2y") -> pd.DataFrame:
    """Fetches and normalizes daily OHLCV data for all symbols."""
    print(f"Downloading history for {len(EXPANDED_SYMBOLS)} symbols (period={period})...")
    tickers = [f"{s}.NS" for s in EXPANDED_SYMBOLS]
    data = yf.download(tickers, period=period, group_by="ticker", progress=True)

    records = []
    for sym in EXPANDED_SYMBOLS:
        ticker = f"{sym}.NS"
        try:
            if ticker in data.columns.levels[0]:
                df = data[ticker].dropna(subset=["Close"]).copy()
                if len(df) < 50:
                    continue
                df = df.reset_index()
                df["Date"] = pd.to_datetime(df["Date"]).dt.tz_localize(None)
                df["Symbol"] = sym
                df = df.rename(columns={
                    "Open": "Open", "High": "High", "Low": "Low", "Close": "Close", "Volume": "Volume"
                })
                sub = df[["Date", "Symbol", "Open", "High", "Low", "Close", "Volume"]]
                records.append(sub)
        except Exception as e:
            print(f"Skipping {sym}: {e}")

    if not records:
        raise RuntimeError("No records successfully downloaded.")

    full_df = pd.concat(records, ignore_index=True)
    full_df.sort_values(by=["Symbol", "Date"], inplace=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    full_df.to_parquet(output_path, index=False)
    print(f"Saved {len(full_df)} bars across {full_df['Symbol'].nunique()} symbols to {output_path}")
    return full_df


if __name__ == "__main__":
    out_file = Path(__file__).resolve().parent.parent / "data" / "universe_event_history.parquet"
    build_universe_history(out_file)
