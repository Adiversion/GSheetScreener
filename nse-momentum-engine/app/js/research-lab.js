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

  function paintScreenerProfile(sym) {
    const card = document.getElementById('researchScreenerCard');
    if (!card) return;
    const symbol = String(sym || '').trim().toUpperCase();
    let s = null;
    if (typeof state !== 'undefined' && state.payload && Array.isArray(state.payload.all_qualified)) {
      s = state.payload.all_qualified.find(x => String(x.SYMBOL).toUpperCase() === symbol);
    }
    if (!s && typeof state !== 'undefined' && Array.isArray(state.signalData)) {
      s = state.signalData.find(x => String(x.SYMBOL).toUpperCase() === symbol);
    }
    if (!s) { card.style.display = 'none'; card.innerHTML = ''; return; }

    const isDef = (typeof state !== 'undefined' && state.payload?.regime?.regime === 'DEFENSIVE_CASH') || (s.STATUS === 'CASH');
    const cmp = parseFloat(s.CMP);
    const hi52 = parseFloat(s.HIGH_52W) || cmp;
    const prox = hi52 > 0 ? (((hi52 - cmp) / hi52) * 100).toFixed(1) : '0.0';
    const cms = parseFloat(s.CMS_SCORE) ? parseFloat(s.CMS_SCORE).toFixed(1) : (s.CMS_SCORE || '–');
    const aqs = parseFloat(s.AQS_SCORE) ? Math.round(parseFloat(s.AQS_SCORE)) : '–';
    const vol = parseFloat(s.VOL_SURGE_RATIO || s.VOL_RATIO || 1.0).toFixed(1);
    const rsi = parseFloat(s.RSI_14) ? parseFloat(s.RSI_14).toFixed(1) : '–';
    const atr = s.ATR_PCT != null ? parseFloat(s.ATR_PCT).toFixed(1) : (s.ATR_14 && cmp ? ((parseFloat(s.ATR_14) / cmp) * 100).toFixed(1) : '–');
    const to = s.TURNOVER_CRORES != null ? parseFloat(s.TURNOVER_CRORES).toFixed(1) : '–';
    const setup = (s.SETUP_QUALITY || 'Stage-2 Leader').toString().replace(/_/g, ' ');
    const isTrap = s.IS_TRAP_VETO || s.INSTITUTIONAL_GRADE === 'RETAIL_TRAP';
    const isPrime = s.AQS_GRADE === 'PRIME_ACCUMULATION' || s.INSTITUTIONAL_GRADE === 'PRIME_INSTITUTIONAL';

    card.style.display = 'block';
    card.innerHTML = `
      <div class="card__head" style="margin-bottom:8px;">
        <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
          <h3 style="margin:0;">${s.SYMBOL} · Screener Diagnostic</h3>
          <span class="badge ${isDef ? 'badge--defensive' : 'badge--bull'}">${isDef ? '🛡️ Defensive Watchlist' : '🟢 Active Leader'}</span>
          ${isTrap ? '<span class="tag tag--risk">⚠️ Retail Trap</span>' : isPrime ? '<span class="tag tag--prime">★ Inst Prime</span>' : ''}
          <span class="badge badge--brand">${setup}</span>
        </div>
        <div>
          <span class="num" style="font-size:1.25rem;font-weight:700;">₹${isNaN(cmp) ? s.CMP : cmp.toFixed(2)}</span>
          <span class="muted" style="font-size:0.75rem;margin-left:6px;">(−${prox}% from 52W high)</span>
        </div>
      </div>
      <div class="cred-grid" style="margin-top:8px;">
        <div class="cred-item"><small>CMS Score</small><span style="color:var(--brand);">${cms}</span></div>
        <div class="cred-item ${aqs >= 75 ? 'is-bull' : 'is-caution'}"><small>AQS (Anti-Trap)</small><span>${aqs}/100</span></div>
        <div class="cred-item ${vol >= 1.0 ? 'is-bull' : 'is-bear'}"><small>Vol Surge</small><span>${vol}x</span></div>
        <div class="cred-item"><small>RSI (14)</small><span>${rsi}</span></div>
        <div class="cred-item"><small>Daily ATR%</small><span>${atr}%</span></div>
        <div class="cred-item"><small>20d Turnover</small><span>₹${to} Cr</span></div>
        <div class="cred-item"><small>Circuit Band</small><span>${s.CIRCUIT_BAND || '20'}%</span></div>
        <div class="cred-item"><small>Closing Range (CR)</small><span>${s.CLOSING_RANGE ? (parseFloat(s.CLOSING_RANGE) * 100).toFixed(0) + '%' : '–'}</span></div>
      </div>
      ${s.FTF_TRIGGER ? `<div style="margin-top:10px;padding:8px 12px;border-radius:var(--radius-sm);background:var(--surface-2);border:1px solid var(--border-soft);font-size:0.76rem;">
        <strong style="color:var(--accent);">🎯 Actionable Trigger:</strong> ${s.FTF_TRIGGER}
        ${s.PIVOT_RESISTANCE ? `<span class="muted" style="margin-left:8px;">(Pivot: ₹${s.PIVOT_RESISTANCE} · Floor: ₹${s.DOWNSIDE_FLOOR || '–'})</span>` : ''}
      </div>` : ''}
    `;
  }

  function paintReport(symbol, r, isLive = false) {
    paintScreenerProfile(symbol);
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

  const isValidSym = s => typeof s === 'string' && s.trim().length >= 2 && !/^[—\-_\s]+$/.test(s.trim()) && s.trim().toUpperCase() !== 'NONE';

  async function runLiveBacktest(sym) {
    let symbol = String(sym || '').trim().toUpperCase().replace(/\.NS$/, '');
    if (!isValidSym(symbol)) {
      const topValid = typeof state !== 'undefined' && state.payload?.all_qualified?.find(x => isValidSym(x.SYMBOL))?.SYMBOL;
      symbol = topValid || 'CUPID';
    }
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

    // Render Quick leader chips (from current session if available)
    const chipsWrap = document.querySelector('.research-quick-chips');
    if (chipsWrap && typeof state !== 'undefined' && state.payload?.all_qualified?.length > 0) {
      const isDef = state.payload?.regime?.regime === 'DEFENSIVE_CASH';
      const syms = state.payload.all_qualified.filter(x => isValidSym(x.SYMBOL)).slice(0, 7).map(x => x.SYMBOL);
      chipsWrap.innerHTML = `<span style="font-size:0.75rem;color:var(--text-dim);font-weight:600;text-transform:uppercase;">${isDef ? '🛡️ Defensive Watchlist:' : 'Quick leaders:'}</span>` +
        syms.map(s => `<button class="chip chip--sm chip-leader-suggest" data-sym="${s}">${s}</button>`).join('');
    }
    document.querySelectorAll('.chip-leader-suggest').forEach(chip => {
      chip.onclick = () => { if (chip.dataset.sym) { if (input) input.value = chip.dataset.sym; runLiveBacktest(chip.dataset.sym); } };
    });

    // Auto-load initial stock if grid is empty
    const currentTitle = document.getElementById('researchSymbolTitle');
    if (currentTitle && (!currentTitle.textContent || currentTitle.textContent === 'Statistical Study')) {
      const topSym = (typeof state !== 'undefined' && state.payload?.all_qualified?.find(x => isValidSym(x.SYMBOL))?.SYMBOL);
      const activeSym = typeof state !== 'undefined' && isValidSym(state.activeStock?.SYMBOL) ? state.activeStock.SYMBOL : null;
      const initialSym = activeSym || topSym || 'CUPID';
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
