# Changelog

All notable changes to NSE Momentum Engine are documented here.
Format: [Version] — YYYY-MM-DD

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
