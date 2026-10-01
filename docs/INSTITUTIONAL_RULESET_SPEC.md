# Institutional Quant Momentum Specification
**System Version:** 2.5.0 (Implementation-Grade Specification)  
**Target Market:** National Stock Exchange of India (NSE Cash Equities)  
**Execution Paradigm:** Serverless Automated End-of-Day Screening with Live Protobuf WebSockets & GTT Execution  

---

## 1. Executive Architecture & Core Philosophy

This architecture eliminates emotional discretion, retail chasing, and unhedged drawdowns by unifying four quantitative frameworks into a layered pipeline:
1. **Mark Minervini's Specific Entry Point Analysis (SEPA):** Stage 2 structural mark-up template and Volatility Contraction Ratio (VCR) compression.
2. **William O'Neil's CANSLIM:** Breakout volume surge confirmation against 20-day institutional accumulation benchmarks.
3. **AQR Factor Momentum:** Cross-sectional percentile ranking combining intermediate-term momentum (3M ROC) with proximity to 52-week highs.
4. **Da, Gurun, & Warachka's "Frog-in-the-Pan" (FIP):** Information discreteness filtering continuous steady accumulation vs. single-day discrete speculative spikes.

### System Layer Separation
```text
[Raw NSE Bhavcopy & Historical EOD Bars]
                 │
                 ▼
[Layer 1: Data Validation & Universe Safety (Turnover, Price, Circuit Bands)]
                 │
                 ▼
[Layer 2: Macro Regime Governor (Nifty 500 ^CRSLDX vs 50/200 SMA)]
                 │
                 ▼
[Layer 3: Trend & Structural Mark-up (Minervini-Inspired Stage-2 Template)]
                 │
                 ▼
[Layer 4: Cross-Sectional Momentum Engine (CMS Percentile Ranking)]
                 │
                 ▼
[Layer 5: Quality & Anti-Trap Triad (Volume Confirmation, VCR Coiling, FIP Discreteness)]
                 │
                 ▼
[Layer 6: Over-Extension & Volatility Risk Ceilings (SMA50 Distance <= 25%, ATR% <= 6.5%)]
                 │
                 ▼
[Layer 7: Capital Sizing & Two-Tier Execution State Machine (GTT Orders)]
```

---

## 2. Layer 1: Universe Definition & Liquidity Safety

All 2,600+ NSE listed cash equities are evaluated after the market close (15:30 IST) against strict liquidity and circuit constraints:

- **Single-Day Turnover Floor:** $\text{Turnover}_{\text{day}} \ge ₹2.0\text{ Crore}$
- **20-Day Average Daily Turnover (ADTV):** $\text{ADTV}_{20} = \frac{1}{20}\sum_{i=0}^{19} (\text{Close}_i \times \text{Volume}_i) \ge ₹5.0\text{ Crore}$
- **Price Floor:** $\text{CMP} \ge ₹50.00$ (filters illiquid penny stocks susceptible to pump-and-dump manipulation).
- **Circuit Band Disqualification:** Official NSE daily circuit price bands of **2% and 5% are strictly disqualified**. Narrow bands carry extreme lower-circuit freeze risks, preventing stop-loss execution. Only $\ge 10\%$ or dynamic F&O bands are permitted.

---

## 3. Layer 2: Macro Regime Governor (Nifty 500 Benchmark)

The macro environment is benchmarked against the Nifty 500 Index (`^CRSLDX`):
- **Bull Market:** $\text{Close} > \text{SMA}_{50} \land \text{Close} > \text{SMA}_{200}$  
  *Action:* 100% long deployment allowed. Standard stop-loss $-5\%$ to $-7\%$.
- **Correction Watch:** $\text{SMA}_{200} < \text{Close} \le \text{SMA}_{50}$  
  *Action:* New entries permitted only for compressed prime setups ($\text{VCR} \le 0.90$).
- **Defensive Cash:** $\text{Close} \le \text{SMA}_{200}$  
  *Action:* **Strict 100% Cash.** No new entries permitted. Existing stops tightened to $-4\%$.

---

## 4. Layer 3: Minervini-Inspired Stage-2 Trend Template

Stocks passing the liquidity filters must satisfy all Stage-2 trend criteria:
1. $\text{CMP} > \text{SMA}_{50} > \text{SMA}_{150} > \text{SMA}_{200}$
2. **Normalized 200 SMA Slope:**
   $$\text{Slope}_{200\%} = \left(\frac{\text{SMA}_{200}[t]}{\text{SMA}_{200}[t-22]} - 1\right) \times 100 > 0.0\%$$
   (Ensures the 200-day moving average is actively trending upwards over the past 22 trading days).
3. $\text{CMP} \ge 0.75 \times \text{High}_{52\text{W}}$ (within 25% of 52-week high).
4. $\text{CMP} \ge 1.30 \times \text{Low}_{52\text{W}}$ (at least 30% above 52-week low).
5. $45 \le \text{RSI}_{14} \le 82$ (momentum sweet zone; values $> 82$ rejected as overbought blow-offs).
6. $\text{ROC}_{1\text{M}} \ge -3.0\% \land \text{ROC}_{2\text{M}} > 0\%$ (anti-downfall momentum retention).

---

## 5. Layer 4: Cross-Sectional Momentum Score (CMS)

The Cross-Sectional Momentum Score is computed strictly across all candidates passing Layers 1–3:
$$\text{CMS} = 0.60 \times \text{PercentileRank}(\text{ROC}_{3\text{M}}) + 0.40 \times \text{PercentileRank}\left(\frac{\text{CMP}}{\text{High}_{52\text{W}}}\right)$$
*Percentile Method:* Scaled $[0.0, 100.0]$ using empirical rank over the active Stage-2 candidate pool.

---

## 6. Layer 5: Institutional Quality Triad (Anti-Trap Filters)

### Dimension A: Volume Accumulation Confirmation
$$\text{Ratio}_{\text{Vol}} = \frac{\text{Volume}_{\text{latest}}}{\text{AverageVolume}_{20}}$$
- $\text{Ratio}_{\text{Vol}} \ge 1.50$: **INSTITUTIONAL SURGE** (Strong Pass — heavy institutional footprint).
- $1.00 \le \text{Ratio}_{\text{Vol}} < 1.50$: **VOLUME CONFIRMED** (Pass — healthy accumulation).
- $0.70 \le \text{Ratio}_{\text{Vol}} < 1.00$: **SUB-AVERAGE** (Caution — insufficient conviction).
- $\text{Ratio}_{\text{Vol}} < 0.70$: **LOW VOLUME TRAP** (Disqualified — high fakeout risk).

### Dimension B: Volatility Contraction Ratio (VCR)
Measures short-term volatility compression relative to intermediate-term base range:
$$\text{Ratio}_{\text{VCR}} = \frac{\text{ATR}_{5}}{\text{ATR}_{20}}$$
- $\text{Ratio}_{\text{VCR}} \le 0.90$: **TIGHT COIL** (Prime setup — extreme range compression).
- $0.90 < \text{Ratio}_{\text{VCR}} \le 1.05$: **NORMAL CONTRACTION** (Pass — orderly consolidation).
- $1.05 < \text{Ratio}_{\text{VCR}} \le 1.25$: **NEUTRAL** (Acceptable base).
- $\text{Ratio}_{\text{VCR}} > 1.25$: **ERRATIC EXPANSION** (Disqualified — whipsaw/distribution risk).

### Dimension C: "Frog-in-the-Pan" (FIP) Information Discreteness
Measures whether momentum is driven by continuous steady accumulation or a single discrete pump.
$$\text{Smoothness} = \frac{N_{\text{positive days}}}{N_{\text{active days}}} \times 100 \quad (\text{over past 40 trading days})$$
$$\text{Max 1D Gain Share} = \frac{\max(g_t)}{\sum_{t=1}^{40} g_t} \times 100 \quad \text{where } g_t = \max(0, \text{Close}_t - \text{Close}_{t-1})$$
*(Note: Denominator is sum of all positive daily gains, guaranteeing stability $[0\%, 100\%]$ without near-zero or negative denominator division errors).*
- $\text{Smoothness} \ge 50.0\% \land \text{Max 1D Gain Share} \le 40.0\%$: **PASS**
  - $\text{Smoothness} \ge 55.0\% \land \text{Max 1D Gain Share} \le 25.0\%$: **STEADY ACCUMULATION**
  - Otherwise: **MODERATE SMOOTHNESS**
- $\text{Smoothness} < 50.0\% \lor \text{Max 1D Gain Share} > 40.0\%$: **DISCRETE JUMP RISK** (Disqualified).

---

## 7. Layer 6: Over-Extension & Volatility Risk Ceilings

To prevent buying at the top of a run, setups are gated by strict over-extension rules:
$$\text{Distance to 50 SMA} = \frac{\text{CMP} - \text{SMA}_{50}}{\text{SMA}_{50}} \times 100 \le 25.0\%$$
$$\text{ATR Volatility Ceiling} = \frac{\text{ATR}_{14}}{\text{CMP}} \times 100 \le 6.5\%$$
*Rule:* Price $> 25.0\%$ above the 50 SMA is classified as **OVER_EXTENDED**. The system rejects deployment, warning the trader to wait for a base pullback or select the next ranked alternate.

---

## 8. Layer 7: Capital Sizing & Dual-Tier Execution

### Sizing Models by Account Tier

#### Tier 1: Retail Compounding Mode (Capital $< ₹50,000$)
- **Single-Leader 100% Rotation:** 100% of capital is deployed into Leader #1.
- **Cost Buffer:** ₹26 statutory buffer ($CMP \le Capital - ₹26$) covering STT, exchange turnover fees, SEBI turnover fees, and DP charges.

#### Tier 2: Institutional Portfolio Mode (Capital $\ge ₹50,000$)
Three binding constraints govern position quantity $Q$:
$$Q = \min\left( Q_{\text{risk}}, Q_{\text{exposure}}, Q_{\text{liquidity}} \right)$$
1. **1% Portfolio Risk Model:**
   $$Q_{\text{risk}} = \left\lfloor \frac{\text{Portfolio Equity} \times 0.01}{\text{Entry Price} - \text{Initial Stop Price}} \right\rfloor$$
2. **15% Maximum Position Exposure:**
   $$Q_{\text{exposure}} = \left\lfloor \frac{\text{Portfolio Equity} \times 0.15}{\text{CMP}} \right\rfloor$$
3. **1.5% Liquidity Participation Cap:**
   $$Q_{\text{liquidity}} = \left\lfloor \frac{\text{ADTV}_{20} \times 0.015}{\text{CMP}} \right\rfloor$$

---

## 9. Two-Tier Profit Booking & GTT State Machine

All trade orders utilize Zerodha Kite / Groww **Good-Till-Triggered (GTT)** orders with a 4-state lifecycle:

| State | Milestone | Stop Level | Execution Action | Rationale |
|---|---|---|---|---|
| **State 0: Risk On** | Entry fill | $2 \times \text{ATR}_{14}$ bounded $[-5\%, -7\%]$ | Place initial GTT sell trigger | Tail-risk protection |
| **State 1: Risk Free** | $+15\%$ Gain | Ratchet stop to $+1.5\%$ | Update GTT trigger to cost-covering floor | Completely covers STT, broker fees, and taxes |
| **State 2: Bank & Trail** | $+22\%$ Gain ($\ge 3R$) | Ratchet runner stop to $+10\%$ | Sell 40% position at $\ge 3R$; keep 60% runner | Locks in bank profit; finances risk-free ride |
| **State 3: Power Runner** | $> +25\%$ Unconstrained | Trailing stop: $\max(\text{SMA}_{50}, \text{EMA}_{20})$ | Remove profit ceiling; trail below 20 EMA | Captures uncapped multibagger trend runs |

*Definition of $R$ in State 2:*
$$R = \text{Entry Price} - \text{Initial Stop Price}$$
$$\text{Target}_{3R} = \text{Entry Price} + 3 \times R$$

---

## 10. Zero Manual Reporting Guarantee

- **100% Deterministic Code Execution:** All decision banners, risk warnings, affordability badges, and sizing quantities are computed directly by `quant_engine.py` and `momentum_quality.py`.
- **No Agent Discretion:** Neither the AI assistant nor human operators manually select or override signals. The terminal displays the live state strictly generated by the underlying mathematical models.
