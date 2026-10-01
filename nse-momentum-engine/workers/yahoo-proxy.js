/**
 * yahoo-proxy.js — Free Cloudflare Worker: CORS proxy for Yahoo quotes & historical candles
 * =========================================================================================
 * Cloudflare's free tier (100,000 requests/day) keyless CORS proxy.
 * Supports:
 *   1. Real-time quotes: ?symbol=CUPID.NS (default range=1d)
 *   2. 365-day candles for backtests: ?symbol=CUPID.NS&range=1y&interval=1d
 */

const YAHOO_HOST = 'query1.finance.yahoo.com';

export default {
  async fetch(request) {
    const cors = {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type',
    };
    const json = (body, status = 200) =>
      new Response(JSON.stringify(body), {
        status,
        headers: { ...cors, 'Content-Type': 'application/json', 'Cache-Control': 'no-store' },
      });

    if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: cors });
    if (request.method !== 'GET') return json({ error: 'method_not_allowed' }, 405);

    const url = new URL(request.url);
    let symbol = (url.searchParams.get('symbol') || '').trim().toUpperCase();
    if (!symbol) return json({ error: 'missing_symbol', hint: 'pass ?symbol=CUPID.NS' }, 400);
    if (!symbol.includes('.')) symbol += '.NS';   // default to NSE

    if (!/^[A-Z0-9&.\-^]{1,24}$/.test(symbol)) return json({ error: 'bad_symbol' }, 400);

    const range = (url.searchParams.get('range') || '1d').toLowerCase();
    const interval = (url.searchParams.get('interval') || '1d').toLowerCase();
    const target = `https://${YAHOO_HOST}/v8/finance/chart/${encodeURIComponent(symbol)}?interval=${encodeURIComponent(interval)}&range=${encodeURIComponent(range)}`;

    let upstream;
    try {
      upstream = await fetch(target, {
        headers: { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36' },
        cf: { cacheTtl: range === '1d' ? 30 : 3600, cacheEverything: true },
      });
    } catch (err) {
      return json({ error: 'upstream_unreachable', message: String(err) }, 502);
    }

    if (!upstream.ok) return json({ error: 'upstream_error', status: upstream.status }, 502);

    let data;
    try {
      data = await upstream.json();
    } catch (err) {
      return json({ error: 'bad_upstream_json' }, 502);
    }

    const res0 = data?.chart?.result?.[0];
    const meta = res0?.meta;
    if (!meta || meta.regularMarketPrice == null) return json({ error: 'no_price', symbol }, 404);

    // 1) Single quote response for live tracking
    if (range === '1d') {
      return json({
        symbol,
        price: meta.regularMarketPrice,
        previousClose: meta.chartPreviousClose ?? meta.previousClose ?? null,
        currency: meta.currency || 'INR',
        marketState: meta.marketState || null,
        asOf: meta.regularMarketTime || null,
      });
    }

    // 2) Historical candles for backtesting
    const timestamps = res0.timestamp || [];
    const quote = (res0.indicators?.quote?.[0]) || {};
    const opens = quote.open || [];
    const highs = quote.high || [];
    const lows = quote.low || [];
    const closes = quote.close || [];
    const volumes = quote.volume || [];

    const candles = [];
    for (let i = 0; i < timestamps.length; i++) {
      const c = closes[i];
      if (c != null && !isNaN(c) && c > 0) {
        candles.push({
          date: new Date(timestamps[i] * 1000).toISOString().split('T')[0],
          time: timestamps[i],
          open: opens[i] != null && !isNaN(opens[i]) ? opens[i] : c,
          high: highs[i] != null && !isNaN(highs[i]) ? highs[i] : c,
          low: lows[i] != null && !isNaN(lows[i]) ? lows[i] : c,
          close: c,
          volume: volumes[i] || 0,
        });
      }
    }

    // 3) Multi-day Failure-to-Fail state memory engine
    const action = (url.searchParams.get('action') || '').toLowerCase();
    if (action === 'memory' || action === 'ftf') {
      const ftf = computeFailureToFail(candles);
      return json({
        symbol,
        action: 'memory',
        ftf,
        latestCandle: candles[candles.length - 1] || null,
      });
    }

    return json({
      symbol,
      range,
      count: candles.length,
      candles,
    });
  },
};

function computeFailureToFail(candles) {
  if (!candles || candles.length < 22) {
    return { state: 'NORMAL_TREND', is_ftf_coiling: false, is_confirmed_breakout: false, diagnostic: 'Insufficient history' };
  }
  const n = candles.length;
  const curr = candles[n - 1];
  const currC = curr.close, currH = curr.high, currL = curr.low, currV = curr.volume;
  const currRng = currH - currL;
  const currCR = currRng > 0 ? (currC - currL) / currRng : 0.5;

  let volSum20 = 0;
  for (let i = n - 20; i < n; i++) volSum20 += candles[i].volume;
  const volSma20 = volSum20 / 20;
  const currVolRatio = volSma20 > 0 ? +(currV / volSma20).toFixed(2) : 1.0;

  let rejection = null;
  const startScan = Math.max(20, n - 16);
  for (let i = n - 2; i >= startScan; i--) {
    const b = candles[i];
    let vSum = 0;
    for (let k = i - 19; k <= i; k++) vSum += (candles[k]?.volume || 0);
    const bSma = vSum / 20;
    if (bSma <= 0) continue;
    const bVR = b.volume / bSma;
    const bRng = b.high - b.low;
    if (bRng <= 0) continue;
    const bCR = (b.close - b.low) / bRng;
    const upperWick = (b.high - Math.max(b.open, b.close)) / bRng;

    let rollingPeak = 0;
    for (let k = Math.max(0, i - 19); k <= i; k++) if (candles[k].high > rollingPeak) rollingPeak = candles[k].high;
    const nearPeak = rollingPeak > 0 && ((rollingPeak - b.high) / rollingPeak <= 0.02);

    if (bVR >= 1.30 && (bCR <= 0.45 || upperWick >= 0.35) && nearPeak) {
      rejection = { idx: i, date: b.date, high: b.high, low: b.low, volRatio: +bVR.toFixed(2), cr: +bCR.toFixed(2) };
      break;
    }
  }

  let peak52 = 0;
  for (let i = Math.max(0, n - 250); i < n; i++) if (candles[i].high > peak52) peak52 = candles[i].high;

  if (!rejection) {
    const distToPeak = peak52 > 0 ? ((peak52 - currH) / peak52) * 100 : 999;
    if (distToPeak <= 2.5) {
      if (currC >= peak52 * 0.998 && currVolRatio >= 1.40 && currCR >= 0.55) {
        return {
          state: 'CONFIRMED_BREAKOUT',
          is_ftf_coiling: false,
          is_confirmed_breakout: true,
          pivot_resistance: +peak52.toFixed(2),
          downside_floor: +(currL).toFixed(2),
          diagnostic: `Cleared resistance (${peak52.toFixed(2)}) on ${currVolRatio}x volume with ${(currCR * 100).toFixed(0)}% close.`,
        };
      }
      let minFloor = currL;
      for (let k = Math.max(0, n - 4); k < n - 1; k++) if (candles[k].low < minFloor) minFloor = candles[k].low;
      return {
        state: 'RESISTANCE_PROBE',
        is_ftf_coiling: false,
        is_confirmed_breakout: false,
        pivot_resistance: +peak52.toFixed(2),
        downside_floor: +minFloor.toFixed(2),
        trigger_guidance: `Buy Stop @ INR ${(peak52 * 1.002).toFixed(2)} on Volume >= 1.5x`,
        diagnostic: `Probing major resistance (${peak52.toFixed(2)}). Rejection wick (CR ${(currCR * 100).toFixed(0)}%) on ${currVolRatio}x volume. Breakout unconfirmed.`,
      };
    }
    return { state: 'NORMAL_TREND', is_ftf_coiling: false, is_confirmed_breakout: false, diagnostic: 'No prior rejection or resistance probe' };
  }

  let minInterClose = currC, minInterLow = currL;
  for (let k = rejection.idx + 1; k < n - 1; k++) {
    if (candles[k].close < minInterClose) minInterClose = candles[k].close;
    if (candles[k].low < minInterLow) minInterLow = candles[k].low;
  }
  const floorHeld = (minInterClose >= rejection.low * 0.985) || (minInterLow >= rejection.low * 0.970);
  const proxPct = +(((rejection.high - currC) / rejection.high) * 100).toFixed(1);
  const highProx = +(((rejection.high - currH) / rejection.high) * 100).toFixed(1);

  const isBreakout = currC > rejection.high && currVolRatio >= 1.40 && currCR >= 0.55;
  const isCoiling = floorHeld && currC <= rejection.high * 1.01 && proxPct <= 3.5 && !isBreakout;
  const isBreakdown = currC < rejection.low * 0.97 && currVolRatio >= 1.30;
  const isProbe = !isBreakout && !isCoiling && !isBreakdown && (proxPct <= 3.5 || highProx <= 2.0);

  let state = 'NORMAL_TREND', diagnostic = 'Price drifting within normal trading band.';
  let trigger = null;
  let floor = rejection.low;

  if (isBreakout) {
    state = 'CONFIRMED_BREAKOUT';
    diagnostic = `Cleared prior rejection peak (${rejection.high}) on ${currVolRatio}x volume with ${(currCR * 100).toFixed(0)}% close.`;
  } else if (isCoiling) {
    state = 'FTF_COILING';
    diagnostic = `Prior rejection at ${rejection.high} (${rejection.date}) absorbed. Floor ${rejection.low} held. Retesting on dry volume (${currVolRatio}x).`;
    trigger = `Buy Stop @ INR ${(rejection.high * 1.002).toFixed(2)} on Volume >= 1.5x`;
  } else if (isProbe) {
    state = 'RESISTANCE_PROBE';
    for (let k = Math.max(0, n - 4); k < n - 1; k++) if (candles[k].low < floor) floor = candles[k].low;
    diagnostic = `Re-testing prior resistance peak (${rejection.high}). Breakout unconfirmed (CR ${(currCR * 100).toFixed(0)}%).`;
    trigger = `Buy Stop @ INR ${(rejection.high * 1.002).toFixed(2)} on Volume >= 1.5x`;
  } else if (isBreakdown) {
    state = 'TRAP_CONFIRMED';
    diagnostic = `Rejection at ${rejection.high} broke below floor ${rejection.low} on heavy volume. True distribution.`;
  }

  return {
    state,
    is_ftf_coiling: isCoiling,
    is_confirmed_breakout: isBreakout,
    pivot_resistance: rejection.high,
    downside_floor: floor,
    floor_held: floorHeld,
    proximity_to_peak_pct: proxPct,
    current_vol_ratio: currVolRatio,
    current_cr: +currCR.toFixed(2),
    trigger_guidance: trigger,
    diagnostic,
  };
}
