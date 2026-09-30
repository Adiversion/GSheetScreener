# 🚀 NSE Momentum Screener — Complete Setup & User Guide

> **Your Repository:** [https://github.com/Adiversion/GSheetScreener](https://github.com/Adiversion/GSheetScreener)  
> **Your Service Account Key:** `D:\GSheetScreener\nse-momentum-engine\nse-screener-1-8294a3dbb1a6.json`  
> **Your Bot's Google Email:** `nse-screener@nse-screener-1.iam.gserviceaccount.com`  
> **Spreadsheet Name:** `NSE Momentum Engine`

---

## 📋 What You Need To Do Right Now (4 Quick Steps)

Everything in the code is built, tested, and pushed to your GitHub repository. Follow these 4 steps to link your Google Sheet and mobile app:

---

### Step 1: Create & Share Your Google Sheet (30 Seconds)

Because Google Cloud service accounts have 0 MB of Drive storage by default, you create the file in your personal Google Drive (which has 15 GB free):

1. Open your browser and go to: **[https://sheets.new](https://sheets.new)**
2. Rename the blank spreadsheet at the top left to:  
   ```text
   NSE Momentum Engine
   ```
3. Click the green **Share** button (top right).
4. In the "Add people and groups" box, paste your bot's email:
   ```text
   nse-screener@nse-screener-1.iam.gserviceaccount.com
   ```
5. Ensure the permission dropdown is set to **Editor**, uncheck "Notify people", and click **Share**.

---

### Step 2: Run the Automated Sheet Configuration (10 Seconds)

Now run the auto-setup script on your computer. It connects to the shared sheet and creates all 5 tabs (`Config`, `RawData`, `Indicators`, `Screener`, `Signal`) with conditional formatting, formulas, and headers:

Open PowerShell / Command Prompt and run:

```powershell
cd D:\GSheetScreener\nse-momentum-engine
python scripts/setup_sheets.py --creds nse-screener-1-8294a3dbb1a6.json
```

You will see green checkmarks for all 5 tabs.

---

### Step 3: Publish the Signal Tab as CSV & Add GitHub Secrets

#### 3.1 Publish Signal Tab as CSV (For your Mobile App)
1. Open your **NSE Momentum Engine** spreadsheet in your browser.
2. Click **File** → **Share** → **Publish to web**.
3. In the dialog:
   - First dropdown: Select **Signal**
   - Second dropdown: Select **Comma-separated values (.csv)**
4. Click **Publish** and confirm with **OK**.
5. **Copy the link** generated (looks like: `https://docs.google.com/spreadsheets/d/.../pub?gid=...&output=csv`). Keep this link handy for Step 4.

#### 3.2 Add Credentials to GitHub Secrets (For Daily Automated Cloud Runs)
1. Open your GitHub Repository Settings:  
   👉 **[https://github.com/Adiversion/GSheetScreener/settings/secrets/actions](https://github.com/Adiversion/GSheetScreener/settings/secrets/actions)**
2. Under **Repository secrets**, click **New repository secret**:
   - **Name:** `GOOGLE_CREDENTIALS_JSON`
   - **Secret:** Open `D:\GSheetScreener\nse-momentum-engine\nse-screener-1-8294a3dbb1a6.json` in Notepad, copy all text, and paste it here.
   - Click **Add secret**.
3. Under the **Variables** tab (next to Secrets):
   - Click **New repository variable**:
   - **Name:** `SHEET_NAME`
   - **Value:** `NSE Momentum Engine`
   - Click **Add variable**.

#### 3.3 Enable GitHub Pages (Free App Hosting)
1. In your GitHub repo, go to **Settings** → **Pages**:  
   👉 **[https://github.com/Adiversion/GSheetScreener/settings/pages](https://github.com/Adiversion/GSheetScreener/settings/pages)**
2. Under **Build and deployment** → **Source**, select **GitHub Actions**.

---

### Step 4: Install the App on Your Phone (Viewer Mode)

1. Open Chrome on your Android phone and visit your GitHub Pages URL:
   ```text
   https://Adiversion.github.io/GSheetScreener/
   ```
2. Tap `⋮` (Chrome menu) → **Add to Home screen** → **Install**.
3. Open the installed **NSE Signal** app on your phone.
4. Tap the **⚙️ Settings** tab at the bottom.
5. In **Google Sheet CSV URL**, paste the URL from Step 3.1.
6. In **Capital Base**, type `1000`.
7. Tap **Save Settings**.

---

## 🎯 How Your Daily Routine Works (Zero Screen Time)

### 1. Daily Cloud Screener (Automatic)
* Every weekday (Monday to Friday) at **5:30 PM IST**, GitHub Actions runs automatically in the cloud.
* It downloads the official NSE Bhavcopy, computes momentum scores, and updates the **Signal** tab with that day's strongest stock.
* If Friday or any weekday was an NSE market holiday, it automatically detects the holiday and uses the previous active trading day.

### 2. How to Place the Manual GTT in Zerodha Kite (30 Seconds)
When you are in cash and the app shows an `ACTIVE_SIGNAL`:

1. Open your **NSE Signal** app on your phone.
2. Review the **Signal Tab**:
   * It shows the Stock Symbol (e.g. `TATAPOWER`), Current Price, Shares to buy, Stop Loss, and Target.
3. Tap **📋 1-Tap Copy GTT Form**:
   * It copies the pre-formatted order details directly to your phone clipboard.
4. Tap **🔗 Open Kite** (or open your Zerodha Kite app):
   * Search the stock symbol.
   * Tap **Create GTT**.
   * Select **Transaction:** `BUY` | **Type:** `OCO (Two-Leg)`.
   * **Stop-Loss:** Set trigger to the exact Stop Loss ₹ shown in your app.
   * **Target:** Set trigger to the exact Target ₹ shown in your app.
   * **Quantity:** Set shares shown in the app.
   * Swipe to create GTT!
5. **Done!** Zerodha's server monitors this order 24/7. When target or stop hits, Zerodha executes it automatically during market hours.

---

## 📈 Compounding & Position Sizing Rules

* **Initial Phase (₹1,000 to ₹4,999):**
  * Allocate 100% of capital into **Rank #1** stock.
  * Why: Defeats Zerodha's flat ₹21.83 DP charge fee drag.
* **Growth Phase (₹5,000 to ₹9,999):**
  * Split capital 50% / 50% between **Rank #1** and **Rank #2** (shown under "Alternate Picks" in the app).
  * Why: Protects against overnight lower-circuit gap downs.
* **Wealth Phase (₹10,000+):**
  * Split capital across the **Top 3 winners** (33% each).

---

## 💡 Updating Your Capital After a Trade Exits
Whenever Zerodha notifies you that your GTT target or stop-loss was triggered:
1. Open Google Sheets on your phone.
2. Go to the **Config** tab.
3. Tap Cell **B2** (`CAPITAL_BASE`) and enter your new total balance (e.g., `1180`).
4. The screener dynamically updates your maximum price ceiling and calculates exact position sizing for the next trade!

---

## 🛡️ Cost Guarantee
Every single component in this stack costs **₹0.00**:
* NSE Market Data: 100% Free
* GitHub Actions: 100% Free (<1% of monthly free tier)
* Google Sheets & Drive API: 100% Free
* GitHub Pages Hosting: 100% Free
* Zerodha GTT: 100% Free
