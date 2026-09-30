# NSE Momentum Engine 📈

> **₹1,000 compounding strategy** — Weekly NSE trend-following, fully automated, zero-maintenance, mobile-first.
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
- [Weekly Workflow](#weekly-workflow)
- [For AI Agents](#for-ai-agents)

---

## What This Does

Every **Friday at 4:00 PM IST** (post NSE market close), GitHub Actions automatically:

1. Downloads the NSE official **Bhavcopy CSV** (all ~1,800 EQ stocks, free, official)
2. Runs quantitative filters + momentum scoring on rolling history
3. Picks the **#1 ranked stock** (or signals CASH if no stock qualifies)
4. Writes results to **Google Sheets** (Signal tab)
5. Your **Android app** reads the Sheet → shows the trade with GTT levels
6. You tap **⚡ Auto-Place GTT** → Zerodha places the order automatically (free Kite Connect Personal)

Total weekly time: **~3 minutes on Friday evening**.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  NSE Archives (Official)                                    │
│  nsearchives.nseindia.com/...sec_bhavdata_full_DDMMYYYY.csv│
└────────────────────────────┬────────────────────────────────┘
                             │  Every Friday 16:00 IST
                             ▼
┌─────────────────────────────────────────────────────────────┐
│  GitHub Actions — run_screener.yml                          │
│  src/data_pump.py                                           │
│  • Downloads Bhavcopy                                       │
│  • Appends to Google Sheets RawData tab (history)          │
│  • Computes SMA50, SMA200, RSI14, ATR14, CMS score         │
│  • Applies 6-layer filter stack                             │
│  • Writes Rank #1 + Top 3 to Signal tab                    │
└────────────────────────────┬────────────────────────────────┘
                             │  gspread (Google Sheets API)
                             ▼
┌─────────────────────────────────────────────────────────────┐
│  Google Sheets — "NSE Momentum Engine"                      │
│  ├── Config   : Capital, price limits (user edits B2)       │
│  ├── RawData  : All weekly Bhavcopy rows (auto-growing)     │
│  ├── Indicators: Pivot + formula-based indicator summaries  │
│  ├── Screener : All stocks that pass filters                │
│  └── Signal   : Rank #1 winner + GTT levels (published CSV) │
└────────────────────────────┬────────────────────────────────┘
                             │  Published CSV URL (public read)
                             ▼
┌─────────────────────────────────────────────────────────────┐
│  NSE Signal App (Android)                                   │
│  Installed from: GitHub Pages (PWA) or APK (GitHub Release) │
│  ├── Signal tab    : Stock + GTT levels + RSI gauge         │
│  ├── Portfolio tab : Capital tracker + sparkline chart      │
│  ├── History tab   : Past trades + P&L                      │
│  └── Settings tab  : Sheet URL + Kite API key               │
└────────────────────────────┬────────────────────────────────┘
                             │  Kite Connect API (free Personal)
                             ▼
┌─────────────────────────────────────────────────────────────┐
│  Zerodha Kite — GTT Order Placed                            │
│  Two-leg OCO: Stop-loss + Target1 placed automatically      │
└─────────────────────────────────────────────────────────────┘
```

---

## Project Structure

```
nse-momentum-engine/
│
├── 📁 .github/workflows/
│   ├── run_screener.yml     ← ⭐ Main: Friday screener + Sheets push
│   ├── deploy_app.yml       ← Auto-deploy PWA to GitHub Pages
│   └── build_android.yml    ← Build signed APK via Bubblewrap TWA
│
├── 📁 android/
│   └── twa-manifest.json    ← Bubblewrap config (edit YOUR_GITHUB_USERNAME)
│
├── 📁 app/                  ← Installable PWA / Android app source
│   ├── index.html           ← 4-tab app shell
│   ├── manifest.json        ← Makes app installable on Android
│   ├── sw.js                ← Service worker (offline support)
│   ├── .well-known/
│   │   └── assetlinks.json  ← Digital Asset Links (paste SHA-256 after first build)
│   ├── css/
│   │   └── style.css        ← Dark trading theme
│   ├── js/
│   │   └── app.js           ← Full app logic + Zerodha Kite integration
│   └── icons/
│       ├── icon-192.svg
│       └── icon-512.svg
│
├── 📁 docs/                 ← Full documentation
│   ├── ARCHITECTURE.md      ← System design + data flow
│   ├── GOOGLE_SHEETS_SETUP.md ← Step-by-step GSheets guide
│   ├── ANDROID_SETUP.md     ← APK build via GitHub Actions
│   ├── ZERODHA_SETUP.md     ← Kite Connect free API guide
│   └── AGENT_GUIDE.md       ← For AI agents working on this repo
│
├── 📁 scripts/
│   └── setup_sheets.py      ← ⭐ One-time Google Sheets auto-setup script
│
├── 📁 src/
│   ├── data_pump.py         ← ⭐ Main engine: Bhavcopy → filter → Sheets
│   └── engine.py            ← Legacy engine (yfinance-based, kept for reference)
│
├── 📁 data/
│   └── last_run.json        ← Timestamp of last successful run
│
├── .gitignore
├── requirements.txt         ← Python dependencies
├── CHANGELOG.md             ← Version history
└── README.md                ← This file
```

---

## Quick Start

### Prerequisites
- GitHub account (free)
- Google account (free)
- Android phone with Chrome
- Zerodha account (for trading)

### Step 1 — Fork & Clone

```bash
# Fork this repo on GitHub, then:
git clone https://github.com/YOUR_USERNAME/nse-momentum-engine.git
cd nse-momentum-engine
```

### Step 2 — Google Cloud Setup (10 min, one-time)

See **[docs/GOOGLE_SHEETS_SETUP.md](docs/GOOGLE_SHEETS_SETUP.md)** for full guide.

Quick version:
1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create project → Enable Google Sheets API + Google Drive API
3. Create Service Account → Download JSON key
4. Run the auto-setup script:
   ```bash
   pip install gspread google-auth
   python scripts/setup_sheets.py --creds path/to/your-credentials.json --share your@gmail.com
   ```
5. The script creates all 5 tabs with correct formatting and formulas.

### Step 3 — GitHub Secrets

Go to your repo → **Settings → Secrets and variables → Actions**

**Secrets:**
| Name | Value |
|------|-------|
| `GOOGLE_CREDENTIALS_JSON` | Full contents of your service account JSON file |
| `ANDROID_KEYSTORE_B64` | Base64-encoded keystore (for Android APK builds) |
| `ANDROID_KEY_ALIAS` | `nsesignal` |
| `ANDROID_KEY_PASSWORD` | Your keystore key password |
| `ANDROID_STORE_PASSWORD` | Your keystore store password |

**Variables:**
| Name | Value |
|------|-------|
| `SHEET_NAME` | `NSE Momentum Engine` |

### Step 4 — Enable GitHub Pages

Settings → Pages → Source: **GitHub Actions**

Push any change → `deploy_app.yml` runs → you get:
`https://YOUR_USERNAME.github.io/nse-momentum-engine/`

### Step 5 — Update TWA Manifest

Edit [`android/twa-manifest.json`](android/twa-manifest.json) — replace `YOUR_GITHUB_USERNAME` with your actual username.

### Step 6 — Install the App

**Option A — Instant PWA (now):**
1. Open Chrome on Android
2. Visit `https://YOUR_USERNAME.github.io/nse-momentum-engine/`
3. Menu → Add to Home screen → Install

**Option B — Native APK (better experience):**
1. GitHub → Actions → **Build Android App** → Run workflow
2. After it completes: Releases → download `.apk` → install on Android

### Step 7 — Configure the App

Open NSE Signal app → **Settings tab**:
1. Paste the Google Sheets Signal CSV URL (see [docs/GOOGLE_SHEETS_SETUP.md](docs/GOOGLE_SHEETS_SETUP.md))
2. Enter starting capital: `1000`
3. (Optional) Enter Kite API Key + Token for auto-GTT

### Step 8 — First Manual Run

GitHub → Actions → **Weekly NSE Momentum Screener** → **Run workflow**

This seeds the initial data. After this, it runs automatically every Friday at 4 PM IST.

---

## Documentation

| Document | Purpose |
|----------|---------|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Full system design, data flows, design decisions |
| [docs/GOOGLE_SHEETS_SETUP.md](docs/GOOGLE_SHEETS_SETUP.md) | Complete Google Sheets setup (manual + automated) |
| [docs/ANDROID_SETUP.md](docs/ANDROID_SETUP.md) | Android APK build via GitHub Actions |
| [docs/ZERODHA_SETUP.md](docs/ZERODHA_SETUP.md) | Kite Connect free API + GTT automation |
| [docs/AGENT_GUIDE.md](docs/AGENT_GUIDE.md) | **For AI agents** — codebase map, conventions, known issues |
| [CHANGELOG.md](CHANGELOG.md) | Version history |

---

## Strategy Logic

### Filter Stack (6 layers — all must pass)

| # | Filter | Rule |
|---|--------|------|
| 1 | **Price Band** | `₹100 ≤ CMP ≤ (Capital - ₹26)` — dynamically scales with capital |
| 2 | **Volume** | 20-day avg volume ≥ 500,000 shares |
| 3 | **Trend Regime** | `CMP > 50-DMA > 200-DMA` (Stage 2 uptrend) |
| 4 | **Anti-Downfall** | 1-Month ROC > -3% AND 2-Month ROC > 0% |
| 5 | **52W Proximity** | Within 15% of 52-week high |
| 6 | **RSI Guard** | `40 ≤ RSI(14) ≤ 70` (not overbought, not oversold) |

### Composite Momentum Score (CMS)

```
CMS = (0.50 × 3M_ROC) + (0.30 × 52W_Proximity_Score) + (0.20 × Volume_Score)
```

Where:
- `3M_ROC` = 60-day return % (open-ended)
- `52W_Proximity_Score` = `(1 - |distance_from_52W_high|) × 100` → 0-100 scale
- `Volume_Score` = normalized `(5d_avg / 50d_avg)` → 0-100 scale (capped)

### GTT Risk Levels (per trade)

| Milestone | Price Level | Action |
|-----------|-------------|--------|
| Initial Stop | `max(CMP × 0.93, CMP - 2×ATR)` | Hard exit — never move this down |
| M1 Hit (+15%) | `CMP × 1.15` | Move stop to `CMP × 1.025` (+2.5%) |
| M2 Hit (+30%) | `CMP × 1.30` | Move stop to `CMP × 1.15` (+15%) |
| M3 Hit (+50%) | `CMP × 1.50` | Trail via 20-DMA or 2×ATR |

### Why Single-Position, 100% Allocation?

At ₹1,000 capital, Zerodha charges a flat DP charge of ~₹21.83 per scrip per sell transaction.
- Splitting into 2 stocks = 2× DP charges = ~₹44 on exits = 4.4% cost drag
- Single stock = 1× DP charge = 2.2% cost drag at ₹1K
- The M1 stop at +2.5% is calibrated to cover all round-trip costs

---

## Weekly Workflow

| Time (IST) | Action | Who |
|-----------|--------|-----|
| Friday 16:00 | Screener runs | GitHub Actions (automatic) |
| Friday ~16:10 | Signal tab updated | Google Sheets (automatic) |
| Friday 16:10 | Open NSE Signal app → Signal tab | You |
| Friday 16:12 | Refresh Kite token (if needed) | You (~30 sec) |
| Friday 16:13 | Tap ⚡ Auto-Place GTT | You (1 tap) |
| After exit | Update capital in Config tab B2 | You |

---

## For AI Agents

See **[docs/AGENT_GUIDE.md](docs/AGENT_GUIDE.md)** for a complete technical guide.

**Quick orientation:**
- The main logic lives in [`src/data_pump.py`](src/data_pump.py)
- The app UI lives in [`app/js/app.js`](app/js/app.js) (838 lines, vanilla JS, no dependencies)
- The GitHub Actions entry point is [`.github/workflows/run_screener.yml`](.github/workflows/run_screener.yml)
- Strategy constants are at the top of `data_pump.py` — all configurable via env vars
- The Google Sheets schema is documented in [`docs/GOOGLE_SHEETS_SETUP.md`](docs/GOOGLE_SHEETS_SETUP.md)

---

## Changelog

See [CHANGELOG.md](CHANGELOG.md)

---

## License

Personal use. Not financial advice.
