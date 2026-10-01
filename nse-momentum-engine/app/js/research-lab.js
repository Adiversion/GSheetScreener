/**
 * research-lab.js — UI Controller & Data Fetcher for Backtest Research Lab
 * =========================================================================
 * Manages user ticker searches, 365-day candle fetching, and report rendering.
 */

'use strict';

(function(root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.ResearchLab = factory();
})(typeof self !== 'undefined' ? self : this, function() {

  const DEFAULT_PROXY = 'https://nse-quote.audittool-api.workers.dev';

  function getProxyUrl() {
    try {
      const userProxy = (typeof store !== 'undefined' && store.get ? store.get('nse_live_proxy', '') : localStorage.getItem('nse_live_proxy') || '');
      if (userProxy && userProxy.trim()) return userProxy.trim().replace(/\/+$/, '');
    } catch (_) {}
    return DEFAULT_PROXY;
  }

  async function fetchCandles(sym) {
    const symbol = String(sym || '').trim().toUpperCase();
    const symNs = symbol.includes('.') ? symbol : `${symbol}.NS`;
    const proxy = getProxyUrl();

    // 1. Try Cloudflare Worker proxy (keyless, free)
    if (proxy) {
      try {
        const url = `${proxy}/?symbol=${encodeURIComponent(symNs)}&range=1y&interval=1d`;
        const res = await fetch(url, { cache: 'no-store' });
        if (res.ok) {
          const json = await res.json();
          if (json && Array.isArray(json.candles) && json.candles.length >= 20) {
            return json.candles;
          }
        }
      } catch (_) {}
    }

    // 2. Direct Yahoo Finance endpoint (fallback in non-CORS contexts)
    try {
      const directUrl = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(symNs)}?range=1y&interval=1d`;
      const res = await fetch(directUrl, { cache: 'no-store' });
      if (res.ok) {
        const data = await res.json();
        const res0 = data?.chart?.result?.[0];
        const timestamps = res0?.timestamp || [];
        const quote = res0?.indicators?.quote?.[0] || {};
        const candles = [];
        for (let i = 0; i < timestamps.length; i++) {
          const c = quote.close?.[i];
          if (c != null && !isNaN(c) && c > 0) {
            candles.push({
              date: new Date(timestamps[i] * 1000).toISOString().split('T')[0],
              open: quote.open?.[i] ?? c,
              high: quote.high?.[i] ?? c,
              low: quote.low?.[i] ?? c,
              close: c,
              volume: quote.volume?.[i] ?? 0,
            });
          }
        }
        if (candles.length >= 20) return candles;
      }
    } catch (_) {}

    return null;
  }

  function paintReport(symbol, r, isLive = false) {
    const title = document.getElementById('researchSymbolTitle');
    const grid = document.getElementById('researchGrid');
    const verdict = document.getElementById('researchVerdict');
    const foot = document.getElementById('researchFoot');
    if (!grid) return;

    if (title) {
      title.innerHTML = `Backtest Study — ${symbol} ` +
        (isLive ? '<span class="badge badge--bull" style="font-size:0.75rem;vertical-align:middle;margin-left:8px;">⚡ Live 365-Day Engine</span>'
                : '<span class="badge badge--muted" style="font-size:0.75rem;vertical-align:middle;margin-left:8px;">💾 Offline Disk Report</span>');
    }

    if (!r) {
      if (verdict) { verdict.className = 'badge'; verdict.textContent = 'No report'; }
      grid.innerHTML = `
        <div class="cred-item" style="grid-column: 1 / -1; padding: 20px; text-align: center;">
          <small>Status</small>
          <span style="margin: 8px 0; display:block;">No pre-computed report for ${symbol}.</span>
          <button class="btn btn--primary btn--sm" id="btnRunLiveInline" style="margin-top:8px;">
            ⚡ Run Live 365-Day Backtest for ${symbol}
          </button>
        </div>`;
      if (foot) foot.textContent = `Connected proxy: ${getProxyUrl()}`;
      const btnInline = document.getElementById('btnRunLiveInline');
      if (btnInline) btnInline.addEventListener('click', () => runLiveBacktest(symbol));
      return;
    }

    const s = r.study || {}, sim = r.simulation || {}, v = r.verdict || {};
    const score = v.score == null ? '–' : v.score;
    if (verdict) {
      verdict.className = 'badge ' + (v.credible ? 'badge--bull' : 'badge--defensive');
      verdict.textContent = (v.credible ? 'Credible · ' : 'Low credibility · ') + score;
    }

    const item = (k, val, tone) => `<div class="cred-item ${tone || ''}"><small>${k}</small><span>${val}</span></div>`;
    grid.innerHTML = [
      item('+15% hit rate', s.target_hit_rate_pct != null ? s.target_hit_rate_pct + '%' : '–', s.target_hit_rate_pct >= 55 ? 'is-bull' : 'is-caution'),
      item('Stopped out', s.stop_hit_rate_pct != null ? s.stop_hit_rate_pct + '%' : '–', 'is-bear'),
      item('Expectancy', s.expectancy_pct != null ? (s.expectancy_pct >= 0 ? '+' : '') + s.expectancy_pct + '%' : '–', s.expectancy_pct >= 0 ? 'is-bull' : 'is-bear'),
      item('Signals (365d)', s.observations != null ? s.observations : '–'),
      item('Avg hold → target', s.avg_hold_to_target_days != null ? s.avg_hold_to_target_days + 'd' : '–'),
      item('Median days → +15%', s.median_days_to_target ? `${s.median_days_to_target}d` : (s.time_to_target?.trading_days?.median ? `${s.time_to_target.trading_days.median}d` : '–')),
      item('Rotation cycles', sim.cycles != null ? sim.cycles : '–'),
      item('Win rate', sim.win_rate_pct != null ? sim.win_rate_pct + '%' : '–', sim.win_rate_pct >= 50 ? 'is-bull' : 'is-caution'),
      item('Sim return', sim.total_return_pct != null ? (sim.total_return_pct >= 0 ? '+' : '') + sim.total_return_pct + '%' : '–', sim.total_return_pct >= 0 ? 'is-bull' : 'is-bear'),
    ].join('');

    const periodStr = r.period ? ` · backtested ${r.period.start} → ${r.period.end} (${r.period.bars || 250} bars)` : '';
    if (foot) foot.textContent = (v.summary || '') + periodStr;
  }

  async function runLiveBacktest(sym) {
    const symbol = String(sym || '').trim().toUpperCase().replace(/\.NS$/, '');
    if (!symbol) return;

    const input = document.getElementById('researchCustomTicker');
    if (input) input.value = symbol;

    const grid = document.getElementById('researchGrid');
    const title = document.getElementById('researchSymbolTitle');
    const verdict = document.getElementById('researchVerdict');
    const foot = document.getElementById('researchFoot');

    if (title) title.textContent = `Analyzing ${symbol}…`;
    if (verdict) { verdict.className = 'badge'; verdict.textContent = 'Calculating…'; }
    if (grid) {
      grid.innerHTML = `<div class="cred-item" style="grid-column: 1 / -1; padding: 24px; text-align: center;">
        <span class="status-pulse-dot live" style="display:inline-block; margin-right:8px;"></span>
        <span>Fetching 365-day candles for <strong>${symbol}</strong> via Cloudflare Proxy and computing Stage-2 forward outcomes…</span>
      </div>`;
    }

    try {
      const candles = await fetchCandles(symbol);
      if (!candles || candles.length < 20) {
        // Fallback: check if static offline report exists
        const offlineRes = await fetch(`data/backtests/${encodeURIComponent(symbol)}.json?_t=` + Date.now(), { cache: 'no-store' });
        if (offlineRes.ok) {
          const report = await offlineRes.json();
          paintReport(symbol, report, false);
          return;
        }
        throw new Error(`Unable to retrieve 365-day candles for ${symbol}. Please check internet connection or worker proxy.`);
      }

      if (typeof ResearchEngine === 'undefined') throw new Error('ResearchEngine module not loaded.');
      const report = ResearchEngine.run(candles, { symbol, evalBars: 250, targetPct: 0.15 });
      if (!report) throw new Error('Engine calculation yielded no result.');

      if (typeof state !== 'undefined') {
        state.backtests = state.backtests || {};
        state.backtests[symbol] = report;
      }
      paintReport(symbol, report, true);
    } catch (err) {
      if (grid) {
        grid.innerHTML = `<div class="cred-item is-bear" style="grid-column: 1 / -1; padding: 18px;">
          <small>Notice</small>
          <span>${err.message || 'Error executing backtest.'}</span>
        </div>`;
      }
      if (verdict) { verdict.className = 'badge badge--defensive'; verdict.textContent = 'Fetch error'; }
      if (foot) foot.textContent = `Connected proxy: ${getProxyUrl()}`;
    }
  }

  function initUI() {
    const input = document.getElementById('researchCustomTicker');
    const btnRun = document.getElementById('btnRunLiveBacktest');
    const kbd = document.getElementById('kbdRunBacktest');

    const execute = () => {
      const val = input ? input.value.trim() : '';
      if (val) runLiveBacktest(val);
    };

    if (btnRun) btnRun.onclick = execute;
    if (kbd) kbd.onclick = execute;
    if (input) {
      input.onkeydown = (e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          execute();
        }
      };
    }

    // Quick leader chips
    document.querySelectorAll('.chip-leader-suggest').forEach(chip => {
      chip.onclick = () => {
        const sym = chip.dataset.sym;
        if (sym) {
          if (input) input.value = sym;
          runLiveBacktest(sym);
        }
      };
    });

    // Auto-load initial stock if grid is empty
    const currentTitle = document.getElementById('researchSymbolTitle');
    if (currentTitle && (!currentTitle.textContent || currentTitle.textContent === 'Statistical Study')) {
      const initialSym = (typeof state !== 'undefined' && state.activeStock && state.activeStock.SYMBOL)
        || (typeof state !== 'undefined' && state.signalData && state.signalData[0] && state.signalData[0].SYMBOL)
        || 'CUPID';
      if (input) input.value = initialSym;
      runLiveBacktest(initialSym);
    }
  }

  return {
    init: initUI,
    runLive: runLiveBacktest,
    paint: paintReport,
  };
});
