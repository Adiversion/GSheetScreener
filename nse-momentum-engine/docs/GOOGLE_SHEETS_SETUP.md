# Google Sheets Setup Guide

> **Quick path**: Run `python scripts/setup_sheets.py --creds your-creds.json` to auto-create everything.
> Manual steps below if you prefer to understand what's being built.

---

## Overview — 5 Tabs

| Tab | Who writes it | Purpose |
|-----|--------------|---------|
| **Config** | You (manually) | Capital, price limits — the control panel |
| **RawData** | `data_pump.py` (auto) | Weekly Bhavcopy OHLCV, grows over time |
| **Indicators** | Formulas + `data_pump.py` | Indicator summaries per symbol |
| **Screener** | `data_pump.py` (auto) | All stocks that passed filters |
| **Signal** | `data_pump.py` (auto) | Rank #1 winner — read by mobile app |

---

## Part 1 — Google Cloud Setup (One-Time, ~10 minutes)

### 1.1 Create a Google Cloud Project

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Click **Select a project** → **New Project**
3. Name: `NSE Screener` → **Create**
4. Wait ~30 seconds

### 1.2 Enable APIs

1. **APIs & Services → Library**
2. Search `Google Sheets API` → **Enable**
3. Search `Google Drive API` → **Enable**

### 1.3 Create Service Account

1. **APIs & Services → Credentials**
2. **+ Create Credentials → Service Account**
3. Name: `nse-screener-bot` → **Create and Continue** → **Done**
4. Click the new service account → **Keys tab** → **Add Key → Create new key → JSON**
5. A `.json` file downloads — **keep it safe, back it up**

### 1.4 Add to GitHub Secrets

1. Open the downloaded JSON file — copy the **entire contents**
2. GitHub repo → **Settings → Secrets and variables → Actions**
3. **New repository secret**:
   - Name: `GOOGLE_CREDENTIALS_JSON`
   - Value: paste the entire JSON

---

## Part 2 — Auto-Setup Script (Recommended)

The script creates and formats all 5 tabs automatically:

```bash
# Install dependencies
pip install gspread google-auth google-api-python-client

# Run the setup (creates the sheet + all tabs + formatting)
python scripts/setup_sheets.py --creds path/to/your-credentials.json

# Also share with your personal Gmail (so you can view/edit it)
python scripts/setup_sheets.py --creds path/to/your-credentials.json --share your@gmail.com
```

The script prints:
```
✅ Spreadsheet ready: https://docs.google.com/spreadsheets/d/YOUR_SHEET_ID/edit
📊 Sheet ID: YOUR_SHEET_ID

📋 Next steps:
1. Go to File → Share → Publish to web
2. Select "Signal" tab → "Comma-separated values (.csv)" → Publish
3. Copy the CSV URL → paste in NSE Signal app → Settings
```

---

## Part 3 — Manual Tab Setup (If Not Using Script)

### Config Tab

Click cell **A1**, type `Parameter`, Tab to B1: `Value`, Tab to C1: `Note`, Enter.

Fill rows 2–11:

| A | B | C |
|---|---|---|
| CAPITAL_BASE | 1000 | **← Update this after every exit** |
| MIN_PRICE | 100 | Fixed minimum CMP |
| MAX_PRICE | =B2-26 | Auto-calculated |
| MIN_AVG_VOLUME | 500000 | 20-day volume floor |
| STOP_PCT | 0.07 | 7% hard stop |
| M1_TARGET_PCT | 0.15 | +15% Milestone 1 |
| M2_TARGET_PCT | 0.30 | +30% Milestone 2 |
| M3_TARGET_PCT | 0.50 | +50% Milestone 3 |
| M1_STOP_PCT | 0.025 | +2.5% ratchet after M1 |
| M2_STOP_PCT | 0.15 | +15% ratchet after M2 |

**Format B2 as Currency:** Select B2 → Format → Number → ₹

**Highlight B2 light blue:** So it's obvious this is the key cell to update.

### RawData Tab

Paste headers into row 1 (one per column A through N):
```
SYMBOL  SERIES  OPEN  HIGH  LOW  CLOSE  LAST  PREVCLOSE  TOTTRDQTY  TOTTRDVAL  TIMESTAMP  TOTALTRADES  ISIN  FETCH_DATE
```

Freeze row 1: View → Freeze → 1 row

This tab fills automatically. Do not edit it.

### Indicators Tab

Paste headers into row 1:
```
SYMBOL  LATEST_CLOSE  HIGH_52W  DATA_POINTS  HAS_HISTORY  SMA_50_APPROX  SMA_200_APPROX  ROC_20  ROC_40  ROC_60  VOL_20_AVG  PROX_52W  CMS_SCORE_APPROX
```

In **A2**, paste:
```
=IFERROR(SORT(UNIQUE(FILTER(RawData!A2:A, RawData!A2:A<>""))), "")
```
This auto-populates all unique symbols from RawData.

In **D2** (DATA_POINTS — how many weeks of data per symbol):
```
=IFERROR(COUNTIF(RawData!A:A, A2)-1, 0)
```
Drag down.

In **E2** (HAS_HISTORY — needs 250+ bars):
```
=IF(D2>=250, "YES", "NO")
```
Drag down.

> All other indicator columns (SMA50, SMA200, RSI, etc.) are computed by `data_pump.py` in Python and written directly to the Signal tab. The formula approximations here are reference only.

### Screener Tab

Paste headers:
```
SYMBOL  CMP  CMS_SCORE  RSI_14  ROC_1M  ROC_2M  ROC_3M  SMA_50  SMA_200  ATR_14  HIGH_52W  SHARES  CAPITAL_REQ  INITIAL_STOP  M1_TARGET  M2_TARGET  M3_TARGET  PASSES_ALL
```

Add a note in A1: `Data written by GitHub Actions every Friday at 16:00 IST. Do not edit.`

This tab is populated automatically by `data_pump.py`.

### Signal Tab

Paste headers (Row 1):
```
STATUS  TIMESTAMP  SYMBOL  CMP  CMS_SCORE  ROC_1M  ROC_2M  ROC_3M  RSI_14  SMA_50  SMA_200  ATR_14  HIGH_52W  SHARES  CAPITAL_REQUIRED  INITIAL_STOP  M1_TARGET  M1_STOP  M2_TARGET  M2_STOP  M3_TARGET  CAPITAL_BASE  TOTAL_QUALIFIED
```

Put a placeholder in Row 2:
```
CASH  [today's date]  —  —  —  ...
```

**Conditional formatting on column A:**
- Format → Conditional formatting
- Rule 1: `Text is exactly "ACTIVE_SIGNAL"` → Background: Green
- Rule 2: `Text is exactly "CASH"` → Background: Grey

---

## Part 4 — Publish Signal Tab as CSV (Required for App)

This is what lets the mobile app read your data without a login.

1. **File → Share → Publish to web**
2. First dropdown: select **Signal**
3. Second dropdown: select **Comma-separated values (.csv)**
4. Click **Publish** → click **OK** to confirm
5. Copy the URL — it looks like:
   ```
   https://docs.google.com/spreadsheets/d/SHEET_ID/pub?gid=SHEET_GID&single=true&output=csv
   ```

6. Open **NSE Signal app** → **⚙️ Settings** → paste this URL → Save

> **Privacy note**: The Signal tab is publicly readable by anyone with this URL. It shows your current stock pick, capital, and GTT levels. If you want privacy, read about using the Google Sheets API with an API key instead (more complex setup).

---

## Part 5 — Share with Service Account

The Python script needs write access to your sheet.

1. Open your Google Sheet → **Share** (top right)
2. Paste the `client_email` from your service account JSON
   (looks like: `nse-screener-bot@nse-screener-xxx.iam.gserviceaccount.com`)
3. Give it **Editor** access → **Share**

---

## Part 6 — Updating Capital (Weekly Ritual)

After every trade exit on Zerodha:

1. Open Google Sheets on your phone
2. Go to **Config** tab
3. Tap cell **B2**
4. Type new capital amount → ✓ (checkmark/Enter)

**Net capital calculation:**
```
New Capital = (Exit Price × Shares)
            - (Exit Price × Shares × 0.001)   [STT 0.1% on sell]
            - 20                               [Zerodha brokerage]
            - 21.83                            [DP charge]
            - (20 × 0.18)                      [GST on brokerage]
            ≈ (Exit Price × Shares) - 45.43
```

Or use the **NSE Signal app** → **💼 Portfolio** → **Record Exit** modal — it calculates net capital automatically.

---

## Troubleshooting

| Problem | Solution |
|---------|---------|
| Script fails: `SpreadsheetNotFound` | The sheet name must match `SHEET_NAME` env var exactly |
| Script fails: `APIError: [403]` | Service account not shared with the spreadsheet |
| App shows "Failed to fetch" | Signal tab not published to web, or wrong CSV URL |
| Signal tab empty | First run of data_pump.py hasn't completed yet |
| RawData has duplicate rows | `append_to_rawdata()` idempotency check failed — check FETCH_DATE column |
| MAX_PRICE not updating | data_pump.py couldn't find `MAX_PRICE` row in Config tab — check spelling |
