# Architecture — NSE Momentum Engine

> Single source of truth for system design. Written to be understood by both
> humans and AI agents modifying this codebase.

---

## System Overview

A **weekday quantitative momentum screener** for NSE-listed Indian equities,
built for:

- **Capital**: ₹1,000 starting (fully compounding, single-position)
- **Platform**: Zerodha Kite (execution) + GitHub Actions (compute) + static JSON (data)
- **Interface**: Android PWA app (no PC, no terminal)
- **Cost**: ₹0/month (GitHub Actions free tier + GitHub Pages free + Kite Personal API free)

There is **no database and no Google Sheets**. The engine writes plain JSON files
that are committed to the repo and served by GitHub Pages.

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

       │  Weekday download + yfinance rolling history
       ▼

[src/quant_engine.py — GitHub Actions Runner]
  1. Download official Bhavcopy for the session
  2. Load/build rolling per-symbol history (app/data/history + yfinance)
  3. Compute SMA50/150/200, RSI-14, ATR-14, ROC_1M/2M/3M, CMS score
  4. Apply the Stage-2 filter stack, then rank by CMS
  5. Determine the market regime (Nifty 500 vs 50/200 DMA)
  6. Emit signal.json / screener.json / signal.csv + history snapshot

       │  git commit + push (static files)
       ▼

[app/data/ — plain JSON, published by GitHub Pages]
  ├── signal.json      → winner + rows + all_qualified + regime + manifest
  ├── screener.json    → every qualifying stock with scores
  ├── signal.csv       → flat CSV feed (fallback / spreadsheets)
  ├── history/<date>.json
  ├── history/manifest.json
  └── backtests/<SYMBOL>.json + _index.json   (credibility studies)

       │  static fetch (GitHub Pages CDN, no auth)
       ▼

[app/js/app.js — NSE Signal PWA]
  1. fetchSignal()  → HTTP GET data/signal.json → render
  2. renderSignal() → hero + RSI gauge + GTT table
  3. renderAllStocksTable() → ranked grid, Cred column joins credentials
  4. renderCredibility() → loads data/backtests/<SYMBOL>.json

       │  Kite Connect API (optional, free Personal tier)
       ▼

[Zerodha Kite — GTT Order]
  POST https://api.kite.trade/gtt/triggers
  Type: two-leg (OCO)
  Leg 1: SELL at INITIAL_STOP (stop-loss)
  Leg 2: SELL at the rotation target (+15%)
```

---

## Component Map

### `src/quant_engine.py` — Main Engine (production screener)

| Area | Purpose | Key Notes |
|------|---------|-----------|
| Bhavcopy loader | Official end-of-day file | Needs a User-Agent header; filters EQ series |
| History loader | Rolling OHLCV per symbol | Reads `app/data/history/*` + yfinance |
| `compute_*` indicators | SMA50/150/200, RSI-14, ATR-14, ROC | Reference implementations |
| Filter stack | Stage-2 trend template + liquidity + RSI + ROC | See README "Strategy Logic" |
| CMS scoring | Cross-sectional percentile rank | `0.60·pctile(ROC_3M) + 0.40·pctile(52W proximity)` |
| Regime detector | Nifty 500 vs 50/200 DMA | `BULL_MARKET` / `CORRECTION_WATCH` / `DEFENSIVE_CASH` |
| Winner sizing | Whole-position sizing | Picks the top affordable leader |

### `src/trade_lifecycle.py` — Exit / rotation state machine

| Symbol | Purpose |
|--------|---------|
| `TradeLifecycleManager` | Drives a position through states and emits order signals |
| `TradeState` | `STATE_0_OPEN → STATE_1_RISK_FREE → … → STATE_CLOSED` |
| `OrderAction` / `ExitReason` | `FULL_CLOSE`, `ROTATION_TARGET`, … |
| `MarketBar` / `Position` | Inputs to the manager |

Rotation mode: `TradeLifecycleManager(rotation_target_pct=0.15)` emits a
`FULL_CLOSE` with `action = ROTATE_TO_NEXT_LEADER` when the position hits +15%.
Leaving the parameter at `None` preserves the two-tier behaviour.

### `app/js/app.js` — Frontend App

| Section | Purpose |
|---------|---------|
| `parseCSV()`, `store` | CSV fallback parser + localStorage wrapper |
| `fetchSignal()` | Fetch `data/signal.json`, route to render |
| `renderSignal()` / `renderActiveSignal()` | Hero, RSI gauge, GTT table |
| `renderPortfolio()` | Rotation plan, equity curve, stats |
| `renderHistory()` | Trade log + session snapshots |
| `renderAllStocksTable()` / `buildGridRow()` | Ranked grid incl. CMS + Cred |
| `renderCredibility()` / `ensureCredIndex()` | Backtest panel + `_index.json` join |
| Zerodha module | Kite API, copy-to-clipboard, open-in-Kite |

### `.github/workflows/` (repo root)

| File | Trigger | Purpose |
|------|---------|---------|
| `run_screener.yml` | Weekday crons + manual | Runs `quant_engine.py`, commits `app/data/` |
| `deploy_app.yml` | Push to main | Deploys `nse-momentum-engine/app/` to GitHub Pages |

---

## Output Schema

### `app/data/signal.json`

Top-level keys: `status, timestamp, trade_date, trade_date_display, is_today,
bhavcopy_status, capital_base, total_qualified, regime, winner, alternates,
rows, all_qualified, skewness_proof, history_manifest`.

Each entry in `all_qualified` carries: `SYMBOL, CMP, CMS_SCORE, ROC_1M, ROC_2M,
ROC_3M, RSI_14, SMA_50, SMA_150, SMA_200, ATR_14, ATR_PCT, HIGH_52W,
TURNOVER_CRORES, CIRCUIT_BAND, IS_PRICE_PRIME/SETUP flags, INITIAL_STOP,
M1_TARGET, M2_TARGET, M3_TARGET`, …

### `app/data/backtests/_index.json`

```json
{
  "generated_at": "…",
  "count": 46,
  "entries": [
    {
      "symbol": "CUPID",
      "credible": true,
      "score": 58.5,
      "pace": "fast",
      "target_hit_rate_pct": 61.5,
      "stop_hit_rate_pct": 12.0,
      "expectancy_pct": 6.75,
      "median_days_to_target": 8.0,
      "median_calendar_days_to_target": 12.0,
      "avg_cycle_days": 10.2,
      "total_return_pct": 44.9
    }
  ]
}
```

---

## Key Design Decisions

### Why static JSON instead of a spreadsheet / database?

- GitHub Pages serves the files for free, with no auth and no rate limits
- The repo *is* the database — every session is a versioned commit
- No credentials to leak, no Google Cloud project, no service account
- The PWA can cache the files and work offline

### Why the official Bhavcopy (plus yfinance for history)?

- Bhavcopy is NSE's own official end-of-day file — authoritative
- One HTTP request per session covers all stocks
- yfinance fills the rolling history for indicators; it is a convenience, not
  the source of truth for the signal-day prices

### Why daily instead of weekly?

- CNC delivery positions benefit from catching Stage-2 breakouts early
- The +15% rotation target is reached in days-to-weeks (median ~14 trading days)
- The engine still enforces trend quality, so noise is filtered structurally

### Why single-position 100% allocation?

- DP charge is flat per stock per sell (~₹15.93)
- At ₹1K, two stocks = double DP charges on exits
- Single stock = maximum capital efficiency
- Risk is managed via the GTT stop, not diversification

### Why TWA (Trusted Web Activity) for Android?

- The PWA already works — TWA just wraps it natively
- No React Native / Flutter — zero code duplication
- GitHub Actions builds and signs the APK — no local tools required
- Distribute via direct APK download (no Play Store needed)

---

## Environment Variables / Secrets Reference

| Name | Where | Value | Used by |
|------|-------|-------|---------|
| `ANDROID_KEYSTORE_B64` | GitHub Secret | base64 of `.jks` file | `build_android.yml` |
| `ANDROID_KEY_ALIAS` | GitHub Secret | `nsesignal` | `build_android.yml` |
| `ANDROID_KEY_PASSWORD` | GitHub Secret | keystore key password | `build_android.yml` |
| `ANDROID_STORE_PASSWORD` | GitHub Secret | keystore store password | `build_android.yml` |

No Google credentials are required.

---

## Known Limitations & Edge Cases

| Issue | Impact | Mitigation |
|-------|--------|-----------|
| NSE market holiday | Bhavcopy 404 error | Engine handles HTTPError gracefully → no-op |
| `< 250 bars` of history | Symbol skipped | First months: progressively more symbols qualify |
| Bhavcopy URL format change | Download fails | Monitor NSE circulars; URL stable since 2020 |
| yfinance is unofficial | History fetch can break | Bhavcopy is the signal-day source of truth |
| Kite access token expired | Auto-GTT fails | User refreshes token; app shows the state |
| Split/bonus in history | CMP discontinuity | Not auto-adjusted — minor impact at this frequency |

---

## Testing

```bash
# Unit tests (no network)
python tests/test_trade_lifecycle.py
python tests/test_single_stock_backtest.py

# Credibility reports for every leader
python scripts/single_stock_backtest.py --all
python scripts/single_stock_backtest.py --rebuild-index
```

Test the PWA locally:
```bash
cd nse-momentum-engine/app
python -m http.server 8080
# Open http://localhost:8080 in Chrome
```

---

## Dependencies

**Python (`requirements.txt`):**
- `pandas>=2.0.0` — DataFrame operations
- `numpy>=1.24.0` — Numerical computing
- `requests>=2.31.0` — HTTP downloads
- `yfinance>=0.2.36` — Rolling history backfill
- `duckdb>=1.0.0`, `pyarrow>=15.0.0` — Parquet/analytics tooling

**JavaScript (zero external deps):**
- Vanilla HTML/CSS/JavaScript only — no npm, no bundler, no framework
- Works offline via service worker

**GitHub Actions:**
- `actions/checkout@v4`, `actions/setup-python@v5`, `actions/setup-node@v4`
- `actions/configure-pages@v5`, `actions/upload-pages-artifact@v3`, `actions/deploy-pages@v4`
- `actions/setup-java@v4`, `android-actions/setup-android@v3`, `softprops/action-gh-release@v2`
