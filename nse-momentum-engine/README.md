# NSE Momentum Engine 📈

> **₹1,000 compounding strategy** — Daily NSE trend-following, fully automated, zero-maintenance, mobile-first.
>
> Built for a Zerodha trader operating exclusively on mobile. No PC required after setup.

---

## 📑 Table of Contents

- [What This Does](#what-this-does)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Quick Start](#quick-start)
- [Documentation](#documentation)
- [Strategy Logic](#strategy-logic)
- [Daily Workflow](#daily-workflow)
- [For AI Agents](#for-ai-agents)

---

## What This Does

Every **weekday after the NSE close**, GitHub Actions automatically:

1. Downloads the NSE official **Bhavcopy CSV** (all EQ stocks, free, official)
2. Runs the quant engine (Minervini Stage-2 trend template + momentum scoring) on rolling history
3. Picks the **#1 ranked leader** (or signals CASH if nothing qualifies)
4. Writes the result straight into `app/data/signal.json` (no spreadsheet, no database)
5. Your **Android app** (PWA) reads that static JSON → shows the trade with GTT levels
6. You place the GTT in Kite (manual or ⚡ Auto-Place via free Kite Connect Personal)

Total daily time: **~2 minutes after the close**. No Google account or Google Sheets required.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  NSE Archives (Official Bhavcopy)  +  yfinance (rolling)    │
└────────────────────────────┬────────────────────────────────┘
                             │  Weekdays, post-close (cron)
                             ▼
┌─────────────────────────────────────────────────────────────┐
│  GitHub Actions — run_screener.yml                          │
│  src/quant_engine.py                                        │
│  • Downloads Bhavcopy, builds rolling history               │
│  • Computes SMA50/150/200, RSI-14, ATR-14, ROC, CMS score   │
│  • Applies the Stage-2 filter stack + ranks the leaders     │
│  • Emits signal.json / screener.json / history snapshots    │
└────────────────────────────┬────────────────────────────────┘
                             │  git commit + push (static files)
                             ▼
┌─────────────────────────────────────────────────────────────┐
│  app/data/  (plain JSON on GitHub Pages)                    │
│  ├── signal.json      : winner + rows + all_qualified       │
│  ├── screener.json    : every qualifying stock + scores     │
│  ├── history/         : per-session snapshots + manifest    │
│  └── backtests/       : per-symbol credibility studies      │
└────────────────────────────┬────────────────────────────────┘
                             │  static fetch (GitHub Pages CDN)
                             ▼
┌─────────────────────────────────────────────────────────────┐
│  NSE Signal App (PWA / Android TWA)                         │
│  ├── Signal tab    : Stock + GTT levels + RSI gauge         │
│  ├── Portfolio tab : Rotation plan + equity curve           │
│  ├── History tab   : Past trades + session snapshots        │
│  └── Settings tab  : Capital base + Kite API key            │
└────────────────────────────┬────────────────────────────────┘
                             │  Kite Connect API (free Personal)
                             ▼
┌─────────────────────────────────────────────────────────────┐
│  Zerodha Kite — GTT Order Placed                            │
│  Two-leg OCO: Stop-loss + Target (rotate at +15%)           │
└─────────────────────────────────────────────────────────────┘
```

---

## Project Structure

```
nse-momentum-engine/
│
├── 📁 .github/workflows/    (repo-root workflows live in ../../.github/workflows)
│
├── 📁 android/
│   └── twa-manifest.json    ← Bubblewrap config (edit YOUR_GITHUB_USERNAME)
│
├── 📁 app/                  ← Installable PWA / Android app source
│   ├── index.html           ← 4-tab app shell
│   ├── manifest.json        ← Makes app installable on Android
│   ├── sw.js                ← Service worker (offline support)
│   ├── css/style.css        ← Dark trading theme
│   ├── js/app.js            ← Full app logic + Zerodha Kite integration
│   └── data/                ← Static data published with the app
│       ├── signal.json      ← Live signal (written by the engine)
│       ├── screener.json    ← Full ranked screener
│       ├── history/         ← Daily snapshots + manifest
│       └── backtests/       ← Per-symbol credibility reports + _index.json
│
├── 📁 docs/                 ← Full documentation
│   ├── ARCHITECTURE.md      ← System design + data flow
│   ├── ANDROID_SETUP.md     ← APK build via GitHub Actions
│   ├── ZERODHA_SETUP.md     ← Kite Connect free API guide
│   └── AGENT_GUIDE.md       ← For AI agents working on this repo
│
├── 📁 scripts/
│   ├── single_stock_backtest.py ← Credibility study + rotation backtest
│   ├── backtest.py          ← Legacy 2-year strategy backtest
│   └── compare_strategies.py
│
├── 📁 src/
│   ├── quant_engine.py      ← ⭐ Main engine: Bhavcopy → filters → signal.json
│   ├── trade_lifecycle.py   ← Lifecycle / exit state machine (incl. rotation)
│   └── engine.py            ← Legacy engine (yfinance-based, kept for reference)
│
├── 📁 tests/
│   ├── test_trade_lifecycle.py
│   └── test_single_stock_backtest.py
│
├── requirements.txt         ← Python dependencies
├── CHANGELOG.md             ← Version history
└── README.md                ← This file
```

---

## Quick Start

### Prerequisites
- GitHub account (free)
- Android phone with Chrome
- Zerodha account (for trading)

### Step 1 — Fork & Clone

```bash
# Fork this repo on GitHub, then:
git clone https://github.com/YOUR_USERNAME/nse-momentum-engine.git
cd nse-momentum-engine
```

### Step 2 — Enable GitHub Pages

Settings → Pages → Source: **GitHub Actions**

Push any change → `deploy_app.yml` runs → you get:
`https://YOUR_USERNAME.github.io/GSheetScreener/`

### Step 3 — Update TWA Manifest

Edit [`android/twa-manifest.json`](android/twa-manifest.json) — replace `YOUR_GITHUB_USERNAME` with your actual username.

### Step 4 — Install the App

**Option A — Instant PWA (now):**
1. Open Chrome on Android
2. Visit your GitHub Pages URL
3. Menu → Add to Home screen → Install

**Option B — Native APK (better experience):**
1. GitHub → Actions → **Build Android App** → Run workflow
2. After it completes: Releases → download `.apk` → install on Android

### Step 5 — Configure the App

Open NSE Signal app → **Settings tab**:
1. Enter starting capital: `1000`
2. (Optional) Enter Kite API Key + Token for auto-GTT

### Step 6 — First Manual Run

GitHub → Actions → **Daily NSE Momentum Screener** → **Run workflow**

This seeds the initial data. After this, it runs automatically on a weekday schedule.

---

## Documentation

| Document | Purpose |
|----------|---------|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Full system design, data flows, design decisions |
| [docs/ANDROID_SETUP.md](docs/ANDROID_SETUP.md) | Android APK build via GitHub Actions |
| [docs/ZERODHA_SETUP.md](docs/ZERODHA_SETUP.md) | Kite Connect free API + GTT automation |
| [docs/AGENT_GUIDE.md](docs/AGENT_GUIDE.md) | **For AI agents** — codebase map, conventions, known issues |
| [CHANGELOG.md](CHANGELOG.md) | Version history |

---

## Strategy Logic

The engine implements a Mark Minervini **Stage-2 trend template** with a
momentum (CMS) ranking.

### Filter Stack (all must pass)

| # | Filter | Rule |
|---|--------|------|
| 1 | **Trend template** | `CMP > 50-DMA > 150-DMA > 200-DMA` and 200-DMA rising |
| 2 | **52W structure** | Within −25% of the 52-week high **and** ≥ +30% off the low |
| 3 | **RSI guard** | `45 ≤ RSI(14) ≤ 82` |
| 4 | **Anti-downfall** | 1-Month ROC ≥ −3% **and** 2-Month ROC > 0% |
| 5 | **Liquidity** | 20-day average turnover ≥ ₹5 Cr |
| 6 | **Circuit band** | 2% and 5% circuit-band names excluded |

The candidate pool is the **top 300 by single-day turnover** after a
prefilter (CMP ≥ ₹50, volume ≥ 100k, turnover ≥ ₹2 Cr).

### Composite Momentum Score (CMS)

```
CMS = 0.60 × percentile(ROC_3M) + 0.40 × percentile(52W proximity)
```

Both components are cross-sectional percentiles within the session's pool, so
the score always spans 0–100 for the day.

### GTT Risk Levels (per trade)

| Milestone | Price Level | Action |
|-----------|-------------|--------|
| Initial Stop | `entry − min(7%, max(5%, 2×ATR/entry))` | Hard exit — never move this down |
| Rotate (+15%) | `entry × 1.15` | Rotation mode: sell the full position |
| Trail 1 (+22%) | `entry × 1.22` | Optional: bank 40%, move stop to +10% |
| Trail 2 (+50%+) | `entry × 1.50` ref | Optional: uncapped trail on the runner |

### Why Single-Position, 100% Allocation?

At ₹1,000 capital, Zerodha charges a flat DP charge per scrip per sell.
- Splitting into 2 stocks = 2× DP charges on exits → ~4.4% cost drag
- Single stock = 1× DP charge → ~2.2% cost drag at ₹1K
- The stop/target calibration accounts for this round-trip cost

### Rotation mode — +15% cycles (terminal default)

One capital base, compounded by fixed-target rotation:

1. Deploy the **entire equity** into the #1 ranked leader at market open.
2. The initial ATR stop (−5% to −7%) caps the downside.
3. When the position reaches **+15%**, sell it in full.
4. Reinvest **principal + profit** into the next ranked leader and repeat.

No capital is ever added after the first deposit. `TradeLifecycleManager`
supports this via `rotation_target_pct=0.15`; when it is left at `None` the
original two-tier (risk-free → bank 40% → trailing runner) behaviour is kept.

### Single-stock credibility backtest

Before committing to a name, test how it behaved historically under the exact
rotation rules — how often it reached +15% before the stop:

```bash
python scripts/single_stock_backtest.py --symbol CUPID   # one stock, full report
python scripts/single_stock_backtest.py --all            # every current leader
python scripts/single_stock_backtest.py --time-analysis  # how long +15% takes
python scripts/single_stock_backtest.py --rebuild-index   # refresh the app index
```

Reports are written to `app/data/backtests/<SYMBOL>.json` and surface in the
terminal's **Backtest credibility** panel for the selected stock, plus a
screener **Cred** column ranked from `app/data/backtests/_index.json`. Each
report contains a forward-outcome study (target-hit rate, stop rate, expectancy,
holding times) and a compounding rotation simulation from ₹1,000.
The script reads `src/quant_engine.py` only as a reference for indicator and
filter definitions — it never imports or changes it.

---

## Daily Workflow

| Time (IST) | Action | Who |
|-----------|--------|-----|
| Weekday post-close | Screener runs | GitHub Actions (automatic) |
| ~30 min later | `signal.json` committed & Pages redeployed | GitHub Actions (automatic) |
| Evening | Open NSE Signal app → Signal tab | You |
| — | Refresh Kite token (if needed) | You (~30 sec) |
| — | Place/rotate GTT at +15% | You (1 tap) |
| After exit | Record the exit in Portfolio tab | You |

---

## For AI Agents

See **[docs/AGENT_GUIDE.md](docs/AGENT_GUIDE.md)** for a complete technical guide.

**Quick orientation:**
- The main logic lives in [`src/quant_engine.py`](src/quant_engine.py)
- The exit/rotation state machine lives in [`src/trade_lifecycle.py`](src/trade_lifecycle.py)
- The app UI lives in [`app/js/app.js`](app/js/app.js) (vanilla JS, no dependencies)
- The GitHub Actions entry point is [`../../.github/workflows/run_screener.yml`](../../.github/workflows/run_screener.yml)
- The engine writes static JSON into `app/data/` — there is **no database and no Google Sheets**
- Strategy constants are at the top of `quant_engine.py`

---

## Changelog

See [CHANGELOG.md](CHANGELOG.md)

---

## License

Personal use. Not financial advice.
