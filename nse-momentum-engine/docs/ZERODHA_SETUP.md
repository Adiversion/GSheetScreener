# Zerodha Kite Connect Setup

## Tier Overview

| Tier | Cost | Includes | Missing |
|------|------|----------|---------|
| **Personal** | **FREE** | Orders (all types incl. GTT), Portfolio, Positions, Funds | Live WebSocket feed, Historical candle data |
| Connect | ₹500/month per app | Everything + live feed + historical data | — |

> This strategy only needs **GTT order placement** → **Personal tier (FREE)** is sufficient.

---

## Step 1 — Create Developer Account

1. Go to [developers.kite.trade](https://developers.kite.trade)
2. Click **Login** — use your existing Zerodha credentials
3. Click **Create new app**
4. Fill in:
   - **App name**: `NSE Signal`
   - **App type**: `Personal`
   - **Redirect URL**: `https://YOUR_USERNAME.github.io/nse-momentum-engine/`
   - **Description**: Personal momentum screener
5. Click **Create**

Your **API Key** appears on the app dashboard. Save it.

---

## Step 2 — Enter API Key in App

1. Open **NSE Signal** app on Android
2. Tap **⚙️ Settings** tab
3. Scroll to **Zerodha Kite Connect** section
4. Paste your API Key
5. Leave Access Token blank for now
6. Tap **Save Kite Settings**

---

## Step 3 — Get Daily Access Token (Friday morning, ~30 seconds)

The access token expires at **midnight IST daily**. You need a fresh one each Friday.

### Option A — Login Flow (bookmark this)

Bookmark this URL (replace `YOUR_API_KEY`):
```
https://kite.zerodha.com/connect/login?api_key=YOUR_API_KEY&v=3
```

Each Friday:
1. Open the bookmarked URL in Chrome
2. Login to Zerodha if prompted
3. After login, you'll be redirected to:
   `https://YOUR_USERNAME.github.io/nse-momentum-engine/?request_token=ABCDEF123&action=login&status=success`
4. Copy the `request_token` value from the URL

### Option B — Extract from DevTools (alternative)

1. Login to [kite.zerodha.com](https://kite.zerodha.com) normally
2. Open Chrome DevTools (F12 on PC / tap menu → Developer tools)
3. Go to **Network** tab
4. Click any item in Kite → find an API call to `api.kite.trade`
5. Look at the **Request Headers** → `Authorization: token API_KEY:ACCESS_TOKEN`
6. Copy the `ACCESS_TOKEN` part

### Paste Token in App

1. Open **NSE Signal** app → **⚙️ Settings**
2. Paste the Access Token in the **Access Token** field
3. Tap **Save Kite Settings**
4. Status shows: ✅ Kite configured. GTT auto-place enabled.

---

## Step 4 — Auto-Place GTT

After every Friday screener run:

1. Open NSE Signal app → **📡 Signal** tab
2. Verify the signal is `ACTIVE_SIGNAL` (not CASH)
3. Review the GTT levels table
4. Tap **⚡ Auto-Place GTT**
5. The app places a **Two-Leg OCO GTT**:
   - **Leg 1**: SELL at `INITIAL_STOP` → stop-loss
   - **Leg 2**: SELL at `M1_TARGET` → take profit

---

## GTT Milestone Management (Manual Steps)

After placing the initial GTT, you manage milestones manually in Kite:

### After M1 Hit (+15%)

1. Open Kite → GTT Orders
2. Find your active GTT → Edit
3. Change stop trigger from `INITIAL_STOP` to `M1_STOP` value
4. (The M1_STOP value is in the app's Signal tab)

### After M2 Hit (+30%)

1. Open Kite → GTT Orders → Edit
2. Change stop trigger to `M2_STOP` value

### After M3 Hit (+50%)

1. Kite doesn't support trailing stops natively
2. Check stock every Friday
3. Use the 20-DMA from the app's Indicators section as your trail reference
4. Manually adjust GTT stop when 20-DMA moves up significantly

---

## Without API Key — Manual Options

The app provides two alternatives that don't require API setup:

### 🔗 Open in Kite Button
- Opens `kite.zerodha.com` with the stock pre-searched
- You manually fill in GTT values (2-3 minutes)

### 📋 Copy GTT Details Button
Copies this to clipboard:
```
═══ NSE Signal GTT Order ═══
Stock   : TATAPOWER (NSE)
CMP     : ₹430.50
Shares  : 2 shares
Capital : ₹861.00

── Initial Stop ──────────────
Trigger : ₹400.37  (hard stop)

── Milestone 1 (+15%) ────────
Target  : ₹495.08
→ Move stop to ₹441.26 after M1 hit

── Milestone 2 (+30%) ────────
Target  : ₹559.65
→ Move stop to ₹495.08 after M2 hit

── Milestone 3 (+50%) ────────
Target  : ₹645.75
→ Trail via 20-DMA after M3 hit

CMS Score: 68.42  |  RSI: 58.2  |  ATR: 12.30
Generated: 30/09/2026, 4:13:15 pm
```

Paste this anywhere (notes, WhatsApp self-message) and use it as a reference while filling Kite GTT manually.

---

## Cost Math (Why Personal Tier is Fine)

| Item | Cost |
|------|------|
| Kite Connect Personal API | ₹0/month |
| GTT placement | ₹0 |
| GTT execution (if triggered) | Normal Zerodha brokerage (₹20 flat) |
| DP charge (on sell) | ~₹21.83 per scrip per day sold |
| STT on sell | 0.1% of sell value |

For a ₹1,000 position at +15% (₹150 gross profit):
- Brokerage: ₹20
- DP charge: ₹21.83
- STT: ₹1.15 (on ₹1,150 sell)
- Total costs: ~₹43
- **Net profit: ~₹107 (10.7% net return)**

The M1 stop at +2.5% ensures you never lose money on a position that reached +15%.
