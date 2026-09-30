#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
setup_sheets.py — Auto-create and configure the 'NSE Momentum Engine' Google Sheet.

Usage:
    python scripts/setup_sheets.py --creds path/to/creds.json
    python scripts/setup_sheets.py --creds path/to/creds.json --share myemail@gmail.com

Or via environment variable:
    GOOGLE_CREDENTIALS_JSON='{...json...}' python scripts/setup_sheets.py
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime

# Fix Windows console UTF-8 emoji encoding
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

# ──────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ──────────────────────────────────────────────────────────────────────────────
SPREADSHEET_NAME = "NSE Momentum Engine"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# Tab names in order
TAB_CONFIG     = "Config"
TAB_RAWDATA    = "RawData"
TAB_INDICATORS = "Indicators"
TAB_SCREENER   = "Screener"
TAB_SIGNAL     = "Signal"
ALL_TABS       = [TAB_CONFIG, TAB_RAWDATA, TAB_INDICATORS, TAB_SCREENER, TAB_SIGNAL]

# Colour helpers (RGB → gspread userEnteredFormat dicts)
def rgb(r, g, b):
    return {"red": r / 255, "green": g / 255, "blue": b / 255}

COLOUR_DARK_BLUE   = rgb(23, 54, 93)    # header rows
COLOUR_WHITE       = rgb(255, 255, 255)
COLOUR_LIGHT_BLUE  = rgb(173, 216, 230) # CAPITAL_BASE highlight
COLOUR_GREEN       = rgb(0, 204, 102)   # ACTIVE_SIGNAL
COLOUR_GREY_BG     = rgb(189, 189, 189) # CASH
COLOUR_GREY_TEXT   = rgb(120, 120, 120) # instruction row text
COLOUR_YELLOW_HDR  = rgb(255, 192, 0)   # Indicators / Screener header alternative

# ──────────────────────────────────────────────────────────────────────────────
# CREDENTIAL LOADING
# ──────────────────────────────────────────────────────────────────────────────

def load_credentials(creds_path: str | None) -> Credentials:
    """Load service-account credentials from a JSON file or the env variable."""
    env_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")

    if env_json:
        print("🔑  Loading credentials from GOOGLE_CREDENTIALS_JSON env var …")
        try:
            info = json.loads(env_json)
        except json.JSONDecodeError as exc:
            print(f"❌  GOOGLE_CREDENTIALS_JSON is not valid JSON: {exc}")
            sys.exit(1)
        return Credentials.from_service_account_info(info, scopes=SCOPES)

    if creds_path:
        if not os.path.isfile(creds_path):
            print(f"❌  Credentials file not found: {creds_path}")
            sys.exit(1)
        print(f"🔑  Loading credentials from {creds_path} …")
        return Credentials.from_service_account_file(creds_path, scopes=SCOPES)

    print("❌  No credentials provided. Use --creds or set GOOGLE_CREDENTIALS_JSON.")
    sys.exit(1)


# ──────────────────────────────────────────────────────────────────────────────
# SPREADSHEET OPEN / CREATE
# ──────────────────────────────────────────────────────────────────────────────

def open_or_create_spreadsheet(gc: gspread.Client, service_email: str = "") -> gspread.Spreadsheet:
    """Open existing spreadsheet or create a new one."""
    try:
        sh = gc.open(SPREADSHEET_NAME)
        print(f"📂  Opened existing spreadsheet: '{SPREADSHEET_NAME}'")
        return sh
    except gspread.SpreadsheetNotFound:
        try:
            sh = gc.create(SPREADSHEET_NAME)
            print(f"✨  Created new spreadsheet: '{SPREADSHEET_NAME}'")
            return sh
        except Exception as e:
            email_hint = service_email or "your service account email"
            print("\n" + "═" * 65)
            print("⚠️  Google Cloud Service Accounts have 0 MB of Drive storage.")
            print(f"    Error: {e}")
            print("\n👉  QUICK 30-SECOND FIX (Do this once):")
            print(f"    1. Open your browser and go to: https://sheets.new")
            print(f"    2. Name the blank spreadsheet: '{SPREADSHEET_NAME}'")
            print(f"    3. Click 'Share' (top right) and paste your bot's email:")
            print(f"       👉  {email_hint}")
            print(f"    4. Set permission to 'Editor' and click 'Share'.")
            print(f"    5. Re-run this command: python scripts/setup_sheets.py --creds path/to/key.json")
            print("═" * 65 + "\n")
            sys.exit(1)


# ──────────────────────────────────────────────────────────────────────────────
# TAB MANAGEMENT HELPERS
# ──────────────────────────────────────────────────────────────────────────────

def get_or_create_tab(sh: gspread.Spreadsheet, title: str) -> gspread.Worksheet:
    """Return an existing worksheet or add a new one."""
    try:
        ws = sh.worksheet(title)
        print(f"   📄  Tab '{title}' already exists — will reconfigure.")
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=title, rows=1000, cols=30)
        print(f"   ➕  Created tab '{title}'.")
    return ws


def delete_default_sheet_if_present(sh: gspread.Spreadsheet):
    """Remove the default 'Sheet1' tab that Google creates automatically."""
    try:
        default = sh.worksheet("Sheet1")
        # Only delete if there are other worksheets present
        if len(sh.worksheets()) > 1:
            sh.del_worksheet(default)
            print("   🗑️   Removed default 'Sheet1' tab.")
    except gspread.WorksheetNotFound:
        pass


# ──────────────────────────────────────────────────────────────────────────────
# SHEETS API BATCH-UPDATE HELPER
# ──────────────────────────────────────────────────────────────────────────────

def batch_update(service, spreadsheet_id: str, requests: list):
    """Execute a batchUpdate via the Sheets v4 REST API."""
    if not requests:
        return
    body = {"requests": requests}
    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id, body=body
    ).execute()
    # Small sleep to avoid quota bursts
    time.sleep(0.5)


def freeze_rows(sheet_id: int, count: int = 1) -> dict:
    return {
        "updateSheetProperties": {
            "properties": {
                "sheetId": sheet_id,
                "gridProperties": {"frozenRowCount": count},
            },
            "fields": "gridProperties.frozenRowCount",
        }
    }


def bold_row(sheet_id: int, row_index: int) -> dict:
    """Bold a single row (0-based row_index)."""
    return {
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": row_index,
                "endRowIndex": row_index + 1,
            },
            "cell": {
                "userEnteredFormat": {
                    "textFormat": {"bold": True}
                }
            },
            "fields": "userEnteredFormat.textFormat.bold",
        }
    }


def colour_range(sheet_id: int, start_row: int, end_row: int,
                 start_col: int, end_col: int, bg: dict, fg: dict | None = None) -> dict:
    fmt = {"backgroundColor": bg}
    if fg:
        fmt["textFormat"] = {"foregroundColor": fg, "bold": True}
    return {
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": start_row,
                "endRowIndex": end_row,
                "startColumnIndex": start_col,
                "endColumnIndex": end_col,
            },
            "cell": {"userEnteredFormat": fmt},
            "fields": "userEnteredFormat.backgroundColor"
                      + (",userEnteredFormat.textFormat" if fg else ""),
        }
    }


def number_format_range(sheet_id: int, start_row: int, end_row: int,
                         start_col: int, end_col: int, pattern: str, fmt_type: str = "NUMBER") -> dict:
    return {
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": start_row,
                "endRowIndex": end_row,
                "startColumnIndex": start_col,
                "endColumnIndex": end_col,
            },
            "cell": {
                "userEnteredFormat": {
                    "numberFormat": {"type": fmt_type, "pattern": pattern}
                }
            },
            "fields": "userEnteredFormat.numberFormat",
        }
    }


def add_note(service, spreadsheet_id: str, sheet_id: int, row: int, col: int, note: str):
    """Add a note (comment) to a single cell."""
    batch_update(service, spreadsheet_id, [
        {
            "updateCells": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": row,
                    "endRowIndex": row + 1,
                    "startColumnIndex": col,
                    "endColumnIndex": col + 1,
                },
                "rows": [{"values": [{"note": note}]}],
                "fields": "note",
            }
        }
    ])


def merge_cells(sheet_id: int, start_row: int, end_row: int,
                start_col: int, end_col: int) -> dict:
    return {
        "mergeCells": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": start_row,
                "endRowIndex": end_row,
                "startColumnIndex": start_col,
                "endColumnIndex": end_col,
            },
            "mergeType": "MERGE_ALL",
        }
    }


def add_conditional_formatting(sheet_id: int, col_index: int,
                                 text_value: str, bg_colour: dict) -> dict:
    """Add a conditional formatting rule: if cell text == text_value → apply bg_colour."""
    return {
        "addConditionalFormatRule": {
            "rule": {
                "ranges": [{
                    "sheetId": sheet_id,
                    "startRowIndex": 1,          # row 2 onwards (0-based)
                    "startColumnIndex": col_index,
                    "endColumnIndex": col_index + 1,
                }],
                "booleanRule": {
                    "condition": {
                        "type": "TEXT_EQ",
                        "values": [{"userEnteredValue": text_value}],
                    },
                    "format": {"backgroundColor": bg_colour},
                },
            },
            "index": 0,
        }
    }


def set_column_width(sheet_id: int, col_index: int, pixel_width: int) -> dict:
    return {
        "updateDimensionProperties": {
            "range": {
                "sheetId": sheet_id,
                "dimension": "COLUMNS",
                "startIndex": col_index,
                "endIndex": col_index + 1,
            },
            "properties": {"pixelSize": pixel_width},
            "fields": "pixelSize",
        }
    }


# ──────────────────────────────────────────────────────────────────────────────
# TAB 1: Config
# ──────────────────────────────────────────────────────────────────────────────

def setup_config_tab(sh: gspread.Spreadsheet, service):
    print("\n📋  Configuring Tab 1: Config …")
    ws = get_or_create_tab(sh, TAB_CONFIG)
    ws.clear()
    sid = ws.id
    spread_id = sh.id

    headers = ["Parameter", "Value", "Note"]
    rows = [
        ["CAPITAL_BASE",    1000,           "Update after every exit"],
        ["MIN_PRICE",        100,           "Fixed minimum CMP"],
        ["MAX_PRICE",       "=B2-26",       "Auto-calculated by script each Friday"],
        ["MIN_AVG_VOLUME",  500000,         "20-day volume floor"],
        ["STOP_PCT",         0.07,          "7% hard stop"],
        ["M1_TARGET_PCT",    0.15,          "+15% Milestone 1"],
        ["M2_TARGET_PCT",    0.30,          "+30% Milestone 2"],
        ["M3_TARGET_PCT",    0.50,          "+50% Milestone 3"],
        ["M1_STOP_PCT",      0.025,         "+2.5% ratchet after M1"],
        ["M2_STOP_PCT",      0.15,          "+15% ratchet after M2"],
    ]

    all_data = [headers] + rows
    ws.update("A1", all_data, value_input_option="USER_ENTERED")

    requests = [
        # Freeze row 1
        freeze_rows(sid, 1),
        # Bold header row
        bold_row(sid, 0),
        # Dark-blue header
        colour_range(sid, 0, 1, 0, 3, COLOUR_DARK_BLUE, COLOUR_WHITE),
        # Light-blue highlight on CAPITAL_BASE row (row 2, 0-based index 1)
        colour_range(sid, 1, 2, 0, 3, COLOUR_LIGHT_BLUE),
        # Currency format for B2 (CAPITAL_BASE)
        number_format_range(sid, 1, 2, 1, 2, "₹#,##0.00", "CURRENCY"),
        # Number format for B3:B11
        number_format_range(sid, 2, 11, 1, 2, "0.######", "NUMBER"),
        # Column widths
        set_column_width(sid, 0, 180),
        set_column_width(sid, 1, 120),
        set_column_width(sid, 2, 300),
    ]
    batch_update(service, spread_id, requests)
    print("   ✅  Config tab ready.")


# ──────────────────────────────────────────────────────────────────────────────
# TAB 2: RawData
# ──────────────────────────────────────────────────────────────────────────────

def setup_rawdata_tab(sh: gspread.Spreadsheet, service):
    print("\n📥  Configuring Tab 2: RawData …")
    ws = get_or_create_tab(sh, TAB_RAWDATA)
    ws.clear()
    sid = ws.id
    spread_id = sh.id

    headers = [
        "SYMBOL", "SERIES", "OPEN", "HIGH", "LOW", "CLOSE",
        "LAST", "PREVCLOSE", "TOTTRDQTY", "TOTTRDVAL",
        "TIMESTAMP", "TOTALTRADES", "ISIN", "FETCH_DATE"
    ]
    ws.update("A1", [headers])

    requests = [
        freeze_rows(sid, 1),
        bold_row(sid, 0),
        colour_range(sid, 0, 1, 0, len(headers), COLOUR_DARK_BLUE, COLOUR_WHITE),
        set_column_width(sid, 0, 120),   # SYMBOL
        set_column_width(sid, 1, 80),    # SERIES
        set_column_width(sid, 10, 150),  # TIMESTAMP
        set_column_width(sid, 13, 120),  # FETCH_DATE
    ]
    batch_update(service, spread_id, requests)

    # Add note to A1
    add_note(service, spread_id, sid, 0, 0,
             "Auto-filled every Friday by GitHub Actions. Do not edit.")
    print("   ✅  RawData tab ready.")


# ──────────────────────────────────────────────────────────────────────────────
# TAB 3: Indicators
# ──────────────────────────────────────────────────────────────────────────────

def setup_indicators_tab(sh: gspread.Spreadsheet, service):
    print("\n📊  Configuring Tab 3: Indicators …")
    ws = get_or_create_tab(sh, TAB_INDICATORS)
    ws.clear()
    sid = ws.id
    spread_id = sh.id

    headers = [
        "SYMBOL", "LATEST_CLOSE", "HIGH_52W", "DATA_POINTS",
        "HAS_HISTORY", "SMA_50_APPROX", "SMA_200_APPROX",
        "ROC_20", "ROC_40", "ROC_60", "VOL_20_AVG",
        "PROX_52W", "CMS_SCORE_APPROX"
    ]
    ws.update("A1", [headers])

    # Formula row 2: SYMBOL list via SORT/UNIQUE/FILTER from RawData
    formula_a2 = '=IFERROR(SORT(UNIQUE(FILTER(RawData!A2:A,RawData!A2:A<>""))),"No data")'
    # LATEST_CLOSE: index into RawData using QUERY
    formula_b2 = (
        '=IFERROR(INDEX(QUERY(RawData!$A:$N,'
        '"SELECT F WHERE A=\'"&A2&"\' ORDER BY N DESC LIMIT 1",0),1,1),"")'
    )

    ws.update("A2", [[formula_a2]], value_input_option="USER_ENTERED")
    ws.update("B2", [[formula_b2]], value_input_option="USER_ENTERED")

    requests = [
        freeze_rows(sid, 1),
        bold_row(sid, 0),
        colour_range(sid, 0, 1, 0, len(headers), COLOUR_DARK_BLUE, COLOUR_WHITE),
        set_column_width(sid, 0, 120),
        set_column_width(sid, 1, 120),
    ]
    batch_update(service, spread_id, requests)

    # Notes
    add_note(service, spread_id, sid, 0, 0,
             "Computed from RawData. Full indicator computation (SMA, RSI, ATR) is done by "
             "the Python data_pump.py script. These formulas give approximate values.")

    # Notes on columns that need Python computation
    col_notes = {
        2: "HIGH_52W — Computed by data_pump.py (max CLOSE over 52 weeks).",
        3: "DATA_POINTS — Number of daily rows available for this symbol.",
        4: "HAS_HISTORY — TRUE if DATA_POINTS >= 200.",
        5: "SMA_50_APPROX — Simple moving average over last 50 closes (Python).",
        6: "SMA_200_APPROX — Simple moving average over last 200 closes (Python).",
        7: "ROC_20 — Rate of Change over 20 trading days (Python).",
        8: "ROC_40 — Rate of Change over 40 trading days (Python).",
        9: "ROC_60 — Rate of Change over 60 trading days (Python).",
        10: "VOL_20_AVG — Average daily traded quantity over last 20 days (Python).",
        11: "PROX_52W — CMP / 52-week-high proximity ratio (Python).",
        12: "CMS_SCORE_APPROX — Composite Momentum Score (Python). Ranks stocks.",
    }
    for col_idx, note_text in col_notes.items():
        add_note(service, spread_id, sid, 0, col_idx, note_text)

    print("   ✅  Indicators tab ready.")


# ──────────────────────────────────────────────────────────────────────────────
# TAB 4: Screener
# ──────────────────────────────────────────────────────────────────────────────

def setup_screener_tab(sh: gspread.Spreadsheet, service):
    print("\n🔍  Configuring Tab 4: Screener …")
    ws = get_or_create_tab(sh, TAB_SCREENER)
    ws.clear()
    sid = ws.id
    spread_id = sh.id

    headers = [
        "SYMBOL", "CMP", "CMS_SCORE", "RSI_14", "ROC_1M", "ROC_2M", "ROC_3M",
        "SMA_50", "SMA_200", "ATR_14", "HIGH_52W", "SHARES", "CAPITAL_REQ",
        "INITIAL_STOP", "M1_TARGET", "M2_TARGET", "M3_TARGET", "PASSES_ALL"
    ]
    instruction_row = [
        "Data written here by GitHub Actions every Friday at 16:00 IST"
    ] + [""] * (len(headers) - 1)

    ws.update("A1", [headers, instruction_row])

    requests = [
        freeze_rows(sid, 1),
        bold_row(sid, 0),
        colour_range(sid, 0, 1, 0, len(headers), COLOUR_DARK_BLUE, COLOUR_WHITE),
        # Grey text for instruction row
        {
            "repeatCell": {
                "range": {
                    "sheetId": sid,
                    "startRowIndex": 1,
                    "endRowIndex": 2,
                },
                "cell": {
                    "userEnteredFormat": {
                        "textFormat": {
                            "foregroundColor": COLOUR_GREY_TEXT,
                            "italic": True,
                        }
                    }
                },
                "fields": "userEnteredFormat.textFormat.foregroundColor,"
                          "userEnteredFormat.textFormat.italic",
            }
        },
        set_column_width(sid, 0, 120),
        set_column_width(sid, 1, 90),
        set_column_width(sid, 2, 110),
        set_column_width(sid, 17, 110),  # PASSES_ALL
    ]
    batch_update(service, spread_id, requests)

    add_note(service, spread_id, sid, 0, 0,
             "This tab is populated by data_pump.py (Python). "
             "The Signal tab contains the rank #1 winner. Do not edit this tab.")
    print("   ✅  Screener tab ready.")


# ──────────────────────────────────────────────────────────────────────────────
# TAB 5: Signal
# ──────────────────────────────────────────────────────────────────────────────

def setup_signal_tab(sh: gspread.Spreadsheet, service):
    print("\n📡  Configuring Tab 5: Signal …")
    ws = get_or_create_tab(sh, TAB_SIGNAL)
    ws.clear()
    sid = ws.id
    spread_id = sh.id

    headers = [
        "STATUS", "TIMESTAMP", "SYMBOL", "CMP", "CMS_SCORE",
        "ROC_1M", "ROC_2M", "ROC_3M", "RSI_14", "SMA_50", "SMA_200",
        "ATR_14", "HIGH_52W", "SHARES", "CAPITAL_REQUIRED", "INITIAL_STOP",
        "M1_TARGET", "M1_STOP", "M2_TARGET", "M2_STOP", "M3_TARGET",
        "CAPITAL_BASE", "TOTAL_QUALIFIED"
    ]
    n_cols = len(headers)  # 23

    now_ts = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    placeholder_row = ["CASH", now_ts] + ["—"] * (n_cols - 2)

    ws.update("A1", [headers, placeholder_row])

    requests = [
        freeze_rows(sid, 1),
        bold_row(sid, 0),
        # Dark-blue header
        colour_range(sid, 0, 1, 0, n_cols, COLOUR_DARK_BLUE, COLOUR_WHITE),
        # Bold headers
        {
            "repeatCell": {
                "range": {
                    "sheetId": sid,
                    "startRowIndex": 0,
                    "endRowIndex": 1,
                },
                "cell": {
                    "userEnteredFormat": {
                        "textFormat": {"bold": True, "foregroundColor": COLOUR_WHITE}
                    }
                },
                "fields": "userEnteredFormat.textFormat.bold,"
                          "userEnteredFormat.textFormat.foregroundColor",
            }
        },
        # Conditional formatting — ACTIVE_SIGNAL → green
        add_conditional_formatting(sid, 0, "ACTIVE_SIGNAL", COLOUR_GREEN),
        # Conditional formatting — CASH → grey
        add_conditional_formatting(sid, 0, "CASH", COLOUR_GREY_BG),
        # Column widths
        set_column_width(sid, 0, 140),   # STATUS
        set_column_width(sid, 1, 180),   # TIMESTAMP
        set_column_width(sid, 2, 120),   # SYMBOL
        set_column_width(sid, 3, 90),    # CMP
        set_column_width(sid, 4, 110),   # CMS_SCORE
        set_column_width(sid, 14, 150),  # CAPITAL_REQUIRED
        set_column_width(sid, 15, 130),  # INITIAL_STOP
    ]
    batch_update(service, spread_id, requests)

    add_note(service, spread_id, sid, 0, 0,
             "READ-ONLY — Written by data_pump.py every Friday. "
             "Published as CSV for the NSE Signal mobile app.")
    print("   ✅  Signal tab ready.")


# ──────────────────────────────────────────────────────────────────────────────
# TAB ORDERING
# ──────────────────────────────────────────────────────────────────────────────

def reorder_tabs(sh: gspread.Spreadsheet, service):
    """Reorder tabs to match the desired sequence."""
    print("\n🔀  Reordering tabs …")
    worksheets = {ws.title: ws for ws in sh.worksheets()}
    requests = []
    for idx, tab_name in enumerate(ALL_TABS):
        if tab_name in worksheets:
            requests.append({
                "updateSheetProperties": {
                    "properties": {
                        "sheetId": worksheets[tab_name].id,
                        "index": idx,
                    },
                    "fields": "index",
                }
            })
    batch_update(service, sh.id, requests)
    print("   ✅  Tab order set.")


# ──────────────────────────────────────────────────────────────────────────────
# SHARING
# ──────────────────────────────────────────────────────────────────────────────

def share_with_email(sh: gspread.Spreadsheet, email: str):
    """Share the spreadsheet with the given email as Editor."""
    print(f"\n📤  Sharing spreadsheet with {email} …")
    sh.share(email, perm_type="user", role="writer", notify=True)
    print(f"   ✅  Shared with {email} (Editor).")


# ──────────────────────────────────────────────────────────────────────────────
# FINAL CHECKLIST + INSTRUCTIONS
# ──────────────────────────────────────────────────────────────────────────────

def print_summary(sh: gspread.Spreadsheet, share_email: str | None):
    spread_url = f"https://docs.google.com/spreadsheets/d/{sh.id}"
    signal_gid = None
    for ws in sh.worksheets():
        if ws.title == TAB_SIGNAL:
            signal_gid = ws.id
            break

    print("\n" + "=" * 65)
    print("🏁  SETUP COMPLETE — NSE Momentum Engine")
    print("=" * 65)
    print(f"\n📋  Spreadsheet Name : {SPREADSHEET_NAME}")
    print(f"🔗  Spreadsheet URL  : {spread_url}")
    print(f"🆔  Spreadsheet ID   : {sh.id}")
    if signal_gid is not None:
        print(f"📡  Signal Sheet GID : {signal_gid}")

    print("\n" + "-" * 65)
    print("📌  PUBLISH SIGNAL TAB AS CSV (for PWA app)")
    print("-" * 65)
    print("  1. Open the spreadsheet URL above in a browser.")
    print("  2. Go to  File → Share → Publish to web")
    print("  3. In the first dropdown, select  'Signal'")
    print("  4. In the second dropdown, select 'Comma-separated values (.csv)'")
    print("  5. Click  'Publish'  and confirm.")
    print("  6. Copy the published CSV URL — it looks like:")
    print(f"     https://docs.google.com/spreadsheets/d/{sh.id}")
    print("     /pub?gid=<SIGNAL_GID>&single=true&output=csv")
    if signal_gid:
        csv_url = (
            f"https://docs.google.com/spreadsheets/d/{sh.id}"
            f"/pub?gid={signal_gid}&single=true&output=csv"
        )
        print(f"\n     Likely URL → {csv_url}")
    print("  7. Paste this URL into your PWA app's config / .env.")

    print("\n" + "-" * 65)
    print("🔐  SHARING THE SHEET WITH YOUR SERVICE ACCOUNT")
    print("-" * 65)
    print("  If you haven't already, share the sheet with the service")
    print("  account email (found in your credentials JSON under 'client_email')")
    print("  and grant it 'Editor' access.")
    print("  Use:  python scripts/setup_sheets.py --creds creds.json --share <email>")

    print("\n" + "-" * 65)
    print("✅  DONE CHECKLIST")
    print("-" * 65)
    items = [
        ("Config tab created & formatted",          True),
        ("RawData tab created with 14 headers",     True),
        ("Indicators tab with SORT/UNIQUE formula", True),
        ("Screener tab with instruction row",       True),
        ("Signal tab with conditional formatting",  True),
        ("All header rows: dark-blue, white text",  True),
        ("CAPITAL_BASE row highlighted light-blue", True),
        ("Tabs reordered correctly",                True),
        ("Signal placeholder row (CASH) added",    True),
        (f"Shared with {share_email}",              share_email is not None),
    ]
    for label, done in items:
        icon = "✅" if done else "⬜"
        print(f"  {icon}  {label}")

    print("\n" + "=" * 65)
    print("🚀  Next step: run  python scripts/data_pump.py  to fill data.")
    print("=" * 65 + "\n")


# ──────────────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(
        description="Auto-create and configure the NSE Momentum Engine Google Sheet."
    )
    parser.add_argument(
        "--creds",
        metavar="PATH",
        help="Path to the service-account JSON credentials file.",
    )
    parser.add_argument(
        "--share",
        metavar="EMAIL",
        help="Email address to share the spreadsheet with (Editor access).",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    print("\n🚀  NSE Momentum Engine — Google Sheet Setup")
    print("=" * 65)

    # ── 1. Credentials
    creds = load_credentials(args.creds)

    # ── 2. gspread client
    gc = gspread.authorize(creds)

    # ── 3. Sheets v4 service (for advanced formatting)
    service = build("sheets", "v4", credentials=creds)

    # ── 4. Open / create spreadsheet
    service_email = getattr(creds, "service_account_email", "")
    sh = open_or_create_spreadsheet(gc, service_email)

    # ── 5. Ensure all required tabs exist first (so reorder works)
    print("\n🗂️   Ensuring all 5 tabs exist …")
    for tab_name in ALL_TABS:
        get_or_create_tab(sh, tab_name)

    # ── 6. Remove default Sheet1 if it snuck in
    delete_default_sheet_if_present(sh)

    # ── 7. Configure each tab
    setup_config_tab(sh, service)
    setup_rawdata_tab(sh, service)
    setup_indicators_tab(sh, service)
    setup_screener_tab(sh, service)
    setup_signal_tab(sh, service)

    # ── 8. Reorder tabs
    reorder_tabs(sh, service)

    # ── 9. Optional sharing
    if args.share:
        share_with_email(sh, args.share)

    # ── 10. Print summary
    print_summary(sh, args.share)


if __name__ == "__main__":
    main()
