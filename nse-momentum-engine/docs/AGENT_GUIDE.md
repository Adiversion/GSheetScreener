# AI Agent Guide — NSE Momentum Engine

> **Read this first** before modifying any file in this repository.
> This guide explains the codebase structure, conventions, and common tasks for AI agents.

---

## Repository Purpose

This is a **weekly NSE stock screener** for a ₹1,000 compounding strategy.
A Zerodha trader runs this fully from their Android phone.

**The system is intentionally simple**:
- One Python script runs on GitHub Actions every Friday
- Results go to Google Sheets
- A PWA app reads Google Sheets and shows the trade
- Zerodha Kite places the GTT order (one tap or auto via API)

---

## File Ownership Map

> If you're asked to modify something, find it here first.

```
STRATEGY LOGIC        → src/data_pump.py        (Python)
APP UI                → app/js/app.js            (Vanilla JS, 1000+ lines)
APP STYLING           → app/css/style.css        (CSS variables, mobile-first)
APP SHELL             → app/index.html           (4-tab structure)
SCREENER SCHEDULE     → .github/workflows/run_screener.yml
APP DEPLOYMENT        → .github/workflows/deploy_app.yml
ANDROID BUILD         → .github/workflows/build_android.yml
SHEETS AUTO-SETUP     → scripts/setup_sheets.py  (run once)
ANDROID TWA CONFIG    → android/twa-manifest.json
ASSET LINKS           → app/.well-known/assetlinks.json
```

---

## Critical Rules — Do Not Break

1. **Signal tab schema is fixed** — The PWA reads a published CSV from this tab. If you change column order or names in `write_signal_tab()`, you MUST also update `parseCSV` mapping in `app/js/app.js`. Columns: `STATUS, TIMESTAMP, SYMBOL, CMP, CMS_SCORE, ROC_1M, ROC_2M, ROC_3M, RSI_14, SMA_50, SMA_200, ATR_14, HIGH_52W, SHARES, CAPITAL_REQUIRED, INITIAL_STOP, M1_TARGET, M1_STOP, M2_TARGET, M2_STOP, M3_TARGET, CAPITAL_BASE, TOTAL_QUALIFIED`

2. **`append_to_rawdata()` must stay idempotent** — It checks if the date already exists before inserting. Never remove this check or the sheet will get duplicate rows on re-runs.

3. **`MAX_PRICE = CAPITAL_BASE - 26`** — The 26 buffer accounts for DP charges + STT + rounding. Changing this math breaks position sizing.

4. **The app has zero external JS dependencies** — Never add npm packages, CDN scripts, or build steps to the app. It must work as plain static files.

5. **Service worker cache name** — If you change `app/css/style.css` or `app/js/app.js` significantly, bump the cache version in `app/sw.js`: `const CACHE_NAME = 'nse-signal-v2'` (increment v1 → v2).

6. **NSE Bhavcopy User-Agent** — The NSE server blocks requests without a proper User-Agent. Always keep `"User-Agent": "Mozilla/5.0 (compatible; NSE-Screener/2.0)"` in the headers.

---

## Common Tasks

### Task: Change a strategy parameter (e.g., stop from -7% to -8%)

Edit `src/data_pump.py`:
```python
STOP_PCT = 0.08   # line ~32
```
The GTT output values auto-recalculate. No other files need changing.

### Task: Add a new filter

In `src/data_pump.py`, inside `screen_symbol()`:
```python
# Add after existing filters, before CMS calculation
your_value = compute_something(df)
if your_value < THRESHOLD:
    return None
```
Also update `docs/ARCHITECTURE.md` filter stack table.

### Task: Add a new column to the Signal tab output

1. In `data_pump.py` → `screen_symbol()` → add to returned dict
2. In `data_pump.py` → `SIGNAL_COLS` list → append new column name
3. In `app/js/app.js` → find where signal columns are read → add display logic
4. Update `docs/ARCHITECTURE.md` Signal Tab schema table

### Task: Add a new app tab

1. `app/index.html` → add `<section class="tab-panel" id="tabNEW">` 
2. `app/index.html` → add nav item in `<nav class="bottom-nav">`
3. `app/js/app.js` → add `renderNEW()` function
4. `app/js/app.js` → in `switchTab()` add case for new tab
5. `app/css/style.css` → add any new component styles

### Task: Update the Google Sheets setup

Edit `scripts/setup_sheets.py`. Run with:
```bash
python scripts/setup_sheets.py --creds path/to/creds.json
```
The script is idempotent — safe to re-run on existing sheets.

### Task: Trigger a build

- **Screener**: GitHub → Actions → Weekly NSE Momentum Screener → Run workflow
- **App deploy**: Push any change to `app/` on main branch
- **Android APK**: GitHub → Actions → Build Android App → Run workflow

---

## Data Types Reference

### Signal dict returned by `screen_symbol()`
```python
{
    "STATUS":           "ACTIVE_SIGNAL",   # str
    "SYMBOL":           "RELIANCE",        # str (no .NS suffix)
    "CMP":              2850.45,           # float
    "CMS_SCORE":        72.31,             # float
    "ROC_1M":           "+4.23%",          # str (formatted)
    "ROC_2M":           "+8.11%",          # str
    "ROC_3M":           "+18.50%",         # str
    "RSI_14":           58.2,              # float
    "SMA_50":           2740.10,           # float
    "SMA_200":          2480.30,           # float
    "ATR_14":           62.5,              # float
    "HIGH_52W":         2920.00,           # float
    "SHARES":           0,                 # int (filled in main())
    "CAPITAL_REQUIRED": 0.0,               # float (filled in main())
    "INITIAL_STOP":     2725.45,           # float
    "M1_TARGET":        3277.02,           # float
    "M1_STOP":          2921.71,           # float
    "M2_TARGET":        3705.59,           # float
    "M2_STOP":          3277.02,           # float
    "M3_TARGET":        4275.68,           # float
    "CAPITAL_BASE":     1000.0,            # float
    "TOTAL_QUALIFIED":  0,                 # int (filled after all screening)
}
```

### Config dict returned by `read_config()`
```python
{
    "capital_base": 1000.0,   # from Config!B2
    "min_price":    100.0,    # fixed
    "max_price":    974.0,    # = capital_base - 26
}
```

### localStorage keys in app.js
```javascript
'nse_sheet_url'         // Google Sheets published CSV URL
'nse_capital_base'      // Starting capital (₹)
'nse_current_capital'   // Current running capital after exits
'nse_capital_history'   // Array of {date, capital} for chart
'nse_signal_history'    // Array of past trades
'nse_last_signal'       // {rows, fetchedAt} for offline fallback
'nse_kite_api_key'      // Kite Connect API key
'nse_kite_access_token' // Kite access token (daily expiry)
'nse_active_gtts'       // Array of {symbol, gttId, ...} for placed GTTs
```

---

## Coding Conventions

### Python (`src/`, `scripts/`)
- Functions are standalone (no class instances except gspread objects)
- All config at top of file as module-level constants
- Progress printed with emoji prefixes: `[INFO]`, `[WARN]`, `[ERROR]`
- Error handling: individual symbol failures are caught and skipped; critical failures (no sheets connection, no bhavcopy) raise and fail the job
- All monetary values stored as `float`, formatted only at output time
- Timezone: always use IST (`timezone(timedelta(hours=5, minutes=30))`) — never UTC for display

### JavaScript (`app/js/app.js`)
- Strict mode (`'use strict'` at top)
- State object is module-level `state = {...}`
- `store` object wraps localStorage (handles JSON parse/stringify)
- All DOM IDs are camelCase: `btnRefresh`, `signalContent`, `gttBody`
- Toast system: `showToast(message, 'success'|'warn'|'error'|'info')`
- No `console.log` in production paths (use `console.error` for caught exceptions)

### CSS (`app/css/style.css`)
- All colors via CSS variables defined in `:root`
- Mobile-first (`min-width` media queries for any desktop overrides)
- Transitions use `var(--transition)` = `0.22s cubic-bezier(.4,0,.2,1)`

---

## Testing Checklist (Before Committing)

- [ ] `python src/data_pump.py` — does it run without errors? (needs real creds)
- [ ] `python scripts/setup_sheets.py --creds ...` — does it create/update tabs?
- [ ] Open `app/index.html` via `python -m http.server` → does the app load?
- [ ] Signal tab with `STATUS=CASH` → does app show cash state correctly?
- [ ] Signal tab with `STATUS=ACTIVE_SIGNAL` → do GTT levels render?
- [ ] `app/manifest.json` — is `start_url` still correct relative path?
- [ ] `android/twa-manifest.json` — is `YOUR_GITHUB_USERNAME` replaced?
- [ ] `app/.well-known/assetlinks.json` — is SHA-256 fingerprint filled in?

---

## Frequently Asked Questions

**Q: Why is there both `engine.py` and `data_pump.py`?**
A: `engine.py` was the original yfinance-based implementation. `data_pump.py` is the current production version using NSE Bhavcopy + Google Sheets. `engine.py` is kept for reference only — do not use it in workflows.

**Q: The screener runs but writes CASH — why?**
A: This happens when `build_symbol_history()` has < 250 data points per symbol. The first 5 months of running will have this issue as history accumulates. After 250 Fridays (~5 years) every stock has full history. Realistically, after 50 Fridays (~1 year) most liquid stocks pass.

**Q: Can I add more assets (F&O, BSE)?**
A: BSE Bhavcopy is at `bseindia.com/download/BhavCopy/Equity/EQ{DDMMYYYY}_CSV.ZIP`. For F&O, NSE archives have separate Bhavcopy files. Keep them in separate tabs in Google Sheets.

**Q: The PWA doesn't install on Android — why?**
A: Check:
1. Site is HTTPS (GitHub Pages = yes)
2. `manifest.json` is linked in `<head>` with correct path
3. Service worker is registered without errors (Chrome DevTools → Application → Service Workers)
4. User has spent >30 seconds on the page OR you're using the `beforeinstallprompt` button in Settings

**Q: Auto-GTT fails with "Invalid token"?**
A: The Kite access token expires at midnight IST daily. User must paste a fresh token in Settings. The app shows this clearly in the kiteStatus div.
