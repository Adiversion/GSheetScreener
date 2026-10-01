#!/usr/bin/env python3
"""
NSE Quant Strategy Research Tournament
=======================================

Compares:
  A) USER_V25  - locked implementation of the supplied v2.5 specification
  B) INDEPENDENT_MOMENTUM - independently designed momentum benchmark
  C) NSE_MOMENTUM_PROXY - 6M/12M volatility-adjusted momentum proxy inspired by
                           the published Nifty500 Momentum methodology

Also runs ablations of the user's strategy:
  Stage2
  Stage2 + CMS
  Stage2 + CMS + Volume
  Stage2 + CMS + VCR
  Stage2 + CMS + FIP
  Full v2.5

IMPORTANT:
- For serious research, use point-in-time NSE data. Do NOT use today's universe
  for historical periods if you want to claim a survivorship-bias-free result.
- The script intentionally does not silently download a current NSE universe and
  call it historical. Local NSE historical data is the preferred input.
- Signals are generated using information available at EOD t and executed at
  the next trading day's open by default.
- Transaction costs/slippage are explicit parameters.
- The user's rules are kept as close as possible to the supplied v2.5 file.
- Some rules (broker GTT behavior, exact NSE auction mechanics, corporate-action
  handling) cannot be inferred from OHLCV alone and therefore have explicit
  conservative assumptions.

Expected normalized stock CSV columns:
    date,symbol,open,high,low,close,volume[,turnover,price_band,series]
date can be YYYY-MM-DD.

Expected benchmark CSV:
    date,close
for NIFTY500.

Optional:
    price_band: numeric percentage or categorical value
    series: e.g. EQ

Usage:
    python nse_quant_tournament.py --data ./data --benchmark ./data/NIFTY500.csv

For a quick prototype using Yahoo Finance:
    python nse_quant_tournament.py --yfinance
This mode is NOT suitable for a final NSE research claim because the universe
is not point-in-time and Yahoo's historical coverage/adjustments differ from
official NSE data.
"""

from __future__ import annotations

import argparse
import math
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------

@dataclass
class Config:
    initial_capital: float = 1_000_000.0

    # User v2.5
    daily_turnover_min: float = 2_00_00_000.0       # ₹2 Cr
    adtv20_min: float = 5_00_00_000.0               # ₹5 Cr
    price_min: float = 50.0
    rsi_min: float = 45.0
    rsi_max: float = 82.0
    roc1m_min: float = -0.03
    roc2m_min: float = 0.0
    slope200_min: float = 0.0
    vcr_prime: float = 0.90
    vcr_reject: float = 1.25
    volume_pass: float = 1.00
    volume_strong: float = 1.50
    volume_reject: float = 0.70
    fip_smooth_min: float = 50.0
    fip_jump_share_max: float = 40.0
    extension_max: float = 25.0
    atr_pct_max: float = 6.5
    risk_fraction: float = 0.01
    exposure_fraction: float = 0.15
    liquidity_fraction: float = 0.015

    # User regime
    regime_bull_exposure: float = 1.00
    regime_correction_exposure: float = 0.50
    regime_defensive_exposure: float = 0.00

    # Independent strategy
    independent_top_n: int = 10
    independent_lookback_short: int = 126   # ~6 months
    independent_lookback_long: int = 252    # ~12 months
    independent_vol_window: int = 63
    independent_min_price: float = 50.0
    independent_adtv_min: float = 5_00_00_000.0

    # Execution assumptions
    slippage_bps: float = 10.0
    brokerage_bps: float = 0.0
    transaction_cost_bps: float = 10.0
    stamp_and_other_bps: float = 5.0

    # Research
    warmup_days: int = 260
    rebalance_days: int = 5
    max_positions: int = 10


CFG = Config()

# ---------------------------------------------------------------------------
# DATA
# ---------------------------------------------------------------------------

REQUIRED = {"date", "symbol", "open", "high", "low", "close", "volume"}

def read_stock_data(data_dir: Path) -> pd.DataFrame:
    files = sorted(data_dir.glob("*.csv"))
    frames = []
    for f in files:
        if f.name.upper().startswith("NIFTY500"):
            continue
        try:
            df = pd.read_csv(f)
        except Exception:
            continue
        cols = {c.lower().strip(): c for c in df.columns}
        if not REQUIRED.issubset(cols):
            continue
        df = df.rename(columns={v: k for k, v in cols.items() if k in cols})
        # normalize names after rename
        df = df.rename(columns={
            "date": "date", "symbol": "symbol", "open": "open",
            "high": "high", "low": "low", "close": "close",
            "volume": "volume"
        })
        if "turnover" in df.columns:
            df["turnover"] = pd.to_numeric(df["turnover"], errors="coerce")
        if "price_band" in df.columns:
            df["price_band"] = df["price_band"]
        if "series" in df.columns:
            df["series"] = df["series"]
        frames.append(df)

    if not frames:
        raise FileNotFoundError(
            f"No normalized stock CSVs found in {data_dir}. "
            "See DATA_FORMAT.md."
        )

    out = pd.concat(frames, ignore_index=True)
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    for c in ["open", "high", "low", "close", "volume"]:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    if "turnover" not in out.columns:
        out["turnover"] = out["close"] * out["volume"]
    else:
        out["turnover"] = out["turnover"].fillna(out["close"] * out["volume"])

    out = out.dropna(subset=["date", "symbol", "open", "high", "low", "close", "volume"])
    out["symbol"] = out["symbol"].astype(str).str.upper().str.strip()
    out = out.sort_values(["symbol", "date"]).drop_duplicates(["symbol", "date"])
    return out


def read_benchmark(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    cols = {c.lower().strip(): c for c in df.columns}
    date_col = cols.get("date")
    close_col = cols.get("close")
    if not date_col or not close_col:
        raise ValueError("Benchmark CSV must contain date and close columns.")
    out = df[[date_col, close_col]].copy()
    out.columns = ["date", "close"]
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out["close"] = pd.to_numeric(out["close"], errors="coerce")
    return out.dropna().sort_values("date").drop_duplicates("date")


# ---------------------------------------------------------------------------
# INDICATORS
# ---------------------------------------------------------------------------

def rsi(series: pd.Series, n: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/n, adjust=False, min_periods=n).mean()
    avg_loss = loss.ewm(alpha=1/n, adjust=False, min_periods=n).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def atr(df: pd.DataFrame, n: int) -> pd.Series:
    prev = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev).abs(),
        (df["low"] - prev).abs()
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1/n, adjust=False, min_periods=n).mean()


def add_indicators(g: pd.DataFrame) -> pd.DataFrame:
    g = g.sort_values("date").copy()
    c = g["close"]

    g["sma50"] = c.rolling(50).mean()
    g["sma150"] = c.rolling(150).mean()
    g["sma200"] = c.rolling(200).mean()

    g["slope200pct"] = (g["sma200"] / g["sma200"].shift(22) - 1.0) * 100.0

    g["high52"] = c.rolling(252).max()
    g["low52"] = c.rolling(252).min()

    g["rsi14"] = rsi(c, 14)

    g["roc1m"] = c / c.shift(21) - 1.0
    g["roc2m"] = c / c.shift(42) - 1.0
    g["roc3m"] = c / c.shift(63) - 1.0

    g["atr5"] = atr(g, 5)
    g["atr14"] = atr(g, 14)
    g["atr20"] = atr(g, 20)
    g["vcr"] = g["atr5"] / g["atr20"]

    g["vol20"] = g["volume"].rolling(20).mean()
    g["vol_ratio"] = g["volume"] / g["vol20"]

    g["adtv20"] = g["turnover"].rolling(20).mean()

    g["distance_sma50_pct"] = (c / g["sma50"] - 1.0) * 100.0
    g["atr_pct"] = g["atr14"] / c * 100.0

    # FIP-inspired custom metric, deliberately using percentage returns.
    daily_ret = c.pct_change()
    positive = daily_ret.clip(lower=0)
    active = daily_ret.notna()
    pos_days = positive.gt(0).rolling(40).sum()
    active_days = active.rolling(40).sum()
    g["fip_smoothness"] = pos_days / active_days * 100.0

    positive_gain_sum = positive.rolling(40).sum()
    max_positive_gain = positive.rolling(40).max()
    g["fip_max_gain_share"] = (
        max_positive_gain / positive_gain_sum.replace(0, np.nan) * 100.0
    )

    # Independent momentum score components
    g["mom6m"] = c / c.shift(126) - 1.0
    g["mom12m"] = c / c.shift(252) - 1.0
    g["vol63"] = daily_ret.rolling(63).std() * np.sqrt(252)
    g["mom6_vol_adj"] = g["mom6m"] / g["vol63"].replace(0, np.nan)
    g["mom12_vol_adj"] = g["mom12m"] / g["vol63"].replace(0, np.nan)

    return g


def prepare_indicators(stocks: pd.DataFrame) -> pd.DataFrame:
    return stocks.groupby("symbol", group_keys=False).apply(add_indicators).reset_index(drop=True)


# ---------------------------------------------------------------------------
# NSE / UNIVERSE SAFETY
# ---------------------------------------------------------------------------

def band_allowed(x) -> bool:
    """Strategy policy, not an NSE rule: reject explicit 2% and 5% fixed bands."""
    if pd.isna(x):
        return True
    s = str(x).strip().upper().replace("%", "")
    try:
        v = float(s)
        return not math.isclose(v, 2.0) and not math.isclose(v, 5.0)
    except Exception:
        # Dynamic/no-fixed-band labels are allowed unless explicitly 2/5.
        return "2%" not in s and "5%" not in s


def universe_filter(day: pd.DataFrame) -> pd.DataFrame:
    x = day.copy()
    x = x[x["close"] >= CFG.price_min]
    x = x[x["turnover"] >= CFG.daily_turnover_min]
    x = x[x["adtv20"] >= CFG.adtv20_min]
    if "price_band" in x.columns:
        x = x[x["price_band"].map(band_allowed)]
    if "series" in x.columns:
        # Keep EQ by default when series is supplied.
        x = x[x["series"].fillna("EQ").astype(str).str.upper().isin(["EQ", "BE", "BZ"])]
    return x


# ---------------------------------------------------------------------------
# BENCHMARK REGIME
# ---------------------------------------------------------------------------

def benchmark_regime(bench: pd.DataFrame) -> pd.DataFrame:
    b = bench.copy()
    b["sma50"] = b["close"].rolling(50).mean()
    b["sma200"] = b["close"].rolling(200).mean()

    b["regime"] = np.select(
        [
            (b["close"] > b["sma50"]) & (b["close"] > b["sma200"]),
            (b["close"] > b["sma200"]) & (b["close"] <= b["sma50"]),
            (b["close"] <= b["sma200"]),
        ],
        ["BULL", "CORRECTION", "DEFENSIVE"],
        default="UNKNOWN",
    )

    b["exposure"] = b["regime"].map({
        "BULL": CFG.regime_bull_exposure,
        "CORRECTION": CFG.regime_correction_exposure,
        "DEFENSIVE": CFG.regime_defensive_exposure,
    }).fillna(0.0)

    return b


# ---------------------------------------------------------------------------
# CROSS-SECTIONAL RANKING
# ---------------------------------------------------------------------------

def pct_rank(s: pd.Series) -> pd.Series:
    # Empirical percentile [0,100], with ties handled consistently.
    return s.rank(method="average", pct=True) * 100.0


def add_cross_sectional_scores(day: pd.DataFrame) -> pd.DataFrame:
    x = day.copy()
    x["roc3_rank"] = pct_rank(x["roc3m"])
    x["high_prox"] = x["close"] / x["high52"]
    x["high_prox_rank"] = pct_rank(x["high_prox"])
    x["cms"] = 0.60 * x["roc3_rank"] + 0.40 * x["high_prox_rank"]

    # Independent score: normalized combination of 6M and 12M vol-adjusted momentum.
    x["mom6_rank"] = pct_rank(x["mom6_vol_adj"])
    x["mom12_rank"] = pct_rank(x["mom12_vol_adj"])
    x["independent_score"] = 0.50 * x["mom6_rank"] + 0.50 * x["mom12_rank"]

    return x


# ---------------------------------------------------------------------------
# USER V2.5 SIGNAL
# ---------------------------------------------------------------------------

def stage2_mask(x: pd.DataFrame) -> pd.Series:
    return (
        (x["close"] > x["sma50"]) &
        (x["sma50"] > x["sma150"]) &
        (x["sma150"] > x["sma200"]) &
        (x["slope200pct"] > CFG.slope200_min) &
        (x["close"] >= 0.75 * x["high52"]) &
        (x["close"] >= 1.30 * x["low52"]) &
        (x["rsi14"] >= CFG.rsi_min) &
        (x["rsi14"] <= CFG.rsi_max) &
        (x["roc1m"] >= CFG.roc1m_min) &
        (x["roc2m"] > CFG.roc2m_min)
    )


def quality_mask(x: pd.DataFrame) -> pd.Series:
    return (
        (x["vol_ratio"] >= CFG.volume_pass) &
        (x["vcr"] <= CFG.vcr_reject) &
        (x["fip_smoothness"] >= CFG.fip_smooth_min) &
        (x["fip_max_gain_share"] <= CFG.fip_jump_share_max)
    )


def extension_mask(x: pd.DataFrame) -> pd.Series:
    return (
        (x["distance_sma50_pct"] <= CFG.extension_max) &
        (x["atr_pct"] <= CFG.atr_pct_max)
    )


def user_v25_candidates(day: pd.DataFrame, regime: str) -> pd.DataFrame:
    x = universe_filter(day)
    x = x[stage2_mask(x)].copy()

    if regime == "DEFENSIVE":
        return x.iloc[0:0]

    # Correction regime: VCR <= 0.90 as specified.
    if regime == "CORRECTION":
        x = x[x["vcr"] <= CFG.vcr_prime]

    x = add_cross_sectional_scores(x)
    x = x[quality_mask(x)]
    x = x[extension_mask(x)]

    # Strongest CMS first.
    return x.sort_values(["cms", "roc3m"], ascending=False)


# ---------------------------------------------------------------------------
# INDEPENDENT STRATEGY
# ---------------------------------------------------------------------------

def independent_candidates(day: pd.DataFrame, regime: str) -> pd.DataFrame:
    x = universe_filter(day)

    # No Minervini, RSI, VCR, FIP, or O'Neil volume filter.
    x = x.dropna(subset=["mom6_vol_adj", "mom12_vol_adj"])
    x = add_cross_sectional_scores(x)

    # Independent strategy uses regime only as exposure scaling.
    # It does not force 100% cash below SMA200.
    x = x.sort_values("independent_score", ascending=False)
    return x.head(CFG.independent_top_n)


# ---------------------------------------------------------------------------
# NSE MOMENTUM PROXY
# ---------------------------------------------------------------------------

def nse_momentum_candidates(day: pd.DataFrame) -> pd.DataFrame:
    x = universe_filter(day)
    x = x.dropna(subset=["mom6_vol_adj", "mom12_vol_adj"])
    x = add_cross_sectional_scores(x)

    # Proxy, not an exact replication of the official index:
    # official methodology should be used if licensed/official constituent
    # history is supplied.
    x["nse_proxy_score"] = (
        0.50 * pct_rank(x["mom6_vol_adj"]) +
        0.50 * pct_rank(x["mom12_vol_adj"])
    )
    return x.sort_values("nse_proxy_score", ascending=False).head(CFG.independent_top_n)


# ---------------------------------------------------------------------------
# BACKTEST ENGINE
# ---------------------------------------------------------------------------

@dataclass
class Position:
    symbol: str
    qty: int
    entry: float
    stop: float
    entry_date: pd.Timestamp
    initial_r: float
    remaining: int
    state: int = 0


class Backtester:
    def __init__(self, data: pd.DataFrame, bench: pd.DataFrame, strategy: str):
        self.data = data.sort_values(["date", "symbol"]).copy()
        self.bench = bench.set_index("date")
        self.strategy = strategy
        self.cash = CFG.initial_capital
        self.positions: Dict[str, Position] = {}
        self.equity_curve = []
        self.trades = []

        self.by_date = {d: g for d, g in self.data.groupby("date")}
        self.dates = sorted(self.by_date.keys())

    def cost_rate(self):
        return (
            CFG.slippage_bps +
            CFG.brokerage_bps +
            CFG.transaction_cost_bps +
            CFG.stamp_and_other_bps
        ) / 10000.0

    def execute_buy(self, symbol, qty, price, date, stop, initial_r):
        if qty <= 0 or price <= 0:
            return
        notional = qty * price
        cost = notional * self.cost_rate()
        total = notional + cost
        if total > self.cash:
            qty = int(self.cash / (price * (1 + self.cost_rate())))
            if qty <= 0:
                return
            notional = qty * price
            cost = notional * self.cost_rate()
            total = notional + cost

        self.cash -= total
        self.positions[symbol] = Position(
            symbol=symbol,
            qty=qty,
            entry=price,
            stop=stop,
            entry_date=date,
            initial_r=initial_r,
            remaining=qty,
        )

    def execute_sell(self, symbol, qty, price, date, reason):
        p = self.positions.get(symbol)
        if p is None or qty <= 0:
            return
        qty = min(qty, p.remaining)
        notional = qty * price
        cost = notional * self.cost_rate()
        self.cash += notional - cost
        pnl = (price - p.entry) * qty - cost
        self.trades.append({
            "symbol": symbol,
            "entry_date": p.entry_date,
            "exit_date": date,
            "entry": p.entry,
            "exit": price,
            "qty": qty,
            "pnl": pnl,
            "return_pct": (price / p.entry - 1) * 100,
            "reason": reason,
            "holding_days": (date - p.entry_date).days,
        })
        p.remaining -= qty
        if p.remaining <= 0:
            del self.positions[symbol]

    def mark_to_market(self, day):
        equity = self.cash
        for symbol, p in self.positions.items():
            row = day[day["symbol"] == symbol]
            if len(row):
                equity += p.remaining * float(row.iloc[0]["close"])
            else:
                equity += p.remaining * p.entry
        self.equity_curve.append({"date": day["date"].iloc[0], "equity": equity})

    def sizing_user(self, row, entry):
        atr14 = float(row["atr14"])
        raw_stop = entry - 2 * atr14
        bounded_stop = max(entry * 0.93, min(raw_stop, entry * 0.95))
        risk_per_share = entry - bounded_stop
        if risk_per_share <= 0:
            return 0, bounded_stop

        equity = self.equity_curve[-1]["equity"] if self.equity_curve else CFG.initial_capital
        q_risk = math.floor(equity * CFG.risk_fraction / risk_per_share)
        q_exposure = math.floor(equity * CFG.exposure_fraction / entry)
        q_liq = math.floor(float(row["adtv20"]) * CFG.liquidity_fraction / entry)
        return max(0, min(q_risk, q_exposure, q_liq)), bounded_stop

    def run(self):
        # Signals at t, fills at next available trading day's open.
        pending = None

        for i, date in enumerate(self.dates):
            day = self.by_date[date]

            # Execute prior signal at today's open.
            if pending is not None:
                for order in pending:
                    symbol = order["symbol"]
                    if symbol not in set(day["symbol"]):
                        continue
                    row = day[day["symbol"] == symbol].iloc[0]
                    open_px = float(row["open"]) * (1 + CFG.slippage_bps / 10000.0)

                    if order["side"] == "BUY":
                        if self.strategy == "USER_V25":
                            qty, stop = self.sizing_user(row, open_px)
                            if qty > 0:
                                initial_r = open_px - stop
                                self.execute_buy(symbol, qty, open_px, date, stop, initial_r)
                        else:
                            # Equal-weight-ish allocation, capped by available cash.
                            equity = self.equity_curve[-1]["equity"] if self.equity_curve else CFG.initial_capital
                            target_value = equity / CFG.max_positions
                            qty = int(target_value / open_px)
                            if qty > 0:
                                stop = open_px * 0.92
                                self.execute_buy(symbol, qty, open_px, date, stop, open_px-stop)
                pending = None

            # Stop handling for currently held positions using today's OHLC.
            for symbol in list(self.positions.keys()):
                p = self.positions[symbol]
                r = day[day["symbol"] == symbol]
                if r.empty:
                    continue
                row = r.iloc[0]
                low = float(row["low"])
                high = float(row["high"])

                # Conservative stop simulation: if stop is touched, assume stop fill.
                if low <= p.stop:
                    self.execute_sell(symbol, p.remaining, p.stop, date, "STOP")
                    continue

                gain = float(row["close"]) / p.entry - 1

                if self.strategy == "USER_V25":
                    if p.state == 0 and gain >= 0.15:
                        p.stop = p.entry * 1.015
                        p.state = 1

                    if p.state <= 1 and gain >= 0.22 and float(row["close"]) >= p.entry + 3*p.initial_r:
                        qty_to_sell = math.floor(p.remaining * 0.40)
                        if qty_to_sell > 0:
                            self.execute_sell(symbol, qty_to_sell, float(row["close"]), date, "STATE2_40PCT")
                            if symbol in self.positions:
                                self.positions[symbol].stop = p.entry * 1.10
                                self.positions[symbol].state = 2

                    if symbol in self.positions and gain > 0.25:
                        trail = max(float(row["sma50"]), float(row["close"]))  # fallback below EMA if EMA unavailable
                        # Use a true 20EMA for the actual trail.
                        ema20 = float(row.get("ema20", np.nan))
                        if np.isfinite(ema20):
                            trail = max(float(row["sma50"]), ema20) * 0.995
                        self.positions[symbol].stop = max(self.positions[symbol].stop, trail)
                        self.positions[symbol].state = 3

            # Mark portfolio.
            self.mark_to_market(day)

            # Generate next-day signal.
            if i >= len(self.dates) - 1:
                continue

            regime = "UNKNOWN"
            if date in self.bench.index:
                regime = str(self.bench.loc[date, "regime"])

            if self.strategy == "USER_V25":
                candidates = user_v25_candidates(day, regime)
            elif self.strategy == "INDEPENDENT":
                candidates = independent_candidates(day, regime)
            elif self.strategy == "NSE_MOMENTUM_PROXY":
                candidates = nse_momentum_candidates(day)
            else:
                raise ValueError(self.strategy)

            # Avoid repeatedly buying held names.
            candidates = candidates[~candidates["symbol"].isin(self.positions.keys())]

            if self.strategy == "USER_V25":
                # User's regime exposure:
                if regime == "BULL":
                    target_n = CFG.max_positions
                elif regime == "CORRECTION":
                    target_n = max(1, CFG.max_positions // 2)
                else:
                    target_n = 0
                candidates = candidates.head(target_n)
            else:
                candidates = candidates.head(CFG.max_positions)

            pending = [{"symbol": s, "side": "BUY"} for s in candidates["symbol"].tolist()]

        # Liquidate remaining positions at final close for report completeness.
        final_date = self.dates[-1]
        final_day = self.by_date[final_date]
        for symbol in list(self.positions.keys()):
            row = final_day[final_day["symbol"] == symbol]
            if len(row):
                self.execute_sell(symbol, self.positions[symbol].remaining,
                                  float(row.iloc[0]["close"]), final_date, "END")

        return self.results()

    def results(self):
        eq = pd.DataFrame(self.equity_curve)
        if eq.empty:
            return {
                "equity": eq,
                "trades": pd.DataFrame(self.trades),
                "metrics": {}
            }

        eq["peak"] = eq["equity"].cummax()
        eq["drawdown"] = eq["equity"] / eq["peak"] - 1

        days = max((eq["date"].iloc[-1] - eq["date"].iloc[0]).days, 1)
        years = days / 365.25
        cagr = (eq["equity"].iloc[-1] / eq["equity"].iloc[0]) ** (1 / years) - 1

        daily_ret = eq["equity"].pct_change().dropna()
        sharpe = np.nan
        if daily_ret.std() > 0:
            sharpe = daily_ret.mean() / daily_ret.std() * np.sqrt(252)

        downside = daily_ret[daily_ret < 0].std()
        sortino = np.nan if not downside or np.isnan(downside) else daily_ret.mean()/downside*np.sqrt(252)

        trades = pd.DataFrame(self.trades)
        if len(trades):
            wins = trades.loc[trades["pnl"] > 0, "pnl"]
            losses = trades.loc[trades["pnl"] < 0, "pnl"]
            pf = wins.sum() / abs(losses.sum()) if len(losses) else np.inf
            win_rate = (trades["pnl"] > 0).mean()
            expectancy = trades["pnl"].mean()
        else:
            pf = np.nan
            win_rate = np.nan
            expectancy = np.nan

        metrics = {
            "initial_capital": CFG.initial_capital,
            "final_equity": float(eq["equity"].iloc[-1]),
            "CAGR_pct": cagr * 100,
            "max_drawdown_pct": eq["drawdown"].min() * 100,
            "Sharpe": sharpe,
            "Sortino": sortino,
            "profit_factor": pf,
            "win_rate_pct": win_rate * 100 if pd.notna(win_rate) else np.nan,
            "expectancy_per_trade": expectancy,
            "trades": len(trades),
            "avg_holding_days": trades["holding_days"].mean() if len(trades) else np.nan,
        }

        return {"equity": eq, "trades": trades, "metrics": metrics}


# ---------------------------------------------------------------------------
# ABLATION RESEARCH
# ---------------------------------------------------------------------------

def ablation_snapshot(data: pd.DataFrame, bench: pd.DataFrame) -> pd.DataFrame:
    """
    Fast signal-level ablation. This intentionally does not reuse portfolio
    state, so it answers a different question from the portfolio backtest:
    how many candidates survive each filter and how concentrated they are.
    """
    rows = []
    for date, day0 in data.groupby("date"):
        if date not in bench.index:
            continue
        regime = str(bench.loc[date, "regime"])
        day = universe_filter(day0)
        if day.empty:
            continue

        base = len(day)
        s2 = stage2_mask(day).fillna(False)
        n_s2 = int(s2.sum())

        d = day[s2].copy()
        if d.empty:
            rows.append({"date": date, "base": base, "stage2": 0, "cms": 0, "volume": 0, "vcr": 0, "fip": 0, "full": 0})
            continue

        d = add_cross_sectional_scores(d)
        n_cms = len(d)

        vol = d["vol_ratio"] >= CFG.volume_pass
        vcr = d["vcr"] <= CFG.vcr_reject
        fip = (d["fip_smoothness"] >= CFG.fip_smooth_min) & (d["fip_max_gain_share"] <= CFG.fip_jump_share_max)
        ext = extension_mask(d)

        full = vol & vcr & fip & ext
        if regime == "CORRECTION":
            full &= d["vcr"] <= CFG.vcr_prime
        if regime == "DEFENSIVE":
            full &= False

        rows.append({
            "date": date,
            "base": base,
            "stage2": n_s2,
            "cms": n_cms,
            "volume": int(vol.sum()),
            "vcr": int((vol & vcr).sum()),
            "fip": int((vol & vcr & fip).sum()),
            "full": int(full.sum()),
        })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# REPORTING
# ---------------------------------------------------------------------------

def save_results(out_dir: Path, name: str, result: dict):
    out_dir.mkdir(parents=True, exist_ok=True)
    if result["equity"] is not None and len(result["equity"]):
        result["equity"].to_csv(out_dir / f"{name}_equity.csv", index=False)
    if result["trades"] is not None and len(result["trades"]):
        result["trades"].to_csv(out_dir / f"{name}_trades.csv", index=False)
    pd.DataFrame([result["metrics"]]).to_csv(out_dir / f"{name}_metrics.csv", index=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="./data", help="Folder with normalized NSE stock CSVs")
    parser.add_argument("--benchmark", default="./data/NIFTY500.csv")
    parser.add_argument("--out", default="./results")
    args = parser.parse_args()

    data_dir = Path(args.data)
    out_dir = Path(args.out)

    stocks = read_stock_data(data_dir)
    bench = benchmark_regime(read_benchmark(Path(args.benchmark)))

    print(f"Loaded {len(stocks):,} rows, {stocks['symbol'].nunique():,} symbols.")
    print(f"Period: {stocks['date'].min().date()} -> {stocks['date'].max().date()}")

    print("Calculating indicators...")
    stocks = prepare_indicators(stocks)

    print("Running portfolio backtests...")
    all_metrics = []

    for strategy in ["USER_V25", "INDEPENDENT", "NSE_MOMENTUM_PROXY"]:
        print(f"  {strategy}")
        bt = Backtester(stocks, bench, strategy)
        result = bt.run()
        save_results(out_dir, strategy, result)
        m = dict(result["metrics"])
        m["strategy"] = strategy
        all_metrics.append(m)

    print("Running signal-level ablation...")
    abl = ablation_snapshot(stocks, bench)
    abl.to_csv(out_dir / "USER_V25_ablation.csv", index=False)

    comparison = pd.DataFrame(all_metrics)
    comparison = comparison[
        ["strategy", "CAGR_pct", "max_drawdown_pct", "Sharpe", "Sortino",
         "profit_factor", "win_rate_pct", "expectancy_per_trade",
         "trades", "avg_holding_days"]
    ]
    comparison.to_csv(out_dir / "COMPARISON.csv", index=False)

    print("\n=== STRATEGY COMPARISON ===")
    print(comparison.to_string(index=False))

    print("\nFiles written to:", out_dir.resolve())
    print("NOTE: Results are research output, not a claim of future profitability.")


if __name__ == "__main__":
    main()
