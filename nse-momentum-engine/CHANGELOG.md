# Changelog

All notable changes to NSE Momentum Engine are documented here.
Format: [Version] — YYYY-MM-DD

---

## [2.3.0] — 2026-10-01

### Added
- **Live target tracker** — a Portfolio card that tracks one purchased stock against its +15% rotation target (price, move %, distance to target, hit/stopped status). Polls every 60s while open, no cron required.
- **`workers/yahoo-proxy.js`** — a free, keyless Cloudflare Worker CORS proxy for a single Yahoo/NSE quote. Recommended over public CORS proxies, which see every request and get shut down.
- **Live-quote source order** — Twelve Data free key → Worker proxy → scheduled tracker (`targets.json`) → latest screening close.
- **`scripts/track_targets.py`** — keyless scheduled tracker: reads `positions.json`, quotes via Kite Connect (if `KITE_API_KEY`/`KITE_ACCESS_TOKEN` set) or yfinance, and writes `app/data/targets.json`.
- **Daily Rotation Target Tracker** workflow — one post-close reconciliation per weekday.
- **`positions.json`** — plain-file list of open holdings.
- **`tests/test_track_targets.py`** — 10 offline tests for the status/`summary` logic.

### Note
- Google Finance has **no API** (shut down 2012); Yahoo/NSE quote endpoints are CORS-blocked in the browser. A free Twelve Data key or a self-hosted Worker proxy is the practical in-page live source.

---

## [2.2.0] — 2026-10-01

### Added
- **Credibility index** — `scripts/single_stock_backtest.py` now emits `app/data/backtests/_index.json` (best score first) via `build_index()`, and a new offline `--rebuild-index` flag regenerates it from existing reports without re-downloading history.
- **`pace` classification** per stock (`fast` / `medium` / `slow`) derived from median days-to-+15%.
- **Cred column** in the screener grid (sortable), showing the backtest credibility score with pace / hit-rate / median-days tooltips.

### Removed
- **All Google Sheets plumbing** — deleted `src/data_pump.py` and `scripts/setup_sheets.py`; the live Action already runs `src/quant_engine.py`, so the spreadsheet path was dead weight.
- Dropped `gspread`, `google-auth`, `google-api-python-client` from `requirements.txt`.
- Deleted the Sheets docs (`GOOGLE_SHEETS_SETUP.md`, `WHAT_YOU_SHOULD_DO.md`, `SETUP_AND_NEXT_STEPS.md`) and the legacy nested `run_screener.yml`.
- Removed the legacy `nse_sheet_url` localStorage handling from the app.

### Changed
- README, ARCHITECTURE and AGENT_GUIDE rewritten around the native pipeline (Bhavcopy → `quant_engine.py` → static JSON in `app/data/` → PWA).
- Service worker cache bumped `v9 → v10`.

---

## [2.1.0] — 2026-10-01

### Added
- **Rotation mode** in `TradeLifecycleManager` (`rotation_target_pct`): sells the entire position at a fixed target (+15%) so principal + profit can be redeployed into the next leader. Defaults to `None`, preserving the original two-tier behaviour.
- **`scripts/single_stock_backtest.py`** — single-stock credibility study (forward-outcome hit rates, expectancy, holding times) plus a compounding rotation simulation from ₹1,000. CLI (`--symbol`, `--all`) writes `app/data/backtests/<SYMBOL>.json`.
- **Backtest credibility panel** in the terminal inspector, populated from the generated reports.
- **Rotation plan card** on the Portfolio tab: starting capital, current equity, completed cycles, next +15% target and a projected compounding ladder.
- **`tests/test_single_stock_backtest.py`** — offline tests covering the study, simulation, verdict thresholds, pace/index helpers and the rotation exit.

### Changed
- Terminal GTT ticket relabelled for rotation: `Rotate (+15%)` replaces `M1 (Risk-Free)`; the two-tier levels are now shown as optional trailing exits.
- Portfolio lifecycle steps and strategy guide rewritten around the +15% rotation model.

---

## [2.0.0] — 2026-09-30

### Added
- **NSE Bhavcopy data source** — replaced yfinance with official NSE archive CSV download
- **Google Sheets as database** — RawData tab accumulates weekly history; no external DB
- **`src/data_pump.py`** — complete rewrite of screener engine
- **Google Sheets integration** via `gspread` — writes Config, RawData, Indicators, Screener, Signal tabs
- **`scripts/setup_sheets.py`** — one-time Google Sheets auto-setup script (creates all 5 tabs with formatting)
- **NSE Signal PWA app** (`app/`) — installable Android app with 4 tabs:
  - Signal tab with RSI gauge, GTT levels table, ROC chips
  - Portfolio tab with capital tracker and sparkline chart
  - History tab with past trades and P&L
  - Settings tab with Sheet URL, capital, Kite API
- **Service Worker** — offline support, cache-first for assets, network-first for CSV
- **Zerodha Kite Connect integration** (free Personal tier):
  - 🔗 Open in Kite button
  - 📋 Copy GTT Details (clipboard-ready formatted text)
  - ⚡ Auto-Place GTT via API (Two-Leg OCO)
- **Android APK build** via GitHub Actions + Bubblewrap TWA (`build_android.yml`)
- **GitHub Pages deployment** workflow (`deploy_app.yml`)
- **Digital Asset Links** (`app/.well-known/assetlinks.json`) for fullscreen TWA
- **RSI(14) filter** — new filter: 40 ≤ RSI ≤ 70 (avoids overbought/oversold entries)
- **ATR-based adaptive stop** — `max(CMP × 0.93, CMP - 2×ATR)` (tighter of fixed or volatility-based)
- **Dynamic price band** — `MAX_PRICE = CAPITAL_BASE - 26` (scales with capital)
- **Milestone 3 (+50%)** — now computed and exported in Signal tab
- **Top-3 alternates** — Signal tab rows 2–4 show winner + 2 backups
- **Normalized Volume Score** — replaces arbitrary `vol_ratio × 10` with 0-100 scaled score
- **Comprehensive docs** — ARCHITECTURE.md, AGENT_GUIDE.md, GOOGLE_SHEETS_SETUP.md, ANDROID_SETUP.md, ZERODHA_SETUP.md

### Changed
- `MAX_PRICE` changed from hardcoded `₹950` to dynamic `CAPITAL_BASE - 26`
- Anti-downfall filter: 1M ROC threshold changed from `> 0%` to `> -3%` (allows minor shakeouts)
- GTT buffer changed from ₹20 to ₹25 for position sizing
- `datetime.utcnow()` replaced with `datetime.now(timezone.utc)` (Python 3.12 safe)
- Nifty 500 universe URL fixed (old URL was broken, always fell back to 7 stocks)
- GitHub Actions workflow now has `permissions: contents: write` (fixes push on new repos)

### Removed
- `yfinance` dependency — replaced by NSE Bhavcopy
- Hardcoded `MAX_PRICE = 950`
- Telegram alert (replaced by Zerodha auto-GTT + app notification)

### Fixed
- yfinance multi-ticker API mismatch causing KeyErrors
- `vol_ratio` distorting CMS via arbitrary ×10 multiplier
- Missing Milestone 3 in output (was in spec, not in code)

---

## [1.0.0] — 2026-09-30 (Initial)

### Added
- Initial quantitative screener with yfinance data
- GitHub Actions cron runner (Friday 10:30 UTC)
- Composite Momentum Score (CMS) formula
- GTT ratchet levels (M1, M2)
- `data/signals/latest.json` output
- Basic filter stack: price, volume, trend regime, 52W proximity, anti-downfall
