#!/usr/bin/env python3
"""
fetch_tournament_data.py
Downloads historical daily OHLCV data for NSE liquid momentum stocks
and the Nifty 500 benchmark for the strategy tournament.
"""

from pathlib import Path
import pandas as pd
import yfinance as yf

SYMBOLS = [
    "RELIANCE", "TCS", "INFY", "ICICIBANK", "HDFCBANK", "LT", "BHARTIARTL",
    "TATAMOTORS", "NTPC", "POWERGRID", "TITAN", "BAJFINANCE", "TATASTEEL",
    "SUNPHARMA", "COALINDIA", "TRENT", "BEL", "HAL", "BHEL", "DIXON",
    "POLYCAB", "VBL", "ZOMATO", "RECLTD", "PFC", "SUZLON", "MAZDOCK",
    "COCHINSHIP", "RVNL", "IRFC", "RAILTEL", "TITAGARH", "NMDC", "SAIL",
    "HINDALCO", "JINDALSTEL", "VEDL", "CANBK", "PNB", "BANKBARODA",
    "PERSISTENT", "KPITTECH", "CHOLAFIN", "EXIDEIND", "AMBUJACEM",
    "APOLLOTYRE", "INDHOTEL", "OBEROIRLTY", "MCX", "DIVISLAB"
]

BENCHMARK_TICKER = "^CRSLDX"  # Nifty 500


def fetch_all(out_dir: Path, period: str = "4y"):
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"Downloading benchmark ({BENCHMARK_TICKER}) for period '{period}'...")
    b_df = yf.download(BENCHMARK_TICKER, period=period, progress=False)
    if isinstance(b_df.columns, pd.MultiIndex):
        b_df.columns = b_df.columns.get_level_values(0)
    b_df = b_df.reset_index()
    b_df["date"] = pd.to_datetime(b_df["Date"]).dt.strftime("%Y-%m-%d")
    b_df[["date", "Close"]].rename(columns={"Close": "close"}).to_csv(
        out_dir / "NIFTY500.csv", index=False
    )
    print(f"Saved benchmark to {out_dir / 'NIFTY500.csv'} ({len(b_df)} rows).")

    print(f"Downloading {len(SYMBOLS)} NSE stocks...")
    tickers = [f"{s}.NS" for s in SYMBOLS]
    data = yf.download(tickers, period=period, group_by="ticker", progress=False)

    saved_count = 0
    for sym in SYMBOLS:
        ticker = f"{sym}.NS"
        try:
            if ticker in data.columns.levels[0]:
                df = data[ticker].dropna(how="all").copy()
            else:
                continue
            if len(df) < 100:
                continue
            df = df.reset_index()
            df["date"] = pd.to_datetime(df["Date"]).dt.strftime("%Y-%m-%d")
            df["symbol"] = sym
            df["open"] = df["Open"]
            df["high"] = df["High"]
            df["low"] = df["Low"]
            df["close"] = df["Close"]
            df["volume"] = df["Volume"]
            df["turnover"] = df["close"] * df["volume"]
            df["price_band"] = "20%"
            df["series"] = "EQ"

            cols = [
                "date", "symbol", "open", "high", "low", "close",
                "volume", "turnover", "price_band", "series"
            ]
            df[cols].to_csv(out_dir / f"{sym}.csv", index=False)
            saved_count += 1
        except Exception as e:
            print(f"Error saving {sym}: {e}")

    print(f"Successfully saved {saved_count} stock CSVs to {out_dir}.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="tournament_data", help="Output directory")
    parser.add_argument("--period", default="4y", help="Historical period (e.g. 3y, 4y)")
    args = parser.parse_args()
    fetch_all(Path(args.out), period=args.period)
