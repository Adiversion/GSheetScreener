# Institutional Quant Engine V2 Upgrade Plan
## Overcoming Skewness Truncation, Normalizing Momentum Factors, and Mastering NSE Market Realities

> **Document Status**: Ready for Review & Implementation  
> **Target Environment**: Local / Home Development & GitHub Actions Serverless Pipeline  
> **Repository**: `Adiversion/GSheetScreener` (`D:\GSheetScreener`)  
> **Reference Audit**: [`ai research.txt`](file:///D:/GSheetScreener/ai%20research.txt)

---

## 1. Executive Summary & Mathematical Premise

The independent quantitative critique identified the single greatest bottleneck in the current architecture: **Milestone 3 (Forced 100% Exit at +50%) truncates positive skewness.**

Classical Stage-2 momentum models (Mark Minervini's SEPA®, William O'Neil's CANSLIM, Richard Donchian, and Richard Dennis's Turtle Trading) derive their entire mathematical edge from an asymmetric return distribution:

$$\mathbb{E}[\text{Return}] = (\text{Win Rate} \times \text{Avg Win}) - (\text{Loss Rate} \times \text{Avg Loss}) - \text{Friction}$$

In trend-following:
* Win rate is typically **40% to 50%**.
* Average loss is strictly capped at **-7%** via hard stops.
* The mathematical profitability is driven entirely by the **"fat right tail"**—the 5% to 10% of trades that surge **+100%, +250%, or +500%+** (e.g., Trent, Dixon, Cyient DLM, Suzlon).
* **By forcing an exit at +50%, the system cuts winners prematurely**, turning an asymmetric trend-following engine into a high-churn swing screener with excessive tax and STCG drag.

This upgrade plan outlines the mathematical formulas, code changes, and UI updates required to transform the engine into an institutional-grade, multibagger-capturing screener.

---

## 2. Five Core Structural Upgrades

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                 V2 UPGRADE MATRIX                                      │
├─────────────────────┬──────────────────────────────┬───────────────────────────────────┤
│ Component           │ V1 Current State             │ V2 Target State                   │
├─────────────────────┼──────────────────────────────┼───────────────────────────────────┤
│ 1. M3 Profit Exit   │ 100% Forced Exit at +50%     │ Dynamic 50 SMA / 21 EMA Trail     │
│ 2. CMS Score        │ Raw % added to proximity     │ Cross-Sectional Percentile (0–100)│
│ 3. RSI Boundary     │ 45 to 75 (Strict Cap)        │ 45 to 82 (Power Trend Allowed)    │
│ 4. ATR Ceiling      │ ≤ 5.0% Daily ATR             │ ≤ 6.5% Daily ATR (Midcap Fit)     │
│ 5. Market Regime    │ Nifty 50 (Largecap bias)     │ Nifty 500 / Midcap Breadth        │
└─────────────────────┴──────────────────────────────┴───────────────────────────────────┘
```

---

### Upgrade 1: Unlocking Positive Skewness ("The Multibagger Ride")

#### The Problem
Exiting 100% of the position at +50% deprives the account of the compounding explosive phase of institutional markup.

#### The Solution: 4-Stage GTT Lifecycle
Instead of closing the position at +50%, Milestone 3 transitions the trade into a **Trend-Following Ride**:

```
 Entry (₹1,000)
    │
    ├─── [-7%] Emergency Stop Loss ──────────► Hard floor. Max loss capped at ₹70.
    │
    ├─── [+15%] Milestone 1 (M1) ───────────► Stop Loss automatically moves to +2.5% Breakeven.
    │                                          (Trade is now 100% RISK-FREE).
    │
    ├─── [+30%] Milestone 2 (M2) ───────────► Stop Loss ratchets to +15%.
    │                                          (Guarantees banked profit even on sharp reversals).
    │
    └─── [+50%] Milestone 3 (M3) ───────────► "MULTIBAGGER RIDE" ACTIVATES:
                                               1. Stop loss moves to +35% minimum profit lock.
                                               2. Position is held as long as daily Close > 50 SMA
                                                  (or 21-day EMA for high-beta runners).
                                               3. Allows the trade to run to +100%, +250%, +500%+.
```

#### Code Implementation (`quant_engine.py`)
```python
# GTT Levels V2
init_stop = max(round(cmp * (1 - STOP_PCT), 2), round(cmp - 2 * atr_val, 2))
m1 = round(cmp * (1 + M1_PCT), 2)
m1_stop = round(cmp * (1 + M1_STOP_PCT), 2)
m2 = round(cmp * (1 + M2_PCT), 2)
m2_stop = round(cmp * (1 + M2_STOP_PCT), 2)
m3 = round(cmp * (1 + M3_PCT), 2)
m3_stop = round(cmp * (1 + 0.35), 2) # Lock in +35% profit floor at +50% milestone
```

---

### Upgrade 2: Cross-Sectional Percentile Normalized CMS Score

#### The Problem
1. **Formula Redundancy**: $(1 - \frac{52W - CMP}{52W}) \times 100 \equiv \frac{CMP}{52W} \times 100$.
2. **Dimensional Mismatch**: $ROC_{3M}$ can range from $-20\%$ to $+150\%+$, whereas Proximity is strictly $0$ to $100$. Simply adding $0.60 \times ROC_{3M} + 0.40 \times Proximity$ allows extreme $ROC_{3M}$ outliers to completely hijack the score.

#### The Solution: Percentile Normalization
Standardize both dimensions across the candidate universe before blending:

$$\text{Rank}(ROC_{3M}) = \frac{\text{OrdinalRank}(ROC_{3M})}{N} \times 100$$
$$\text{Rank}(Proximity) = \frac{\text{OrdinalRank}(CMP / 52W_{High})}{N} \times 100$$
$$\text{CMS}_{V2} = (0.60 \times \text{Rank}(ROC_{3M})) + (0.40 \times \text{Rank}(Proximity))$$

#### Code Implementation (`quant_engine.py`)
```python
# Compute percentiles across all screened stocks
df_candidates["ROC_3M_PCTILE"] = df_candidates["ROC_3M"].rank(pct=True) * 100
df_candidates["PROX_PCTILE"] = (df_candidates["CMP"] / df_candidates["HIGH_52W"]).rank(pct=True) * 100
df_candidates["CMS_SCORE"] = round(0.60 * df_candidates["ROC_3M_PCTILE"] + 0.40 * df_candidates["PROX_PCTILE"], 1)
```

---

### Upgrade 3: Power Breakout RSI Calibration ($45 \le \text{RSI} \le 82$)

#### The Problem
Capping RSI at 75 causes the screener to filter out top institutional breakout stocks during their initial high-volume surge. When a stock breaks out from a 6-month Stage-1 base on 3× volume, its daily RSI is almost always between 76 and 82.

#### The Solution
* Expand the upper RSI boundary to **82**:
  ```python
  if not (45.0 <= rsi_val <= 82.0):
      continue
  ```
* Any stock with $\text{RSI} > 82$ is tagged `EXTREME_MOMENTUM_OVERBOUGHT` to alert the trader of potential exhaustion.

---

### Upgrade 4: Real-World NSE Midcap Volatility Ceiling ($\text{ATR} \le 6.5\%$)

#### The Problem
An arbitrary 5.0% ATR ceiling drops explosive midcap and smallcap leaders on the NSE, which routinely trade with 5.2% to 6.2% daily ATR during their strongest breakout runs.

#### The Solution
* Set `PRIME_LOW_RISK` ceiling to **$\le 6.5\%$ ATR**:
  ```python
  atr_pct = (atr_val / cmp) * 100
  is_prime = (dist_50 <= 25.0) and (atr_pct <= 6.5)
  setup_quality = "PRIME_LOW_RISK" if is_prime else ("OVER_EXTENDED" if dist_50 > 25.0 else "HIGH_VOLATILITY")
  ```

---

### Upgrade 5: Macro Regime Realignment (Nifty 500)

#### The Problem
The Nifty 50 reflects only 50 large-cap giants. Midcaps and smallcaps frequently run in multi-month independent bull markets while Reliance or HDFC Bank drags the Nifty 50 below its 200 SMA.

#### The Solution
* Replace `^NSEI` with the **Nifty 500 index** (`^CRSLDX` on Yahoo Finance) for regime tracking.
* Benchmark:
  * `BULL_MARKET`: Nifty 500 > 50 SMA > 200 SMA
  * `CORRECTION_WATCH`: Nifty 500 > 200 SMA, below 50 SMA
  * `DEFENSIVE_CASH`: Nifty 500 < 200 SMA

---

## 3. Step-by-Step Execution Plan (For Home Implementation)

### Step 1: Update `quant_engine.py`
* Location: `nse-momentum-engine/src/quant_engine.py`
* Actions:
  1. Update `cands_df` liquidity filter to use `VOLUME >= 100,000` OR `TURNOVER >= 20,000,000`.
  2. Implement cross-sectional percentile CMS scoring.
  3. Expand RSI upper bound to 82 and ATR ceiling to 6.5%.
  4. Update `get_nifty_regime()` to query `^CRSLDX` (Nifty 500).
  5. Add `M3_STOP` at +35% minimum floor with trailing 50 SMA annotation.

### Step 2: Update App UI & GTT Guide
* Location: `nse-momentum-engine/app/index.html` & `app/js/app.js`
* Actions:
  1. In the GTT Levels table, change M3 label from `Take Profit (+50%)` to `M3: Trail 50 SMA (+50%+)`.
  2. Add note: `At +50%, ratchet stop to +35% floor and let trend ride along 50-day SMA.`
  3. Update the Strategy Glossary modal (`#glossaryModal`) with the Multibagger Ride explanation.

### Step 3: Run Engine & Verify Signals Locally
```bash
# In terminal at D:\GSheetScreener
python nse-momentum-engine/src/quant_engine.py
```
* Verify that `data/signal.json` outputs 40+ Stage-2 leaders.
* Check that CMS scores are clean percentiles (0 to 100).
* Verify that #1 Winner and alternates match the updated criteria.

### Step 4: Git Commit & Deploy
```bash
git add -A
git commit -m "feat(quant): implement V2 institutional upgrade - percentile CMS, multibagger trailing stop, and Nifty 500 regime"
git push origin main
```
* GitHub Pages will automatically build and deploy the updated app in ~45 seconds.

---

## 4. Summary of Benefits

1. **Captures Fat Right-Tail Multibaggers**: Eliminates the +50% premature exit rule, allowing genuine leaders to run to +150%–300%+.
2. **Mathematically Pure Factor Ranking**: Percentile CMS scoring prevents single outliers from distorting rankings.
3. **No False Negatives on Power Breakouts**: RSI up to 82 and ATR up to 6.5% capture the real high-beta winners of the NSE.
4. **True Market Breadth**: Nifty 500 regime ensures market signals reflect the entire 2,600-stock universe, not just 50 mega-caps.
