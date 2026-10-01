# Institutional Quant Momentum Specification
**System Version:** 2.4.0  
**Target Market:** National Stock Exchange of India (NSE Cash Equities)  
**Execution Paradigm:** Serverless Automated End-of-Day Screening with Live Protobuf WebSockets & GTT Execution  

---

## 1. Executive Summary & Core Philosophy

This architecture eliminates emotional discretion, retail chasing, and unhedged drawdowns by unifying four institutional frameworks:
1. **Mark Minervini's Specific Entry Point Analysis (SEPA):** Stage 2 structural mark-up validation and Volatility Contraction Patterns (VCP).
2. **William O'Neil's CANSLIM:** Breakout volume surge confirmation against 20-day institutional accumulation benchmarks.
3. **AQR Factor Momentum:** Cross-sectional percentile ranking combining intermediate-term momentum (3M ROC) with proximity to 52-week highs.
4. **Da, Gurun, & Warachka's "Frog-in-the-Pan" (FIP):** Information discreteness filtering continuous institutional accumulation vs. discrete retail pump-and-dump spikes.

---

## 2. The 5 Institutional Screening Gates

Every trading day after the close of the NSE (15:30 IST), the automated pipeline processes all 2,600+ NSE listed equities through five sequential filters:

```
[2,600+ NSE Bhavcopy Equities]
               │
               ▼ Gate 1: Liquidity & Circuit Band Safety
[Top Liquid Equities: Turnover >= ₹5 Cr, Price >= ₹50, Circuit Band >= 10%]
               │
               ▼ Gate 2: Nifty 500 Macro Regime Governor
[Bull Market: Buys Enabled | Correction: Dynamic | Defensive Cash: 100% Cash]
               │
               ▼ Gate 3: Minervini Stage-2 Trend Template
[Price > 50 SMA > 150 SMA > 200 SMA; 200 SMA Slope > 0; Near 52W High]
               │
               ▼ Gate 4: Cross-Sectional Momentum Score (CMS)
[CMS = 0.60 × Percentile(ROC_3M) + 0.40 × Percentile(52W_Proximity)]
               │
               ▼ Gate 5: Institutional Quality Triad (Anti-Trap)
[Volume Surge >= 1.0x + VCP Ratio <= 1.05 + FIP Smoothness >= 50%]
               │
               ▼
[Ranked Institutional Leaders & Automated 1% Risk Allocation]
```

---

## 3. Mathematical Gate Definitions

### Gate 1: Liquidity & Execution Band Safety
- **Single-Day Turnover Floor:** $\text{Turnover}_{\text{day}} \ge ₹2.0\text{ Crore}$
- **20-Day Average Daily Turnover (ADTV):** $\text{ADTV}_{20} = \frac{1}{20}\sum_{i=0}^{19} (\text{Close}_i \times \text{Volume}_i) \ge ₹5.0\text{ Crore}$
- **Price Floor:** $\text{CMP} \ge ₹50.00$ (filters illiquid penny stocks susceptible to manipulation).
- **Circuit Band Disqualification:** Official NSE daily circuit price bands of **2% and 5% are strictly disqualified**. Narrow bands carry extreme lower-circuit freeze risks, preventing stop-loss execution. Only $\ge 10\%$ or dynamic F&O bands are permitted.

### Gate 2: Macro Regime Governor (Nifty 500 Benchmark)
The macro environment is benchmarked against the Nifty 500 Index (`^CRSLDX`):
- **Bull Market:** $\text{Nifty}_{500} > \text{SMA}_{50} \land \text{Nifty}_{500} > \text{SMA}_{200}$  
  *Action:* 100% long deployment allowed. Standard stop-loss $-5\%$ to $-7\%$.
- **Correction Watch:** $\text{SMA}_{200} < \text{Nifty}_{500} \le \text{SMA}_{50}$  
  *Action:* New entries permitted only for prime setups ($\text{VCP} \le 0.90$).
- **Defensive Cash:** $\text{Nifty}_{500} < \text{SMA}_{200}$  
  *Action:* **Strict 100% Cash.** No new entries permitted. Existing stops tightened to $-4\%$.

### Gate 3: Minervini Stage-2 Trend Template
1. $\text{CMP} > \text{SMA}_{50} > \text{SMA}_{150} > \text{SMA}_{200}$
2. $\text{SMA}_{200, t} > \text{SMA}_{200, t-22}$ (200 SMA slope must be non-negative over 1 month).
3. $\text{CMP} \ge 0.75 \times \text{High}_{52\text{W}}$ (within 25% of 52-week high).
4. $\text{CMP} \ge 1.30 \times \text{Low}_{52\text{W}}$ (at least 30% above 52-week low).
5. $45 \le \text{RSI}_{14} \le 82$ (momentum sweet zone; values $> 82$ rejected as overbought blow-offs).
6. $\text{ROC}_{1\text{M}} \ge -3.0\% \land \text{ROC}_{2\text{M}} > 0\%$ (anti-downfall momentum retention).

### Gate 4: Cross-Sectional Momentum Score (CMS)
Scores are normalized across the entire Stage-2 candidate pool $[0, 100]$:
$$\text{CMS} = 0.60 \times \text{PercentileRank}(\text{ROC}_{3\text{M}}) + 0.40 \times \text{PercentileRank}\left(\frac{\text{CMP}}{\text{High}_{52\text{W}}}\right)$$

### Gate 5: The Institutional Anti-Trap Triad

#### Dimension A: Volume Surge Confirmation
$$\text{Ratio}_{\text{Vol}} = \frac{\text{Volume}_{\text{latest}}}{\text{AverageVolume}_{20}}$$
- $\text{Ratio}_{\text{Vol}} \ge 1.50$: **INSTITUTIONAL SURGE** (high conviction breakout).
- $1.0 \le \text{Ratio}_{\text{Vol}} < 1.50$: **VOLUME CONFIRMED** (acceptable accumulation).
- $\text{Ratio}_{\text{Vol}} < 0.70$: **LOW VOLUME TRAP** (retail fakeout risk; disqualified).

#### Dimension B: Volatility Contraction Pattern (VCP) Ratio
$$\text{Ratio}_{\text{VCP}} = \frac{\text{ATR}_{5}}{\text{ATR}_{20}}$$
- $\text{Ratio}_{\text{VCP}} \le 0.90$: **TIGHT COIL** (extreme volatility compression prior to expansion).
- $0.90 < \text{Ratio}_{\text{VCP}} \le 1.05$: **NORMAL CONTRACTION** (institutional base).
- $\text{Ratio}_{\text{VCP}} > 1.25$: **ERRATIC EXPANSION** (whipsaw zone; disqualified).

#### Dimension C: "Frog-in-the-Pan" (FIP) Information Discreteness
Measures whether momentum is driven by gradual institutional buying or a single speculative gap:
$$\text{Smoothness} = \frac{N_{\text{positive days}}}{N_{\text{active days}}} \times 100 \quad (\text{over past 40 trading days})$$
$$\text{Max 1D Jump Share} = \frac{\max(\Delta \text{Price}_{1\text{D}})}{\text{Price}_t - \text{Price}_{t-40}} \times 100$$
- $\text{Smoothness} \ge 50.0\% \land \text{Max 1D Jump Share} < 60.0\%$: **STEADY ACCUMULATION** (Pass).
- Otherwise: **DISCRETE JUMP RISK** (Mean-reversion retail trap; disqualified).

---

## 4. Over-Extension & Volatility Risk Ceilings

Even if a stock passes all Stage-2 criteria, it is flagged as **OVER-EXTENDED** if:
$$\text{Distance to 50 SMA} = \frac{\text{CMP} - \text{SMA}_{50}}{\text{SMA}_{50}} \times 100 > 25.0\%$$
$$\text{ATR Volatility Ceiling} = \frac{\text{ATR}_{14}}{\text{CMP}} \times 100 > 6.5\%$$
*Rule:* The system refuses to deploy into over-extended leaders (+30%+ above 50 SMA). It automatically alerts the trader to wait for a base pullback or select the next ranked alternate.

---

## 5. Position Sizing & 1% Capital Risk Model

To prevent single-stock ruin, position size is determined by three binding constraints:

$$Q = \min\left( Q_{\text{risk}}, Q_{\text{exposure}}, Q_{\text{liquidity}} \right)$$

1. **Portfolio Risk Model (1% Equity Risk):**
   $$Q_{\text{risk}} = \left\lfloor \frac{\text{Portfolio Equity} \times 0.01}{\text{Entry Price} - \text{Stop Loss Price}} \right\rfloor$$
2. **Maximum Position Exposure (15% Equity Cap):**
   $$Q_{\text{exposure}} = \left\lfloor \frac{\text{Portfolio Equity} \times 0.15}{\text{CMP}} \right\rfloor$$
3. **Turnover Participation Limit (Max 1.5% of 20-Day ADTV):**
   $$Q_{\text{liquidity}} = \left\lfloor \frac{\text{ADTV}_{20} \times 0.015}{\text{CMP}} \right\rfloor$$

*Micro-Account Scaling:* For initial ₹1,000 retail compounding accounts, quantity is budgeted with a ₹26 buffer for statutory STT, exchange turnover fees, and DP charges ($CMP \le Capital - ₹26$).

---

## 6. Trade Execution & GTT State Machine

All trade orders utilize Zerodha Kite / Groww **Good-Till-Triggered (GTT)** orders with a 4-state lifecycle:

| State | Milestone | Stop Level | Execution Action | Rationale |
|---|---|---|---|---|
| **State 0: Risk On** | Entry | $2 \times \text{ATR}_{14}$ bounded $[-5\%, -7\%]$ | Place initial GTT sell trigger | Tail-risk protection |
| **State 1: Risk Free** | $+15\%$ Gain | Ratchet stop to $+1.5\%$ | Update GTT trigger to breakeven | Completely covers STT, broker fees, and taxes |
| **State 2: Bank & Trail** | $+22\%$ Gain | Ratchet runner stop to $+10\%$ | Sell 40% position at $\ge 3R$; keep 60% runner | Locks in bank profit; finances risk-free ride |
| **State 3: Power Runner** | $> +25\%$ Unconstrained | Trailing stop: 50 SMA / 20 EMA | Remove profit ceiling; trail below 20 EMA | Captures uncapped multibagger trend runs |

---

## 7. Zero Manual Reporting Guarantee

- **100% Deterministic Code Execution:** All decision banners, risk warnings, affordability badges, and sizing quantities are computed directly by `quant_engine.py` and `momentum_quality.py`.
- **No Agent Discretion:** Neither the AI agent nor human operators manually select or override signals. The terminal displays the live state strictly generated by the underlying mathematical models.
