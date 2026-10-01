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

    return json({
      symbol,
      range,
      count: candles.length,
      candles,
    });
  },
};
