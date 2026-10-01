# AI Agent Guide — NSE Momentum Engine

> **Read this first** before modifying any file in this repository.
> This guide explains the codebase structure, conventions, and common tasks for AI agents.

---

## Repository Purpose

This is a **weekday NSE stock screener** for a ₹1,000 compounding strategy.
A Zerodha trader runs this fully from their Android phone.

**The system is intentionally simple**:
- One Python script runs on GitHub Actions after each session
- The engine writes plain JSON into `app/data/` (no database, no Google Sheets)
- A PWA app reads that static JSON and shows the trade
- Zerodha Kite places the GTT order (one tap or auto via API)

---

## File Ownership Map

> If you're asked to modify something, find it here first.

```
STRATEGY LOGIC        → src/quant_engine.py      (Python — read-only reference)
EXIT / ROTATION       → src/trade_lifecycle.py   (Python state machine)
CREDIBILITY BACKTEST  → scripts/single_stock_backtest.py
APP UI                → app/js/app.js            (Vanilla JS)
APP STYLING           → app/css/style.css        (CSS variables, mobile-first)
APP SHELL             → app/index.html           (4-tab structure)
SCREENER SCHEDULE     → ../../.github/workflows/run_screener.yml   (repo root)
APP DEPLOYMENT        → ../../.github/workflows/deploy_app.yml      (repo root)
ANDROID BUILD         → ../../.github/workflows/build_android.yml   (repo root)
ANDROID TWA CONFIG    → android/twa-manifest.json
ASSET LINKS           → app/.well-known/assetlinks.json
TESTS                 → tests/test_trade_lifecycle.py, tests/test_single_stock_backtest.py
```

> Note: GitHub Actions only reads workflows from the **repository root**
> (`.github/workflows/`), which is one level above `nse-momentum-engine/`.

---

## Critical Rules — Do Not Break

1. **The engine output schema is the contract** — The PWA reads
   `app/data/signal.json`. If you change a field name or type in the engine, you
   MUST update the corresponding read in `app/js/app.js`. Key fields:
   `SYMBOL, CMP, CMS_SCORE, ROC_1M, ROC_2M, ROC_3M, RSI_14, SMA_50, SMA_150,
   SMA_200, ATR_14, ATR_PCT, HIGH_52W, TURNOVER_CRORES, CIRCUIT_BAND,
   INITIAL_STOP, M1_TARGET, M2_TARGET`.

2. **`src/quant_engine.py` is the source of truth and is treated as read-only**
   for feature work — the backtest tool and lifecycle reference it but never
   import or mutate it. Change it only with explicit intent, and re-run the
   tests afterwards.

3. **The app has zero external JS dependencies** — Never add npm packages, CDN
   scripts, or build steps to the app. It must work as plain static files.

4. **Service worker cache name** — If you change `app/css/style.css` or
   `app/js/app.js`, bump the cache version in `app/sw.js`
   (`const CACHE_NAME = 'nse-signal-vN'` → increment N).

5. **NSE Bhavcopy User-Agent** — The NSE server blocks requests without a
   proper User-Agent. Always keep a browser-like `User-Agent` header.

6. **Rotation semantics** — `TradeLifecycleManager(rotation_target_pct=0.15)`
   sells the whole position at +15%. Passing `None` keeps the legacy two-tier
   behaviour. Do not silently change the default.

---

## Common Tasks

### Task: Change a strategy parameter (e.g. the +15% target)

The rotation target lives in `src/trade_lifecycle.py` (the `rotation_target_pct`
parameter) and in the backtest defaults in `scripts/single_stock_backtest.py`
(`DEFAULTS["target_pct"]`). The terminal copy in `app/js/app.js`
(`m1Target = entry * 1.15`) must be kept in sync.

### Task: Add a new filter

In `src/quant_engine.py`, inside the screening pass, add the condition before
the CMS ranking. Also update the filter table in `docs/ARCHITECTURE.md` and the
README "Strategy Logic" section.

### Task: Add a new column to the screener grid

1. Ensure the field is emitted per stock in `app/data/signal.json`
2. `app/index.html` → add a `<th class="num col-X" data-sort="X">`
3. `app/js/app.js` → add the `<td class="num col-X">` in `buildGridRow()` and a
   getter in `renderAllStocksTable()`
4. `app/css/style.css` → add a column-priority media query and, if needed, the
   mobile `display: flex` list
5. Bump the service worker cache version

### Task: Add a new app tab

1. `app/index.html` → add `<section class="tab-panel" id="tabNEW">`
2. `app/index.html` → add a nav item in `<nav class="bottom-nav">`
3. `app/js/app.js` → add `renderNEW()` and a `switchTab()` case
4. `app/css/style.css` → add any new component styles

### Task: Regenerate the credibility index

```bash
python scripts/single_stock_backtest.py --all            # full re-run (network)
python scripts/single_stock_backtest.py --rebuild-index   # offline, from existing reports
```

`--rebuild-index` reads every `app/data/backtests/<SYMBOL>.json` and rebuilds
`_index.json` (best score first) without touching the network.

### Task: Trigger a build

- **Screener**: GitHub → Actions → Daily NSE Momentum Screener → Run workflow
- **App deploy**: Push any change on the main branch
- **Android APK**: GitHub → Actions → Build Android App → Run workflow

---

## Data Types Reference

### Per-stock dict in `signal.json → all_qualified`

```python
{
    "SYMBOL":            "RELIANCE",   # str (no .NS suffix)
    "CMP":               2850.45,      # float
    "CMS_SCORE":         72.31,        # float (0–100 percentile composite)
    "ROC_1M":            4.23,         # float (percent)
    "ROC_2M":            8.11,
    "ROC_3M":            18.50,
    "RSI_14":            58.2,         # float
    "SMA_50":            2740.10,
    "SMA_150":           2600.00,
    "SMA_200":           2480.30,
    "ATR_14":            62.5,
    "ATR_PCT":           2.19,         # float
    "HIGH_52W":          2920.00,
    "TURNOVER_CRORES":   82.0,         # float (20-day avg turnover ₹ Cr)
    "CIRCUIT_BAND":      20,           # int (percent)
    "INITIAL_STOP":      2725.45,
    "M1_TARGET":         3277.02,      # +15% rotation target
    "M2_TARGET":         3705.59,
    "M3_TARGET":         4275.68,
    "IS_PRIME":          True,         # bool
}
```

### `app/data/backtests/<SYMBOL>.json`

```python
{
    "symbol": "CUPID",
    "generated_at": "2026-09-30T…Z",
    "period": {"start": "2023-09-29", "end": "2026-09-30", "bars": 750},
    "pace": "fast",                     # fast | medium | slow | unknown
    "params": {"capital": 1000.0, "target_pct": 15.0, "…": "…"},
    "study": {
        "observations": 26,
        "target_hit_rate_pct": 61.5,
        "stop_hit_rate_pct": 12.0,
        "expectancy_pct": 6.75,
        "time_to_target": {"trading_days": {"median": 8.0, "…": "…"}, "…": "…"},
    },
    "simulation": {"cycles": 26, "final_capital": 1449.0, "…": "…"},
    "verdict": {"credible": True, "score": 58.5, "summary": "…"},
}
```

### localStorage keys in app.js

```javascript
'nse_capital_base'      // Starting capital (₹)
'nse_current_capital'   // Current running capital after exits
'nse_capital_history'   // Array of {date, capital} for chart
'nse_signal_history'    // Array of past trades
'nse_last_signal'       // {rows, payload, fetchedAt} for offline fallback
'nse_kite_api_key'      // Kite Connect API key
'nse_kite_access_token' // Kite access token (daily expiry)
'nse_active_gtts'       // Array of {symbol, gttId, …} for placed GTTs
```

---

## Coding Conventions

### Python (`src/`, `scripts/`)
- Functions are standalone; configuration lives as module-level constants
- Progress printed with emoji prefixes: `[INFO]`, `[WARN]`, `[ERROR]`
- Individual symbol failures are caught and skipped; critical failures (no
  bhavcopy, no data) raise and fail the job
- All monetary values stored as `float`, formatted only at output time
- Timezone: always use IST (`timezone(timedelta(hours=5, minutes=30))`) for display

### JavaScript (`app/js/app.js`)
- Strict mode (`'use strict'` at top)
- Module-level `state = {...}` object
- `store` object wraps localStorage (handles JSON parse/stringify)
- DOM IDs are camelCase: `btnRefresh`, `signalContent`, `gttBody`
- Toast system: `showToast(message, 'success'|'warn'|'error'|'info')`
- The V2 render layer is appended at the end of the file; later function
  declarations supersede earlier ones

### CSS (`app/css/style.css`)
- All colors via CSS variables in `:root`
- Mobile-first (`min-width` media queries for desktop overrides)
- Column priority: highest-value columns stay visible on narrow grids

---

## Testing Checklist (Before Committing)

- [ ] `python tests/test_trade_lifecycle.py` — lifecycle + rotation exits pass
- [ ] `python tests/test_single_stock_backtest.py` — backtester + index pass
- [ ] `node --check app/js/app.js` — no syntax errors
- [ ] Open `app/index.html` via `python -m http.server` → does the app load?
- [ ] `STATUS=CASH` signal → does the app show the cash state correctly?
- [ ] `STATUS=ACTIVE_SIGNAL` signal → do GTT levels render?
- [ ] Credibility panel loads `data/backtests/<SYMBOL>.json` for a selected stock
- [ ] `app/manifest.json` — is `start_url` correct relative path?
- [ ] `android/twa-manifest.json` — is `YOUR_GITHUB_USERNAME` replaced?
- [ ] `app/.well-known/assetlinks.json` — is the SHA-256 fingerprint filled in?

---

## Frequently Asked Questions

**Q: Why is there both `engine.py` and `quant_engine.py`?**
A: `engine.py` was the original yfinance-based implementation. `quant_engine.py`
is the current production engine (Bhavcopy + rolling history + CMS). `engine.py`
is kept for reference only — do not use it in workflows.

**Q: The screener writes CASH — why?**
A: Either the market regime is `DEFENSIVE_CASH` (Nifty 500 below its 200-DMA),
or no stock passed the Stage-2 filter stack. Early on, limited rolling history
also means fewer symbols qualify.

**Q: Can I add more assets (F&O, BSE)?**
A: BSE Bhavcopy is at `bseindia.com/download/BhavCopy/Equity/EQ{DDMMYYYY}_CSV.ZIP`.
For F&O, NSE archives have separate Bhavcopy files. Add a separate data source
and an `app/data/` output — do not put them in the same signal file.

**Q: The PWA doesn't install on Android — why?**
A: Check:
1. Site is HTTPS (GitHub Pages = yes)
2. `manifest.json` is linked in `<head>` with the correct path
3. Service worker registers without errors (Chrome DevTools → Application → Service Workers)
4. The user has spent >30 seconds on the page, or uses the install button

**Q: Auto-GTT fails with "Invalid token"?**
A: The Kite access token expires at midnight IST daily. The user must paste a
fresh token in Settings. The app shows this clearly in the kite status area.
