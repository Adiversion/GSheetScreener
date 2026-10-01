# USER_V25 — Accumulation Quality / Anti-Trap Optimization Specification
## AI-Agent Research & Implementation Brief

**Document purpose:** Give an AI coding/research agent a complete, implementation-oriented understanding of the current USER_V25 NSE momentum system and the proposed next optimization: separating **genuine sustained demand** from stocks that merely look strong because of speculative/retail-driven price action.

**Target market:** NSE India cash equities  
**Operational screening universe:** approximately 2,300 currently relevant NSE cash stocks in the user's screener. The underlying ruleset describes the broader NSE listed cash-equity universe as 2,600+; do not confuse the two numbers.  
**Primary benchmark:** NIFTY 500  
**Evaluation philosophy:** do not optimize for a prettier backtest; determine whether the proposed signals actually discriminate future returns and downside risk before adding them to the production strategy.

---

# 1. Executive Problem Statement

The current screener can reduce roughly 2,300 NSE cash stocks to a much smaller group of technically strong candidates.

The difficult question is not:

> "Which stocks are strong?"

It is:

> "Among the technically strong stocks, which ones are strong because of persistent, orderly demand and which ones are strong because of a short-lived speculative move?"

A stock can simultaneously satisfy:

- price above major moving averages,
- positive momentum,
- close near its 52-week high,
- strong cross-sectional momentum rank,
- acceptable ATR,
- a recent volume surge,

and still be a poor candidate if the move is dominated by:

- one or two abnormal price jumps,
- heavy volume with weak price progress,
- repeated failed breakouts,
- heavy-volume selloffs,
- expanding volatility after an extended move,
- thin liquidity,
- gap-driven performance,
- unstable price discovery.

Therefore, the next optimization should **not** be another independent momentum strategy.

It should be a **quality discriminator inside USER_V25**.

Recommended conceptual name:

```text
AQS = Accumulation Quality Score
```

Alternative labels:

```text
Demand Quality Score
Price-Volume Quality Score
Accumulation / Distribution Quality
Trap-Risk Score
```

Do NOT call it:

```text
Institutional Buying Detector
Smart Money Detector
Retail Trap Detector
```

OHLCV data cannot identify the identity of market participants. It can only identify price-volume behavior that is **consistent with** sustained demand, supply absorption, distribution, speculative concentration, etc.

---

# 2. Existing USER_V25 Architecture

Current implementation-grade architecture:

```text
Raw NSE EOD Data
      |
      v
Layer 1 — Universe Safety
      |
      v
Layer 2 — NIFTY 500 Market Regime
      |
      v
Layer 3 — Stage-2 Structural Trend
      |
      v
Layer 4 — Cross-Sectional Momentum Score (CMS)
      |
      v
Layer 5 — Existing Anti-Trap Triad
      |       - Volume
      |       - VCR
      |       - FIP
      |
      v
Layer 6 — Extension / Volatility Ceilings
      |
      v
Layer 7 — Position Sizing + GTT Lifecycle
```

The proposed research layer is:

```text
Layer 5A / 5B — Accumulation Quality
      |
      +-- Effort vs Result
      +-- Up-volume vs Down-volume behavior
      +-- Pullback quality
      +-- Breakout quality
      +-- Failed-breakout / rejection behavior
      +-- FIP-style discreteness
      +-- Relative-strength persistence
      |
      v
Trap-Risk / Demand-Quality Classification
```

This should initially be a **research score**, not an automatic hard filter.

---

# 3. Current USER_V25 — Exact Core Logic

## 3.1 Layer 1 — Universe Safety

Current requirements:

```text
Single-day turnover >= ₹2 Cr

20-day ADTV >= ₹5 Cr

CMP >= ₹50
```

ADTV:

```text
ADTV20 = mean(Close[t] * Volume[t], 20)
```

Historical NSE price-band information must be used where available.

Current specification disqualifies fixed 2% and 5% bands and permits >=10% or dynamic/F&O-type bands.

Important implementation rule:

**Do not use today's circuit-band classification for historical dates.**

The circuit-band status must be point-in-time.

---

# 4. Layer 2 — NIFTY 500 Regime Governor

Use NIFTY 500 as the broad-market regime benchmark.

Base regime definitions:

### Bull

```text
Close > SMA50
AND
Close > SMA200
```

### Correction

```text
SMA200 < Close <= SMA50
```

### Defensive

```text
Close <= SMA200
```

Current USER_V25 defensive policy is:

```text
100% cash
```

This is a strategy rule, not a universal financial truth.

For research, regime sensitivity should be tested separately rather than assuming that 100% cash is automatically optimal.

---

# 5. Layer 3 — Stage-2 Structural Trend

Current structural template:

```text
CMP > SMA50
SMA50 > SMA150
SMA150 > SMA200
```

Normalized 200-day moving-average slope:

```text
SMA200_slope_pct =
    (SMA200[t] / SMA200[t-22] - 1) * 100

Requirement:
SMA200_slope_pct > 0
```

52-week positioning:

```text
CMP >= 0.75 * High52W
CMP >= 1.30 * Low52W
```

Momentum sanity:

```text
RSI14 >= 45
RSI14 <= 82

ROC1M >= -3%

ROC2M > 0
```

Interpretation:

The stock must already be in a persistent intermediate-term uptrend rather than merely experiencing an isolated daily spike.

---

# 6. Layer 4 — Cross-Sectional Momentum Score

CMS is calculated **only among candidates that have already passed Layers 1–3**.

```text
CMS =
    0.60 * PercentileRank(ROC3M)
  + 0.40 * PercentileRank(CMP / High52W)
```

Scaled:

```text
0 to 100
```

The percentile rank is empirical across the active Stage-2 candidate pool.

This is important because the system scans a very broad NSE universe.

The system should not ask:

```text
"Is this stock strong in isolation?"
```

It should ask:

```text
"How strong is this stock relative to all other currently eligible NSE candidates?"
```

---

# 7. Current Anti-Trap Triad

## 7.1 Volume Ratio

Current metric:

```text
VolumeRatio =
    Volume[t] / AverageVolume20[t]
```

Current interpretation:

```text
>= 1.50  -> institutional surge
1.00-1.50 -> volume confirmed
0.70-1.00 -> sub-average
< 0.70 -> reject
```

### Important correction for future implementation

Do not describe >=1.50 as proof of institutional buying.

It only means:

```text
current volume is unusually high relative to its 20-day average.
```

The missing information is:

```text
WHAT DID THE PRICE DO WITH THAT VOLUME?
```

That missing relationship is exactly why AQS is being proposed.

---

# 8. Existing VCR

```text
VCR = ATR5 / ATR20
```

Current interpretation:

```text
<= 0.90      -> tight coil
0.90-1.05    -> normal contraction
1.05-1.25    -> neutral
> 1.25       -> reject
```

VCR measures volatility compression/expansion.

It does NOT determine whether the compression is:

```text
healthy accumulation
```

or:

```text
lack of demand / dead trading
```

Therefore VCR should remain a component, but it should not be treated as a complete accumulation detector.

---

# 9. Existing FIP-Inspired Filter

Current 40-day smoothness:

```text
Smoothness =
    positive_days / active_days * 100
```

Current maximum one-day gain share:

```text
g_t = max(0, Close_t - Close_(t-1))

MaxGainShare =
    max(g_t) / sum(g_t) * 100
```

Current concept:

```text
Prefer gradual persistent appreciation
over a return path dominated by a few large positive days.
```

This is inspired by the academic Frog-in-the-Pan literature but is **not an exact replication of the published academic FIP measure**.

That distinction must remain explicit in code comments and documentation.

Published research:

Da, Gurun & Warachka, "Frog in the Pan: Continuous Information and Momentum", Review of Financial Studies, 2014.

https://academic.oup.com/rfs/article-abstract/27/7/2171/1578455

The paper reports stronger momentum continuation for stocks whose information/returns arrive more continuously rather than in discrete dramatic moves.

A later 2024 Finance Research Letters paper studies the market-state dependence of the effect:

https://www.sciencedirect.com/science/article/pii/S1544612324004045

---

# 10. Why AQS Is Needed

Current USER_V25 has three useful but incomplete anti-trap ideas:

```text
Volume -> how much activity occurred?

VCR -> how compressed/expanded is volatility?

FIP -> how continuous was the price path?
```

AQS should answer:

```text
What did the market actually accomplish with the volume?

How did the stock behave on advances versus declines?

Were pullbacks orderly?

Were breakouts accepted or rejected?

Was supply absorbed or did heavy volume fail to move price?

Was the trend persistent or dependent on isolated jumps?
```

This is the central research direction.

---

# 11. Research Inspiration — Mark Minervini / SEPA / VCP

Relevant concept family:

- Stage-2 trend structure
- relative strength
- volatility contraction
- proper bases
- breakout near a defined pivot
- volume confirmation
- avoiding extended/late entries

Reference:

Investors.com / IBD material:

https://www.investors.com/how-to-invest/investors-corner/amd-stock-buy-point/

IBD methodology overview:

https://www.investors.com/how-to-invest/investors-corner/four-pillars-of-ibd-methodology/

### What to borrow

Borrow the **mechanical concepts**:

```text
trend structure
relative strength
base quality
contraction
breakout confirmation
volume confirmation
```

Do not attempt to reproduce discretionary chart interpretation literally.

A machine needs definitions that can be calculated from historical data.

---

# 12. Research Inspiration — Wyckoff

Wyckoff is especially relevant to the "genuine strength vs trap" question because it explicitly studies price and volume together.

Core idea:

```text
Effort = volume
Result = price movement
```

Potential warning condition:

```text
very high effort
+
very weak result
```

This can be treated as a possible supply/distribution warning.

Another useful distinction:

```text
healthy advance:
    rising price
    + expanding/healthy demand
    + controlled pullbacks

potential distribution:
    high volume
    + poor upward progress
    + repeated rejection
    + heavy-volume declines
```

Useful research reference:

https://www.wyckoffanalytics.com/

### Important limitation

Wyckoff terminology is partly discretionary.

Terms such as:

```text
spring
UTAD
SOS
LPS
absorption
distribution
```

must not be directly implemented unless the agent first converts them into deterministic rules.

The objective is to extract measurable price-volume relationships, not to code subjective chart labels.

---

# 13. Research Inspiration — ICT / Smart Money Concepts

ICT/SMC includes concepts such as:

```text
Fair Value Gaps
Order Blocks
Liquidity Sweeps
Break of Structure
Change of Character
Optimal Trade Entry
```

These concepts are popular but are often described subjectively.

A current systematic-testing reference:

https://www.buildalpha.com/backtest-ict-and-smc/

A recent mechanical backtest example:

https://statoasis.com/overfit/research/ict-backtest-what-survives

Another discussion of the codification problem:

https://www.rawedge.io/blog/smc-ict-backtesting

### Decision for USER_V25

Do NOT add an "ICT layer" merely because the terminology sounds institutional.

Do NOT assume:

```text
FVG = institutional order
Order Block = smart money footprint
Liquidity sweep = guaranteed reversal
```

Instead, if desired, extract only objectively measurable phenomena:

```text
failed breakout
prior-high sweep + close back below level
range expansion followed by rejection
break of recent structure
gap/imbalance behavior
```

Then test them as independent event-study features.

This should be secondary research, not the primary architecture.

---

# 14. Proposed Accumulation Quality Score (AQS)

## 14.1 Purpose

AQS should rank the stocks that have already passed the current trend/momentum filters.

The intended question is:

```text
Among technically strong candidates, which price-volume paths
show the strongest evidence of persistent, orderly demand?
```

It should initially produce:

```text
AQS: 0-100
```

and:

```text
TrapRisk:
    LOW
    MEDIUM
    HIGH
```

The labels are descriptive classifications, not claims about trader identity.

---

# 15. AQS Component A — Effort vs Result

For each trading day:

```text
VolumeZ_t =
    Volume_t / Median(Volume_{t-N:t-1})
```

or preferably a robust percentile/z-score formulation.

Define price result:

```text
Result_t =
    signed_return_t
```

or:

```text
Result_t =
    (Close_t - Close_{t-1}) / Close_{t-1}
```

Potential warning:

```text
high VolumeZ
+
small/negative return
```

Potential positive evidence:

```text
high VolumeZ
+
strong positive return
+
strong close location
```

Do not use a single bar in isolation.

Aggregate over rolling windows such as:

```text
10D
20D
40D
```

Candidate derived measures:

```text
PositiveEffortEfficiency
NegativeEffortEfficiency
HighVolumeWeakResultRate
HighVolumeStrongResultRate
```

---

# 16. AQS Component B — Up-Volume vs Down-Volume

Separate volume according to daily return sign.

```text
UpVolume =
    sum(Volume_t where Return_t > 0)

DownVolume =
    sum(Volume_t where Return_t < 0)
```

Possible ratio:

```text
UVDR =
    UpVolume / (UpVolume + DownVolume)
```

Interpretation:

```text
higher UVDR
    -> more volume occurred on advancing sessions

lower UVDR
    -> more volume occurred on declining sessions
```

Do not treat this as proof of accumulation.

It is a price-volume asymmetry measure.

Also calculate the same measure over multiple windows:

```text
10D
20D
40D
```

This prevents one unusually large day from completely determining the result.

---

# 17. AQS Component C — Up-Day / Down-Day Efficiency

Volume alone is not enough.

Measure:

```text
positive return per unit of volume
```

and:

```text
negative return per unit of volume
```

Possible implementation:

```text
UpEfficiency =
    sum(max(Return_t,0)) / sum(VolumeNormalized_t on up days)

DownEfficiency =
    sum(abs(min(Return_t,0))) / sum(VolumeNormalized_t on down days)
```

Normalize volume first so that stock size does not dominate.

Possible signal:

```text
high positive efficiency
+
low negative efficiency
```

is preferable to:

```text
low positive efficiency
+
high negative efficiency
```

This is a research hypothesis and must be tested.

---

# 18. AQS Component D — Pullback Quality

This is one of the most important proposed features.

For each impulse leg followed by a pullback, measure:

### Advance

```text
price gain
volume behavior
range behavior
duration
```

### Pullback

```text
price retracement
volume behavior
range behavior
duration
```

Healthy pattern hypothesis:

```text
advance:
    strong/normal demand

pullback:
    smaller price damage
    lower volume
    lower range expansion
    no structural breakdown
```

Potentially unhealthy pattern:

```text
advance:
    strong price move

pullback:
    heavy volume
    large-range down days
    rapid retracement
```

Suggested ratios:

```text
PullbackDepthPct

PullbackVolumeRatio =
    AvgPullbackVolume / AvgPriorAdvanceVolume

PullbackATRRatio =
    AvgPullbackATR / AvgPriorAdvanceATR
```

Potential quality improvement:

```text
good:
PullbackDepth low
PullbackVolumeRatio low
PullbackATRRatio <= 1

bad:
PullbackDepth high
PullbackVolumeRatio high
PullbackATRRatio > 1
```

---

# 19. AQS Component E — Breakout Quality

Do not define a breakout simply as:

```text
Close > High52W
```

Instead identify a structural resistance/pivot level.

Potential deterministic breakout definition:

```text
Resistance =
    highest close/high over prior N sessions
```

Then:

```text
BreakoutClose > Resistance
```

Require:

```text
close location near high of day
volume expansion
not excessively extended
```

Possible Close Location Value:

```text
CLV =
    (2*Close - High - Low) / (High - Low)
```

or:

```text
CloseLocation =
    (Close - Low) / (High - Low)
```

A strong breakout candidate might have:

```text
breakout
+
high CLV
+
relative volume expansion
+
controlled ATR
```

---

# 20. AQS Component F — Breakout Failure / Rejection

A genuine trend candidate should not repeatedly show failed breakouts.

Define a deterministic failed breakout:

```text
Day t:
    Close_t > prior resistance

AND within K sessions:
    Close <= prior resistance
```

Optional stronger definition:

```text
breakout above resistance
+
large volume
+
close back below resistance
```

Track:

```text
FailedBreakoutCount_60D
FailedBreakoutCount_120D
```

Possible penalty:

```text
more recent failed breakouts
=> lower AQS
```

This feature may be more useful than adding complex ICT terminology because it captures an objectively measurable "liquidity sweep / failed acceptance" phenomenon.

---

# 21. AQS Component G — FIP / Discreteness

Keep the existing FIP-inspired logic.

But consider a scale-invariant implementation.

Instead of:

```text
g_t = max(0, Close_t - Close_{t-1})
```

also test:

```text
r_t = Close_t / Close_{t-1} - 1

g_t = max(0, r_t)

MaxGainShare =
    max(g_t) / sum(g_t)
```

This is preferable for cross-sectional comparison because a ₹10 gain means very different things for a ₹50 stock versus a ₹2,000 stock.

Research both formulations before replacing the current one.

---

# 22. AQS Component H — Relative Strength Persistence

Current CMS already captures:

```text
3M momentum
+
distance to 52W high
```

AQS should not duplicate CMS.

Instead test persistence:

```text
How often did the stock outperform the relevant benchmark
over rolling windows?
```

Example:

```text
RS_20
RS_40
RS_60
```

Possible persistence:

```text
RSPositiveRate =
    count(window_return_stock > window_return_benchmark)
    / number_of_windows
```

This distinguishes:

```text
one large outperformance event
```

from:

```text
repeated relative outperformance
```

---

# 23. Proposed AQS Feature Vector

Initial research vector:

```text
AQS_FEATURES = {

    volume_effort_result_10d,
    volume_effort_result_20d,
    volume_effort_result_40d,

    up_volume_ratio_10d,
    up_volume_ratio_20d,
    up_volume_ratio_40d,

    up_efficiency,
    down_efficiency,

    pullback_depth,
    pullback_volume_ratio,
    pullback_atr_ratio,

    breakout_quality,
    failed_breakout_count_60d,
    failed_breakout_count_120d,

    fip_smoothness_40d,
    max_gain_share_40d,

    relative_strength_persistence_20d,
    relative_strength_persistence_40d,
    relative_strength_persistence_60d
}
```

Do NOT immediately assign arbitrary weights.

First establish whether the features have predictive information.

---

# 24. Critical Research Method — Do Not Hard-Gate First

This is the most important instruction for the AI agent.

Do NOT do:

```text
invent AQS formula
+
backtest
+
observe higher CAGR
+
declare success
```

That is vulnerable to data mining.

Instead:

```text
Full NSE universe
        |
        v
Current Layer 1-3 eligibility
        |
        v
Record every candidate
        |
        v
Calculate AQS features
        |
        v
Observe future returns
```

For every candidate/date, record:

```text
symbol
date
sector if available
regime
Stage2 status
CMS
all AQS features
entry price
forward 5D return
forward 10D return
forward 20D return
forward 40D return
forward 60D return
maximum favorable excursion
maximum adverse excursion
```

Do not require the candidate to pass AQS first.

This creates an honest research dataset.

---

# 25. Cross-Sectional Quantile Test

For each AQS feature:

```text
Q1 = bottom 20%
Q2
Q3
Q4
Q5 = top 20%
```

Then calculate future outcomes.

Example:

```text
Feature: UpVolumeRatio20

Q1:
median Fwd20D
mean Fwd20D
hit rate
MDD / MAE

Q5:
median Fwd20D
mean Fwd20D
hit rate
MDD / MAE
```

The desired evidence is not merely:

```text
Q5 CAGR > Q1 CAGR
```

Look for:

```text
monotonic relationship
```

For example:

```text
Q1  -> poor
Q2  -> weak
Q3  -> neutral
Q4  -> positive
Q5  -> strongest
```

A monotonic gradient is much more interesting than:

```text
Q1 weak
Q2 strong
Q3 weak
Q4 strong
Q5 weak
```

---

# 26. Test Multiple Forward Horizons

At minimum:

```text
5 trading days
10 trading days
20 trading days
40 trading days
60 trading days
```

Reason:

A feature may identify:

```text
short-term breakout quality
```

without improving:

```text
60-day momentum
```

The agent must not assume the correct holding horizon.

---

# 27. Test Conditional on Existing USER_V25 Strength

The most important analysis is not:

```text
AQS across all NSE stocks
```

It is:

```text
AQS among stocks already passing:
    Layer 1
    Layer 2
    Layer 3
```

Then separately:

```text
AQS among top CMS candidates
```

This answers the actual production question:

> When the existing screener gives us 50 strong stocks, can AQS tell us which ones deserve greater attention?

---

# 28. Candidate Ranking Model

Do not immediately replace CMS.

Current concept:

```text
CMS = momentum / trend strength
```

Proposed:

```text
CMS = strength

AQS = quality of that strength
```

Therefore the eventual ranking could become:

```text
Primary:
    CMS

Secondary:
    AQS

Risk:
    TrapRisk
```

Possible display:

| Rank | Symbol | CMS | AQS | Trap Risk | Interpretation |
|---:|---|---:|---:|---|---|
| 1 | XYZ | 97 | 92 | Low | Strong + orderly |
| 2 | ABC | 99 | 61 | Medium | Strong but less clean |
| 3 | DEF | 94 | 88 | Low | Strong persistent behavior |
| 4 | GHI | 98 | 39 | High | Strong momentum, questionable path |

This is a **ranking aid**, not a claim that AQS identifies the true owner of the shares.

---

# 29. Potential AQS Scoring Architecture

Only after feature testing should weights be introduced.

A possible architecture:

```text
AQS =
    25% Demand / Effort-Result
  + 20% Up-vs-Down Volume Quality
  + 20% Pullback Quality
  + 15% Breakout Quality
  + 10% FIP Continuity
  + 10% Relative Strength Persistence
```

These weights are **NOT approved production weights**.

They are merely a starting experimental hypothesis.

The agent must not optimize them blindly.

Preferred method:

1. establish feature direction;
2. test monotonicity;
3. test stability by year;
4. test stability by regime;
5. test sector robustness;
6. test out-of-sample;
7. only then create a composite score.

---

# 30. Trap Risk Classification

Instead of a binary:

```text
TRAP / NOT TRAP
```

use:

```text
LOW
MEDIUM
HIGH
```

Possible high-risk triggers:

```text
repeated failed breakouts
+
high-volume weak-result sessions
+
heavy down-volume
+
large one-day gain share
+
rapid pullback after breakout
+
excessive extension
```

Possible low-risk characteristics:

```text
persistent relative strength
+
positive volume asymmetry
+
controlled pullbacks
+
strong breakout acceptance
+
low gain concentration
+
limited failed breakouts
```

Again:

These are **behavioral classifications from market data**, not proof of retail participation or institutional ownership.

---

# 31. Important Distinction: "Retail Trap" Cannot Be Observed Directly

The agent must never write:

```text
"This stock is being bought by retail."

"This is institutional accumulation."

"Smart money is buying."

"Institutions are trapped."

```

unless there is an independent dataset that actually identifies participant type.

OHLCV can support statements such as:

```text
"Price-volume behavior is consistent with sustained demand."

"Heavy volume produced relatively weak upward progress."

"The stock has a high frequency of failed breakouts."

"The return path is highly concentrated in a small number of sessions."

```

This language discipline is mandatory.

---

# 32. ICT/SMC Feature Extraction — Optional Research Track

If the agent wants to test ICT/SMC ideas, convert them into measurable events.

### Liquidity sweep hypothesis

Example:

```text
High_t > prior_N_day_high
AND
Close_t < prior_N_day_high
```

Then measure:

```text
forward 5D
forward 10D
forward 20D
```

for:

```text
bullish sweep
bearish rejection
```

### Fair Value Gap

Define mechanically:

```text
Bullish FVG:
High[t-2] < Low[t]
```

Then test:

```text
FVG created
+
trend state
+
volume state
+
future return
```

Do not assume the gap has predictive value.

### Break of Structure

Define a prior swing algorithmically.

Example:

```text
Close_t > previous confirmed swing high
```

Then test the event.

### Rule

If a concept cannot be defined identically by two independent implementations, it is not ready for the production engine.

---

# 33. Why ICT Should Not Become the Main USER_V25 Architecture

The current objective is:

```text
2,300 stocks
    ->
50 strong candidates
    ->
identify highest-quality candidates
```

ICT/SMC is often used as a trade-entry framework.

USER_V25 is primarily a:

```text
cross-sectional EOD equity selection system
```

These are different problems.

Therefore:

```text
AQS / price-volume quality
```

fits the architecture better than:

```text
full ICT/SMC entry framework
```

---

# 34. Data Requirements

For each NSE stock/date, ideally store:

```text
symbol
isin
date

open
high
low
close
volume
turnover

adjusted_close
adjusted_open/high/low if methodology requires

circuit_band
listing_date
delisting_date
suspension_status

sector
industry

NIFTY500 membership if applicable
NIFTY500 regime values
```

Derived:

```text
SMA20
SMA50
SMA150
SMA200

ATR5
ATR14
ATR20

RSI14

ROC1M
ROC2M
ROC3M
ROC6M
ROC12M

High52W
Low52W

VolumeRatio20
ADTV20

VCR

FIP smoothness
FIP max gain share

CMS
```

New AQS fields should be appended rather than replacing existing signals.

---

# 35. Corporate Actions

Adjusted historical prices must be used consistently for indicators affected by corporate actions:

```text
momentum
moving averages
RSI
ROC
ATR
52-week high/low
VCR
FIP
AQS
```

A stock split/dividend/corporate action must not create an artificial:

```text
crash
breakout
momentum reversal
```

Use point-in-time corporate-action-aware data.

---

# 36. Listings and Delistings

Do not introduce survivorship bias.

If a stock listed on:

```text
15-Aug-2025
```

it must not appear in:

```text
Jan-2025
Feb-2025
...
Jul-2025
```

before it existed.

Likewise, securities must remain in the historical dataset until the date on which they actually became unavailable.

---

# 37. Look-Ahead Bias Rules

Absolutely prohibited:

```text
using future High52W
using future volume
using future index constituents
using future circuit bands
using future corporate actions
using future listing status
using future sector classification
using future benchmark membership
```

At date `t`, every feature must be computable from information available at or before `t`.

If the signal is generated after the close:

```text
signal timestamp = close of t
```

Execution should occur:

```text
next tradable session
```

unless the production architecture explicitly models a different execution mechanism.

---

# 38. Warm-Up vs Evaluation Period

If evaluation is:

```text
2025-01-01 through 2026-10-01
```

the system may use earlier history for indicator warm-up.

But:

```text
warm-up data may calculate indicators
```

and must NOT:

```text
generate positions that contaminate the evaluation period.
```

Example:

```text
Warm-up:
2022-01-01 -> 2024-12-31

Evaluation:
2025-01-01 -> 2026-10-01
```

At 2025-01-01:

```text
portfolio must begin flat
```

unless a specific test explicitly says otherwise.

This was a known defect in an earlier benchmark implementation and must not recur.

---

# 39. Recommended Research Dataset

Create one row per:

```text
candidate × signal date
```

Schema example:

```text
date
symbol
regime

stage2_pass
cms

volume_ratio
vcr
fip_smoothness
fip_max_gain_share

aqs_effort_result
aqs_up_volume
aqs_down_efficiency
aqs_pullback
aqs_breakout
aqs_failed_breakout
aqs_rs_persistence

aqs_raw
trap_risk

entry_price

fwd_5d
fwd_10d
fwd_20d
fwd_40d
fwd_60d

mae_20d
mae_40d
mfe_20d
mfe_40d
```

---

# 40. Statistical Evaluation

For every feature and composite:

### Central tendency

```text
mean
median
```

### Hit rate

```text
P(FwdReturn > 0)
```

### Tail

```text
P(FwdReturn < -10%)
P(FwdReturn < -20%)
```

### Risk

```text
median MAE
95th percentile MAE
```

### Monotonicity

Calculate the relationship between:

```text
feature quantile
```

and:

```text
future return
```

Use rank correlation where appropriate.

### Stability

Repeat by:

```text
calendar year
market regime
sector
market-cap bucket
liquidity bucket
```

---

# 41. Out-of-Sample Requirement

A feature should not be accepted simply because it works on:

```text
2025-2026
```

Use a walk-forward framework.

Example:

```text
Train:
2020-2023

Validation:
2024

Test:
2025

Then roll forward.
```

Or:

```text
Train:
2020-2024

Test:
2025

Final untouched test:
2026
```

Exact periods depend on available clean data.

The final test period should remain untouched during feature/threshold development.

---

# 42. Multiple-Testing Warning

If the agent tests:

```text
100 features
x
10 windows
x
10 thresholds
```

then some apparently strong result will occur by chance.

Therefore record:

```text
number of hypotheses tested
```

and maintain a research log.

Do not silently discard failed experiments.

Preferred process:

```text
hypothesis
    ->
predefined feature
    ->
predefined test
    ->
result
    ->
decision
```

---

# 43. No CAGR-First Optimization

Do not optimize AQS for:

```text
maximum CAGR
```

as the primary objective.

First ask:

```text
Does the feature discriminate future outcomes?
```

Then:

```text
Does it remain useful out-of-sample?
```

Then:

```text
Does it improve the actual portfolio?
```

Only after that should portfolio-level metrics be considered.

---

# 44. Final Portfolio-Level Test

Compare at least:

```text
USER_V25
```

against:

```text
USER_V25 + AQS ranking
```

and:

```text
USER_V25 + AQS hard filter
```

But do not assume the hard filter is better.

Potential configurations:

```text
AQS used only for ranking
AQS top 75%
AQS top 50%
AQS top 25%
AQS as position-size modifier
AQS as veto only for HIGH trap risk
```

The simplest robust result should be preferred over a highly parameterized rule.

---

# 45. Position Sizing Integration — Later Phase

Do not initially let AQS alter position size.

First prove predictive value.

If proven, possible later use:

```text
Base risk = 1.0%

AQS high:
    1.0x risk

AQS medium:
    0.75x

AQS low:
    0.50x
```

These multipliers are examples only.

Do not implement them without evidence.

---

# 46. Existing Position Sizing

Current Tier-2 concept:

```text
Q = min(Qrisk, Qexposure, Qliquidity)
```

Where:

```text
Qrisk =
floor(
    Equity * 0.01 /
    (Entry - InitialStop)
)
```

Exposure:

```text
Qexposure =
floor(
    Equity * 0.15 / CMP
)
```

Liquidity:

```text
Qliquidity =
floor(
    ADTV20 * 0.015 / CMP
)
```

Do not change this merely to accommodate AQS.

---

# 47. Existing GTT Lifecycle

Current lifecycle:

### State 0

Initial stop:

```text
2 * ATR14
```

bounded to approximately:

```text
-5% to -7%
```

### State 1

At:

```text
+15%
```

raise stop by approximately:

```text +1.5%
```

with cost-covering floor.

### State 2

At:

```text +22%
AND
>= 3R
```

sell:

```text 40%
```

retain:

```text 60%
```

and use runner protection.

### State 3

Above:

```text +25%
```

trail using:

```text max(SMA50, EMA20)
```

Do not mix entry-quality research with exit optimization in the first AQS experiment.

---

# 48. Recommended Candidate Output

The screener should eventually expose:

```text
Symbol
CMP
CMS
AQS
Trap Risk
Stage2
VCR
FIP
Volume Ratio
RS Persistence
Breakout Quality
Failed Breakouts
```

Example:

```text
---------------------------------------------------------------
SYMBOL   CMS   AQS   TRAP   VCR   FIP   VOL   BREAKOUT
---------------------------------------------------------------
ABC      98    93    LOW    0.82  71    1.34  HIGH
XYZ      99    58    MED    0.91  62    2.10  MED
PQR      95    91    LOW    0.87  68    1.21  HIGH
LMN      97    42    HIGH   1.11  49    2.80  LOW
---------------------------------------------------------------
```

Interpretation:

```text
CMS answers:
    How strong is the stock?

AQS answers:
    How clean/consistent is the strength?

Trap Risk answers:
    How many warning characteristics are present?
```

---

# 49. Agent Implementation Order

Follow this order exactly.

## Phase 1 — Audit current implementation

Confirm:

```text
Stage2
CMS
Volume
VCR
FIP
Extension
Regime
```

against the implementation-grade specification.

## Phase 2 — Build candidate event table

Do not change production behavior.

Store every Layer 1–3 candidate.

## Phase 3 — Calculate AQS features

Do not hard-filter.

## Phase 4 — Forward-return analysis

Run:

```text
5D
10D
20D
40D
60D
```

## Phase 5 — Quantile analysis

Use:

```text
Q1-Q5
```

for each feature.

## Phase 6 — Stability analysis

Test:

```text
year
regime
sector
liquidity
market-cap
```

## Phase 7 — Feature selection

Retain only features showing:

```text
economic rationale
+
monotonicity
+
out-of-sample stability
+
reasonable effect size
```

## Phase 8 — Composite AQS

Only now construct:

```text
AQS 0-100
```

## Phase 9 — Portfolio integration

Compare:

```text
ranking
vs
filter
vs
position-size modifier
```

## Phase 10 — Freeze specification

Only after independent validation.

---

# 50. What the AI Agent Must NOT Do

Do not:

1. Add 20 indicators simply because they are available.
2. Add ICT terminology without deterministic definitions.
3. Call high volume "institutional buying" automatically.
4. Optimize thresholds on the final test period.
5. Use future constituent membership.
6. Use today's circuit-band status for historical dates.
7. Allow warm-up positions to contaminate evaluation.
8. Use unadjusted prices across corporate actions.
9. Optimize solely for CAGR.
10. Remove failed experiments from the research log.
11. Claim statistical significance without an appropriate test.
12. Treat practitioner methodologies as academic proof.
13. Treat academic FIP as identical to the current USER_V25 FIP implementation.
14. Assume AQS improves performance before testing.
15. Replace the current architecture before measuring incremental information.

---

# 51. Evidence Hierarchy

When deciding what to add:

### Tier 1 — Peer-reviewed empirical evidence

Examples:

```text
Frog-in-the-Pan literature
```

### Tier 2 — Transparent practitioner methodology

Examples:

```text
Minervini / SEPA
O'Neil / CANSLIM
Wyckoff
```

Useful for hypothesis generation.

### Tier 3 — Mechanical third-party backtests

Useful as independent sanity checks.

### Tier 4 — Trading content / social media

Useful only for generating hypotheses.

### Tier 5 — Unverified claims

Do not use as evidence.

---

# 52. Web Reference Library

## Academic / Research

### Frog in the Pan — Oxford / Review of Financial Studies

https://academic.oup.com/rfs/article-abstract/27/7/2171/1578455

Primary academic reference for continuous vs discrete information and momentum.

### Frog in the Pan — CFA Digest

https://rpc.cfainstitute.org/research/cfa-digest/2015/03/frog-in-the-pan-continuous-information-and-momentum

Useful secondary summary.

### Frog in the Pan and Market State — Finance Research Letters

https://www.sciencedirect.com/science/article/pii/S1544612324004045

Useful for understanding interaction with market state.

---

## Minervini / IBD / Breakout Research

### Investors.com / IBD

https://www.investors.com/

Use for practitioner material around:

```text
relative strength
base structures
breakouts
volume confirmation
market direction
```

### Example IBD breakout material

https://www.investors.com/how-to-invest/investors-corner/amd-stock-buy-point/

Use as a reference for the type of breakout/relative-strength reasoning being discussed, not as statistical proof.

---

## Wyckoff

### Wyckoff Analytics

https://www.wyckoffanalytics.com/

Use for:

```text
effort vs result
accumulation
distribution
springs
sign of strength
sign of weakness
volume-price relationships
```

Translate discretionary concepts into deterministic formulas before coding.

---

## ICT / Smart Money Concepts

### Build Alpha — Mechanical ICT/SMC Testing

https://www.buildalpha.com/backtest-ict-and-smc/

Useful for seeing how subjective concepts can be converted into explicit rules.

### StatOasis — ICT/SMC Backtest

https://statoasis.com/overfit/research/ict-backtest-what-survives

Useful as a cautionary example of testing codified ICT/SMC rules rather than assuming the narrative.

### Raw Edge — SMC/ICT Backtesting

https://www.rawedge.io/blog/smc-ict-backtesting

Useful discussion of why subjective definitions create testing problems.

---

# 53. Recommended Research Question

The agent should treat this as the central research question:

> Given an NSE cash-equity universe of approximately 2,300 stocks, after applying liquidity safety, NIFTY 500 regime context, Stage-2 structural trend and cross-sectional momentum ranking, can objectively measurable price-volume features distinguish persistent/orderly momentum from momentum dominated by speculative jumps, failed breakouts, heavy-volume rejection, and poor pullback behavior?

Secondary questions:

```text
1. Which individual AQS features contain independent information beyond CMS?

2. Are AQS features predictive at 5/10/20/40/60-day horizons?

3. Are the relationships monotonic?

4. Do they survive across 2025 and 2026 separately?

5. Do they survive bull/correction/defensive regimes?

6. Do they survive across sectors?

7. Does AQS improve ranking more than hard filtering?

8. Does AQS reduce maximum adverse excursion?

9. Does AQS reduce false breakout frequency?

10. Does AQS improve risk-adjusted portfolio outcomes without excessive turnover?
```

---

# 54. Final Design Principle

The objective is NOT:

```text
Find the magical indicator that identifies "smart money".
```

The objective is:

```text
Start with strong momentum.

Then measure whether the path to that momentum
looks orderly, persistent and accepted by the market.

Penalize:
    concentration
    rejection
    failed breakouts
    heavy-volume weak results
    poor pullbacks
    unstable volatility

Reward:
    persistent relative strength
    efficient advances
    controlled pullbacks
    healthy breakout acceptance
    gradual return accumulation
    favorable price-volume asymmetry
```

The final conceptual pipeline should therefore become:

```text
~2,300 NSE STOCKS
        |
        v
LIQUIDITY / DATA SAFETY
        |
        v
MARKET REGIME
        |
        v
STAGE-2
        |
        v
CMS
        |
        v
~50 PRIME CANDIDATES
        |
        v
ACCUMULATION QUALITY / AQS
        |
        +-----------------------------+
        |                             |
        v                             v
HIGH-QUALITY STRENGTH          QUESTIONABLE STRENGTH
        |                             |
        v                             v
LOWER TRAP-RISK                HIGHER TRAP-RISK
        |
        v
RANK / SIZE / EXECUTE
```

The critical distinction is:

```text
CMS = strength
AQS = quality of strength
```

That is the core optimization to investigate before adding another large strategy family.
