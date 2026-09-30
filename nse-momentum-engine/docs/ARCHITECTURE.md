# Architecture — NSE Momentum Engine

> This document is the single source of truth for system design. Written to be understood by both humans and AI agents modifying this codebase.

---

## System Overview

A **weekly quantitative momentum screener** for NSE-listed Indian equities, built for:
- **Capital**: ₹1,000 starting (fully compounding, single-position)
- **Platform**: Zerodha Kite (execution) + Google Sheets (data/brain) + GitHub Actions (compute)
- **Interface**: Android PWA app (no PC, no terminal)
- **Cost**: ₹0/month (GitHub Actions free tier + Google Sheets free + Kite Personal API free)

---

## Data Flow (Detailed)

```
[NSE Archives — Official Source of Truth]
  URL: nsearchives.nseindia.com/products/content/sec_bhavdata_full_DDMMYYYY.csv
  Format: CSV, ~1,800 rows, one per EQ-series stock
  Columns: SYMBOL, SERIES, OPEN, HIGH, LOW, CLOSE, LAST, PREVCLOSE,
           TOTTRDQTY, TOTTRDVAL, TIMESTAMP, TOTALTRADES, ISIN
  Availability: ~16:30 IST each trading day
  Cost: Free (HTTP GET, no auth required)
  User-Agent: Required to avoid 403 blocks

       │  Weekly download (Friday)
       ▼

[src/data_pump.py — GitHub Actions Runner]
  1. get_last_friday_ddmmyyyy()   → date string for download URL
  2. download_bhavcopy(date)      → pd.DataFrame (EQ series only)
  3. connect_sheets()             → gspread.Spreadsheet object
  4. append_to_rawdata(sh, df)    → idempotent append to RawData tab
  5. read_config(sh)              → dict: capital, min/max price
  6. build_symbol_history(sh)     → dict: symbol → DataFrame (OHLCV, sorted)
  7. screen_symbol(sym, df, cfg)  → dict or None (if filtered out)
  8. write_signal_tab(sh, results)→ writes top-3 rows to Signal tab

       │  gspread (Google Sheets API v4)
       ▼

[Google Sheets — "NSE Momentum Engine"]
  ├── Config tab    → User sets CAPITAL_BASE (B2). Script reads it, writes MAX_PRICE (B4).
  ├── RawData tab   → Grows by ~1,800 rows each Friday. Becomes rolling history DB.
  ├── Indicators tab → Formula-based pivot (QUERY/ARRAYFORMULA). Approximate only.
  ├── Screener tab  → Written by data_pump.py. All qualifying stocks + scores.
  └── Signal tab    → Written by data_pump.py. 3 rows: winner + 2 alternates.
                      Published as CSV → read by app without authentication.

       │  Published CSV URL (public, no auth)
       │  https://docs.google.com/spreadsheets/d/ID/pub?gid=GID&output=csv
       ▼

[app/js/app.js — NSE Signal PWA]
  1. fetchSignal()  → HTTP GET published CSV → parseCSV() → render
  2. renderSignal() → calls wireZerodhaButtons(sig) after rendering GTT table
  3. wireZerodhaButtons() → binds onClick for Open/Copy/AutoGTT buttons

       │  Kite Connect API (optional, free Personal tier)
       ▼

[Zerodha Kite — GTT Order]
  POST https://api.kite.trade/gtt/triggers
  Type: two-leg (OCO)
  Leg 1: SELL at INITIAL_STOP (stop-loss)
  Leg 2: SELL at M1_TARGET (+15%)
```

---

## Component Map

### `src/data_pump.py` — Main Engine

| Function | Purpose | Key Notes |
|----------|---------|-----------|
| `get_last_friday_ddmmyyyy()` | Returns DDMMYYYY string | IST timezone aware |
| `download_bhavcopy(date)` | HTTP GET from NSE archives | Needs User-Agent header. Filters EQ series only. |
| `connect_sheets()` | Returns gspread Spreadsheet | Reads `GOOGLE_CREDENTIALS_JSON` env var |
| `append_to_rawdata(sh, df, date)` | Appends Bhavcopy to RawData tab | **Idempotent** — checks date column before inserting |
| `read_config(sh)` | Reads capital + price limits | Also writes back dynamic MAX_PRICE |
| `build_symbol_history(sh)` | Builds per-symbol OHLCV history | Reads entire RawData tab. Returns dict[symbol → DataFrame] |
| `rsi(series, n)` | Wilder RSI | Standard implementation |
| `atr(df, n)` | Average True Range | Uses high/low/close, handles first bar |
| `screen_symbol(sym, df, cfg)` | 6-filter + CMS scoring | Returns dict or None |
| `write_signal_tab(sh, candidates, cfg)` | Writes Signal tab | Top 3 rows. Clears tab first. |

### `app/js/app.js` — Frontend App (838 lines)

| Section | Lines (approx) | Purpose |
|---------|----------------|---------|
| Constants + State | 1–27 | LS keys, state object |
| `parseCSV()` | 30–65 | RFC 4180 CSV parser |
| `store` object | 68–75 | localStorage wrapper |
| `fmt()`, `fmtPct()` | 78–92 | Number formatters |
| `showToast()` | 94–115 | Toast notifications |
| `showSkeleton()` | 118–122 | Loading skeletons toggle |
| `switchTab()` | 125–145 | Tab navigation |
| `fetchSignal()` | 148–200 | Fetch + parse + route to render |
| `renderActiveSignal()` | 202–310 | Full signal render (hero, RSI gauge, GTT table) |
| `renderCashState()` | 312–340 | Cash state render |
| `renderPortfolio()` | 345–480 | Capital chart + stats |
| `renderHistory()` | 485–540 | Trade history list |
| `renderSettings()` | 543–600 | Settings form |
| Zerodha module | 820–1000 | Kite API, copy, open |
| BOOT `init()` | ~1000+ | App initialization |

### `.github/workflows/`

| File | Trigger | Purpose |
|------|---------|---------|
| `run_screener.yml` | Cron: Friday 10:30 UTC (16:00 IST) + manual | Runs data_pump.py, commits last_run.json |
| `deploy_app.yml` | Push to main (app/** paths) | Deploys app/ folder to GitHub Pages |
| `build_android.yml` | Manual + version tags `v*` | Bubblewrap TWA → signed APK → GitHub Release |

---

## Google Sheets Schema

### Config Tab

| Row | A (Parameter) | B (Value) | C (Note) |
|-----|--------------|-----------|---------|
| 1 | **headers** | | |
| 2 | CAPITAL_BASE | **1000** | ← User updates this |
| 3 | MIN_PRICE | 100 | Fixed |
| 4 | MAX_PRICE | =B2-26 | Auto-set by script |
| 5 | MIN_AVG_VOLUME | 500000 | |
| 6 | STOP_PCT | 0.07 | |
| 7 | M1_TARGET_PCT | 0.15 | |
| 8 | M2_TARGET_PCT | 0.30 | |
| 9 | M3_TARGET_PCT | 0.50 | |
| 10 | M1_STOP_PCT | 0.025 | |
| 11 | M2_STOP_PCT | 0.15 | |

### Signal Tab (read by PWA app)

Columns: `STATUS, TIMESTAMP, SYMBOL, CMP, CMS_SCORE, ROC_1M, ROC_2M, ROC_3M, RSI_14, SMA_50, SMA_200, ATR_14, HIGH_52W, SHARES, CAPITAL_REQUIRED, INITIAL_STOP, M1_TARGET, M1_STOP, M2_TARGET, M2_STOP, M3_TARGET, CAPITAL_BASE, TOTAL_QUALIFIED`

- Row 1: Headers
- Row 2: Rank #1 winner (or CASH row)
- Row 3: Rank #2 alternate
- Row 4: Rank #3 alternate

---

## Key Design Decisions

### Why NSE Bhavcopy instead of yfinance?
- yfinance is an unofficial Yahoo Finance scraper — breaks without warning
- Bhavcopy is the NSE's own official end-of-day file — always authoritative
- One HTTP request per week gets ALL stocks — vs. thousands for yfinance multi-ticker

### Why Google Sheets as the database?
- Free, infinitely accessible, editable from phone
- The RawData tab becomes a growing historical database over time
- No separate database infrastructure needed
- Capital updates are a single cell edit

### Why weekly (Friday) instead of daily?
- NSE cash delivery (CNC) works best with multi-week trends
- Reduces noise from daily market fluctuations
- DP charge economics: at ₹1K capital, even ±1 unnecessary trade costs 2%+

### Why single-position 100% allocation?
- DP charge is flat per stock per sell (₹21.83)
- At ₹1K, two stocks = double DP charges on exits
- Single stock = maximum efficiency
- Risk is managed via GTT stop, not diversification

### Why TWA (Trusted Web Activity) for Android?
- The PWA already works perfectly — TWA just wraps it natively
- No React Native / Flutter needed — zero code duplication
- GitHub Actions builds and signs the APK — no local tools required
- User can distribute via direct APK download (no Play Store)

---

## Environment Variables / Secrets Reference

| Name | Where | Value | Used by |
|------|-------|-------|---------|
| `GOOGLE_CREDENTIALS_JSON` | GitHub Secret | Full service account JSON | `data_pump.py`, `setup_sheets.py` |
| `SHEET_NAME` | GitHub Variable | `NSE Momentum Engine` | `data_pump.py` |
| `ANDROID_KEYSTORE_B64` | GitHub Secret | base64 of .jks file | `build_android.yml` |
| `ANDROID_KEY_ALIAS` | GitHub Secret | `nsesignal` | `build_android.yml` |
| `ANDROID_KEY_PASSWORD` | GitHub Secret | keystore key password | `build_android.yml` |
| `ANDROID_STORE_PASSWORD` | GitHub Secret | keystore store password | `build_android.yml` |

---

## Known Limitations & Edge Cases

| Issue | Impact | Mitigation |
|-------|--------|-----------|
| NSE market holiday on Friday | Bhavcopy 404 error | `data_pump.py` handles HTTPError gracefully → no-op |
| < 250 bars of history | Symbol skipped | First ~5 months: progressively more symbols qualify |
| Bhavcopy URL format change | Download fails | Monitor NSE circulars; URL has been stable since 2020 |
| Google Sheets row limit (10M cells) | Won't hit for ~4 years | At 2000 stocks × 14 cols × 52 weeks = 1.5M cells/year |
| Kite access token expired | Auto-GTT fails | User must refresh daily; shown clearly in app UI |
| Split/bonus adjustments in history | CMP discontinuity | Not handled — minor impact at weekly frequency |

---

## Testing

No automated tests currently. To test manually:

```bash
# Test data download only
cd src
GOOGLE_CREDENTIALS_JSON='...' python data_pump.py

# Test with a specific date (set env var before running)
# Modify get_last_friday_ddmmyyyy() to return a known date
```

To test the PWA app locally:
```bash
cd app
python -m http.server 8080
# Open http://localhost:8080 in Chrome
```

---

## Dependencies

**Python (`requirements.txt`):**
- `pandas>=2.0.0` — DataFrame operations
- `numpy>=1.24.0` — Numerical computing
- `requests>=2.31.0` — HTTP downloads
- `gspread>=6.0.0` — Google Sheets API client
- `google-auth>=2.20.0` — OAuth2 credentials

**JavaScript (zero external deps):**
- Vanilla HTML/CSS/JavaScript only
- No npm, no bundler, no framework
- Works offline via service worker

**GitHub Actions:**
- `actions/checkout@v4`
- `actions/setup-python@v5`
- `actions/setup-java@v4`
- `android-actions/setup-android@v3`
- `actions/setup-node@v4`
- `actions/upload-artifact@v4`
- `softprops/action-gh-release@v2`
- `actions/configure-pages@v5`
- `actions/upload-pages-artifact@v3`
- `actions/deploy-pages@v4`
