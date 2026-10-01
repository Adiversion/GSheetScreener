/**
 * yahoo-proxy.js — Free Cloudflare Worker: CORS proxy for a single Yahoo quote
 * =========================================================================
 * Why this exists
 * ---------------
 * The PWA is a static site. Browsers block direct calls to Yahoo Finance (and
 * NSE) because those servers don't send `Access-Control-Allow-Origin`. This tiny
 * Worker runs server-side (where CORS does not apply), fetches the quote, and
 * returns it with CORS headers so the app can read it.
 *
 * It is **keyless** and runs on Cloudflare's free tier (100,000 requests/day) —
 * no cron, no GitHub Actions minutes, no market-data signup.
 *
 * NOTE: do not point the app at a public CORS proxy. A public proxy sees every
 * request you make, gets rate-limited, and disappears without warning. Host your
 * own copy — it takes ~5 minutes and then it's yours.
 *
 * Deploy (free, ~5 minutes)
 * -------------------------
 *  1. Create a free account at https://dash.cloudflare.com
 *  2. Workers & Pages → Create → Create Worker → give it a name (e.g. nse-quote)
 *  3. Replace the default code with this file, then Deploy.
 *  4. Copy the URL: https://nse-quote.<your-subdomain>.workers.dev
 *  5. Paste that URL into the app: Portfolio → Live target tracker →
 *     "Live-quote key (free)" → Proxy URL.
 *
 * Usage
 * -----
 *   GET https://<your-worker>.workers.dev/?symbol=CUPID.NS
 *   → { "symbol": "CUPID.NS", "price": 123.45, "currency": "INR", "asOf": 1690000000 }
 *
 * Only Yahoo's chart endpoint is proxied, and only for GET — it is not an open
 * relay.
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

    // Only allow safe ticker characters — this is not an open proxy.
    if (!/^[A-Z0-9&.\-^]{1,24}$/.test(symbol)) return json({ error: 'bad_symbol' }, 400);

    const target = `https://${YAHOO_HOST}/v8/finance/chart/${encodeURIComponent(symbol)}?interval=1d&range=1d`;

    let upstream;
    try {
      upstream = await fetch(target, {
        headers: { 'User-Agent': 'Mozilla/5.0 (compatible; nse-quote-worker/1.0)' },
        cf: { cacheTtl: 30, cacheEverything: true },
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

    const meta = data && data.chart && data.chart.result && data.chart.result[0] && data.chart.result[0].meta;
    if (!meta || meta.regularMarketPrice == null) return json({ error: 'no_price', symbol }, 404);

    return json({
      symbol,
      price: meta.regularMarketPrice,
      previousClose: meta.chartPreviousClose ?? meta.previousClose ?? null,
      currency: meta.currency || 'INR',
      marketState: meta.marketState || null,
      asOf: meta.regularMarketTime || null,
    });
  },
};
