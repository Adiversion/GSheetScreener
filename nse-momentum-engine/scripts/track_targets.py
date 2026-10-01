#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
track_targets.py — Daily price tracker for open rotation positions
=================================================================
Once a position is live (a GTT placed in Kite), you want to know — every day —
how close it is to the +15% rotation target and how much room is left before the
stop. This script does exactly that from a plain `positions.json` file and writes
a small status file the PWA can render.

Price sources (in priority order, all free):
  1. Kite Connect LTP  — official, real-time. Used only when KITE_API_KEY and
     KITE_ACCESS_TOKEN are present in the environment.
  2. yfinance          — keyless daily close. Always available as a fallback.

No Google Finance: its API was shut down in 2012 and only survives as the
GOOGLEFINANCE() spreadsheet formula.

positions.json format
---------------------
    {
      "positions": [
        {"symbol": "CUPID", "entry": 100.0, "shares": 9,
         "target_pct": 15, "stop_pct": 6}
      ]
    }

`target_pct` / `stop_pct` are optional per-position (percent). Defaults come
from the CLI (`--target`, `--stop`).

Usage
-----
    python scripts/track_targets.py                       # uses positions.json
    python scripts/track_targets.py --positions my.json
    python scripts/track_targets.py --out app/data/targets.json
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import datetime, timezone

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DATA_DIR = os.path.join(ROOT_DIR, "app", "data")
DEFAULT_POSITIONS = os.path.join(ROOT_DIR, "positions.json")
DEFAULT_OUT = os.path.join(APP_DATA_DIR, "targets.json")

DEFAULT_TARGET_PCT = 0.15
DEFAULT_STOP_PCT = 0.06
NEAR_FRACTION = 0.70   # "approaching" when >= 70% of the way to target


# ─────────────────────────────────────────────────────────────────────────────
# Pure evaluation logic (no network — unit tested)
# ─────────────────────────────────────────────────────────────────────────────
def evaluate_position(entry: float, cmp: float, target_pct: float,
                      stop_pct: float, shares: int = 0) -> dict:
    """Classify one position against its target and stop."""
    entry = float(entry or 0.0)
    cmp = float(cmp or 0.0)
    target_pct = float(target_pct)
    stop_pct = float(stop_pct)

    pnl_pct = ((cmp - entry) / entry * 100.0) if entry > 0 else 0.0
    target_price = entry * (1.0 + target_pct)
    stop_price = entry * (1.0 - stop_pct)
    to_target_pct = ((target_price - cmp) / cmp * 100.0) if cmp > 0 else 0.0

    if cmp <= stop_price:
        status = "stopped"
    elif cmp >= target_price:
        status = "hit"
    elif pnl_pct >= target_pct * 100.0 * NEAR_FRACTION:
        status = "near"
    else:
        status = "holding"

    return {
        "pnl_pct": round(pnl_pct, 2),
        "pnl_value": round((cmp - entry) * int(shares or 0), 2),
        "target_price": round(target_price, 2),
        "stop_price": round(stop_price, 2),
        "to_target_pct": round(to_target_pct, 2),
        "status": status,
    }


def summarise(entries: list) -> dict:
    """Counts used by the app header / badge."""
    counts = {"hit": 0, "near": 0, "holding": 0, "stopped": 0}
    for e in entries:
        counts[e.get("status", "holding")] = counts.get(e.get("status", "holding"), 0) + 1
    return {"count": len(entries), **counts}


# ─────────────────────────────────────────────────────────────────────────────
# IO
# ─────────────────────────────────────────────────────────────────────────────
def load_positions(path: str) -> list:
    if not path or not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("positions", []) or []
    return []


def fetch_prices(symbols: list) -> tuple:
    """Return ({symbol: cmp}, source). Tries Kite Connect, then yfinance."""
    symbols = [str(s).upper() for s in symbols if s]
    if not symbols:
        return {}, "none"

    kite = _fetch_kite(pairs=symbols)
    if kite:
        return kite, "kite"

    return _fetch_yfinance(symbols), "yfinance"


def _fetch_kite(pairs: list) -> dict:
    api_key = os.environ.get("KITE_API_KEY", "")
    token = os.environ.get("KITE_ACCESS_TOKEN", "")
    if not (api_key and token):
        return {}
    try:
        import requests

        instruments = [f"NSE:{s}" for s in pairs]
        resp = requests.get(
            "https://api.kite.trade/quote/ltp",
            params={"i": instruments},
            headers={
                "X-Kite-Version": "3",
                "Authorization": f"token {api_key}:{token}",
            },
            timeout=20,
        )
        resp.raise_for_status()
        payload = resp.json()
        data = payload.get("data", {}) if isinstance(payload, dict) else {}
        out = {}
        for s in pairs:
            node = data.get(f"NSE:{s}")
            if node and node.get("last_price") is not None:
                out[s] = float(node["last_price"])
        return out
    except Exception as exc:  # noqa: BLE001 — fall back to yfinance
        print(f"[WARN] Kite LTP unavailable ({exc}); falling back to yfinance")
        return {}


def _fetch_yfinance(symbols: list) -> dict:
    try:
        import yfinance as yf
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] yfinance not available: {exc}")
        return {}

    tickers = [s if s.endswith(".NS") else f"{s}.NS" for s in symbols]
    try:
        data = yf.download(tickers, period="5d", interval="1d", progress=False,
                           group_by="ticker", threads=True, auto_adjust=False)
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] yfinance download failed: {exc}")
        return {}

    out = {}
    for s, t in zip(symbols, tickers):
        try:
            series = data[t]["Close"].dropna() if hasattr(data, "columns") and t in data else None
            if series is not None and len(series):
                price = float(series.iloc[-1])
                if math.isfinite(price):
                    out[s] = price
        except Exception:
            continue
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Build
# ─────────────────────────────────────────────────────────────────────────────
def build_targets(positions: list, prices: dict, source: str,
                  default_target: float, default_stop: float) -> dict:
    entries = []
    for p in positions:
        sym = str(p.get("symbol", "")).upper()
        if not sym:
            continue
        cmp = prices.get(sym)
        entry = float(p.get("entry") or 0.0)
        shares = int(p.get("shares") or 0)
        target_pct = float(p.get("target_pct", default_target * 100.0)) / 100.0
        stop_pct = float(p.get("stop_pct", default_stop * 100.0)) / 100.0

        row = {
            "symbol": sym,
            "entry": round(entry, 2),
            "shares": shares,
            "target_pct": round(target_pct * 100.0, 1),
            "stop_pct": round(stop_pct * 100.0, 1),
        }
        if cmp is None:
            row.update({"cmp": None, "status": "no_price", "pnl_pct": None,
                        "pnl_value": None, "target_price": round(entry * (1 + target_pct), 2),
                        "stop_price": round(entry * (1 - stop_pct), 2), "to_target_pct": None})
        else:
            row["cmp"] = round(float(cmp), 2)
            row.update(evaluate_position(entry, float(cmp), target_pct, stop_pct, shares))
        entries.append(row)

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": source,
        "default_target_pct": round(default_target * 100.0, 1),
        "default_stop_pct": round(default_stop * 100.0, 1),
        "summary": summarise(entries),
        "entries": entries,
    }


def _print_report(out: dict) -> None:
    print("=" * 64)
    print("\U0001f3af  ROTATION TARGET TRACKER")
    print("=" * 64)
    if not out["entries"]:
        print("  No open positions. Add them to positions.json.")
        print("=" * 64)
        return
    print(f"  Source: {out['source']}   Target: +{out['default_target_pct']}%   Stop: -{out['default_stop_pct']}%")
    for e in out["entries"]:
        if e.get("status") == "no_price":
            print(f"  · {e['symbol']:12s} no price available")
            continue
        flag = {"hit": "\u2705 TARGET HIT", "near": "\U0001f7e1 NEAR",
                "holding": "\U0001f535 HOLDING", "stopped": "\U0001f534 STOPPED"}[e["status"]]
        print(f"  · {e['symbol']:12s} \u20b9{e['cmp']:>9,.2f}  {e['pnl_pct']:+6.2f}%  "
              f"\u2192 target \u20b9{e['target_price']:>9,.2f} ({e['to_target_pct']:+.1f}%)  {flag}")
    s = out["summary"]
    print("-" * 64)
    print(f"  {s['count']} tracked · {s['hit']} hit · {s['near']} near · {s['holding']} holding · {s['stopped']} stopped")
    print("=" * 64)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Daily target tracker for open rotation positions")
    ap.add_argument("--positions", default=DEFAULT_POSITIONS, help="Path to positions.json")
    ap.add_argument("--out", default=DEFAULT_OUT, help="Where to write targets.json")
    ap.add_argument("--target", type=float, default=DEFAULT_TARGET_PCT, help="Rotation target as a decimal (0.15)")
    ap.add_argument("--stop", type=float, default=DEFAULT_STOP_PCT, help="Stop as a decimal (0.06)")
    args = ap.parse_args(argv)

    positions = load_positions(args.positions)
    symbols = [str(p.get("symbol", "")).upper() for p in positions if p.get("symbol")]
    prices, source = ({}, "none") if not symbols else fetch_prices(symbols)

    out = build_targets(positions, prices, source, args.target, args.stop)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)

    _print_report(out)
    print(f"\U0001f4be Saved: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
