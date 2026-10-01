/**
 * research-engine.js — Pure Stage-2 Credibility & 365-Day Backtest Engine
 * =======================================================================
 * Pure, deterministic mathematical engine for single-stock credibility studies.
 * Evaluates signals over the past 365 days of trading bars. Zero DOM/state mutation.
 */

'use strict';

(function(root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.ResearchEngine = factory();
})(typeof self !== 'undefined' ? self : this, function() {

  const DEFAULTS = {
    capital: 1000.0,
    targetPct: 0.15,
    stopFloorPct: 0.05,
    stopCapPct: 0.07,
    stopAtrMult: 2.0,
    maxHoldDays: 60,
    rsiMin: 40.0,
    rsiMax: 82.0,
    sttRate: 0.001,
    dpCharge: 15.93,
    buffer: 26.0,
    evalBars: 250, // ~365 calendar days of trading bars
  };

  function calcSMA(arr, period) {
    const out = new Float64Array(arr.length);
    let sum = 0;
    for (let i = 0; i < arr.length; i++) {
      sum += arr[i];
      if (i >= period) sum -= arr[i - period];
      out[i] = i >= period - 1 ? sum / period : NaN;
    }
    return out;
  }

  function calcRSI(closes, period = 14) {
    const out = new Float64Array(closes.length);
    let gainSum = 0, lossSum = 0;
    for (let i = 0; i < closes.length; i++) {
      if (i === 0) { out[i] = NaN; continue; }
      const diff = closes[i] - closes[i - 1];
      const gain = diff > 0 ? diff : 0;
      const loss = diff < 0 ? -diff : 0;
      gainSum += gain;
      lossSum += loss;
      if (i > period) {
        const oldDiff = closes[i - period] - closes[i - period - 1];
        gainSum -= oldDiff > 0 ? oldDiff : 0;
        lossSum -= oldDiff < 0 ? -oldDiff : 0;
      }
      if (i >= period) {
        const avgGain = gainSum / period;
        const avgLoss = lossSum / period;
        out[i] = avgLoss === 0 ? 100 : (100 - (100 / (1 + avgGain / avgLoss)));
      } else {
        out[i] = NaN;
      }
    }
    return out;
  }

  function calcATR(highs, lows, closes, period = 14) {
    const out = new Float64Array(closes.length);
    const tr = new Float64Array(closes.length);
    let sum = 0;
    for (let i = 0; i < closes.length; i++) {
      if (i === 0) {
        tr[i] = highs[i] - lows[i];
      } else {
        const h_l = highs[i] - lows[i];
        const h_pc = Math.abs(highs[i] - closes[i - 1]);
        const l_pc = Math.abs(lows[i] - closes[i - 1]);
        tr[i] = Math.max(h_l, h_pc, l_pc);
      }
      sum += tr[i];
      if (i >= period) sum -= tr[i - period];
      out[i] = i >= period - 1 ? sum / period : NaN;
    }
    return out;
  }

  function calcROC(closes, period = 40) {
    const out = new Float64Array(closes.length);
    for (let i = 0; i < closes.length; i++) {
      out[i] = i >= period && closes[i - period] > 0
        ? ((closes[i] / closes[i - period]) - 1.0) * 100.0
        : NaN;
    }
    return out;
  }

  function stopDistance(entry, atr, p) {
    const atrPct = entry > 0 ? (p.stopAtrMult * atr) / entry : p.stopCapPct;
    return Math.min(p.stopCapPct, Math.max(p.stopFloorPct, atrPct));
  }

  function qualifies(i, closes, sma50, sma200, sma20, rsi, roc, p) {
    const c = closes[i];
    if (!c || c <= 0 || isNaN(c)) return false;
    const s50 = sma50[i];
    if (isNaN(s50)) return false;
    const s200 = sma200[i];
    if (!isNaN(s200)) {
      if (!(c > s50 && s50 > s200)) return false;
    } else {
      const s20 = sma20[i];
      if (isNaN(s20) || !(c > s50 && s50 > s20)) return false;
    }
    const r = rsi[i];
    if (isNaN(r) || r < p.rsiMin || r > p.rsiMax) return false;
    const rc = roc[i];
    if (isNaN(rc) || rc <= 0) return false;
    return true;
  }

  function runStudy(candles, p) {
    const n = candles.length;
    if (n < 30) return { observations: 0 };

    const opens = candles.map(c => c.open);
    const highs = candles.map(c => c.high);
    const lows = candles.map(c => c.low);
    const closes = candles.map(c => c.close);

    const sma20 = calcSMA(closes, 20);
    const sma50 = calcSMA(closes, 50);
    const sma200 = calcSMA(closes, 200);
    const rsi = calcRSI(closes, 14);
    const atr = calcATR(highs, lows, closes, 14);
    const roc = calcROC(closes, 40);

    const startIdx = Math.max(50, n - p.evalBars);
    const outcomes = [];

    for (let i = startIdx; i < n - 1; i++) {
      if (!qualifies(i, closes, sma50, sma200, sma20, rsi, roc, p)) continue;
      const entry = opens[i + 1] || closes[i];
      if (!entry || entry <= 0 || isNaN(entry)) continue;

      const stopPct = stopDistance(entry, atr[i], p);
      const stop = entry * (1.0 - stopPct);
      const target = entry * (1.0 + p.targetPct);
      const end = Math.min(i + 1 + p.maxHoldDays, n - 1);

      let outcome = 'timeout', exitPrice = closes[end], hold = end - (i + 1);
      for (let j = i + 1; j <= end; j++) {
        if (lows[j] <= stop) { outcome = 'stop'; exitPrice = stop; hold = j - (i + 1); break; }
        if (highs[j] >= target) { outcome = 'target'; exitPrice = target; hold = j - (i + 1); break; }
      }
      outcomes.push({ outcome, grossPct: ((exitPrice / entry) - 1.0) * 100.0, holdDays: hold });
    }

    const obs = outcomes.length;
    if (!obs) return { observations: 0, target_hit_rate_pct: 0, stop_hit_rate_pct: 0, expectancy_pct: 0 };

    const tgt = outcomes.filter(o => o.outcome === 'target');
    const stp = outcomes.filter(o => o.outcome === 'stop');
    const totGross = outcomes.reduce((acc, o) => acc + o.grossPct, 0);
    const tgtHolds = tgt.map(o => o.holdDays).sort((a, b) => a - b);

    return {
      observations: obs,
      target_hits: tgt.length,
      stop_hits: stp.length,
      timeouts: obs - tgt.length - stp.length,
      target_hit_rate_pct: Math.round((tgt.length / obs) * 1000) / 10,
      stop_hit_rate_pct: Math.round((stp.length / obs) * 1000) / 10,
      expectancy_pct: Math.round((totGross / obs) * 100) / 100,
      avg_hold_to_target_days: tgt.length ? Math.round((tgt.reduce((s, o) => s + o.holdDays, 0) / tgt.length) * 10) / 10 : null,
      median_days_to_target: tgtHolds.length ? tgtHolds[Math.floor(tgtHolds.length / 2)] : null,
    };
  }

  function runSimulation(candles, p) {
    const n = candles.length;
    const opens = candles.map(c => c.open), highs = candles.map(c => c.high);
    const lows = candles.map(c => c.low), closes = candles.map(c => c.close);
    const sma20 = calcSMA(closes, 20), sma50 = calcSMA(closes, 50);
    const sma200 = calcSMA(closes, 200), rsi = calcRSI(closes, 14);
    const atr = calcATR(highs, lows, closes, 14), roc = calcROC(closes, 40);

    const maxClose = Math.max(...closes.slice(Math.max(0, n - p.evalBars)));
    let capital = p.capital < maxClose ? Math.ceil((maxClose * 10) / 1000) * 1000 : p.capital;
    const initial = capital;
    const trades = [];
    const startIdx = Math.max(50, n - p.evalBars);

    let i = startIdx;
    while (i < n - 1) {
      if (!qualifies(i, closes, sma50, sma200, sma20, rsi, roc, p)) { i++; continue; }
      const entry = opens[i + 1] || closes[i];
      const affordable = Math.floor((capital - p.buffer) / entry);
      if (affordable < 1) { i++; continue; }

      const shares = affordable;
      const stopPct = stopDistance(entry, atr[i], p);
      const stop = entry * (1.0 - stopPct), target = entry * (1.0 + p.targetPct);
      const end = Math.min(i + 1 + p.maxHoldDays, n - 1);

      capital -= (shares * entry * (1.0 + p.sttRate));
      let exitPrice = closes[end], exitIdx = end;
      for (let j = i + 1; j <= end; j++) {
        if (lows[j] <= stop) { exitPrice = stop; exitIdx = j; break; }
        if (highs[j] >= target) { exitPrice = target; exitIdx = j; break; }
      }
      const gross = shares * exitPrice;
      const net = gross - (gross * p.sttRate) - p.dpCharge;
      capital += net;
      const pnl = net - (shares * entry * (1.0 + p.sttRate));
      trades.push({ pnl, holdDays: exitIdx - (i + 1) });
      i = exitIdx + 1;
    }

    if (!trades.length) return { cycles: 0, final_capital: initial, total_return_pct: 0, win_rate_pct: 0 };
    const wins = trades.filter(t => t.pnl > 0);
    return {
      cycles: trades.length,
      final_capital: Math.round(capital * 100) / 100,
      total_return_pct: Math.round(((capital / initial) - 1.0) * 1000) / 10,
      win_rate_pct: Math.round((wins.length / trades.length) * 1000) / 10,
      avg_cycle_days: Math.round((trades.reduce((s, t) => s + t.holdDays, 0) / trades.length) * 10) / 10,
    };
  }

  function buildVerdict(study) {
    const obs = study.observations || 0;
    if (obs < 6) return { credible: false, score: null, summary: 'Not enough historical signals in past 365 days.' };
    const hit = study.target_hit_rate_pct || 0, stop = study.stop_hit_rate_pct || 0, exp = study.expectancy_pct || 0;
    const score = Math.max(0, Math.min(100, hit * 0.8 + (exp + 7.0) * 1.5 - stop * 0.3));
    const credible = hit >= 55.0 && exp > 0.0;
    const hitRnd = Math.round(hit), stopRnd = Math.round(stop);
    let summary = '';
    if (credible && score >= 70) summary = `Strong edge: reached +15% before stop in ${hitRnd}% of signals.`;
    else if (credible) summary = `Positive edge: +15% hit before stop in ${hitRnd}% of signals.`;
    else if (hit >= 45) summary = `Marginal: only ${hitRnd}% of signals reached +15% before stop.`;
    else summary = `Weak: stops dominate (${stopRnd}% stopped, ${hitRnd}% reached target).`;
    return { credible, score: Math.round(score * 10) / 10, summary };
  }

  return {
    run: function(candles, options = {}) {
      const p = { ...DEFAULTS, ...options };
      if (!Array.isArray(candles) || candles.length < 20) return null;
      const study = runStudy(candles, p);
      const simulation = runSimulation(candles, p);
      const verdict = buildVerdict(study);
      const n = candles.length;
      const startCandle = candles[Math.max(0, n - p.evalBars)];
      const endCandle = candles[n - 1];

      return {
        symbol: (options.symbol || 'CUSTOM').toUpperCase(),
        generated_at: new Date().toISOString(),
        period: {
          start: startCandle?.date || '365d ago',
          end: endCandle?.date || 'today',
          bars: Math.min(n, p.evalBars),
        },
        study,
        simulation,
        verdict,
      };
    }
  };
});
