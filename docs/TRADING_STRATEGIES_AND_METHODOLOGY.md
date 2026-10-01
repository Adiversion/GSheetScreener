# Trading Strategies & Methodology Playbook
**Document Version:** 1.0.0  
**Target Market:** National Stock Exchange of India (NSE Cash Equities)  
**System Architecture:** Quantitative Momentum Screener, Risk Engine & GTT Trade Lifecycle  

---

## Executive Overview

This system operates not as a single speculative indicator, but as an **integrated multi-strategy quantitative execution stack**. It translates institutional momentum anomalies and risk-budgeting principles into automated screening, sizing, and exit rules for Indian equities.

---

## Strategy 1: Minervini SEPA Stage-2 Trend Continuation (Core Alpha)

### Concept & Theoretical Edge
Markets spend 70% of their time in choppy consolidations (Stage 1 accumulation or Stage 3 distribution) and 30% in sustained directional mark-up (Stage 2). Minervini's SEPA (Specific Entry Point Analysis) combined with Stan Weinstein's Stage Analysis isolates the exact transition where institutional accumulation drives price into Stage 2.

### Criteria & Rules:
1. **Moving Average Alignment (Mark-Up Structure):**
   $$\text{CMP} > \text{SMA}_{50} > \text{SMA}_{150} > \text{SMA}_{200}$$
2. **Long-Term Trend Confirmation:**
   $$\text{SMA}_{200}[t] > \text{SMA}_{200}[t-22] \quad (\text{Normalized slope } > 0.0\% \text{ over 1 month})$$
3. **52-Week High Proximity (Leader Filter):**
   $$\text{CMP} \ge 0.75 \times \text{High}_{52\text{W}} \quad (\text{Within 25% of annual highs})$$
   $$\text{CMP} \ge 1.30 \times \text{Low}_{52\text{W}} \quad (\text{At least 30% above annual lows})$$
4. **Momentum Sweet Zone:**
   $$45.0 \le \text{RSI}_{14} \le 82.0$$
   *(Filters sluggish, lagging stocks while rejecting blow-off climax overbought extremes).*

---

## Strategy 2: Two-Tier +15% Rotation Cycle (Retail Compounding Mode)

### Concept & Theoretical Edge
For retail and micro-accounts ($< ₹50,000$), traditional multi-position diversification (e.g., 20 positions with 5% capital each) suffers from fee drag and slow capital turnover. Strategy 2 focuses **100% of capital into the single highest-conviction Stage-2 leader** for rapid, low-friction compounding cycles.

### Execution Rules:
1. **Entry:** 100% of account equity is deployed into Leader #1 (budgeting ₹26 for statutory transaction fees).
2. **Stop Loss (Risk Bounded):** Initial stop is placed at $2 \times \text{ATR}_{14}$, strictly bounded between $-5.0\%$ and $-7.0\%$.
3. **Exit Target (+15% Clean Exit):**
   $$\text{Target Price} = \text{Entry Price} \times 1.15$$
   The **entire position (100% of shares)** is sold immediately upon reaching $+15\%$.
4. **Redeployment:**
   The full proceeds (initial principal + profit) are rolled into the next newly screened Leader #1.
5. **Compounding Mathematics:**
   $$1.15^5 = 2.011 \quad (5 \text{ completed cycles double the account capital})$$

---

## Strategy 3: The 40/60 Asymmetric Multibagger Trail (Portfolio Mode)

### Concept & Theoretical Edge
For accounts $\ge ₹50,000$, Strategy 3 provides an asymmetric payoff profile. It locks in realized profits early to guarantee a risk-free trade, while retaining an uncapped runner to capture multi-month 50%–200%+ power trends.

### 4-State Execution Lifecycle:
```text
State 0: Risk On (Entry)
  ├── Stop: 2×ATR14 bounded [-5%, -7%]
  └── Target: Monitor for +15% expansion
         │
         ▼
State 1: Risk Free (+15% Gain)
  ├── Stop: Ratchet to +1.5% cost-covering floor (zero downside risk)
  └── STT, exchange charges, and taxes fully funded
         │
         ▼
State 2: Bank & Trail (+22% Gain / >= 3R)
  ├── Sell: Bank 40% of shares at >= 3R
  └── Runner Stop: Ratchet remaining 60% runner stop to +10% guaranteed profit
         │
         ▼
State 3: Uncapped Power Runner (> +25% Gain)
  ├── Ceiling: Removed entirely
  └── Trailing Stop: Dynamically trailed below max(50 SMA, 20 EMA)
```

---

## Strategy 4: The Institutional Anti-Trap Defense (Quality Gates)

Even inside Stage 2, over 50% of breakouts fail as retail traps (false breakouts on low volume or expanding whipsaw volatility). Strategy 4 acts as a strict disqualification veto:

### 1. High-Volume Accumulation Surge (O'Neil CANSLIM)
$$\text{Ratio}_{\text{Vol}} = \frac{\text{Volume}_{\text{latest}}}{\text{AverageVolume}_{20}}$$
- $\text{Ratio}_{\text{Vol}} \ge 1.50\times$: Heavy institutional buying (Strong Pass).
- $1.00\times \le \text{Ratio}_{\text{Vol}} < 1.50\times$: Normal accumulation (Pass).
- $\text{Ratio}_{\text{Vol}} < 0.70\times$: **Low Volume Trap** (Disqualified).

### 2. Volatility Contraction Ratio (VCR Compression)
$$\text{Ratio}_{\text{VCR}} = \frac{\text{ATR}_{5}}{\text{ATR}_{20}}$$
- $\text{Ratio}_{\text{VCR}} \le 0.90$: Tight coil compression prior to expansion (Prime Pass).
- $0.90 < \text{Ratio}_{\text{VCR}} \le 1.05$: Normal orderly base (Pass).
- $\text{Ratio}_{\text{VCR}} > 1.25$: **Erratic Volatility Expansion** (Disqualified).

### 3. "Frog-in-the-Pan" (FIP) Information Discreteness
Measures path smoothness vs. speculative discrete jump risk:
$$\text{Smoothness} = \frac{N_{\text{positive days}}}{N_{\text{active days}}} \times 100 \ge 50.0\%$$
$$\text{Max 1D Gain Share} = \frac{\max(g_t)}{\sum_{t=1}^{40} g_t} \times 100 \le 40.0\% \quad (g_t = \max(0, \Delta \text{Close}_t))$$
- Rejects stocks propelled by a single 20% speculative gap. Only gradual, persistent institutional buying passes.

### 4. Over-Extension Ceiling
$$\text{Distance to 50 SMA} = \frac{\text{CMP} - \text{SMA}_{50}}{\text{SMA}_{50}} \times 100 > 25.0\% \implies \text{OVER\_EXTENDED}$$
- Refuses to buy extended leaders. Demands pullbacks to moving averages or fresh bases.

---

## Strategy 5: Macro Capital Preservation Circuit Breaker (Regime Governor)

### Concept & Theoretical Edge
Paul Tudor Jones' fundamental rule: *"I always look at the 200-day moving average of stocks or indices. My metric for anything I own is: is it above the 200-day?"* In Indian equities, when the broader market is in a structural bear market, individual momentum breakouts fail at rates exceeding 80%.

### Rules:
1. **Benchmark:** Nifty 500 Index (`^CRSLDX`).
2. **Defensive Cash Trigger:**
   $$\text{Close}_{\text{Nifty500}} \le \text{SMA}_{200}$$
3. **Execution Directive:**
   - **Immediate 100% Cash Preservation:** New entries are banned ($0$ shares permitted).
   - Existing open positions have their State 0 stops tightened from $-6\%$ to $-4\%$.
   - Protects accumulated annual profits from broad market drawdowns.

---

## Strategy 6: Execution & Liquidity Hygiene

1. **Turnover Floor:** 20-day Average Daily Turnover (ADTV) $\ge ₹5.0\text{ Crore}$ ensures complete market depth with zero slippage for retail size.
2. **Circuit Band Safety:** $2\%$ and $5\%$ price bands are disqualified. Prevents lower-circuit freeze lockups where stops cannot be executed.
3. **GTT Standing Orders:** Orders are pre-committed through Zerodha Kite / Groww Good-Till-Triggered standing order infrastructure, eliminating emotional execution errors and screen watching.
