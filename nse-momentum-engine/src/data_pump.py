"""
NSE Momentum Data Pump — v2.0
================================
Role: GitHub Actions data fetcher.
- Downloads NSE Bhavcopy (all EQ stocks, one CSV per Friday)
- Computes indicators + filters on rolling window from Google Sheets history
- Writes clean Signal output to Google Sheets "Signal" tab
- Updates "RawData", "Config" tabs
- Sends push notification via Google Sheets published CSV (read by PWA app)
"""

import os
import io
import json
import math
import requests
import numpy as np
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timezone, timedelta

# ─────────────────────────────────────────────────────────────────────────
# CONFIG  (all read from env / GitHub Secrets)
# ─────────────────────────────────────────────────────────────────────────
GOOGLE_CREDENTIALS_JSON = os.environ["GOOGLE_CREDENTIALS_JSON"]
SHEET_NAME              = os.environ.get("SHEET_NAME", "NSE Momentum Engine")
IST                     = timezone(timedelta(hours=5, minutes=30))

# Strategy constants
MIN_PRICE      = 100.0
MIN_AVG_VOLUME = 500_000
STOP_PCT       = 0.07
M1_PCT         = 0.15
M1_STOP_PCT    = 0.025
M2_PCT         = 0.30
M2_STOP_PCT    = 0.15
M3_PCT         = 0.50
BUFFER         = 26.0   # DP + taxes + rounding buffer

BHAVCOPY_URL = "https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{date}.csv"
HEADERS      = {"User-Agent": "Mozilla/5.0 (compatible; NSE-Screener/2.0; +https://github.com)"}


# ─────────────────────────────────────────────────────────────────────────
# STEP 1 — Get last Friday's date
# ─────────────────────────────────────────────────────────────────────────

def get_last_friday_ddmmyyyy() -> str:
    today     = datetime.now(IST)
    days_back = (today.weekday() - 4) % 7  # 4 = Friday
    friday    = today - timedelta(days=days_back)
    return friday.strftime("%d%m%Y")


# ─────────────────────────────────────────────────────────────────────────
# STEP 2 — Download Bhavcopy
# ─────────────────────────────────────────────────────────────────────────

def download_bhavcopy(date_str: str) -> pd.DataFrame:
    url  = BHAVCOPY_URL.format(date=date_str)
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    df = pd.read_csv(io.StringIO(resp.text))
    # Normalize column names (NSE sometimes has trailing spaces)
    df.columns = [c.strip().upper() for c in df.columns]
    # Keep EQ series (exclude FO, BE, SME, IL, N1, etc.)
    df = df[df["SERIES"].str.strip() == "EQ"].copy()
    df["FETCH_DATE"] = date_str
    print(f"[INFO] Bhavcopy {date_str}: {len(df)} EQ stocks downloaded")
    return df


# ─────────────────────────────────────────────────────────────────────────
# STEP 3 — Connect to Google Sheets
# ─────────────────────────────────────────────────────────────────────────

def connect_sheets() -> gspread.Spreadsheet:
    creds_info = json.loads(GOOGLE_CREDENTIALS_JSON)
    scopes     = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.file",
    ]
    creds  = Credentials.from_service_account_info(creds_info, scopes=scopes)
    client = gspread.authorize(creds)
    return client.open(SHEET_NAME)


# ─────────────────────────────────────────────────────────────────────────
# STEP 4 — Append Bhavcopy to RawData tab (idempotent)
# ─────────────────────────────────────────────────────────────────────────

def append_to_rawdata(sh: gspread.Spreadsheet, df: pd.DataFrame, date_str: str):
    try:
        raw_tab = sh.worksheet("RawData")
    except gspread.WorksheetNotFound:
        raw_tab = sh.add_worksheet("RawData", rows=50000, cols=20)
        # Write header
        raw_tab.append_row(list(df.columns), value_input_option="USER_ENTERED")

    # Idempotency: check if this date already exists
    all_dates = raw_tab.col_values(df.columns.get_loc("FETCH_DATE") + 1)
    if date_str in all_dates:
        print(f"[INFO] {date_str} already in RawData. Skipping append.")
        return

    rows = df.fillna("").values.tolist()
    raw_tab.append_rows(rows, value_input_option="USER_ENTERED")
    print(f"[INFO] Appended {len(rows)} rows to RawData for {date_str}")


# ─────────────────────────────────────────────────────────────────────────
# STEP 5 — Read Config tab (capital base, etc.)
# ─────────────────────────────────────────────────────────────────────────

def read_config(sh: gspread.Spreadsheet) -> dict:
    try:
        cfg_tab = sh.worksheet("Config")
    except gspread.WorksheetNotFound:
        cfg_tab = sh.add_worksheet("Config", rows=20, cols=3)
        # Bootstrap default config
        cfg_tab.update("A1:C5", [
            ["Parameter",       "Value",    "Note"],
            ["CAPITAL_BASE",    1000,       "Update after every trade exit"],
            ["MIN_PRICE",       100,        "Fixed minimum CMP"],
            ["MAX_PRICE",       974,        "Auto-updated by script"],
            ["MIN_AVG_VOLUME",  500000,     "20-day avg volume floor"],
        ])

    records = cfg_tab.get_all_values()
    config  = {}
    for row in records[1:]:  # skip header
        if len(row) >= 2 and row[0]:
            try:
                config[row[0].strip()] = float(str(row[1]).replace("₹","").replace(",",""))
            except ValueError:
                config[row[0].strip()] = row[1]

    capital  = config.get("CAPITAL_BASE", 1000.0)
    max_price = capital - BUFFER - 1.0

    # Write back dynamic MAX_PRICE
    for i, row in enumerate(records):
        if row and row[0].strip() == "MAX_PRICE":
            cfg_tab.update_cell(i + 1, 2, round(max_price, 2))
            break

    print(f"[INFO] Config: CAPITAL=₹{capital}, MAX_PRICE=₹{max_price:.2f}")
    return {"capital_base": capital, "min_price": MIN_PRICE, "max_price": max_price}


# ─────────────────────────────────────────────────────────────────────────
# STEP 6 — Build rolling OHLCV history per symbol from RawData
# ─────────────────────────────────────────────────────────────────────────

def build_symbol_history(sh: gspread.Spreadsheet) -> dict[str, pd.DataFrame]:
    """
    Reads RawData tab and pivots into per-symbol DataFrames with
    columns: [CLOSE, HIGH, LOW, OPEN, TOTTRDQTY] indexed by date.
    Returns dict: symbol -> DataFrame (sorted oldest first)
    """
    raw_tab = sh.worksheet("RawData")
    records = raw_tab.get_all_records()

    if not records:
        return {}

    df_all = pd.DataFrame(records)
    df_all.columns = [c.strip().upper() for c in df_all.columns]

    needed = ["SYMBOL", "FETCH_DATE", "OPEN", "HIGH", "LOW", "CLOSE", "TOTTRDQTY"]
    for col in needed:
        if col not in df_all.columns:
            print(f"[WARN] Column {col} missing from RawData")
            return {}

    for col in ["OPEN", "HIGH", "LOW", "CLOSE", "TOTTRDQTY"]:
        df_all[col] = pd.to_numeric(df_all[col], errors="coerce")

    history = {}
    for sym, grp in df_all.groupby("SYMBOL"):
        grp = grp.sort_values("FETCH_DATE").set_index("FETCH_DATE")
        history[sym] = grp[["OPEN", "HIGH", "LOW", "CLOSE", "TOTTRDQTY"]].rename(
            columns={"TOTTRDQTY": "Volume"}
        )

    print(f"[INFO] History built for {len(history)} symbols")
    return history


# ─────────────────────────────────────────────────────────────────────────
# STEP 7 — Technical Indicators
# ─────────────────────────────────────────────────────────────────────────

def rsi(series: pd.Series, n: int = 14) -> float:
    delta = series.diff()
    gain  = delta.clip(lower=0).rolling(n).mean()
    loss  = (-delta.clip(upper=0)).rolling(n).mean()
    rs    = gain / loss.replace(0, np.nan)
    return float((100 - 100 / (1 + rs)).iloc[-1])


def atr(df: pd.DataFrame, n: int = 14) -> float:
    h, l, c = df["HIGH"], df["LOW"], df["CLOSE"]
    pc = c.shift(1)
    tr = pd.concat([(h - l), (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return float(tr.rolling(n).mean().iloc[-1])


# ─────────────────────────────────────────────────────────────────────────
# STEP 8 — Screen & Score each symbol
# ─────────────────────────────────────────────────────────────────────────

def screen_symbol(sym: str, df: pd.DataFrame, config: dict) -> dict | None:
    if len(df) < 250:
        return None

    close = df["CLOSE"]
    cmp   = float(close.iloc[-1])

    if not (config["min_price"] <= cmp <= config["max_price"]):
        return None
    if math.isnan(cmp) or cmp <= 0:
        return None

    # Anti-downfall
    if len(close) <= 41:
        return None
    roc_20 = (cmp - close.iloc[-21]) / close.iloc[-21]
    roc_40 = (cmp - close.iloc[-41]) / close.iloc[-41]
    if roc_20 <= -0.03 or roc_40 <= 0:   # -3% buffer on 1M, strict 0 on 2M
        return None

    # Trend regime
    sma_50  = float(close.rolling(50).mean().iloc[-1])
    sma_200 = float(close.rolling(200).mean().iloc[-1])
    if not (cmp > sma_50 > sma_200):
        return None

    # 52W proximity
    high_52w = float(df["HIGH"].iloc[-252:].max())
    dist_52w = (cmp - high_52w) / high_52w
    if dist_52w < -0.15:
        return None

    # Volume
    avg_vol_20 = float(df["Volume"].rolling(20).mean().iloc[-1])
    if avg_vol_20 < MIN_AVG_VOLUME:
        return None

    # RSI guard
    rsi_val = rsi(close)
    if not (40 <= rsi_val <= 70):
        return None

    # CMS
    roc_60    = ((cmp - close.iloc[-61]) / close.iloc[-61]) * 100
    prox_score = (1 - abs(dist_52w)) * 100
    raw_vr     = df["Volume"].iloc[-5:].mean() / df["Volume"].iloc[-50:].mean()
    vol_score  = min(max((raw_vr - 0.5) / 2.5, 0), 1) * 100
    cms        = 0.50 * roc_60 + 0.30 * prox_score + 0.20 * vol_score

    # ATR stop
    atr_val     = atr(df)
    initial_stop = round(max(cmp - 2 * atr_val, cmp * (1 - STOP_PCT)), 2)

    capital    = config["capital_base"]
    shares     = int((capital - BUFFER) // cmp)
    if shares < 1:
        return None

    return {
        "STATUS":           "ACTIVE_SIGNAL",
        "SYMBOL":           sym.replace(".NS", ""),
        "CMP":              round(cmp, 2),
        "CMS_SCORE":        round(cms, 2),
        "ROC_1M":           f"+{round(roc_20*100,2)}%",
        "ROC_2M":           f"+{round(roc_40*100,2)}%",
        "ROC_3M":           f"+{round(roc_60,2)}%",
        "RSI_14":           round(rsi_val, 1),
        "SMA_50":           round(sma_50, 2),
        "SMA_200":          round(sma_200, 2),
        "ATR_14":           round(atr_val, 2),
        "HIGH_52W":         round(high_52w, 2),
        "SHARES":           shares,
        "CAPITAL_REQUIRED": round(shares * cmp, 2),
        "INITIAL_STOP":     initial_stop,
        "M1_TARGET":        round(cmp * (1 + M1_PCT), 2),
        "M1_STOP":          round(cmp * (1 + M1_STOP_PCT), 2),
        "M2_TARGET":        round(cmp * (1 + M2_PCT), 2),
        "M2_STOP":          round(cmp * (1 + M2_STOP_PCT), 2),
        "M3_TARGET":        round(cmp * (1 + M3_PCT), 2),
        "CAPITAL_BASE":     capital,
        "TOTAL_QUALIFIED":  0,   # filled after screening all symbols
    }


# ─────────────────────────────────────────────────────────────────────────
# STEP 9 — Write Signal tab (read by PWA app via published CSV URL)
# ─────────────────────────────────────────────────────────────────────────

SIGNAL_COLS = [
    "STATUS", "TIMESTAMP", "SYMBOL", "CMP", "CMS_SCORE",
    "ROC_1M", "ROC_2M", "ROC_3M", "RSI_14",
    "SMA_50", "SMA_200", "ATR_14", "HIGH_52W",
    "SHARES", "CAPITAL_REQUIRED",
    "INITIAL_STOP", "M1_TARGET", "M1_STOP",
    "M2_TARGET", "M2_STOP", "M3_TARGET",
    "CAPITAL_BASE", "TOTAL_QUALIFIED",
]


def write_signal_tab(sh: gspread.Spreadsheet, candidates: list[dict], config: dict):
    try:
        sig_tab = sh.worksheet("Signal")
        sig_tab.clear()
    except gspread.WorksheetNotFound:
        sig_tab = sh.add_worksheet("Signal", rows=10, cols=len(SIGNAL_COLS))

    now_ist = datetime.now(IST).strftime("%Y-%m-%d %H:%M IST")
    total   = len(candidates)

    if not candidates:
        rows = [SIGNAL_COLS, [
            "CASH", now_ist,
            "—", "—", "—", "—", "—", "—", "—",
            "—", "—", "—", "—", "—", "—",
            "—", "—", "—", "—", "—", "—",
            config["capital_base"], 0,
        ]]
    else:
        rows = [SIGNAL_COLS]
        for rank, c in enumerate(candidates[:3]):  # top 3 rows
            c["TOTAL_QUALIFIED"] = total
            c["TIMESTAMP"]       = now_ist
            rows.append([c.get(col, "") for col in SIGNAL_COLS])

    sig_tab.update(rows, value_input_option="USER_ENTERED")
    print(f"[INFO] Signal tab written: {candidates[0]['SYMBOL'] if candidates else 'CASH'}")


# ─────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────

def main():
    date_str = get_last_friday_ddmmyyyy()
    print(f"\n{'='*60}")
    print(f"NSE Momentum Engine — {date_str}")
    print(f"{'='*60}")

    # Download today's data
    today_df = download_bhavcopy(date_str)

    # Connect to Google Sheets
    sh = connect_sheets()

    # Append to history
    append_to_rawdata(sh, today_df, date_str)

    # Read config (capital, price limits)
    config = read_config(sh)

    # Build rolling history per symbol
    history = build_symbol_history(sh)

    if len(history) == 0:
        print("[WARN] Not enough history yet for indicator-based screening.")
        print("[INFO] Writing CASH signal — run again after a few weeks of data accumulation.")
        write_signal_tab(sh, [], config)
        return

    # Screen all symbols
    candidates = []
    for sym, df_sym in history.items():
        result = screen_symbol(sym, df_sym, config)
        if result:
            candidates.append(result)

    print(f"[INFO] Qualified: {len(candidates)} / {len(history)} stocks")

    # Sort by CMS descending
    candidates.sort(key=lambda x: x["CMS_SCORE"], reverse=True)

    # Write Signal tab
    write_signal_tab(sh, candidates, config)

    # Console summary
    if candidates:
        w = candidates[0]
        print(f"\n🏆 WINNER: {w['SYMBOL']} @ ₹{w['CMP']}")
        print(f"   CMS: {w['CMS_SCORE']} | RSI: {w['RSI_14']} | ATR: {w['ATR_14']}")
        print(f"   Stop: ₹{w['INITIAL_STOP']} | M1: ₹{w['M1_TARGET']} | M2: ₹{w['M2_TARGET']}")
        print(f"   Buy: {w['SHARES']} shares @ ₹{w['CAPITAL_REQUIRED']}")
    else:
        print("\n📉 CASH — Market breadth weak. No stocks passed all filters.")

    print(f"\n✅ Done. Check Google Sheets → Signal tab for full output.")


if __name__ == "__main__":
    main()
