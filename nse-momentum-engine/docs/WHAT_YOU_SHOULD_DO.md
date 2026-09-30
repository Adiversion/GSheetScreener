# What You Should Do — Step-by-Step Action Guide 🚀

> This is your exact, step-by-step checklist to get everything running right now, followed by how your system automatically handles fallbacks if Zerodha or NSE changes policies.

---

## 📋 Table of Contents
1. [Action Checklist (What to Do Right Now)](#1-action-checklist-what-to-do-right-now)
2. [How the 4-Tier NSE Data Fallback Works (Fluently & Automatically)](#2-how-the-4-tier-nse-data-fallback-works)
3. [Broker Independence: What Happens if Zerodha Fails or Changes Policy](#3-broker-independence-what-happens-if-zerodha-fails)
4. [Your Weekly 3-Minute Friday Routine](#4-your-weekly-3-minute-friday-routine)

---

## 1. Action Checklist (What to Do Right Now)

Follow these **6 steps** once. Everything after this is automatic.

### Step 1: Create a GitHub Repository & Push Your Code

1. Open your browser and go to [github.com/new](https://github.com/new).
2. Set repository name: `nse-momentum-engine` (can be **Private** or **Public**).
3. Leave "Initialize with README" **unchecked** (we already have everything committed locally).
4. Click **Create repository**.
5. Copy your repository URL (e.g., `https://github.com/YOUR_USERNAME/nse-momentum-engine.git`).
6. In your command prompt or terminal inside `D:\GSheetScreener\nse-momentum-engine`, run:
   ```bash
   git remote add origin https://github.com/YOUR_USERNAME/nse-momentum-engine.git
   git branch -M main
   git push -u origin main
   ```

---

### Step 2: One-Time Google Sheets Setup (~5 minutes)

You have an automated script that creates all 5 tabs (`Config`, `RawData`, `Indicators`, `Screener`, `Signal`) with conditional formatting, formulas, and headers:

1. **Get your Google Service Account key JSON** (free):
   - Go to [console.cloud.google.com](https://console.cloud.google.com) → Create Project `NSE Screener`.
   - APIs & Services → Library → Enable **Google Sheets API** and **Google Drive API**.
   - Credentials → **Create Credentials** → **Service Account** → Create → Click it → **Keys** tab → **Add Key (JSON)**.
   - A `.json` file will download to your computer.
2. **Run the auto-setup script**:
   ```bash
   pip install gspread google-auth google-api-python-client
   python scripts/setup_sheets.py --creds path/to/your-key.json --share your-email@gmail.com
   ```
   *(This creates the spreadsheet **"NSE Momentum Engine"** in your Google Drive and shares it with your Gmail as Editor).*
3. **Publish the Signal tab as CSV** (so your mobile app can read it):
   - Open your newly created Google Sheet in your browser.
   - Click **File** → **Share** → **Publish to web**.
   - Select tab: **Signal** | Format: **Comma-separated values (.csv)**.
   - Click **Publish** and copy the generated link.

---

### Step 3: Add GitHub Secrets & Variables

Go to your GitHub repo → **Settings** → **Secrets and variables** → **Actions**:

1. Under **Repository secrets**, click **New repository secret**:
   - `GOOGLE_CREDENTIALS_JSON`: Paste the entire text inside your Google service account `.json` file.
2. Under **Variables** tab (next to Secrets), click **New repository variable**:
   - `SHEET_NAME`: `NSE Momentum Engine`

---

### Step 4: Enable GitHub Pages (Free Hosting for Your App)

1. In your GitHub repo, go to **Settings** → **Pages**.
2. Under **Build and deployment** → **Source**, select **GitHub Actions**.
3. Any push to `main` will automatically deploy your app to:
   `https://YOUR_USERNAME.github.io/nse-momentum-engine/`

---

### Step 5: Install the App on Your Phone

Open Chrome on your Android phone and visit `https://YOUR_USERNAME.github.io/nse-momentum-engine/`:
- **Instant PWA**: Tap `⋮` (Chrome menu) → **Add to Home screen** → **Install**.
- **Settings configuration**:
  1. Open the **NSE Signal** app on your phone.
  2. Tap **⚙️ Settings** tab.
  3. Paste the **Signal CSV URL** from Step 2.
  4. Starting Capital: `1000`.
  5. Tap **Save Settings**.

---

### Step 6: Trigger the First Test Run

To verify everything works before Friday:
1. In your GitHub repo, go to **Actions** tab.
2. Click **Weekly NSE Momentum Screener** on the left.
3. Click **Run workflow** → **Run workflow**.
4. Within 2-3 minutes, it downloads the official Bhavcopy, updates Google Sheets, and your phone app displays the signal!

---

## 2. How the 4-Tier NSE Data Fallback Works

The screener engine (`src/data_pump.py`) features a **fluent, browser-mimicking, 4-tier fallback pipeline**:

```
                       [Every Friday 16:00 IST]
                                  │
                                  ▼
           [Step 0: NSE Browser Handshake (Cookie Session)]
            GET https://www.nseindia.com/ (with Chrome headers)
                                  │
         ┌────────────────────────┼────────────────────────┐
         ▼                        ▼                        ▼
     [Tier 1]                 [Tier 2]                 [Tier 3]
NSE Official UDiFF       NSE Legacy Bhavcopy      NSE Historical Archive
   (Common .csv.zip)    (sec_bhavdata_full.csv)       (.csv.zip)
         │                        │                        │
         └────────────────────────┼────────────────────────┘
                                  │ (If all 3 NSE URLs 404 or maintenance)
                                  ▼
                              [Tier 4]
                     Emergency Liquid Fallback
                     (yfinance Nifty 500 data)
                                  │
                                  ▼
               [Standardized Canonical DataFrame]
         (All columns normalized: SYMBOL, OPEN, HIGH...)
                                  │
                                  ▼
                   Pushed to Google Sheets RawData
```

### Why this is fluent and automatic:
1. **Handles NSE WAF / Anti-Bot Security**: It doesn't blindly `curl` or `requests.get`. It establishes a real browser session, capturing session cookies and sending appropriate `Referer` and `User-Agent` headers.
2. **Modern UDiFF Standard**: Since July 2024, NSE deprecated legacy reports in favor of UDiFF Common Bhavcopy (`BhavCopy_NSE_CM_0_0_0_{date}_F_0000.csv.zip`). Tier 1 automatically decompresses this zip in memory, maps headers (`TCKRSYMB` → `SYMBOL`, `CLSPRIC` → `CLOSE`), and filters `EQ` series equities.
3. **No Downtime**: If NSE archives undergo server maintenance on Friday night, Tier 4 automatically switches to live pricing so your weekly cycle is never broken.

---

## 3. Broker Independence: What Happens if Zerodha Fails?

> **Key Architecture Rule**: Your screener does **NOT** depend on Zerodha to analyze stocks or generate signals. It uses official exchange data.

If Zerodha Kite changes its policies, revokes free API access, or experiences platform downtime, you have **zero vendor lock-in**:

| Execution Method | Cost | How It Works | Status |
|------------------|------|--------------|--------|
| **1. ⚡ Auto-Place GTT (Kite API)** | Free (Personal) | 1-tap automated OCO GTT placement via Kite Connect API | Primary |
| **2. 📋 Copy GTT Details** | Free | Copies trigger, stop-loss, and target values to clipboard. Paste into **Groww GTT**, **Upstox GTT**, **Angel One**, or call your broker. | **Universal Fallback** |
| **3. 🔗 Open in Kite** | Free | Opens stock directly in Kite web search with one click | Quick Manual |
| **4. 🌱 Groww / 📊 Chart** | Free | Opens stock directly in Groww or TradingView to trade on alternate accounts | **Broker Fallback** |

You are never dependent on any single broker.

---

## 4. Your Weekly 3-Minute Friday Routine

Once set up, here is all you do every week:

```
Friday 4:00 PM IST  → GitHub Actions runs automatically in cloud.
Friday 4:10 PM IST  → Open NSE Signal app on your phone.
                      • If CASH: Market breadth weak. Relax and do nothing.
                      • If ACTIVE_SIGNAL: 
                        Option A: Tap "⚡ Auto-Place GTT" (takes 2 seconds)
                        Option B: Tap "📋 Copy GTT Details" and place in Kite/Groww.
Monday 9:15 AM IST  → Order executes automatically at market open.
```

### When a Trade Exits (Target or Stop hit):
1. Open Google Sheets on your phone.
2. Go to **Config** tab → Cell **B2** (`CAPITAL_BASE`).
3. Enter your new capital (e.g., `1180`).
4. The screener dynamically scales your maximum affordable price (`MAX_PRICE = CAPITAL_BASE - 26`) and position sizing for the next trade!
