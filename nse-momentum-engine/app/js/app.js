/* ═══════════════════════════════════════════════════════
   NSE Signal – app.js
   Full application logic for the PWA
═══════════════════════════════════════════════════════ */

'use strict';

/* ─── Constants ─── */
const LS = {
  CAPITAL_BASE:    'nse_capital_base',
  CAPITAL_HISTORY: 'nse_capital_history',
  SIGNAL_HISTORY:  'nse_signal_history',
  LAST_SIGNAL:     'nse_last_signal',
  CURRENT_CAPITAL: 'nse_current_capital',
};

const DEFAULT_CAPITAL = 1000;

/* ─── State ─── */
let state = {
  currentTab:    'Signal',
  signalData:    null,   // parsed CSV rows
  installPrompt: null,
  refreshing:    false,
};

/* ══════════════════════════════════════════════════════
   UTILITIES
══════════════════════════════════════════════════════ */

/** Parse CSV text, handling quoted fields that may contain commas */
function parseCSV(text) {
  const lines = text.trim().split('\n');
  if (lines.length < 2) return [];

  function parseLine(line) {
    const fields = [];
    let current = '';
    let inQuote = false;
    for (let i = 0; i < line.length; i++) {
      const ch = line[i];
      if (ch === '"') {
        if (inQuote && line[i + 1] === '"') { current += '"'; i++; }
        else { inQuote = !inQuote; }
      } else if (ch === ',' && !inQuote) {
        fields.push(current.trim());
        current = '';
      } else {
        current += ch;
      }
    }
    fields.push(current.trim());
    return fields;
  }

  const headers = parseLine(lines[0]);
  return lines.slice(1).filter(l => l.trim()).map(line => {
    const vals = parseLine(line);
    const obj = {};
    headers.forEach((h, i) => { obj[h.trim()] = vals[i] !== undefined ? vals[i] : ''; });
    return obj;
  });
}

/** Format number as plain float string */
function fmt(val) {
  const n = parseFloat(val);
  return isNaN(n) ? '–' : n.toFixed(2);
}

/** Format number as Indian currency ₹X,XX,XXX.XX */
function fmtINR(val) {
  const n = parseFloat(val);
  if (isNaN(n)) return '₹–';
  return '₹' + n.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

/** Format percentage with sign and color class */
function fmtPct(val) {
  const n = parseFloat(val);
  if (isNaN(n)) return { text: '–', cls: '' };
  const sign = n >= 0 ? '+' : '';
  return { text: sign + n.toFixed(2) + '%', cls: n >= 0 ? 'pos' : 'neg' };
}

/** Calculate % change from base */
function pctChange(entry, exit) {
  return ((exit - entry) / entry) * 100;
}

/** localStorage helpers */
const store = {
  get: (key, fallback = null) => {
    try { const v = localStorage.getItem(key); return v !== null ? JSON.parse(v) : fallback; }
    catch { return fallback; }
  },
  set: (key, val) => {
    try { localStorage.setItem(key, JSON.stringify(val)); } catch(e) { console.warn('LS write fail', e); }
  },
  remove: (key) => {
    try { localStorage.removeItem(key); } catch(_) {}
  }
};

/* ══════════════════════════════════════════════════════
   TOAST SYSTEM
══════════════════════════════════════════════════════ */

function showToast(message, type = 'info', icon = null) {
  const container = document.getElementById('toastContainer');
  const icons = { success: '✅', error: '❌', info: 'ℹ️' };
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.innerHTML = `<span>${icon || icons[type]}</span><span>${message}</span>`;
  container.appendChild(toast);
  setTimeout(() => toast.remove(), 3100);
}

/* ══════════════════════════════════════════════════════
   SERVICE WORKER REGISTRATION
══════════════════════════════════════════════════════ */

if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('./sw.js')
      .then(reg => {
        reg.update();
        console.log('[SW] Registered & Checked for updates:', reg.scope);
        updateOfflineBadge(navigator.onLine);
      })
      .catch(err => console.warn('[SW] Registration failed:', err));
  });
}

window.addEventListener('online',  () => updateOfflineBadge(true));
window.addEventListener('offline', () => updateOfflineBadge(false));

function updateOfflineBadge(online) {
  const badge = document.getElementById('offlineBadge');
  const text  = document.getElementById('offlineText');
  if (online) {
    badge.classList.remove('offline');
    text.textContent = 'Online';
  } else {
    badge.classList.add('offline');
    text.textContent = 'Offline';
  }
}

/* ══════════════════════════════════════════════════════
   INSTALL PROMPT
══════════════════════════════════════════════════════ */

window.addEventListener('beforeinstallprompt', e => {
  e.preventDefault();
  state.installPrompt = e;
  const btn = document.getElementById('btnInstall');
  if (btn) { btn.disabled = false; }
});

document.getElementById('btnInstall').addEventListener('click', async () => {
  if (!state.installPrompt) {
    showToast('Open in Chrome and use ⋮ → "Add to Home Screen"', 'info', '📱');
    return;
  }
  state.installPrompt.prompt();
  const { outcome } = await state.installPrompt.userChoice;
  if (outcome === 'accepted') {
    showToast('NSE Signal installed! 🎉', 'success');
    state.installPrompt = null;
    document.getElementById('btnInstall').disabled = true;
  }
});

/* ══════════════════════════════════════════════════════
   BOTTOM NAV / TAB SWITCHING
══════════════════════════════════════════════════════ */

document.querySelectorAll('.nav-item, .desktop-tab-btn').forEach(item => {
  item.addEventListener('click', () => switchTab(item.dataset.tab));
});

function switchTab(name) {
  if (!name) return;
  state.currentTab = name;
  try { sessionStorage.setItem('nse_active_tab', name); } catch (_) {}
  document.querySelectorAll('.nav-item, .desktop-tab-btn').forEach(n => {
    const on = n.dataset.tab === name;
    n.classList.toggle('active', on);
    if (n.hasAttribute('role')) n.setAttribute('aria-selected', on ? 'true' : 'false');
  });
  document.querySelectorAll('.tab-panel').forEach(p => {
    p.classList.toggle('active', p.id === 'tab' + name);
  });
  closeInspector();
  window.scrollTo({ top: 0, behavior: 'smooth' });
  if (name === 'Portfolio')   renderPortfolio();
  if (name === 'Compounding') renderCompounding();
  if (name === 'History')     renderHistory();
  if (name === 'Settings')    populateSettings();
}

/* ══════════════════════════════════════════════════════
   DATA FETCHING
══════════════════════════════════════════════════════ */

async function fetchSignal(showLoading = true) {
  if (state.refreshing) return;
  if (showLoading) { setRefreshing(true); showSkeleton(true); }

  try {
    let rows = null;
    let payload = null;

    // Direct Native High-Speed Static API (GitHub Pages CDN / local)
    const res = await fetch('data/signal.json?_t=' + Date.now(), { cache: 'no-store' });
    if (res.ok) {
      payload = await res.json();
      rows = payload.rows || [];
    } else {
      const csvRes = await fetch('data/signal.csv?_t=' + Date.now(), { cache: 'no-store' });
      if (csvRes.ok) {
        const text = await csvRes.text();
        rows = parseCSV(text);
      }
    }

    if (!rows || !rows.length) throw new Error('No signal data available');

    state.signalData = rows;
    state.payload = payload;
    store.set(LS.LAST_SIGNAL, { rows, payload, fetchedAt: new Date().toISOString() });

    renderMarketRegime(payload ? payload.regime : null);
    if (state.userCapital && state.userCapital !== DEFAULT_CAPITAL && payload && payload.all_qualified) {
      onCapitalChange(state.userCapital);
    } else {
      renderSignal(rows, payload ? payload.reason : null);
      if (payload && payload.all_qualified) {
        renderAllStocksTable(payload.all_qualified, state.userCapital || DEFAULT_CAPITAL);
      }
    }
    if (payload) {
      if (payload.history_manifest && payload.history_manifest.length) {
        state.historyManifest = payload.history_manifest;
      }
      renderSessionSwitcher(state.historyManifest, payload.trade_date);
    }
    updateLastUpdated(new Date());
    if (showLoading) showToast('Signal refreshed', 'success', '📡');
  } catch (err) {
    console.warn('[Fetch error, checking cache]', err);
    const cached = store.get(LS.LAST_SIGNAL, null);
    if (cached && cached.rows) {
      state.signalData = cached.rows;
      state.payload = cached.payload;
      renderMarketRegime(cached.payload ? cached.payload.regime : null);
      if (state.userCapital && state.userCapital !== DEFAULT_CAPITAL && cached.payload && cached.payload.all_qualified) {
        onCapitalChange(state.userCapital);
      } else {
        renderSignal(cached.rows, cached.payload ? cached.payload.reason : null);
        if (cached.payload && cached.payload.all_qualified) {
          renderAllStocksTable(cached.payload.all_qualified, state.userCapital || DEFAULT_CAPITAL);
        }
      }
      if (cached.payload) {
        if (cached.payload.history_manifest && cached.payload.history_manifest.length) {
          state.historyManifest = cached.payload.history_manifest;
        }
        renderSessionSwitcher(state.historyManifest, cached.payload.trade_date);
      }
      updateLastUpdated(new Date(cached.fetchedAt), true);
      showToast('Showing cached data (offline)', 'info', '📦');
    } else {
      showSkeleton(false);
      renderCashState(null, 'Preserve Capital (Defensive Mode)');
      showToast('Fetch error: ' + err.message, 'error');
    }
  } finally {
    setRefreshing(false);
  }
}

function setRefreshing(val) {
  state.refreshing = val;
  const btn = document.getElementById('btnRefresh');
  btn.classList.toggle('spinning', val);
}

function showSkeleton(show) {
  document.getElementById('signalSkeleton').style.display = show ? 'block' : 'none';
  document.getElementById('signalContent').style.display  = show ? 'none'  : 'block';
}

function updateLastUpdated(date, fromCache = false) {
  const bar = document.getElementById('lastUpdatedBar');
  const txt = document.getElementById('lastUpdatedText');
  bar.style.display = 'flex';
  const timeStr = date.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  const dateStr = date.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' });
  txt.textContent = `${dateStr}, ${timeStr}${fromCache ? ' (cached)' : ''}`;
}

function renderMarketRegime(regime) {
  const bar = document.getElementById('regimeBanner');
  const ticker = document.getElementById('headerRegimeTicker');
  const tickerText = document.getElementById('headerRegimeText');
  const badge = document.getElementById('regimeBadge');
  const title = document.getElementById('regimeTitle');
  const desc = document.getElementById('regimeDesc');
  const decision = document.getElementById('regimeDecision');
  const bench = document.getElementById('regimeBench');

  if (!regime) {
    if (bar) bar.className = 'regime-bar';
    if (badge) { badge.className = 'badge'; badge.textContent = '—'; }
    if (title) title.textContent = 'Market regime unavailable';
    if (desc) desc.textContent = 'No screening run found for this session.';
    if (decision) decision.textContent = '—';
    if (bench) bench.textContent = '';
    if (ticker) ticker.classList.remove('is-active');
    return;
  }

  const cmpStr = regime.nifty_cmp ? fmtINR(regime.nifty_cmp) : '–';
  const isBull = regime.regime === 'BULL_MARKET';
  const isCaution = regime.regime === 'CORRECTION_WATCH';
  const stateWord = isBull ? 'bull' : isCaution ? 'caution' : 'defensive';

  if (bar) bar.className = 'regime-bar ' + stateWord;
  if (badge) {
    badge.className = 'badge badge--' + (isBull ? 'bull' : isCaution ? 'caution' : 'defensive');
    badge.textContent = isBull ? 'Bull market' : isCaution ? 'Correction watch' : 'Defensive cash';
  }
  if (title) title.textContent = 'Nifty 500  ' + cmpStr;
  if (desc) desc.textContent = regime.description || (isBull
    ? 'Confirmed uptrend — full momentum deployment active.'
    : isCaution ? 'Benchmark below its 50-day average — conservative entries only.'
    : 'Benchmark below its 200-day average — 100% capital preserved in cash.');
  if (decision) decision.textContent = isBull ? 'DEPLOY · momentum active'
    : isCaution ? 'SELECTIVE · conservative entries'
    : 'HOLD · 100% cash';
  if (bench) {
    const parts = [];
    if (regime.sma_50)  parts.push('50SMA ' + fmtINR(regime.sma_50));
    if (regime.sma_200) parts.push('200SMA ' + fmtINR(regime.sma_200));
    bench.textContent = parts.join('  ·  ');
  }

  if (ticker && tickerText) {
    ticker.className = 'header-regime is-active ' + stateWord;
    tickerText.textContent = `NIFTY 500 ${cmpStr} · ${isBull ? 'BULL' : isCaution ? 'CORRECTION' : 'DEFENSIVE'}`;
  }
}

/* ══════════════════════════════════════════════════════
   SIGNAL RENDERING
══════════════════════════════════════════════════════ */

function renderSignal(rows, overrideReason = null) {
  showSkeleton(false);
  const hero  = rows ? rows[0] : null;
  const alts  = rows ? rows.slice(1) : [];
  const total = (state.payload && state.payload.total_qualified !== undefined)
    ? state.payload.total_qualified
    : (hero ? (hero.TOTAL_QUALIFIED || '–') : '–');

  // Qualified banner — keep hidden, just update text for internal reads
  const totalEl = document.getElementById('totalQualified');
  if (totalEl) totalEl.textContent = total;

  const isDefensive = (state.payload && state.payload.regime && state.payload.regime.regime === 'DEFENSIVE_CASH')
    || (!hero || hero.STATUS === 'CASH' || !hero.SYMBOL || hero.SYMBOL === '—');

  if (isDefensive) {
    const all = (state.payload && state.payload.all_qualified) || [];
    if (all.length > 0) {
      const topStock = Object.assign({}, all[0]);
      const userCap = state.userCapital || store.get(LS.CURRENT_CAPITAL, DEFAULT_CAPITAL);
      const cmp = parseFloat(topStock.CMP);
      const shares = Math.max(Math.floor((userCap - 26) / cmp), 1);
      topStock.SHARES = shares;
      topStock.CAPITAL_REQUIRED = shares * cmp;
      topStock.CAPITAL_BASE = userCap;
      renderActiveSignal(topStock, all.slice(1, 4), true);
      return;
    } else {
      renderCashState(hero, overrideReason);
      return;
    }
  }

  renderActiveSignal(hero, alts, false);
}

function renderCashState(hero, overrideMsg = null) {
  const heroCard = document.getElementById('heroCard');
  if (heroCard) {
    heroCard.className = 'card signal-hero cash-hero';
    heroCard.innerHTML = `
      <div class="status-badge cash">🛡️ 100% CASH</div>
      <div class="cash-state">
        <div class="cash-icon">🏦</div>
        <div class="cash-label">${overrideMsg || 'Preserve Capital: Market in Defensive Mode'}</div>
        <div class="cash-sub">${hero && hero.TIMESTAMP ? 'Screened: ' + hero.TIMESTAMP : 'Stay patient. Momentum will come.'}</div>
      </div>
    `;
  }
  const rsiCard = document.getElementById('rsiCard');
  const gttCard = document.getElementById('gttCard');
  const altsCard = document.getElementById('altsCard');
  if (rsiCard) rsiCard.style.display = 'none';
  if (gttCard) gttCard.style.display = 'none';
  if (altsCard) altsCard.style.display = 'none';
  showSkeleton(false);
}

function renderActiveSignal(h, alts, isDefensive = false) {
  const heroCard = document.getElementById('heroCard');
  if (!heroCard) return;

  const cmp = parseFloat(h.CMP);
  const cms = parseFloat(h.CMS_SCORE);
  const high52 = parseFloat(h.HIGH_52W) || cmp;
  const proxPct = Math.max(0, ((high52 - cmp) / high52) * 100);
  const fillRatio = (Math.max(5, 100 - proxPct) / 100).toFixed(3);
  const atr = parseFloat(h.ATR_14) || (cmp * 0.04);
  const atrPct = (atr / cmp) * 100;

  if (isDefensive) {
    heroCard.className = 'card signal-hero defensive';
    heroCard.innerHTML = `
      <div class="hero-top-row">
        <div class="status-badge defensive">🛡️ DEFENSIVE WATCHLIST (CASH MODE)</div>
        <span class="hero-rank-badge">Candidate #1 Setup</span>
      </div>
      <div class="defensive-advisory-banner">
        🛡️ <strong>Preserve Capital:</strong> Nifty 500 is trading below its 200-day moving average. New capital deployment is capped at 0 shares (100% Cash preservation). Inspecting candidate for risk monitoring and GTT simulation.
      </div>
      <div class="hero-main-flex">
        <div>
          <div class="hero-symbol">${h.SYMBOL} ${h.IS_PRIME ? '<span class="badge badge-accent" style="font-size:11px; vertical-align:middle; margin-left:6px;">⭐ PRIME</span>' : ''}</div>
          <div class="hero-cmp">${fmtINR(cmp)}</div>
        </div>
        <div class="hero-52w-wrap">
          <div class="hero-52w-labels">
            <span>52W High</span>
            <strong style="color:var(--accent); font-family:var(--font-mono);">${fmtINR(high52)} (-${proxPct.toFixed(1)}%)</strong>
          </div>
          <div class="hero-52w-bar">
            <div class="hero-52w-fill" style="--fill-pct: ${fillRatio};"></div>
          </div>
        </div>
      </div>
      <div class="hero-meta-strip">
        <span class="meta-chip cms-chip">🏆 CMS ${isNaN(cms) ? h.CMS_SCORE : cms.toFixed(1)}</span>
        <span class="meta-chip"><span style="color:var(--text-dim); font-size:0.65rem;">RSI</span> ${parseFloat(h.RSI_14).toFixed(1)}</span>
        <span class="meta-chip"><span style="color:var(--text-dim); font-size:0.65rem;">ATR</span> ${fmtINR(atr)} (${atrPct.toFixed(1)}%)</span>
        <span class="meta-chip"><span style="color:var(--text-dim); font-size:0.65rem;">Band</span> ${h.CIRCUIT_BAND || '20'}%</span>
      </div>
    `;
  } else {
    heroCard.className = 'card signal-hero glowing';
    heroCard.innerHTML = `
      <div class="hero-top-row">
        <div class="status-badge active">🟢 ACTIVE SIGNAL</div>
        <span class="hero-rank-badge">Leader #1 Setup</span>
      </div>
      <div class="hero-main-flex">
        <div>
          <div class="hero-symbol">${h.SYMBOL} ${h.IS_PRIME ? '<span class="badge badge-accent" style="font-size:11px; vertical-align:middle; margin-left:6px;">⭐ PRIME</span>' : ''}</div>
          <div class="hero-cmp">${fmtINR(cmp)}</div>
        </div>
        <div class="hero-52w-wrap">
          <div class="hero-52w-labels">
            <span>52W High</span>
            <strong style="color:var(--accent); font-family:var(--font-mono);">${fmtINR(high52)} (-${proxPct.toFixed(1)}%)</strong>
          </div>
          <div class="hero-52w-bar">
            <div class="hero-52w-fill" style="--fill-pct: ${fillRatio};"></div>
          </div>
        </div>
      </div>
      <div class="hero-meta-strip">
        <span class="meta-chip cms-chip">🏆 CMS ${isNaN(cms) ? h.CMS_SCORE : cms.toFixed(1)}</span>
        <span class="meta-chip"><span style="color:var(--text-dim); font-size:0.65rem;">RSI</span> ${parseFloat(h.RSI_14).toFixed(1)}</span>
        <span class="meta-chip"><span style="color:var(--text-dim); font-size:0.65rem;">ATR</span> ${fmtINR(atr)} (${atrPct.toFixed(1)}%)</span>
        <span class="meta-chip"><span style="color:var(--text-dim); font-size:0.65rem;">Band</span> ${h.CIRCUIT_BAND || '20'}%</span>
      </div>
    `;
  }

  // RSI Gauge & Linear Meter
  const rsiVal = parseFloat(h.RSI_14);
  renderRSIGauge(rsiVal);
  const rsiCard = document.getElementById('rsiCard');
  if (rsiCard) rsiCard.style.display = 'block';

  // ROC Row
  const rocRow = document.getElementById('rocRow');
  if (rocRow) {
    const roc1 = fmtPct(h.ROC_1M);
    const roc2 = fmtPct(h.ROC_2M);
    const roc3 = fmtPct(h.ROC_3M);
    rocRow.innerHTML = `
      <div class="roc-item">
        <div class="roc-period">1 Month</div>
        <div class="roc-val ${roc1.cls}">${roc1.text}</div>
      </div>
      <div class="roc-item">
        <div class="roc-period">2 Month</div>
        <div class="roc-val ${roc2.cls}">${roc2.text}</div>
      </div>
      <div class="roc-item">
        <div class="roc-period">3 Month</div>
        <div class="roc-val ${roc3.cls}">${roc3.text}</div>
      </div>
    `;
  }

  // SMA Row
  const smaRow = document.getElementById('smaRow');
  if (smaRow) {
    const sma50  = parseFloat(h.SMA_50);
    const sma200 = parseFloat(h.SMA_200);
    const aboveSma50  = cmp > sma50;
    const aboveSma200 = cmp > sma200;
    const dist50  = ((cmp - sma50) / sma50) * 100;
    const dist200 = ((cmp - sma200) / sma200) * 100;
    smaRow.innerHTML = `
      <div class="sma-item">
        <div class="sma-label">SMA 50</div>
        <div class="sma-val" style="color:${aboveSma50 ? 'var(--accent)' : 'var(--red)'}">
          ${fmtINR(sma50)} <span style="font-size:10px;">(${dist50 >= 0 ? '+' : ''}${dist50.toFixed(1)}%)</span>
        </div>
      </div>
      <div class="sma-item">
        <div class="sma-label">SMA 200</div>
        <div class="sma-val" style="color:${aboveSma200 ? 'var(--accent)' : 'var(--red)'}">
          ${fmtINR(sma200)} <span style="font-size:10px;">(${dist200 >= 0 ? '+' : ''}${dist200.toFixed(1)}%)</span>
        </div>
      </div>
    `;
  }

  // Liquidity Specs
  const specTurnover = document.getElementById('specTurnover');
  const specATR = document.getElementById('specATR');
  const specCircuit = document.getElementById('specCircuit');
  if (specTurnover) {
    const toCr = parseFloat(h.TURNOVER_CRORES);
    specTurnover.textContent = !isNaN(toCr) ? `₹${toCr.toFixed(1)} Cr` : '₹5.0+ Cr (Liquid)';
  }
  if (specATR) {
    specATR.textContent = `${fmtINR(atr)} (${atrPct.toFixed(1)}%)`;
  }
  if (specCircuit) {
    specCircuit.textContent = `${h.CIRCUIT_BAND || '20'}% Band`;
  }

  // GTT Table
  renderGTT(h);
}

function renderRSIGauge(rsi) {
  const needle = document.getElementById('rsiNeedle');
  const label  = document.getElementById('rsiValueLabel');
  const marker = document.getElementById('rsiMarker');
  if (isNaN(rsi)) return;

  if (needle) {
    const angle = ((Math.min(Math.max(rsi, 0), 100) / 100) * 180) - 90;
    needle.setAttribute('transform', `rotate(${angle}, 80, 80)`);
  }

  let color = 'var(--accent)';
  if (rsi < 45) {
    color = 'var(--red)';
  } else if (rsi > 82) {
    color = 'var(--yellow)';
  }

  if (label) {
    label.textContent = rsi.toFixed(1);
    label.style.color = color;
  }

  if (marker) {
    const pct = Math.min(Math.max(rsi, 0), 100);
    marker.style.setProperty('--rsi-pos', `${pct}%`);
  }
}

function renderGTT(h) {
  state.activeStock = h;
  const gttCard = document.getElementById('gttCard');
  const entryInput = document.getElementById('inputActualEntry');
  const currentEntry = parseFloat(h.ACTUAL_ENTRY || h.CMP);

  if (entryInput) {
    entryInput.value = currentEntry.toFixed(2);
  }
  updateGapPillActive(0);
  recalculateFromEntry(currentEntry);
  gttCard.style.display = 'block';
}

function recalculateFromEntry(entry) {
  const s = state.activeStock;
  if (!s) return;
  const cmp = parseFloat(s.CMP);
  const atr = parseFloat(s.ATR_14) || (cmp * 0.03);
  const capital = state.userCapital || store.get(LS.CURRENT_CAPITAL, DEFAULT_CAPITAL);

  const isDefensive = (state.payload && state.payload.regime && state.payload.regime.regime === 'DEFENSIVE_CASH')
    || (s.STATUS === 'CASH');

  // 1. Calculate gap pct
  const gapPct = ((entry - cmp) / cmp) * 100;
  const gapBadge = document.getElementById('gapBadge');
  const adviceBox = document.getElementById('gapAdviceBox');
  const basisBadge = document.getElementById('gttEntryBasisBadge');

  if (gapBadge) {
    const sign = gapPct >= 0 ? '+' : '';
    gapBadge.textContent = `${sign}${gapPct.toFixed(1)}% Gap`;
    if (gapPct <= 3.0) {
      gapBadge.style.background = 'rgba(16,185,129,0.15)';
      gapBadge.style.color = 'var(--accent)';
    } else if (gapPct <= 5.0) {
      gapBadge.style.background = 'rgba(245,158,11,0.15)';
      gapBadge.style.color = 'var(--yellow)';
    } else {
      gapBadge.style.background = 'rgba(239,68,68,0.15)';
      gapBadge.style.color = 'var(--red)';
    }
  }

  if (adviceBox) {
    if (gapPct <= 3.0) {
      adviceBox.innerHTML = `🟢 <strong>Ideal Entry (0–3% Gap):</strong> Optimal institutional risk-reward. Stop Loss calibrated from ₹${entry.toFixed(2)}.`;
      adviceBox.style.color = 'var(--accent)';
    } else if (gapPct <= 5.0) {
      adviceBox.innerHTML = `🟡 <strong>Extended Gap (+3% to +5%):</strong> Chasing increases pullback risk. Consider scaling in with 50% shares.`;
      adviceBox.style.color = 'var(--yellow)';
    } else {
      adviceBox.innerHTML = `🔴 <strong>Over-Extended Gap (>+5% / Circuit):</strong> DO NOT CHASE! High risk of intraday reversal. Switch to <strong>Alternate #1</strong>.`;
      adviceBox.style.color = 'var(--red)';
    }
  }

  if (basisBadge) {
    basisBadge.textContent = `Entry: ${fmtINR(entry)}`;
  }

  // 2. Recalculate GTT levels based on entry & ATR & Regime
  const atrStopPct = isDefensive ? 0.04 : Math.min(0.07, Math.max(0.05, (2.0 * atr) / entry));
  const initStop = Math.round((entry * (1.0 - atrStopPct)) * 100) / 100;
  const m1Target = Math.round((entry * 1.15) * 100) / 100;
  const m1Stop   = Math.round((entry * 1.015) * 100) / 100; // +1.5% Breakeven floor
  const m2Target = Math.round((entry * 1.22) * 100) / 100; // Bank 40% partial profit (≥3R)
  const m2Stop   = Math.round((entry * 1.10) * 100) / 100; // +10% Profit lock floor on 60% runner
  const m3Target = Math.round((entry * 1.50) * 100) / 100; // Reference display for +50%

  const levels = [
    { cls: 'stop-row', name: 'Initial Stop', nameClass: 'level-stop', target: initStop, stop: null, chg: pctChange(entry, initStop), note: `${isDefensive ? '-4.0% Defensive Stop' : `-${(atrStopPct*100).toFixed(1)}% ATR Stop`}` },
    { cls: 'm1-row', name: 'Rotate (+15%)', nameClass: 'level-m1', target: m1Target, stop: m1Stop, chg: pctChange(entry, m1Target), note: 'Sell the full position & reinvest principal + profit into the next leader' },
    { cls: 'm2-row', name: 'Trail 1 (+22%)', nameClass: 'level-m2', target: m2Target, stop: m2Stop, chg: pctChange(entry, m2Target), note: 'Optional trailing (if you do not rotate): bank 40% at ≥3R, ratchet runner stop to +10%' },
    { cls: 'm3-row', name: 'Trail 2 (+50%+)', nameClass: 'level-m3', target: m3Target, stop: m2Stop, chg: pctChange(entry, m3Target), note: 'Optional trailing: hold the 60% runner on the 50 SMA / 20 EMA trail (no ceiling)' },
  ];

  const body = document.getElementById('gttBody');
  if (body) {
    body.innerHTML = levels.map(lv => {
      const pct = fmtPct(lv.chg);
      return `
        <tr class="${lv.cls}" title="${lv.note}">
          <td><span class="level-name ${lv.nameClass}">${lv.name}</span></td>
          <td>${fmtINR(lv.target)}</td>
          <td>${lv.stop ? fmtINR(lv.stop) : '–'}</td>
          <td><span class="${pct.cls}">${pct.text}</span></td>
        </tr>
      `;
    }).join('');
  }

  // 3. Recalculate Shares & Capital based on entry & 1% portfolio risk model
  const riskAmount = capital * 0.01;
  const riskPerShare = Math.max(entry - initStop, 0.01);
  const riskModelShares = Math.max(Math.floor(riskAmount / riskPerShare), 1);
  const affordableShares = Math.max(Math.floor((capital - 26) / entry), 1);
  const recommendedShares = Math.min(riskModelShares, affordableShares);
  const capRequired = recommendedShares * entry;

  const pills = document.getElementById('tradePills');
  if (pills) {
    if (isDefensive) {
      pills.innerHTML = `
        <div class="trade-pill">
          <div class="pill-label">🛒 Recommended Shares</div>
          <div class="pill-value" style="color:var(--yellow)">0 (Cash Mode)</div>
        </div>
        <div class="trade-pill">
          <div class="pill-label">🧪 Sim. 1% Risk Size</div>
          <div class="pill-value">${recommendedShares} shares (${fmtINR(capRequired)})</div>
        </div>
        <div class="trade-pill">
          <div class="pill-label">💰 Sizing Capital</div>
          <div class="pill-value">${fmtINR(capital)}</div>
        </div>
        <div class="trade-pill">
          <div class="pill-label">🔁 Next cycle (+15%)</div>
          <div class="pill-value">${fmtINR(capRequired * 1.15)}</div>
        </div>
      `;
    } else {
      pills.innerHTML = `
        <div class="trade-pill">
          <div class="pill-label">🛒 1% Risk Sizing</div>
          <div class="pill-value">${recommendedShares} ${recommendedShares === 1 ? 'Share' : 'Shares'}</div>
        </div>
        <div class="trade-pill">
          <div class="pill-label">💰 Capital Outlay</div>
          <div class="pill-value">${fmtINR(capRequired)}</div>
        </div>
        <div class="trade-pill">
          <div class="pill-label">🏦 Account Base</div>
          <div class="pill-value">${fmtINR(capital)}</div>
        </div>
        <div class="trade-pill">
          <div class="pill-label">🔁 Next cycle (+15%)</div>
          <div class="pill-value pos">${fmtINR(capRequired * 1.15)}</div>
        </div>
      `;
    }
  }

  // 4. Update Zerodha Guide Cheat-sheet & wire broker actions
  const guideStop = document.getElementById('guideStopLoss');
  const guideTarget = document.getElementById('guideTarget');
  if (guideStop) guideStop.textContent = `${fmtINR(initStop)} (-${(atrStopPct*100).toFixed(1)}%)`;
  if (guideTarget) guideTarget.textContent = `${fmtINR(m1Target)} (+15.00%)`;

  s.ACTUAL_ENTRY = entry;
  s.CALC_SHARES = isDefensive ? 0 : recommendedShares;
  s.CALC_STOP = initStop;
  s.CALC_M1 = m1Target;

  wireZerodhaButtons(s);
}

function renderAlternates(alts) {
  const altsCard = document.getElementById('altsCard');
  if (altsCard) altsCard.style.display = 'none';
}

/* ══════════════════════════════════════════════════════
   PORTFOLIO TAB (TRADES & POSITIONS)
══════════════════════════════════════════════════════ */

function renderPortfolio() {
  renderLiveTracker();
}

/* ══════════════════════════════════════════════════════
   EXIT MODAL
══════════════════════════════════════════════════════ */

document.getElementById('btnRecordExit').addEventListener('click', openExitModal);
document.getElementById('btnCancelExit').addEventListener('click', closeExitModal);
document.getElementById('exitModal').addEventListener('click', e => {
  if (e.target === document.getElementById('exitModal')) closeExitModal();
});

// Pre-fill symbol from current signal or custom trade
function openExitModal(customTrade) {
  const modal = document.getElementById('exitModal');
  modal.classList.add('open');
  document.body.classList.add('modal-open');
  if (customTrade && customTrade.symbol) {
    document.getElementById('exitSymbol').value = customTrade.symbol || '';
    document.getElementById('exitEntry').value  = customTrade.entry || '';
    if (customTrade.exit) document.getElementById('exitPrice').value = customTrade.exit || '';
    if (customTrade.shares) document.getElementById('exitShares').value = customTrade.shares || '';
  } else if (state.signalData && state.signalData[0] && state.signalData[0].STATUS === 'ACTIVE_SIGNAL') {
    const h = state.signalData[0];
    document.getElementById('exitSymbol').value = h.SYMBOL || '';
    document.getElementById('exitEntry').value  = h.CMP || '';
    document.getElementById('exitShares').value = h.SHARES || '';
  }
  updateExitPreview();
}

function closeExitModal() {
  document.getElementById('exitModal').classList.remove('open');
  document.getElementById('exitCalcPreview').style.display = 'none';
  document.body.classList.remove('modal-open');
}

['exitEntry', 'exitPrice', 'exitShares'].forEach(id => {
  document.getElementById(id).addEventListener('input', updateExitPreview);
});

function updateExitPreview() {
  const entry  = parseFloat(document.getElementById('exitEntry').value);
  const exit   = parseFloat(document.getElementById('exitPrice').value);
  const shares = parseInt(document.getElementById('exitShares').value);
  const preview = document.getElementById('exitCalcPreview');
  if (!entry || !exit || !shares) { preview.style.display = 'none'; return; }

  const pnlPerShare = exit - entry;
  const totalPnl    = pnlPerShare * shares;
  const pct         = pctChange(entry, exit);
  const base        = store.get(LS.CAPITAL_BASE, DEFAULT_CAPITAL);
  const current     = store.get(LS.CURRENT_CAPITAL, base);
  const newCapital  = current + totalPnl;

  const pos = totalPnl >= 0;
  preview.style.display = 'block';
  preview.innerHTML = `
    <div style="display:flex;justify-content:space-between;"><span style="color:var(--text-muted)">Entry</span><span>${fmtINR(entry)}</span></div>
    <div style="display:flex;justify-content:space-between;"><span style="color:var(--text-muted)">Exit</span><span>${fmtINR(exit)}</span></div>
    <div style="display:flex;justify-content:space-between;"><span style="color:var(--text-muted)">Shares</span><span>${shares}</span></div>
    <div class="divider" style="margin:6px 0;"></div>
    <div style="display:flex;justify-content:space-between;"><span style="color:var(--text-muted)">P&L</span>
      <strong style="color:${pos ? 'var(--accent)' : 'var(--red)'}">${pos ? '+' : ''}${fmtINR(totalPnl)} (${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%)</strong></div>
    <div style="display:flex;justify-content:space-between;"><span style="color:var(--text-muted)">New Capital</span>
      <strong style="color:var(--accent)">${fmtINR(newCapital)}</strong></div>
  `;
}

document.getElementById('btnConfirmExit').addEventListener('click', () => {
  const symbol  = document.getElementById('exitSymbol').value.trim().toUpperCase() || 'UNKNOWN';
  const entry   = parseFloat(document.getElementById('exitEntry').value);
  const exit    = parseFloat(document.getElementById('exitPrice').value);
  const shares  = parseInt(document.getElementById('exitShares').value);

  if (!entry || !exit || !shares) {
    showToast('Please fill all fields', 'error'); return;
  }

  const pnl     = (exit - entry) * shares;
  const pct     = pctChange(entry, exit);
  const base    = store.get(LS.CAPITAL_BASE, DEFAULT_CAPITAL);
  const current = store.get(LS.CURRENT_CAPITAL, base);
  const newCap  = Math.max(current + pnl, 0);

  // Update capital
  store.set(LS.CURRENT_CAPITAL, newCap);

  // Capital history
  const capHist = store.get(LS.CAPITAL_HISTORY, []);
  capHist.push({ date: new Date().toISOString(), capital: newCap });
  store.set(LS.CAPITAL_HISTORY, capHist);

  // Signal history
  const sigHist = store.get(LS.SIGNAL_HISTORY, []);
  sigHist.unshift({
    id: Date.now(),
    date: new Date().toISOString(),
    symbol, entry, exit, shares, pnl, pct,
    outcome: pnl > 0 ? 'win' : pnl < 0 ? 'loss' : 'breakeven'
  });
  store.set(LS.SIGNAL_HISTORY, sigHist);

  closeExitModal();
  showToast(`Trade recorded! ${pnl >= 0 ? '🎉' : '💪'} ${pnl >= 0 ? '+' : ''}${fmtINR(pnl)}`, pnl >= 0 ? 'success' : 'info');
  renderPortfolio();
  renderCompounding();
});

document.getElementById('btnResetCapital').addEventListener('click', () => {
  const base = store.get(LS.CAPITAL_BASE, DEFAULT_CAPITAL);
  store.set(LS.CURRENT_CAPITAL, base);
  store.set(LS.CAPITAL_HISTORY, []);
  renderPortfolio();
  renderCompounding();
  showToast('Capital reset to base', 'info', '🔄');
});

/* ══════════════════════════════════════════════════════
   HISTORY TAB
══════════════════════════════════════════════════════ */

function renderHistory() {
  const list    = document.getElementById('historyList');
  const history = store.get(LS.SIGNAL_HISTORY, []);

  if (list) {
    if (!history.length) {
      list.innerHTML = `
        <div class="empty-state">
          <div class="empty-icon">📋</div>
          <p>No trade exits recorded yet.<br>Record closed positions via the Portfolio tab to build your verified trade log.</p>
        </div>`;
    } else {
      list.innerHTML = history.map(t => {
        const outcomeIcon = t.outcome === 'win' ? '🟢' : t.outcome === 'loss' ? '🔴' : '⚪';
        const outcomeClass = t.outcome === 'win' ? 'win' : t.outcome === 'loss' ? 'loss' : 'skip';
        const d = new Date(t.date);
        const dateStr = d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });
        const pnlStr  = `${t.pnl >= 0 ? '+' : ''}${fmtINR(t.pnl)}`;
        const pctStr  = `(${t.pct >= 0 ? '+' : ''}${t.pct.toFixed(2)}%)`;
        return `
          <div class="history-item">
            <div class="hist-icon ${outcomeClass}">${outcomeIcon}</div>
            <div class="hist-body">
              <div class="hist-symbol">${t.symbol}</div>
              <div class="hist-date">${dateStr} · ${t.shares} shares · Entry ${fmtINR(t.entry)}</div>
            </div>
            <div>
              <div class="hist-pnl ${t.pnl >= 0 ? 'pos' : 'neg'}">${pnlStr}</div>
              <div style="font-size:0.68rem; color:var(--text-dim); text-align:right;">${pctStr}</div>
            </div>
          </div>
        `;
      }).join('');
    }
  }

  // Populate Daily Bhavcopy Sessions List
  const sessionsContainer = document.getElementById('historySessionsList');
  if (sessionsContainer) {
    const manifest = (state.payload && state.payload.history_manifest) || [
      { date: '2026-09-30', display_date: '30 Sep 2026', is_today: true },
      { date: '2026-09-29', display_date: '29 Sep 2026', is_today: false }
    ];
    sessionsContainer.innerHTML = manifest.map(m => {
      const isSelected = m.date === (state.selectedDate || '2026-09-30');
      return `
        <div class="session-archive-item ${isSelected ? 'selected' : ''}" onclick="selectSessionDate('${m.date}'); switchTab('Signal');">
          <div class="session-archive-main">
            <div class="session-archive-date">${m.is_today ? '🟢' : '📅'} ${m.display_date || m.date}</div>
            <div class="session-archive-meta">NSE EOD Confirmed Bhavcopy Snapshot</div>
          </div>
          <button class="btn-action inspect" style="font-size:0.75rem; padding:4px 10px;">
            ${isSelected ? 'Active Setup' : 'Load in Terminal 🎯'}
          </button>
        </div>
      `;
    }).join('');
  }
}

/* ══════════════════════════════════════════════════════
   SETTINGS TAB
══════════════════════════════════════════════════════ */

function populateSettings() {
  const capInput = document.getElementById('inputCapitalBase');
  if (capInput) capInput.value = store.get(LS.CAPITAL_BASE, DEFAULT_CAPITAL);
}

document.getElementById('btnSaveSettings').addEventListener('click', () => {
  const capInput = document.getElementById('inputCapitalBase');
  const base = capInput ? parseFloat(capInput.value) : DEFAULT_CAPITAL;

  if (!base || base < 0) { showToast('Please enter a valid capital base', 'error'); return; }

  store.set(LS.CAPITAL_BASE, base);

  // If current capital not set yet, seed it with base
  if (!store.get(LS.CURRENT_CAPITAL, null)) {
    store.set(LS.CURRENT_CAPITAL, base);
  }

  showToast('Settings saved ✅', 'success');
  fetchSignal();
  switchTab('Signal');
});

document.getElementById('btnClearHistory').addEventListener('click', () => {
  if (confirm('Clear all signal history? This cannot be undone.')) {
    store.set(LS.SIGNAL_HISTORY, []);
    showToast('Signal history cleared', 'info', '🗑️');
  }
});

document.getElementById('btnClearCapital').addEventListener('click', () => {
  if (confirm('Clear all capital history entries?')) {
    store.set(LS.CAPITAL_HISTORY, []);
    store.set(LS.CURRENT_CAPITAL, store.get(LS.CAPITAL_BASE, DEFAULT_CAPITAL));
    showToast('Capital history cleared', 'info', '📉');
    renderPortfolio();
    renderCompounding();
  }
});

/* ══════════════════════════════════════════════════════
   VISIBILITY-BASED AUTO-REFRESH
══════════════════════════════════════════════════════ */

document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible' && state.currentTab === 'Signal') {
    fetchSignal(false);
  }
});

/* ══════════════════════════════════════════════════════
   REFRESH BUTTON
══════════════════════════════════════════════════════ */

document.getElementById('btnRefresh').addEventListener('click', () => {
  if (state.currentTab === 'Signal') {
    fetchSignal(true);
  } else {
    // Navigate to signal and refresh
    switchTab('Signal');
    setTimeout(() => fetchSignal(true), 100);
  }
});

/* ══════════════════════════════════════════════════════
   RESIZE → REDRAW CHART
══════════════════════════════════════════════════════ */

let resizeTimer;
window.addEventListener('resize', () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => {
    if (state.currentTab === 'Compounding') renderCompounding();
  }, 200);
});

/* ══════════════════════════════════════════════════════
   ZERODHA KITE INTEGRATION
   - "Open in Kite" → opens kite.zerodha.com with stock pre-searched
   - "Copy GTT Details" → clipboard-ready formatted text
   - "Auto-Place GTT" → calls Kite Connect API (free Personal tier)
══════════════════════════════════════════════════════ */

const KITE = {
  API_URL:  'https://api.kite.trade',
  WEB_URL:  'https://kite.zerodha.com',
  LS_KEY:   'nse_kite_api_key',
  LS_TOKEN: 'nse_kite_access_token',
};

function kiteApiKey()     { return store.get(KITE.LS_KEY,   ''); }
function kiteToken()      { return store.get(KITE.LS_TOKEN, ''); }
function kiteConfigured() { return kiteApiKey() && kiteToken(); }

/** Build Kite auth header */
function kiteHeaders() {
  return {
    'X-Kite-Version': '3',
    'Authorization': `token ${kiteApiKey()}:${kiteToken()}`,
    'Content-Type':  'application/x-www-form-urlencoded',
  };
}

/** Open Kite web with the stock pre-searched and GTT copied */
function openInKite(symbol) {
  const stock = state.activeStock || { SYMBOL: symbol };
  const text = buildGTTClipboardText(stock);
  try {
    navigator.clipboard.writeText(text);
    showToast(`📋 Copied GTT for ${symbol}! Opening Kite…`, 'info', '⚡');
  } catch (_) {}
  window.open('https://kite.zerodha.com/', '_blank', 'noopener');
}

/** Format GTT details as copy-paste text */
function buildGTTClipboardText(sig) {
  const entry = sig.ACTUAL_ENTRY || sig.CMP;
  const shares = sig.CALC_SHARES || sig.SHARES;
  const stop = sig.CALC_STOP || sig.INITIAL_STOP;
  const m1 = sig.CALC_M1 || sig.M1_TARGET;
  const cap = shares * entry;

  return [
    `═══ NSE Signal — GTT Order (Rotation plan) ═══`,
    `Stock   : ${sig.SYMBOL} (NSE)`,
    `Entry   : ₹${fmt(entry)}`,
    `Shares  : ${shares} shares`,
    `Capital : ₹${fmt(cap)}`,
    ``,
    `── GTT Leg 1: SELL at TARGET (+15%) ─────`,
    `Trigger : ₹${fmt(m1)}   → sells the FULL ${shares} shares`,
    `When this fills, redeploy principal + profit into the next leader.`,
    ``,
    `── GTT Leg 2: SELL at STOP ──────────────`,
    `Trigger : ₹${fmt(stop)} (hard stop, -5% to -7% ATR)`,
    `Do NOT move this down.`,
    ``,
    `── Optional (only if you choose NOT to rotate) ──`,
    `Trail 1 (+22%): ₹${fmt(sig.M2_TARGET || (entry * 1.22))} → bank 40%, runner stop ₹${fmt(sig.M2_STOP || (entry * 1.10))}`,
    `Trail 2 (+50%+): hold the runner on a 50 SMA / 20 EMA trail (no ceiling)`,
    ``,
    `Set both GTT legs as SELL · OCO where supported.`,
    `CMS Score: ${sig.CMS_SCORE}  |  RSI: ${sig.RSI_14}`,
    `Generated: ${new Date().toLocaleString('en-IN')}`,
  ].join('\n');
}

/** Place GTT order via Kite Connect API (Personal tier — free) */
async function autoPlaceGTT(sig) {
  if (!kiteConfigured()) {
    showToast('⚠️ Set Kite API Key + Token in Settings first', 'warn');
    return;
  }

  const symbol   = sig.SYMBOL;
  const qty      = parseInt(sig.SHARES);
  const ltp      = parseFloat(sig.CMP);
  const stopTrig = parseFloat(sig.INITIAL_STOP);
  const m1Trig   = parseFloat(sig.M1_TARGET);

  // Kite GTT — OCO (One Cancels Other): stop-loss + target together
  // Kite Connect API: POST /gtt/triggers
  const body = new URLSearchParams({
    type:          'two-leg',                        // OCO
    tradingsymbol: symbol,
    exchange:      'NSE',
    last_price:    ltp.toFixed(2),
    trigger_values: JSON.stringify([stopTrig.toFixed(2), m1Trig.toFixed(2)]),
    orders: JSON.stringify([
      {
        tradingsymbol:    symbol,
        exchange:         'NSE',
        transaction_type: 'SELL',
        quantity:         qty,
        order_type:       'LIMIT',
        product:          'CNC',
        price:            (stopTrig * 0.995).toFixed(2),   // limit 0.5% below trigger
      },
      {
        tradingsymbol:    symbol,
        exchange:         'NSE',
        transaction_type: 'SELL',
        quantity:         qty,
        order_type:       'LIMIT',
        product:          'CNC',
        price:            (m1Trig * 0.998).toFixed(2),     // limit 0.2% below trigger
      }
    ]),
  });

  try {
    showToast('⏳ Placing GTT via Kite API…', 'info');
    const resp = await fetch(`${KITE.API_URL}/gtt/triggers`, {
      method:  'POST',
      headers: kiteHeaders(),
      body,
    });
    const json = await resp.json();

    if (json.status === 'success') {
      const gttId = json.data?.trigger_id;
      showToast(`✅ GTT placed! ID: ${gttId}`, 'success');
      // Save to history
      const existing = store.get('nse_active_gtts', []);
      existing.push({ symbol, gttId, stop: stopTrig, target: m1Trig, cmp: ltp, created: new Date().toISOString() });
      store.set('nse_active_gtts', existing);
    } else {
      const msg = json.message || JSON.stringify(json);
      showToast(`❌ Kite API error: ${msg}`, 'error');
      console.error('[KITE]', json);
    }
  } catch (err) {
    showToast(`❌ Network error: ${err.message}`, 'error');
    console.error('[KITE]', err);
  }
}

/** Wire Zerodha buttons in Signal tab */
function wireZerodhaButtons(sig) {
  const wrap = document.getElementById('zerodhaActions');
  if (!wrap || !sig) return;
  wrap.style.display = 'block';

  // Populate manual guide cheat-sheet
  const stopEl = document.getElementById('guideStopLoss');
  if (stopEl) stopEl.textContent = `₹${fmt(sig.INITIAL_STOP)} (Hard SL)`;

  const tgtEl = document.getElementById('guideTarget');
  if (tgtEl) tgtEl.textContent = `₹${fmt(sig.M1_TARGET)} (+15.0%)`;

  const btnKite = document.getElementById('btnOpenKite');
  if (btnKite) {
    btnKite.onclick = () => openInKite(sig.SYMBOL);
  }

  const btnCopy = document.getElementById('btnCopyGTT');
  if (btnCopy) {
    btnCopy.onclick = async () => {
      const text = buildGTTClipboardText(sig);
      try {
        await navigator.clipboard.writeText(text);
        showToast('📋 GTT details copied!', 'success');
      } catch {
        // Fallback for older Android
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.style.position = 'fixed';
        ta.style.opacity  = '0';
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        showToast('📋 GTT details copied!', 'success');
      }
    };
  }

  const btnAuto = document.getElementById('btnAutoGTT');
  if (btnAuto) {
    btnAuto.onclick = () => autoPlaceGTT(sig);
  }

  const btnGroww = document.getElementById('btnOpenGroww');
  if (btnGroww) {
    btnGroww.onclick = () => {
      window.open(`https://groww.in/search?q=${encodeURIComponent(sig.SYMBOL)}`, '_blank', 'noopener');
    };
  }

  const btnTV = document.getElementById('btnOpenTV');
  if (btnTV) {
    btnTV.onclick = () => {
      window.open(`https://in.tradingview.com/chart/?symbol=NSE%3A${encodeURIComponent(sig.SYMBOL)}`, '_blank', 'noopener');
    };
  }
}

/** Kite Settings: Save */
const btnSaveKite = document.getElementById('btnSaveKite');
if (btnSaveKite) {
  btnSaveKite.addEventListener('click', () => {
    const key   = document.getElementById('kiteApiKey')?.value.trim();
    const token = document.getElementById('kiteAccessToken')?.value.trim();
    if (!key) { showToast('⚠️ API Key is required', 'warn'); return; }
    store.set(KITE.LS_KEY,   key);
    store.set(KITE.LS_TOKEN, token || '');
    const status = document.getElementById('kiteStatus');
    if (status) {
      status.textContent = token
        ? `✅ Kite configured. GTT auto-place enabled.`
        : `⚠️ API Key saved. Add Access Token to enable auto-GTT.`;
      status.style.color = token ? 'var(--accent)' : 'var(--yellow)';
    }
    showToast('💾 Kite settings saved', 'success');
  });
}

/** Load Kite settings into inputs on Settings tab open */
function loadKiteSettings() {
  const keyEl   = document.getElementById('kiteApiKey');
  const tokEl   = document.getElementById('kiteAccessToken');
  const statEl  = document.getElementById('kiteStatus');
  if (keyEl)  keyEl.value  = kiteApiKey();
  if (tokEl)  tokEl.value  = kiteToken();
  if (statEl) {
    if (kiteConfigured()) {
      statEl.textContent = '✅ Kite configured. GTT auto-place enabled.';
      statEl.style.color = 'var(--accent)';
    } else if (kiteApiKey()) {
      statEl.textContent = '⚠️ API Key set. Add Access Token to enable auto-GTT.';
      statEl.style.color = 'var(--yellow)';
    }
  }
}

/* ══════════════════════════════════════════════════════
   CAPITAL CONTROLLER & DYNAMIC STOCK EXPLORER
══════════════════════════════════════════════════════ */

function wireCapitalController() {
  const input = document.getElementById('inputUserCapital');
  const btn = document.getElementById('btnApplyCapital');
  const pills = document.querySelectorAll('.pill-preset');

  const currentCap = store.get(LS.CURRENT_CAPITAL, DEFAULT_CAPITAL);
  state.userCapital = currentCap;
  if (input) input.value = currentCap;
  updatePillActive(currentCap);

  if (btn && input) {
    btn.onclick = () => {
      const val = parseFloat(input.value);
      if (!isNaN(val) && val >= 100) {
        onCapitalChange(val);
        showToast(`Budget set to ₹${val.toLocaleString('en-IN')}`, 'success', '💰');
      } else {
        showToast('Please enter at least ₹100', 'warn');
      }
    };
    input.addEventListener('keypress', e => {
      if (e.key === 'Enter') btn.click();
    });
  }

  pills.forEach(p => {
    p.onclick = () => {
      const cap = parseFloat(p.dataset.cap);
      if (!isNaN(cap)) {
        if (input) input.value = cap;
        onCapitalChange(cap);
        showToast(`Budget set to ₹${cap.toLocaleString('en-IN')}`, 'success', '💰');
      }
    };
  });
}

function updatePillActive(cap) {
  document.querySelectorAll('.pill-preset').forEach(p => {
    p.classList.toggle('active', parseFloat(p.dataset.cap) === cap);
  });
}

let currentFilter = 'all';
let currentSearch = '';

function setupWatchlistSearchAndFilters() {
  const globalSearch = document.getElementById('globalStockSearch');
  const screenerSearch = document.getElementById('screenerSearchInput');
  const btnClear = document.getElementById('btnClearSearch');
  const filterChips = document.querySelectorAll('.filter-chip');

  function applySearch(query) {
    currentSearch = (query || '').trim().toUpperCase();
    if (screenerSearch && screenerSearch.value !== query) {
      screenerSearch.value = query;
    }
    if (globalSearch && globalSearch.value !== query) {
      globalSearch.value = query;
    }
    if (btnClear) {
      btnClear.style.display = query ? 'flex' : 'none';
    }
    const all = (state.payload && state.payload.all_qualified) || [];
    renderAllStocksTable(all, state.userCapital || store.get(LS.CURRENT_CAPITAL, DEFAULT_CAPITAL));
  }

  // Keyboard shortcuts: '/' to focus global search, 'Escape' to blur or close modals
  window.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
      if (document.activeElement && (document.activeElement.tagName === 'INPUT' || document.activeElement.tagName === 'TEXTAREA')) {
        document.activeElement.blur();
      }
      closeExitModal();
      const glossaryModal = document.getElementById('glossaryModal');
      if (glossaryModal && glossaryModal.classList.contains('open')) {
        glossaryModal.classList.remove('open');
        document.body.classList.remove('modal-open');
      }
    } else if (e.key === '/' && document.activeElement.tagName !== 'INPUT' && document.activeElement.tagName !== 'TEXTAREA') {
      e.preventDefault();
      if (globalSearch) {
        globalSearch.focus();
        globalSearch.select();
      }
    }
  });

  if (globalSearch) {
    globalSearch.addEventListener('input', e => {
      if (state.currentTab !== 'Signal') {
        switchTab('Signal');
      }
      applySearch(e.target.value);
    });
    globalSearch.addEventListener('keydown', e => {
      if (e.key === 'Enter') {
        const all = (state.payload && state.payload.all_qualified) || [];
        const match = all.find(s => s.SYMBOL.toUpperCase().includes(currentSearch));
        if (match) {
          selectStockForTrading(match, state.userCapital || store.get(LS.CURRENT_CAPITAL, DEFAULT_CAPITAL));
          globalSearch.blur();
        }
      }
    });
  }

  if (screenerSearch) {
    screenerSearch.addEventListener('input', e => {
      applySearch(e.target.value);
    });
    screenerSearch.addEventListener('keydown', e => {
      if (e.key === 'Enter') {
        const all = (state.payload && state.payload.all_qualified) || [];
        const match = all.find(s => s.SYMBOL.toUpperCase().includes(currentSearch));
        if (match) {
          selectStockForTrading(match, state.userCapital || store.get(LS.CURRENT_CAPITAL, DEFAULT_CAPITAL));
          screenerSearch.blur();
        }
      }
    });
  }

  if (btnClear) {
    btnClear.addEventListener('click', () => {
      applySearch('');
      if (screenerSearch) screenerSearch.focus();
    });
  }

  filterChips.forEach(chip => {
    chip.addEventListener('click', () => {
      filterChips.forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
      currentFilter = chip.dataset.filter || 'all';
      const all = (state.payload && state.payload.all_qualified) || [];
      renderAllStocksTable(all, state.userCapital || store.get(LS.CURRENT_CAPITAL, DEFAULT_CAPITAL));
    });
  });
}

function onCapitalChange(newCapital) {
  state.userCapital = newCapital;
  store.set(LS.CURRENT_CAPITAL, newCapital);
  updatePillActive(newCapital);

  const allStocks = (state.payload && state.payload.all_qualified) || [];
  if (allStocks.length > 0) {
    const isDefensive = (state.payload && state.payload.regime && state.payload.regime.regime === 'DEFENSIVE_CASH');
    let target = state.activeStock ? allStocks.find(s => s.SYMBOL === state.activeStock.SYMBOL) : null;
    if (!target) {
      const affordable = allStocks.filter(s => parseFloat(s.CMP) <= (newCapital - 26));
      target = affordable.length > 0 ? affordable[0] : allStocks[0];
    }
    if (target) {
      const winner = Object.assign({}, target);
      const shares = Math.max(Math.floor((newCapital - 26) / parseFloat(winner.CMP)), 1);
      winner.SHARES = shares;
      winner.CAPITAL_REQUIRED = shares * parseFloat(winner.CMP);
      winner.CAPITAL_BASE = newCapital;
      const alts = allStocks.filter(s => s.SYMBOL !== winner.SYMBOL).slice(0, 3);
      renderActiveSignal(winner, alts, isDefensive);
    }
    renderAllStocksTable(allStocks, newCapital);
  }
}

/* ══════════════════════════════════════════════════════
   ENTRY PRICE (GAP-UP) CONTROLLER
══════════════════════════════════════════════════════ */

function wireEntryPriceController() {
  const input = document.getElementById('inputActualEntry');
  const btnReset = document.getElementById('btnResetEntry');
  const pills = document.querySelectorAll('.pill-gap');

  if (input) {
    input.addEventListener('input', () => {
      const val = parseFloat(input.value);
      if (!isNaN(val) && val > 0 && state.activeStock) {
        recalculateFromEntry(val);
        updateGapPillActive(null);
      }
    });
  }

  if (btnReset) {
    btnReset.onclick = () => {
      if (state.activeStock) {
        const cmp = parseFloat(state.activeStock.CMP);
        input.value = cmp;
        recalculateFromEntry(cmp);
        updateGapPillActive(0);
      }
    };
  }

  pills.forEach(p => {
    p.onclick = () => {
      const gap = parseFloat(p.dataset.gap);
      if (!isNaN(gap) && state.activeStock) {
        const cmp = parseFloat(state.activeStock.CMP);
        const newEntry = Math.round((cmp * (1 + gap / 100)) * 100) / 100;
        if (input) input.value = newEntry;
        recalculateFromEntry(newEntry);
        updateGapPillActive(gap);
      }
    };
  });
}

function updateGapPillActive(gap) {
  document.querySelectorAll('.pill-gap').forEach(p => {
    p.classList.toggle('active', gap !== null && parseFloat(p.dataset.gap) === gap);
  });
}

/* ══════════════════════════════════════════════════════
   SESSION DATE SWITCHER & MARKET STATUS
══════════════════════════════════════════════════════ */

function renderSessionSwitcher(manifest, currentTradeDate) {
  const sessionCard = document.getElementById('sessionCard');
  const pillsContainer = document.getElementById('sessionPills');
  const pendingNotice = document.getElementById('bhavcopyPendingNotice');
  if (!sessionCard || !pillsContainer) return;

  const manifestList = (manifest && manifest.length) ? manifest : (state.historyManifest && state.historyManifest.length ? state.historyManifest : null);
  if (!manifestList || manifestList.length <= 1) {
    sessionCard.hidden = true;
    return;
  }
  sessionCard.hidden = false;

  const isFallback = state.payload && state.payload.bhavcopy_status === 'PREVIOUS_SESSION_FALLBACK';
  if (pendingNotice) {
    pendingNotice.hidden = !isFallback;
  }

  const activeDate = state.selectedDate || currentTradeDate;
  pillsContainer.innerHTML = '';
  manifestList.forEach((m, idx) => {
    const btn = document.createElement('button');
    const isSelected = (m.date === activeDate);
    const isLatest = idx === 0;
    btn.className = `pill-session ${isSelected ? 'active' : ''}`;
    btn.innerHTML = `${isLatest ? '⚡' : '📅'} ${m.display_date || m.date}${isLatest ? ' <span class="tag-latest">Latest</span>' : ''}`;
    btn.title = `${m.display_date}: ${m.total_qualified} qualified leaders`;
    btn.onclick = () => selectSessionDate(m.date);
    pillsContainer.appendChild(btn);
  });

  updateMarketStatusBar(manifestList, currentTradeDate);
}

function updateMarketStatusBar(manifest, currentTradeDate) {
  const bar = document.getElementById('marketStatusBar');
  const dot = document.getElementById('marketStatusDot');
  const phase = document.getElementById('marketStatusPhase');
  const todayEl = document.getElementById('marketStatusToday');
  const desc = document.getElementById('marketStatusDesc');
  const pill = document.getElementById('marketStatusActivePill');
  const activeSessionEl = document.getElementById('marketStatusActiveSession');
  const btnReturn = document.getElementById('btnReturnLatestSession');

  if (!bar) return;

  const manifestList = (manifest && manifest.length) ? manifest : (state.historyManifest && state.historyManifest.length ? state.historyManifest : null);

  // Real-time IST calculation
  const now = new Date();
  const utcMs = now.getTime() + (now.getTimezoneOffset() * 60 * 1000);
  const istDate = new Date(utcMs + (5.5 * 60 * 60 * 1000));
  const day = istDate.getDay(); // 0 Sun, 6 Sat
  const hour = istDate.getHours();
  const minute = istDate.getMinutes();

  const isWeekday = day >= 1 && day <= 5;
  const isMarketOpen = isWeekday && ((hour > 9 || (hour === 9 && minute >= 15)) && (hour < 15 || (hour === 15 && minute <= 30)));
  const isCompilingBhavcopy = isWeekday && ((hour === 15 && minute > 30) || (hour >= 16 && hour < 17) || (hour === 17 && minute <= 30));

  const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  const todayStr = `${String(istDate.getDate()).padStart(2, '0')}-${months[istDate.getMonth()]}-${istDate.getFullYear()}`;
  if (todayEl) todayEl.textContent = `Today: ${todayStr}`;

  const latestSession = (manifestList && manifestList.length > 0) ? manifestList[0] : null;
  const activeDate = state.selectedDate || currentTradeDate;
  const isViewingLatest = !latestSession || (activeDate === latestSession.date);

  const activeItem = manifestList ? manifestList.find(m => m.date === activeDate) : null;
  const activeDisplay = activeItem ? (activeItem.display_date || activeItem.date) : (state.payload && state.payload.trade_date_display ? state.payload.trade_date_display : activeDate);

  if (pill) {
    pill.textContent = `Session: ${activeDisplay}`;
  }
  if (activeSessionEl) {
    activeSessionEl.textContent = activeDisplay;
  }

  if (!isViewingLatest) {
    if (dot) dot.className = 'status-pulse-dot archive';
    if (phase) phase.textContent = `HISTORICAL SESSION ARCHIVE (${activeDisplay})`;
    if (desc) desc.innerHTML = `Viewing historical session snapshot for <strong>${activeDisplay}</strong>. Data preserved for backtest and performance review.`;
    if (btnReturn && latestSession) {
      btnReturn.hidden = false;
      btnReturn.textContent = `Back to Latest (${latestSession.display_date})`;
      btnReturn.onclick = () => selectSessionDate(latestSession.date);
    }
    return;
  }

  if (btnReturn) btnReturn.hidden = true;

  if (state.payload && state.payload.is_today) {
    if (dot) dot.className = 'status-pulse-dot synced';
    if (phase) phase.textContent = 'SESSION SYNCHRONIZED';
    if (desc) desc.innerHTML = `Official NSE Bhavcopy for <strong>${todayStr}</strong> is verified and active.`;
  } else if (isMarketOpen) {
    if (dot) dot.className = 'status-pulse-dot live';
    if (phase) phase.textContent = 'NSE LIVE SESSION (09:15 – 15:30 IST)';
    if (desc) desc.innerHTML = `Today's official Bhavcopy releases post-market (~17:30 IST). Showing latest confirmed session: <strong>${latestSession ? latestSession.display_date : '30 Sep 2026'}</strong>.`;
  } else if (isCompilingBhavcopy) {
    if (dot) dot.className = 'status-pulse-dot compiling';
    if (phase) phase.textContent = 'NSE COMPILING BHAVCOPY (Market Closed)';
    if (desc) desc.innerHTML = `Exchange clearing & reconciliation in progress (releases ~17:30 IST). Showing latest confirmed session: <strong>${latestSession ? latestSession.display_date : '30 Sep 2026'}</strong>.`;
  } else {
    if (dot) dot.className = 'status-pulse-dot neutral';
    if (phase) phase.textContent = 'MARKET CLOSED';
    if (desc) desc.innerHTML = `Next session opens at 09:15 IST. Displaying confirmed session: <strong>${latestSession ? latestSession.display_date : '30 Sep 2026'}</strong>.`;
  }
}

async function selectSessionDate(dateStr) {
  state.selectedDate = dateStr;
  try {
    showSkeleton(true);
    const res = await fetch(`data/history/${dateStr}.json?_t=` + Date.now(), { cache: 'no-store' });
    if (!res.ok) throw new Error(`Could not load session ${dateStr}`);
    const payload = await res.json();

    // Preserve history manifest across session switches
    if (!state.historyManifest || !state.historyManifest.length) {
      try {
        const mRes = await fetch('data/history/manifest.json?_t=' + Date.now(), { cache: 'no-store' });
        if (mRes.ok) state.historyManifest = await mRes.json();
      } catch (_) {}
    }
    payload.history_manifest = state.historyManifest;
    state.payload = payload;
    state.signalData = payload.rows || [];

    renderMarketRegime(payload.regime);
    renderSignal(payload.rows, payload.reason);
    if (payload.all_qualified) {
      renderAllStocksTable(payload.all_qualified, state.userCapital || store.get(LS.CURRENT_CAPITAL, DEFAULT_CAPITAL));
    }
    renderSessionSwitcher(state.historyManifest, dateStr);
    showToast(`Viewing session: ${payload.trade_date_display || dateStr}`, 'info', '📅');
  } catch (err) {
    showToast('Failed to load past session: ' + err.message, 'error');
  } finally {
    showSkeleton(false);
  }
}

/* ══════════════════════════════════════════════════════
   GLOSSARY & STRATEGY GUIDE MODAL
══════════════════════════════════════════════════════ */

function wireGlossaryModal() {
  const modal = document.getElementById('glossaryModal');
  const btnOpen = document.getElementById('btnOpenGlossary');
  const btnClose = document.getElementById('btnCloseGlossary');
  const btnCloseBottom = document.getElementById('btnCloseGlossaryBottom');

  if (btnOpen && modal) {
    btnOpen.onclick = () => {
      modal.classList.add('open');
      document.body.classList.add('modal-open');
    };
  }
  if (btnClose && modal) {
    btnClose.onclick = () => {
      modal.classList.remove('open');
      document.body.classList.remove('modal-open');
    };
  }
  if (btnCloseBottom && modal) {
    btnCloseBottom.onclick = () => {
      modal.classList.remove('open');
      document.body.classList.remove('modal-open');
    };
  }
  if (modal) {
    modal.onclick = e => {
      if (e.target === modal) {
        modal.classList.remove('open');
        document.body.classList.remove('modal-open');
      }
    };
  }
}

/* ══════════════════════════════════════════════════════
   BOOT
══════════════════════════════════════════════════════ */

(function init() {
  // Purge stale 0-stock caches
  try {
    const cached = store.get(LS.LAST_SIGNAL, null);
    if (cached && (!cached.rows || cached.rows.length === 0 || cached.rows[0].STATUS === 'CASH' || (cached.payload && cached.payload.total_qualified === 0))) {
      localStorage.removeItem(LS.LAST_SIGNAL);
    }
  } catch (_) {}

  updateOfflineBadge(navigator.onLine);
  wireCapitalController();
  wireEntryPriceController();
  wireGlossaryModal();
  setupWatchlistSearchAndFilters();
  fetchSignal(true);
})();

/* ══════════════════════════════════════════════════════
   V2 RENDER LAYER — master–detail inspector, regime-aware
   decisioning, sortable data grid, responsive row-cards.
   These declarations intentionally supersede the legacy
   renderers above; the fetch / storage / broker logic is
   untouched.
══════════════════════════════════════════════════════ */

/** Show the inspector as a bottom sheet / drawer under 1024px. */
function openInspector() {
  const pane = document.getElementById('inspectorPane');
  if (!pane) return;
  if (window.matchMedia('(min-width: 1024px)').matches) return;
  pane.classList.add('open');
  let scrim = document.getElementById('inspectorScrim');
  if (!scrim) {
    scrim = document.createElement('div');
    scrim.id = 'inspectorScrim';
    scrim.className = 'scrim';
    scrim.addEventListener('click', closeInspector);
    document.body.appendChild(scrim);
  }
  requestAnimationFrame(() => scrim.classList.add('show'));
}

function closeInspector() {
  const pane = document.getElementById('inspectorPane');
  const scrim = document.getElementById('inspectorScrim');
  if (pane) pane.classList.remove('open');
  if (scrim) scrim.classList.remove('show');
}

function closeInspectorBtn() {
  const btn = document.getElementById('btnCloseInspector');
  if (btn) btn.addEventListener('click', closeInspector);
}

function renderCashState(hero, overrideMsg = null) {
  const heroCard = document.getElementById('heroCard');
  if (heroCard) {
    heroCard.className = 'inspector__header';
    heroCard.innerHTML = `
      <div class="ins-top"><span class="ins-status cash">100% cash</span></div>
      <div class="inspector__empty" style="padding:30px 6px">
        <svg class="ic ic--lg" aria-hidden="true"><use href="#i-bank"/></svg>
        <p><strong style="color:var(--text)">${overrideMsg || 'Preserve capital — defensive regime'}</strong><br>No deployable Stage-2 leader in this session. The engine protects capital and waits.</p>
        ${hero && hero.TIMESTAMP ? `<span class="muted">Screened ${hero.TIMESTAMP}</span>` : ''}
      </div>`;
  }
  const rsiCard = document.getElementById('rsiCard');
  const gttCard = document.getElementById('gttCard');
  const dbox = document.getElementById('decisionBox');
  if (rsiCard) rsiCard.hidden = true;
  if (gttCard) gttCard.hidden = true;
  if (dbox) dbox.hidden = true;
  const credCard = document.getElementById('credCard');
  if (credCard) credCard.hidden = true;
  showSkeleton(false);
}

/** Regime- and risk-aware go / no-go banner for the selected stock. */
function renderDecision(s, isDefensive, capital) {
  const box = document.getElementById('decisionBox');
  if (!box || !s) return;
  const cmp = parseFloat(s.CMP);
  const affordable = cmp <= (capital - 26);
  const band = parseFloat(s.CIRCUIT_BAND) || 20;
  const circuitRisk = s.CIRCUIT_RISK === true || band <= 5;
  const turnover = parseFloat(s.TURNOVER_CRORES) || 0;

  if (isDefensive) {
    box.className = 'decision decision--hold';
    box.hidden = false;
    box.innerHTML = `<svg class="ic" aria-hidden="true"><use href="#i-shield"/></svg>
      <div><strong>No new entry — capital preserved</strong>The benchmark is below its 200-day average. Levels are shown for monitoring and GTT simulation only.</div>`;
    return;
  }
  if (!affordable) {
    box.className = 'decision decision--warn';
    box.hidden = false;
    box.innerHTML = `<svg class="ic" aria-hidden="true"><use href="#i-alert"/></svg>
      <div><strong>Not affordable at ${fmtINR(capital)}</strong>Needs about ${fmtINR(cmp + 26)} for one share. Raise sizing capital or pick a lower-priced leader.</div>`;
    return;
  }
  if (s.SETUP_QUALITY === 'OVER_EXTENDED') {
    box.className = 'decision decision--warn';
    box.hidden = false;
    box.innerHTML = `<svg class="ic" aria-hidden="true"><use href="#i-alert"/></svg>
      <div><strong>⚠️ Over-Extended Setup (+30%+ above 50 SMA)</strong>Price is severely extended above its 50 SMA. Inverted risk-reward. DO NOT CHASE at the top. Wait for a pullback consolidation or pick a fresh basing alternate.</div>`;
    return;
  }
  const credEntry = (state.credIndex || {})[String(s.SYMBOL).toUpperCase()];
  const credScore = credEntry && credEntry.score != null ? credEntry.score : null;
  if (credScore != null && credScore < 50) {
    box.className = 'decision decision--warn';
    box.hidden = false;
    box.innerHTML = `<svg class="ic" aria-hidden="true"><use href="#i-alert"/></svg>
      <div><strong>⚠️ Low Backtest Credibility (Score: ${credScore.toFixed(1)}/100)</strong>3-year historical test shows stops dominate (+15% target reached in only ${credEntry.target_hit_rate_pct != null ? credEntry.target_hit_rate_pct + '%' : 'minority'}). High risk of whipsaw stop-out.</div>`;
    return;
  }
  if (s.INSTITUTIONAL_GRADE === 'RETAIL_TRAP') {
    const reason = (s.INSTITUTIONAL_WARNINGS && s.INSTITUTIONAL_WARNINGS[0]) || 'Low volume or expanding volatility';
    box.className = 'decision decision--warn';
    box.hidden = false;
    box.innerHTML = `<svg class="ic" aria-hidden="true"><use href="#i-alert"/></svg>
      <div><strong>⚠️ Institutional Risk — Retail Trap</strong>${reason}. Institutional volume is missing or volatility is whipsawing. High probability of false breakout.</div>`;
    return;
  }
  if (circuitRisk) {
    box.className = 'decision decision--warn';
    box.hidden = false;
    box.innerHTML = `<svg class="ic" aria-hidden="true"><use href="#i-alert"/></svg>
      <div><strong>Execution risk — ${band}% circuit band</strong>Narrow bands can lock into the lower circuit and trap an exit. Prefer a wider-band alternate.</div>`;
    return;
  }
  box.className = 'decision decision--go';
  box.hidden = false;
  box.innerHTML = `<svg class="ic" aria-hidden="true"><use href="#i-check"/></svg>
    <div><strong>Deploy — setup validated</strong>Affordable at ${fmtINR(capital)} with ${turnover ? `₹${turnover.toFixed(1)} Cr 20-day turnover` : 'sufficient liquidity'}. Risk is capped at 1% of equity by the ticket below.</div>`;
}

function renderActiveSignal(h, alts, isDefensive = false) {
  const heroCard = document.getElementById('heroCard');
  if (!heroCard) return;

  const cmp = parseFloat(h.CMP);
  const cms = parseFloat(h.CMS_SCORE);
  const high52 = parseFloat(h.HIGH_52W) || cmp;
  const proxPct = Math.max(0, ((high52 - cmp) / high52) * 100);
  const fillPct = Math.max(4, Math.min(100, 100 - proxPct));
  const atr = parseFloat(h.ATR_14) || (cmp * 0.04);
  const atrPct = cmp ? (atr / cmp) * 100 : 0;
  const rsi = parseFloat(h.RSI_14);
  const setup = (h.SETUP_QUALITY || '').toString().replace(/_/g, ' ');

  heroCard.className = 'inspector__header';
  heroCard.innerHTML = `
    <div class="ins-top">
      <span class="ins-status ${isDefensive ? 'defensive' : 'active'}">${isDefensive ? 'Defensive watchlist' : 'Active signal'}</span>
      <span class="ins-rank">${isDefensive ? 'Candidate #1' : 'Leader #1'}</span>
    </div>
    <div class="ins-identity">
      <span class="ins-symbol">${h.SYMBOL}</span>
      ${h.INSTITUTIONAL_GRADE === 'PRIME_INSTITUTIONAL' ? '<span class="tag tag--prime" style="background:rgba(34,197,94,0.18);color:#22c55e;border:1px solid rgba(34,197,94,0.4)">★ INST PRIME</span>' : ''}
      ${h.INSTITUTIONAL_GRADE === 'RETAIL_TRAP' ? '<span class="tag tag--risk" style="background:rgba(239,68,68,0.18);color:#ef4444;border:1px solid rgba(239,68,68,0.4)">⚠️ RETAIL TRAP</span>' : ''}
      ${h.IS_PRIME && h.INSTITUTIONAL_GRADE !== 'PRIME_INSTITUTIONAL' ? '<span class="tag tag--prime">PRIME</span>' : ''}
      <span class="ins-cmp num">${fmtINR(cmp)}</span>
    </div>
    <div class="ins-sub">${setup || 'Stage-2 momentum leader'}</div>
    <div class="prox">
      <div class="prox__row"><span>52-week high</span><strong>${fmtINR(high52)} · −${proxPct.toFixed(1)}% away</strong></div>
      <div class="prox__track"><span class="prox__fill" style="width:${fillPct}%"></span></div>
    </div>
    <div class="ins-chips">
      <span class="ins-chip"><small>CMS</small><span>${isNaN(cms) ? h.CMS_SCORE : cms.toFixed(1)}</span></span>
      <span class="ins-chip"><small>Vol Surge</small><span style="color:${(parseFloat(h.VOL_SURGE_RATIO) || 1.0) >= 1.0 ? 'var(--accent)' : 'var(--red)'}">${h.VOL_SURGE_RATIO || h.VOL_RATIO || 1.0}x</span></span>
      <span class="ins-chip"><small>VCP</small><span>${h.VCP_RATIO || '1.0'}</span></span>
      <span class="ins-chip"><small>RSI</small><span>${isNaN(rsi) ? '–' : rsi.toFixed(1)}</span></span>
      <span class="ins-chip"><small>ATR</small><span>${atrPct.toFixed(1)}%</span></span>
      <span class="ins-chip"><small>Band</small><span>${h.CIRCUIT_BAND || '20'}%</span></span>
    </div>`;

  const capital = state.userCapital || store.get(LS.CURRENT_CAPITAL, DEFAULT_CAPITAL);
  renderDecision(h, isDefensive, capital);

  renderRSIGauge(rsi);
  const rsiCard = document.getElementById('rsiCard');
  if (rsiCard) rsiCard.hidden = false;

  const rocRow = document.getElementById('rocRow');
  if (rocRow) {
    const r1 = fmtPct(h.ROC_1M), r2 = fmtPct(h.ROC_2M), r3 = fmtPct(h.ROC_3M);
    rocRow.innerHTML = `
      <div class="roc-item"><div class="roc-period">1M</div><div class="roc-val ${r1.cls}">${r1.text}</div></div>
      <div class="roc-item"><div class="roc-period">2M</div><div class="roc-val ${r2.cls}">${r2.text}</div></div>
      <div class="roc-item"><div class="roc-period">3M</div><div class="roc-val ${r3.cls}">${r3.text}</div></div>`;
  }

  const smaRow = document.getElementById('smaRow');
  if (smaRow) {
    const sma50 = parseFloat(h.SMA_50), sma200 = parseFloat(h.SMA_200);
    const d50 = sma50 ? ((cmp - sma50) / sma50) * 100 : 0;
    const d200 = sma200 ? ((cmp - sma200) / sma200) * 100 : 0;
    smaRow.innerHTML = `
      <div class="sma-item"><div class="sma-label">Price vs SMA50</div><div class="sma-val" style="color:${cmp > sma50 ? 'var(--accent)' : 'var(--red)'}">${d50 >= 0 ? '+' : ''}${d50.toFixed(1)}%</div></div>
      <div class="sma-item"><div class="sma-label">Price vs SMA200</div><div class="sma-val" style="color:${cmp > sma200 ? 'var(--accent)' : 'var(--red)'}">${d200 >= 0 ? '+' : ''}${d200.toFixed(1)}%</div></div>`;
  }

  const specTurnover = document.getElementById('specTurnover');
  const specATR = document.getElementById('specATR');
  const specCircuit = document.getElementById('specCircuit');
  if (specTurnover) { const toCr = parseFloat(h.TURNOVER_CRORES); specTurnover.textContent = !isNaN(toCr) ? `₹${toCr.toFixed(1)} Cr` : '—'; }
  if (specATR) specATR.textContent = `${fmtINR(atr)} (${atrPct.toFixed(1)}%)`;
  if (specCircuit) specCircuit.textContent = `${h.CIRCUIT_BAND || '20'}%${h.CIRCUIT_RISK ? ' · risky' : ''}`;

  renderGTT(h);
  renderCredibility(h.SYMBOL);
}

function renderGTT(h) {
  state.activeStock = h;
  const gttCard = document.getElementById('gttCard');
  const entryInput = document.getElementById('inputActualEntry');
  const currentEntry = parseFloat(h.ACTUAL_ENTRY || h.CMP);
  if (entryInput) entryInput.value = currentEntry.toFixed(2);
  updateGapPillActive(0);
  recalculateFromEntry(currentEntry);
  wireZerodhaButtons(h);
  if (gttCard) gttCard.hidden = false;
}

/* ─── Grid sort / filter state ─── */
state.sortKey = state.sortKey || 'rank';
state.sortDir = state.sortDir || 'asc';

function proxPctOf(s) {
  const cmp = parseFloat(s.CMP);
  const hi = parseFloat(s.HIGH_52W) || cmp;
  return hi > 0 ? Math.max(0, ((hi - cmp) / hi) * 100) : 0;
}

function setupShort(s) {
  if (s.INSTITUTIONAL_GRADE === 'RETAIL_TRAP') return '⚠️ Retail Trap';
  if (s.INSTITUTIONAL_GRADE === 'PRIME_INSTITUTIONAL') return '★ Inst. Prime';
  if (s.IS_PRIME) return 'Prime';
  const q = (s.SETUP_QUALITY || '').toString().replace(/_/g, ' ');
  if (!q) return 'Momentum';
  return q.replace(/prime low risk/i, 'Prime').replace(/\b\w/g, c => c.toUpperCase());
}

function buildGridRow(s, idx, userCapital) {
  const cmp = parseFloat(s.CMP);
  const cms = parseFloat(s.CMS_SCORE);
  const rsi = parseFloat(s.RSI_14);
  const roc1 = parseFloat(s.ROC_1M);
  const roc3 = parseFloat(s.ROC_3M);
  const atrPct = parseFloat(s.ATR_PCT);
  const to = parseFloat(s.TURNOVER_CRORES);
  const band = parseFloat(s.CIRCUIT_BAND) || 20;
  const prox = proxPctOf(s);
  const affordable = cmp <= (userCapital - 26);
  const shares = affordable ? Math.max(Math.floor((userCapital - 26) / cmp), 1) : 0;
  const isSelected = state.activeStock && state.activeStock.SYMBOL === s.SYMBOL;
  const rsiTone = rsi < 45 ? 'var(--red)' : rsi <= 82 ? 'var(--accent)' : 'var(--yellow)';
  const cmsClass = cms >= 90 ? 'hi' : cms >= 75 ? 'mid' : 'lo';
  const cred = (state.credIndex || {})[String(s.SYMBOL).toUpperCase()];
  const credScore = cred && cred.score != null ? cred.score : null;
  const credClass = credScore == null ? 'lo' : credScore >= 60 ? 'hi' : credScore >= 40 ? 'mid' : 'lo';
  const credTitle = cred
    ? `Credibility ${cred.credible ? '✓' : '—'} · score ${credScore == null ? '—' : credScore} · pace ${cred.pace} · +15% hit ${cred.target_hit_rate_pct}% · median ${cred.median_days_to_target}d`
    : 'No backtest report';
  const pctCell = v => isNaN(v) ? '–' : `<span class="${v >= 0 ? 'pos' : 'neg'}">${v >= 0 ? '+' : ''}${v.toFixed(1)}%</span>`;

  const isTrap = s.INSTITUTIONAL_GRADE === 'RETAIL_TRAP';
  const isInstPrime = s.INSTITUTIONAL_GRADE === 'PRIME_INSTITUTIONAL';

  const tr = document.createElement('tr');
  tr.className = 'stock-table-row' + (isSelected ? ' selected' : '') + (isTrap ? ' row--trap' : '');
  tr.setAttribute('role', 'row');
  tr.dataset.symbol = s.SYMBOL;
  tr.innerHTML = `
    <td class="col-rank num" data-label="#">${idx + 1}</td>
    <td class="col-sec" data-label="Security">
      <div class="sec-cell">
        <span class="sec-symbol">${s.SYMBOL}</span>
        <span class="sec-tags">
          ${isInstPrime ? '<span class="tag tag--prime" style="background:rgba(34,197,94,0.18);color:#22c55e;border:1px solid rgba(34,197,94,0.4)">★ INST PRIME</span>' : ''}
          ${isTrap ? '<span class="tag tag--risk" style="background:rgba(239,68,68,0.18);color:#ef4444;border:1px solid rgba(239,68,68,0.4)">⚠️ RETAIL TRAP</span>' : ''}
          ${s.IS_PRIME && !isInstPrime ? '<span class="tag tag--prime">PRIME</span>' : ''}
          <span class="tag">${band}% band</span>
          ${(s.CIRCUIT_RISK === true || band <= 5) ? '<span class="tag tag--risk">CIRCUIT RISK</span>' : ''}
        </span>
      </div>
    </td>
    <td class="num" data-label="CMP">${fmtINR(cmp)}</td>
    <td class="num col-cms" data-label="CMS"><span class="score-pill ${cmsClass}">${isNaN(cms) ? '–' : cms.toFixed(1)}</span></td>
    <td class="num col-cred" data-label="Cred"><span class="score-pill ${credClass}" title="${credTitle}">${credScore == null ? '–' : credScore.toFixed(0)}</span></td>
    <td class="num col-rsi" data-label="RSI"><span style="color:${rsiTone}">${isNaN(rsi) ? '–' : rsi.toFixed(1)}</span></td>
    <td class="num col-roc col-roc1" data-label="1M ROC">${pctCell(roc1)}</td>
    <td class="num col-roc" data-label="3M ROC">${pctCell(roc3)}</td>
    <td class="num col-atr" data-label="ATR%">${isNaN(atrPct) ? '–' : atrPct.toFixed(1) + '%'}</td>
    <td class="num col-liq" data-label="Turnover">${isNaN(to) ? '–' : '₹' + to.toFixed(1) + ' Cr'}</td>
    <td class="num col-prox" data-label="vs 52W high">−${prox.toFixed(1)}%</td>
    <td class="col-setup" data-label="Setup">${setupShort(s)}</td>
    <td class="num col-size" data-label="Size">${affordable ? `<span class="size-hint ok">${shares} sh</span>` : '<span class="size-hint no">over budget</span>'}</td>
    <td class="col-action" data-label="Action">
      <button class="btn btn--sm ${isSelected ? 'btn--primary' : 'btn--secondary'}" data-select aria-label="Inspect ${s.SYMBOL}">${isSelected ? 'Open' : 'Inspect'}</button>
    </td>`;
  tr.addEventListener('click', () => selectStockForTrading(s, userCapital));
  return tr;
}

function renderAllStocksTable(stocks, userCapital) {
  const tbody = document.getElementById('allStocksBody');
  const countBadge = document.getElementById('allStocksCountBadge');
  const status = document.getElementById('gridStatus');
  if (!tbody) return;
  userCapital = userCapital || state.userCapital || DEFAULT_CAPITAL;
  const all = stocks || [];
  ensureCredIndex();

  const getters = {
    rank:     (s, i) => i,
    symbol:   (s) => s.SYMBOL,
    cmp:      (s) => parseFloat(s.CMP) || 0,
    cms:      (s) => parseFloat(s.CMS_SCORE) || 0,
    cred:     (s) => { const e = (state.credIndex || {})[String(s.SYMBOL).toUpperCase()]; return e && e.score != null ? e.score : -1; },
    rsi:      (s) => parseFloat(s.RSI_14) || 0,
    roc1:     (s) => parseFloat(s.ROC_1M) || 0,
    roc3:     (s) => parseFloat(s.ROC_3M) || 0,
    atr:      (s) => parseFloat(s.ATR_PCT) || 0,
    turnover: (s) => parseFloat(s.TURNOVER_CRORES) || 0,
    prox:     (s) => proxPctOf(s),
  };

  const q = (currentSearch || '').toUpperCase();
  const labelMap = { all: 'All', prime: 'Prime', sweet_rsi: 'Sweet RSI', affordable: 'Affordable', circuit_safe: 'Circuit-safe', strong_trend: 'Strong trend' };

  const filtered = all.filter(s => {
    if (q && !String(s.SYMBOL).toUpperCase().includes(q)) return false;
    const rsi = parseFloat(s.RSI_14) || 0;
    const cmp = parseFloat(s.CMP) || 0;
    const band = parseFloat(s.CIRCUIT_BAND) || 0;
    const to = parseFloat(s.TURNOVER_CRORES) || 0;
    switch (currentFilter) {
      case 'prime':        return s.IS_PRIME === true || (parseFloat(s.CMS_SCORE) || 0) >= 90;
      case 'sweet_rsi':    return rsi >= 45 && rsi <= 75;
      case 'affordable':   return cmp <= (userCapital - 26);
      case 'circuit_safe': return s.CIRCUIT_RISK !== true && band >= 10 && to >= 5;
      case 'strong_trend': return (parseFloat(s.DIST_50SMA) || 0) > 0 && (parseFloat(s.ROC_2M) || 0) > 0 && rsi <= 82;
      default:             return true;
    }
  });

  const origIndex = new Map(all.map((s, i) => [s, i]));
  const dir = state.sortDir === 'desc' ? -1 : 1;
  const get = getters[state.sortKey] || getters.rank;
  filtered.sort((a, b) => {
    const va = get(a, origIndex.get(a));
    const vb = get(b, origIndex.get(b));
    if (typeof va === 'string' || typeof vb === 'string') return dir * String(va).localeCompare(String(vb));
    return dir * (va - vb);
  });

  if (countBadge) countBadge.textContent = `${filtered.length} / ${all.length} leaders`;
  if (status) status.textContent = `${filtered.length} shown · ${labelMap[currentFilter] || 'All'} · sorted ${state.sortKey} ${state.sortDir}`;

  document.querySelectorAll('.data-grid thead th[data-sort]').forEach(th => {
    if (th.dataset.sort === state.sortKey) th.setAttribute('aria-sort', state.sortDir === 'asc' ? 'ascending' : 'descending');
    else th.removeAttribute('aria-sort');
  });

  tbody.innerHTML = '';
  if (!filtered.length) {
    const row = document.createElement('tr');
    row.innerHTML = `<td colspan="14"><div class="empty-state"><svg class="ic ic--lg" aria-hidden="true"><use href="#i-search"/></svg><p>No leaders match “${currentSearch || labelMap[currentFilter] || 'this filter'}”.</p></div></td>`;
    tbody.appendChild(row);
    return;
  }
  filtered.forEach((s, i) => tbody.appendChild(buildGridRow(s, i, userCapital)));
}

function selectStockForTrading(s, userCapital) {
  const stock = Object.assign({}, s);
  const cmp = parseFloat(stock.CMP);
  const shares = Math.max(Math.floor((userCapital - 26) / cmp), 1);
  stock.SHARES = shares;
  stock.CAPITAL_REQUIRED = shares * cmp;
  stock.CAPITAL_BASE = userCapital;

  const all = (state.payload && state.payload.all_qualified) || [];
  const alts = all.filter(item => item.SYMBOL !== stock.SYMBOL).slice(0, 3);
  const isDefensive = (state.payload && state.payload.regime && state.payload.regime.regime === 'DEFENSIVE_CASH') || (stock.STATUS === 'CASH');

  renderActiveSignal(stock, alts, isDefensive);
  renderAllStocksTable(all, userCapital);
  openInspector();
  if (window.matchMedia('(min-width: 1024px)').matches) {
    const pane = document.getElementById('inspectorPane');
    if (pane) pane.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
}

/* ─── Credibility index (backtest scores for grid ranking) ─── */
function ensureCredIndex() {
  if (state.credIndexLoaded) return;
  state.credIndexLoaded = true;
  state.credIndex = state.credIndex || {};
  fetch('data/backtests/_index.json?_t=' + Date.now(), { cache: 'no-store' })
    .then(res => res.ok ? res.json() : null)
    .then(json => {
      const entries = (json && json.entries) || [];
      if (!entries.length) return;
      entries.forEach(e => { if (e && e.symbol) state.credIndex[String(e.symbol).toUpperCase()] = e; });
      renderAllStocksTable((state.payload && state.payload.all_qualified) || [], state.userCapital || DEFAULT_CAPITAL);
    })
    .catch(() => { /* index is optional; grid still works without it */ });
}

function wireGridSort() {
  document.querySelectorAll('.data-grid thead th[data-sort]').forEach(th => {
    const btn = th.querySelector('.sort-btn');
    if (!btn) return;
    btn.addEventListener('click', () => {
      const key = th.dataset.sort;
      if (state.sortKey === key) state.sortDir = state.sortDir === 'asc' ? 'desc' : 'asc';
      else { state.sortKey = key; state.sortDir = key === 'symbol' ? 'asc' : 'desc'; }
      const all = (state.payload && state.payload.all_qualified) || [];
      renderAllStocksTable(all, state.userCapital || store.get(LS.CURRENT_CAPITAL, DEFAULT_CAPITAL));
    });
  });
}

/* ─── Compounding & Equity ─── */
function renderCompounding() {
  const base = store.get(LS.CAPITAL_BASE, DEFAULT_CAPITAL);
  const current = store.get(LS.CURRENT_CAPITAL, base);
  const history = store.get(LS.CAPITAL_HISTORY, []);
  const sigHist = store.get(LS.SIGNAL_HISTORY, []);

  const disp = document.getElementById('capitalDisplay');
  const baseDisp = document.getElementById('capitalBaseDisp');
  if (disp) disp.textContent = fmtINR(current);
  if (baseDisp) baseDisp.textContent = 'Base ' + fmtINR(base);

  const gain = current - base;
  const gainPct = base > 0 ? (gain / base) * 100 : 0;
  const gainEl = document.getElementById('capitalGain');
  if (gainEl && base > 0) {
    gainEl.className = 'stat__value num ' + (gain >= 0 ? 'tone-bull' : 'tone-bear');
    gainEl.textContent = `${gain >= 0 ? '+' : ''}${fmtINR(gain)} (${gainPct >= 0 ? '+' : ''}${gainPct.toFixed(1)}%)`;
  }

  const trades = sigHist.length;
  const wins = sigHist.filter(s => s.pnl > 0).length;
  const winRate = trades ? ((wins / trades) * 100).toFixed(0) + '%' : '–';
  const st = document.getElementById('statTrades'); if (st) st.textContent = trades;
  const sw = document.getElementById('statWins'); if (sw) sw.textContent = wins;
  const swr = document.getElementById('statWinRate'); if (swr) swr.textContent = winRate;

  // Rotation plan — one capital base compounded by +15% cycles.
  const rotBase = document.getElementById('rotBase');
  if (rotBase) {
    rotBase.textContent = fmtINR(base);
    const rotEquity = document.getElementById('rotEquity');
    const rotCycles = document.getElementById('rotCycles');
    const rotNext = document.getElementById('rotNext');
    if (rotEquity) rotEquity.textContent = fmtINR(current);
    if (rotCycles) rotCycles.textContent = `${trades} (${wins} won)`;
    if (rotNext) rotNext.textContent = fmtINR(current * 1.15);

    const ladder = [1, 5, 10, 15, 20, 30, 52];
    const body = document.getElementById('rotLadder');
    if (body) body.innerHTML = ladder.map(n => {
      const eq = base * Math.pow(1.15, n);
      const ret = (eq / base - 1) * 100;
      return `<tr><td>${n}</td><td class="num">${fmtINR(eq)}</td><td class="num pos">+${ret.toFixed(0)}%</td></tr>`;
    }).join('');

    const note = document.getElementById('rotNote');
    if (note) {
      const double = Math.ceil(Math.LN2 / Math.log(1.15));
      note.textContent = `At +15% per cycle, capital doubles roughly every ${double} completed cycles when every target is hit. Cycle outcomes are recorded from your exits; stop-outs count as failed cycles.`;
    }
  }

  drawCapitalChart(history, base);
}

function drawCapitalChart(history, base) {
  const canvas = document.getElementById('capitalChart');
  const empty = document.getElementById('chartEmpty');
  if (!canvas || !empty) return;
  if (!history || history.length < 2) {
    canvas.style.display = 'none';
    empty.style.display = 'flex';
    return;
  }
  canvas.style.display = 'block';
  empty.style.display = 'none';

  const dpr = window.devicePixelRatio || 1;
  const W = canvas.parentElement.clientWidth || 360;
  const H = Math.max(180, Math.min(260, Math.round(W * 0.34)));
  canvas.width = W * dpr; canvas.height = H * dpr;
  canvas.style.width = W + 'px'; canvas.style.height = H + 'px';
  const ctx = canvas.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, W, H);

  const values = history.map(e => e.capital);
  const minV = Math.min.apply(null, values.concat(base)) * 0.99;
  const maxV = Math.max.apply(null, values.concat(base)) * 1.01;
  const range = (maxV - minV) || 1;
  const PAD_L = 56, PAD_R = 14, PAD_T = 14, PAD_B = 26;
  const cw = W - PAD_L - PAD_R, ch = H - PAD_T - PAD_B;
  const xOf = i => PAD_L + (values.length === 1 ? cw / 2 : (i / (values.length - 1)) * cw);
  const yOf = v => PAD_T + ch - ((v - minV) / range) * ch;
  const money = v => '₹' + Math.round(v).toLocaleString('en-IN');

  ctx.font = '10px ui-monospace, monospace';
  ctx.textAlign = 'right'; ctx.textBaseline = 'middle';
  for (let g = 0; g <= 4; g++) {
    const v = minV + range * (g / 4);
    const y = yOf(v);
    ctx.strokeStyle = 'rgba(255,255,255,0.05)';
    ctx.beginPath(); ctx.moveTo(PAD_L, y); ctx.lineTo(W - PAD_R, y); ctx.stroke();
    ctx.fillStyle = '#6E8095'; ctx.fillText(money(v), PAD_L - 8, y);
  }

  const baseY = yOf(base);
  ctx.setLineDash([4, 4]); ctx.strokeStyle = 'rgba(76,141,255,0.55)';
  ctx.beginPath(); ctx.moveTo(PAD_L, baseY); ctx.lineTo(W - PAD_R, baseY); ctx.stroke(); ctx.setLineDash([]);

  const up = values[values.length - 1] >= base;
  const grad = ctx.createLinearGradient(0, PAD_T, 0, PAD_T + ch);
  grad.addColorStop(0, up ? 'rgba(34,192,138,0.28)' : 'rgba(240,82,90,0.28)');
  grad.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.beginPath(); ctx.moveTo(xOf(0), yOf(values[0]));
  values.forEach((v, i) => { if (i > 0) ctx.lineTo(xOf(i), yOf(v)); });
  ctx.lineTo(xOf(values.length - 1), PAD_T + ch); ctx.lineTo(xOf(0), PAD_T + ch); ctx.closePath();
  ctx.fillStyle = grad; ctx.fill();

  ctx.beginPath(); ctx.moveTo(xOf(0), yOf(values[0]));
  values.forEach((v, i) => { if (i > 0) ctx.lineTo(xOf(i), yOf(v)); });
  ctx.strokeStyle = up ? '#22C08A' : '#F0525A'; ctx.lineWidth = 2; ctx.lineJoin = 'round'; ctx.stroke();

  values.forEach((v, i) => {
    ctx.beginPath(); ctx.arc(xOf(i), yOf(v), 2.5, 0, Math.PI * 2);
    ctx.fillStyle = v >= base ? '#22C08A' : '#F0525A'; ctx.fill();
  });

  ctx.textAlign = 'center'; ctx.textBaseline = 'top'; ctx.fillStyle = '#6E8095';
  const step = Math.max(1, Math.floor(history.length / 5));
  history.forEach((e, i) => {
    if (i % step === 0 || i === history.length - 1) {
      const d = new Date(e.date);
      ctx.fillText(d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' }), xOf(i), PAD_T + ch + 6);
    }
  });
}

/* ─── History ─── */
function renderHistory() {
  const list = document.getElementById('historyList');
  const history = store.get(LS.SIGNAL_HISTORY, []);

  if (list) {
    if (!history.length) {
      list.innerHTML = `<div class="empty-state"><svg class="ic ic--lg" aria-hidden="true"><use href="#i-history"/></svg><p>No closed trades recorded yet. Record an exit from the Portfolio tab to build your verified ledger.</p></div>`;
    } else {
      list.innerHTML = history.map(t => {
        const glyph = t.outcome === 'win' ? '▲' : t.outcome === 'loss' ? '▼' : '■';
        const cls = t.outcome === 'win' ? 'win' : t.outcome === 'loss' ? 'loss' : 'skip';
        const d = new Date(t.date);
        const dateStr = d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });
        return `
          <div class="history-item">
            <div class="hist-icon ${cls}" aria-hidden="true">${glyph}</div>
            <div class="hist-body">
              <div class="hist-symbol">${t.symbol}</div>
              <div class="hist-date">${dateStr} · ${t.shares} shares · ${fmtINR(t.entry)} → ${fmtINR(t.exit)}</div>
            </div>
            <div>
              <div class="hist-pnl ${t.pnl >= 0 ? 'pos' : 'neg'}">${t.pnl >= 0 ? '+' : ''}${fmtINR(t.pnl)}</div>
              <div class="hist-pct">${t.pct >= 0 ? '+' : ''}${t.pct.toFixed(2)}%</div>
            </div>
          </div>`;
      }).join('');
    }
  }

  const sessionsContainer = document.getElementById('historySessionsList');
  if (sessionsContainer) {
    const manifest = (state.payload && state.payload.history_manifest) || [];
    if (!manifest.length) {
      sessionsContainer.innerHTML = `<div class="empty-state"><p>No archived sessions available yet.</p></div>`;
    } else {
      sessionsContainer.innerHTML = manifest.map(m => {
        const isSelected = m.date === (state.selectedDate || (state.payload && state.payload.trade_date));
        const winner = (m.winner && m.winner !== 'CASH') ? m.winner : 'CASH';
        return `
          <div class="session-archive-item ${isSelected ? 'selected' : ''}" role="button" tabindex="0" data-date="${m.date}">
            <div>
              <div class="session-archive-date">${m.display_date || m.date} ${m.is_today ? '<span class="tag tag--prime">today</span>' : ''}</div>
              <div class="session-archive-meta">${m.total_qualified != null ? m.total_qualified + ' leaders qualified' : 'EOD bhavcopy snapshot'}</div>
            </div>
            <div class="session-archive-stats">
              <span>${winner}</span>
              ${m.cms ? `<span class="muted">CMS ${Number(m.cms).toFixed(1)}</span>` : ''}
            </div>
          </div>`;
      }).join('');
      sessionsContainer.querySelectorAll('.session-archive-item').forEach(el => {
        const go = () => { selectSessionDate(el.dataset.date); switchTab('Signal'); };
        el.addEventListener('click', go);
        el.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); go(); } });
      });
    }
  }
}

/* ─── Settings ─── */
function populateSettings() {
  const capInput = document.getElementById('inputCapitalBase');
  if (capInput) capInput.value = store.get(LS.CAPITAL_BASE, DEFAULT_CAPITAL);
  loadKiteSettings();
}

/* ─── Backtest credibility panel ─── */
function renderCredibility(symbol) {
  const card = document.getElementById('credCard');
  const grid = document.getElementById('credGrid');
  const verdict = document.getElementById('credVerdict');
  const foot = document.getElementById('credFoot');
  if (!card || !grid) return;
  if (!symbol) { card.hidden = true; return; }
  state.backtests = state.backtests || {};

  const paint = (r) => {
    card.hidden = false;
    if (!r) {
      if (verdict) { verdict.className = 'badge'; verdict.textContent = 'no report'; }
      grid.innerHTML = '<div class="cred-item"><small>Credibility</small><span>—</span></div>';
      if (foot) foot.textContent = `No backtest report for ${symbol}. Generate one with: python scripts/single_stock_backtest.py --symbol ${symbol}`;
      return;
    }
    const s = r.study || {}, sim = r.simulation || {}, v = r.verdict || {};
    const score = (v.score == null) ? '—' : v.score;
    if (verdict) {
      verdict.className = 'badge ' + (v.credible ? 'badge--bull' : 'badge--defensive');
      verdict.textContent = (v.credible ? 'Credible · ' : 'Low credibility · ') + score;
    }
    const item = (k, val, tone) => `<div class="cred-item ${tone || ''}"><small>${k}</small><span>${val}</span></div>`;
    grid.innerHTML = [
      item('+15% hit rate', s.target_hit_rate_pct != null ? s.target_hit_rate_pct + '%' : '—', s.target_hit_rate_pct >= 55 ? 'is-bull' : 'is-caution'),
      item('Stopped out', s.stop_hit_rate_pct != null ? s.stop_hit_rate_pct + '%' : '—', 'is-bear'),
      item('Expectancy', s.expectancy_pct != null ? (s.expectancy_pct >= 0 ? '+' : '') + s.expectancy_pct + '%' : '—', s.expectancy_pct >= 0 ? 'is-bull' : 'is-bear'),
      item('Signals tested', s.observations != null ? s.observations : '—'),
      item('Avg hold → target', s.avg_hold_to_target_days != null ? s.avg_hold_to_target_days + 'd' : '—'),
      item('Median days → +15%', (s.time_to_target && s.time_to_target.trading_days)
        ? `${s.time_to_target.trading_days.median}d (${s.time_to_target.calendar_days.median} cal)` : '—'),
      item('Rotation cycles', sim.cycles != null ? sim.cycles : '—'),
      item('Sim ₹1k →', sim.final_capital != null ? fmtINR(sim.final_capital) : '—', sim.total_return_pct >= 0 ? 'is-bull' : 'is-bear'),
      item('Sim return', sim.total_return_pct != null ? (sim.total_return_pct >= 0 ? '+' : '') + sim.total_return_pct + '%' : '—', sim.total_return_pct >= 0 ? 'is-bull' : 'is-bear'),
    ].join('');
    if (foot) foot.textContent = (v.summary || '') + (r.period ? `  ·  backtested ${r.period.start} → ${r.period.end}` : '');
  };

  if (state.backtests[symbol] !== undefined) { paint(state.backtests[symbol]); return; }
  card.hidden = false;
  grid.innerHTML = '<div class="cred-item"><small>Backtest</small><span>loading…</span></div>';
  if (foot) foot.textContent = '';
  fetch(`data/backtests/${encodeURIComponent(symbol)}.json?_t=` + Date.now(), { cache: 'no-store' })
    .then(res => res.ok ? res.json() : null)
    .then(json => { state.backtests[symbol] = json; paint(json); })
    .catch(() => { state.backtests[symbol] = null; paint(null); });
}

/* ─── Live target tracker (single purchased stock) ─── */
const LS_LIVE = 'nse_live_stock';
const LS_TD_KEY = 'nse_twelvedata_key';
const LS_PROXY = 'nse_live_proxy';

/**
 * Yahoo Finance WebSocket Protobuf Decoder (Zero-dependency, browser-native)
 * Decodes the PricingData binary payload streamed from wss://streamer.finance.yahoo.com/
 */
function decodeYahooProtobuf(base64Str) {
  if (!base64Str) return null;
  try {
    const binaryString = atob(base64Str);
    const len = binaryString.length;
    const bytes = new Uint8Array(len);
    for (let i = 0; i < len; i++) {
      bytes[i] = binaryString.charCodeAt(i);
    }
    const view = new DataView(bytes.buffer);
    let pos = 0;
    const result = {};

    while (pos < bytes.length) {
      const key = bytes[pos++];
      const wireType = key & 0x07;
      const fieldNumber = key >> 3;

      if (wireType === 0) { // Varint
        let val = 0;
        let shift = 0;
        while (pos < bytes.length) {
          const b = bytes[pos++];
          val |= (b & 0x7f) << shift;
          if ((b & 0x80) === 0) break;
          shift += 7;
        }
        result['f_' + fieldNumber] = val;
      } else if (wireType === 5) { // 32-bit float
        if (pos + 4 <= bytes.length) {
          const val = view.getFloat32(pos, true); // little-endian
          pos += 4;
          if (fieldNumber === 2) result.price = val;
          else if (fieldNumber === 8) result.changePercent = val;
          else if (fieldNumber === 10) result.dayHigh = val;
          else if (fieldNumber === 11) result.dayLow = val;
          else if (fieldNumber === 12) result.change = val;
        } else break;
      } else if (wireType === 2) { // Length-delimited string
        let strLen = 0;
        let shift = 0;
        while (pos < bytes.length) {
          const b = bytes[pos++];
          strLen |= (b & 0x7f) << shift;
          if ((b & 0x80) === 0) break;
          shift += 7;
        }
        let str = '';
        for (let i = 0; i < strLen && (pos + i) < bytes.length; i++) {
          str += String.fromCharCode(bytes[pos + i]);
        }
        pos += strLen;
        if (fieldNumber === 1) result.id = str;
        else if (fieldNumber === 4) result.currency = str;
        else if (fieldNumber === 5) result.exchange = str;
      } else if (wireType === 1) { // 64-bit double
        pos += 8;
      } else {
        break;
      }
    }
    return result;
  } catch (_) {
    return null;
  }
}

let yahooWs = null;
let yahooWsReconnectTimer = null;
const LS_WATCHLIST = 'nse_portfolio_watchlist_v2';

function toYahooSymbol(sym) {
  const s = String(sym || '').trim().toUpperCase();
  if (!s) return '';
  if (s.startsWith('^') || s.includes('.')) return s;
  return s + '.NS';
}

function getTrackedStocks() {
  let list = store.get(LS_WATCHLIST, null);
  if (!Array.isArray(list)) {
    const legacy = store.get(LS_LIVE, null);
    if (legacy && legacy.symbol && parseFloat(legacy.entry) > 0) {
      list = [{
        id: 'pos_' + Date.now(),
        symbol: legacy.symbol.toUpperCase(),
        entry: parseFloat(legacy.entry),
        capital: parseFloat(legacy.capital) || 10000,
        targetPct: parseFloat(legacy.targetPct) || 15
      }];
    } else {
      list = [];
    }
  }
  // Sanitize: remove any corrupted or oversized entries (e.g. pasted docs)
  const valid = list.filter(item => {
    if (!item || !item.symbol) return false;
    const s = String(item.symbol).trim();
    return s.length >= 1 && s.length <= 20 && !s.includes('\n') && !s.includes('#') && /^[A-Z0-9&\-_.]+$/i.test(s);
  });
  if (valid.length !== list.length) {
    store.set(LS_WATCHLIST, valid);
  }
  return valid;
}

function saveTrackedStocks(list) {
  store.set(LS_WATCHLIST, list);
  if (list.length > 0) {
    store.set(LS_LIVE, list[0]);
  } else {
    store.remove(LS_LIVE);
  }
  syncAllStreams();
}

function getAllSubscribedSymbols() {
  const set = new Set(['^CRSLDX', '^NSEI']); // Benchmark always subscribed!
  // Active / inspected stock
  if (state.activeStock && state.activeStock.SYMBOL) {
    const ySym = toYahooSymbol(state.activeStock.SYMBOL);
    if (ySym) set.add(ySym);
  }
  // Hero leader
  if (state.signalData && state.signalData[0] && state.signalData[0].SYMBOL) {
    const ySym = toYahooSymbol(state.signalData[0].SYMBOL);
    if (ySym) set.add(ySym);
  }
  // Top 10 leaders from screener payload
  const all = (state.payload && (state.payload.all_qualified || state.payload.stocks)) || [];
  for (let i = 0; i < Math.min(10, all.length); i++) {
    const s = all[i];
    const sym = s && (s.SYMBOL || s.symbol);
    if (sym) {
      const ySym = toYahooSymbol(sym);
      if (ySym) set.add(ySym);
    }
  }
  // All tracked watchlist stocks
  const list = getTrackedStocks();
  for (const item of list) {
    const ySym = toYahooSymbol(item.symbol);
    if (ySym) set.add(ySym);
  }
  return Array.from(set);
}

function syncAllStreams() {
  const symbols = getAllSubscribedSymbols();
  if (yahooWs && yahooWs.readyState === WebSocket.OPEN) {
    try {
      yahooWs.send(JSON.stringify({ subscribe: symbols }));
      return;
    } catch (_) {}
  }
  connectYahooMultiStream();
}

function connectYahooMultiStream() {
  clearTimeout(yahooWsReconnectTimer);
  const symbols = getAllSubscribedSymbols();

  if (yahooWs) {
    try { yahooWs.close(); } catch (_) {}
    yahooWs = null;
  }

  try {
    yahooWs = new WebSocket('wss://streamer.finance.yahoo.com/');

    yahooWs.onopen = () => {
      yahooWs.send(JSON.stringify({ subscribe: symbols }));
    };

    yahooWs.onmessage = (event) => {
      try {
        const tick = decodeYahooProtobuf(event.data);
        if (!tick || tick.price == null || isNaN(tick.price)) return;
        const roundedPrice = parseFloat(tick.price.toFixed(2));
        
        if (!state.liveWsQuotes) state.liveWsQuotes = {};
        state.liveWsQuotes[tick.id] = {
          symbol: tick.id,
          price: roundedPrice,
          change: tick.change,
          changePercent: tick.changePercent,
          time: Date.now()
        };

        if (tick.id === '^CRSLDX' || tick.id === '^NSEI') {
          handleBenchmarkTick(roundedPrice);
        } else {
          handleStockTick(tick.id, roundedPrice);
        }
      } catch (_) {}
    };

    yahooWs.onerror = () => {};
    yahooWs.onclose = () => {
      yahooWs = null;
      if (document.visibilityState === 'visible') {
        yahooWsReconnectTimer = setTimeout(connectYahooMultiStream, 5000);
      }
    };
  } catch (_) {}
}

function handleStockTick(tickerId, livePrice) {
  const sym = String(tickerId || '').replace(/\.NS$/i, '').toUpperCase();
  if (!sym) return;

  // 1. Update active / hero if matching
  if (state.signalData && state.signalData[0] && state.signalData[0].SYMBOL.toUpperCase() === sym) {
    state.signalData[0].CMP = livePrice;
    const heroCmp = document.querySelector('.hero-cmp');
    if (heroCmp) {
      heroCmp.textContent = fmtINR(livePrice);
    }
  }

  // 2. Update Inspector if open for this symbol
  if (state.activeStock && state.activeStock.SYMBOL.toUpperCase() === sym) {
    state.activeStock.CMP = livePrice;
    const insCmp = document.querySelector('.ins-cmp');
    if (insCmp) {
      insCmp.textContent = fmtINR(livePrice);
    }
    const entryInput = document.getElementById('inputActualEntry');
    const entryVal = parseFloat(entryInput && entryInput.value) || livePrice;
    recalculateFromEntry(entryVal);
  }

  // 3. Update table row CMP if visible
  const row = document.querySelector(`tr[data-symbol="${sym}"]`);
  if (row) {
    const cmpCell = row.querySelector('td[data-label="CMP"]');
    if (cmpCell) {
      cmpCell.textContent = fmtINR(livePrice);
    }
  }

  // 4. Update Portfolio Tab Watchlist
  if (state.currentTab === 'Portfolio') {
    renderLiveTracker();
  }
}

function handleBenchmarkTick(liveCmp) {
  state.liveNiftyCmp = liveCmp;
  const cmpStr = fmtINR(liveCmp);
  const regime = (state.payload && state.payload.regime) || {};
  regime.nifty_cmp = liveCmp;
  const sma50 = regime.sma_50 || 23223.03;
  const sma200 = regime.sma_200 || 22974.87;

  let currentRegime = 'DEFENSIVE_CASH';
  let isBull = false;
  let isCaution = false;
  if (liveCmp >= sma50) {
    currentRegime = 'BULL_MARKET';
    isBull = true;
  } else if (liveCmp >= sma200) {
    currentRegime = 'CORRECTION_WATCH';
    isCaution = true;
  }
  regime.regime = currentRegime;
  const stateWord = isBull ? 'bull' : isCaution ? 'caution' : 'defensive';

  // Desktop header pill
  const ticker = document.getElementById('headerRegimeTicker');
  const tickerText = document.getElementById('headerRegimeText');
  if (ticker && tickerText) {
    ticker.className = 'header-regime is-active ' + stateWord;
    tickerText.innerHTML = `NIFTY 500 ${cmpStr} · ${isBull ? 'BULL' : isCaution ? 'CORRECTION' : 'DEFENSIVE'} <span style="color:var(--accent);font-weight:700;margin-left:4px;font-size:0.72rem;">⚡ Live</span>`;
  }

  // Terminal regime banner
  const title = document.getElementById('regimeTitle');
  const badge = document.getElementById('regimeBadge');
  const bar = document.getElementById('regimeBanner');
  if (title) title.innerHTML = `Nifty 500 ${cmpStr} <span style="font-size:0.72rem;color:var(--accent);vertical-align:middle;margin-left:4px;">⚡ Live</span>`;
  if (badge) {
    badge.className = 'badge badge--' + stateWord;
    badge.textContent = (isBull ? 'Bull market' : isCaution ? 'Correction watch' : 'Defensive cash') + ' · ⚡ Live';
  }
  if (bar) bar.className = 'regime-bar ' + stateWord;
}

/** Classify a live price against the rotation target / stop. */
function liveStatus(entry, cmp, targetPct, stopPct) {
  const t = targetPct / 100, s = (stopPct == null ? 6 : stopPct) / 100;
  const targetPrice = entry * (1 + t);
  const stopPrice = entry * (1 - s);
  const pnlPct = entry > 0 ? ((cmp - entry) / entry) * 100 : 0;
  const toTarget = cmp > 0 ? ((targetPrice - cmp) / cmp) * 100 : 0;
  let status = 'holding';
  if (cmp <= stopPrice) status = 'stopped';
  else if (cmp >= targetPrice) status = 'hit';
  else if (pnlPct >= t * 100 * 0.70) status = 'near';
  return { status, pnlPct, toTarget, targetPrice, stopPrice };
}

async function fetchLiveQuote(symbol) {
  const sym = String(symbol || '').toUpperCase();
  const symNs = toYahooSymbol(sym);
  const errors = [];

  // 0) Yahoo WebSocket live tick cache (real-time sub-second streaming)
  if (state.liveWsQuotes && state.liveWsQuotes[symNs] && (Date.now() - state.liveWsQuotes[symNs].time < 300000)) {
    return { price: state.liveWsQuotes[symNs].price, source: '⚡ Live Stream' };
  }

  // 1) Twelve Data — free key, browser-side, CORS-friendly.
  const key = store.get(LS_TD_KEY, '');
  if (key) {
    try {
      const url = `https://api.twelvedata.com/price?symbol=${encodeURIComponent(sym)}&exchange=NSE&apikey=${encodeURIComponent(key)}`;
      const res = await fetch(url, { cache: 'no-store' });
      const json = await res.json();
      if (json && json.price && !isNaN(parseFloat(json.price))) {
        return { price: parseFloat(json.price), source: 'Twelve Data · live' };
      }
      errors.push(json && json.message ? json.message : 'Twelve Data: no price');
    } catch (_) { errors.push('Twelve Data unreachable'); }
  }

  // 2) Self-hosted Cloudflare Worker proxy — keyless, no cron.
  const proxy = store.get(LS_PROXY, '');
  if (proxy) {
    try {
      const base = String(proxy).replace(/\/+$/, '');
      const res = await fetch(`${base}/?symbol=${encodeURIComponent(symNs)}`, { cache: 'no-store' });
      const json = await res.json();
      if (json && json.price != null && !isNaN(parseFloat(json.price))) {
        return { price: parseFloat(json.price), source: 'Worker proxy · live' };
      }
      errors.push(json && json.error ? ('proxy: ' + json.error) : 'proxy: no price');
    } catch (_) { errors.push('proxy unreachable'); }
  }

  // 3) The scheduled tracker's price (near-live, no key needed).
  try {
    const res = await fetch('data/targets.json?_t=' + Date.now(), { cache: 'no-store' });
    if (res.ok) {
      const json = await res.json();
      const e = (json.entries || []).find(x => String(x.symbol).toUpperCase() === sym);
      if (e && e.cmp != null) return { price: parseFloat(e.cmp), source: 'Scheduled tracker' };
    }
  } catch (_) { /* optional */ }

  // 4) Latest screening price for this symbol.
  const all = (state.payload && state.payload.all_qualified) || [];
  const hit = all.find(s => String(s.SYMBOL).toUpperCase() === sym);
  if (hit && hit.CMP) return { price: parseFloat(hit.CMP), source: 'Screen close' };

  throw new Error(errors.length ? errors[0]
    : 'Waiting for market stream or set a free Twelve Data / Worker proxy fallback');
}

function renderLiveTracker() {
  const body = document.getElementById('liveBody');
  const countBadge = document.getElementById('liveCountBadge');
  if (!body) return;

  const list = getTrackedStocks();
  if (countBadge) countBadge.innerHTML = `${list.length} tracked <span style="margin-left:6px;color:var(--accent);font-weight:700;font-size:0.75rem;">⚡ 1s Live Stream</span>`;

  if (!list.length) {
    body.innerHTML = `
      <div style="text-align:center;padding:24px 12px;" class="muted">
        <svg class="ic ic--lg" style="margin-bottom:8px;opacity:0.5;" aria-hidden="true"><use href="#i-portfolio"/></svg>
        <p>No stocks in watchlist yet. Enter a symbol above or tap <strong>Track this stock</strong> on any leader in the Terminal.</p>
      </div>`;
    syncAllStreams();
    return;
  }

  const isDefensive = (state.payload && state.payload.regime && state.payload.regime.regime === 'DEFENSIVE_CASH');

  body.innerHTML = list.map((item, idx) => {
    const ySym = toYahooSymbol(item.symbol);
    const cached = state.liveWsQuotes && state.liveWsQuotes[ySym];
    let cmp = cached ? cached.price : null;
    let source = cached ? '⚡ Live Stream' : 'Screen close';

    if (cmp == null) {
      const all = (state.payload && state.payload.all_qualified) || [];
      const hit = all.find(s => String(s.SYMBOL).toUpperCase() === item.symbol.toUpperCase());
      if (hit && hit.CMP) cmp = parseFloat(hit.CMP);
    }
    if (cmp == null) {
      cmp = item.entry;
      source = 'Entry price';
    }

    const targetPct = item.targetPct || 15;
    const stopPct = isDefensive ? 4 : 6;
    const { status, pnlPct, toTarget, targetPrice, stopPrice } = liveStatus(item.entry, cmp, targetPct, stopPct);
    const badgeCls = { hit: 'badge--bull', near: 'badge--caution', stopped: 'badge--defensive', holding: 'badge--muted' }[status];
    const badgeTxt = { hit: '✅ TARGET HIT', near: 'Approaching', stopped: 'Stopped out', holding: 'Holding' }[status];

    const cap = parseFloat(item.capital) > 0 ? parseFloat(item.capital) : 0;
    const shares = (cap > 0 && item.entry > 0) ? Math.floor(cap / item.entry) : 0;
    const pnlINR = shares > 0 ? (cmp - item.entry) * shares : null;
    const curVal = shares > 0 ? cmp * shares : null;
    const tone = pnlPct >= 0 ? 'pos' : 'neg';

    const pnlDisp = pnlINR != null 
      ? `<span class="num ${tone} live-pnl-inr">${pnlINR >= 0 ? '+' : ''}${fmtINR(pnlINR)} (${pnlPct >= 0 ? '+' : ''}${pnlPct.toFixed(2)}%)</span>`
      : `<span class="num ${tone}">${pnlPct >= 0 ? '+' : ''}${pnlPct.toFixed(2)}%</span>`;

    return `
      <div class="watchlist-card" data-stock-id="${item.id || idx}">
        <div class="watchlist-card__head">
          <div style="display:flex;align-items:center;gap:10px;">
            <strong style="font-size:1.15rem;letter-spacing:0.02em;">${item.symbol}</strong>
            <span class="badge ${badgeCls}">${badgeTxt}</span>
            ${cached ? '<span class="badge badge--bull" style="font-size:0.65rem;">⚡ 1s Live</span>' : ''}
          </div>
          <div style="display:flex;align-items:baseline;gap:8px;">
            <span class="live-price" style="font-size:1.35rem;">${fmtINR(cmp)}</span>
            ${pnlDisp}
          </div>
        </div>

        <div class="rotation-grid">
          <div class="rstat"><span class="rstat__k">Target (+${targetPct}%)</span><span class="rstat__v tone-bull">${fmtINR(targetPrice)}</span></div>
          <div class="rstat"><span class="rstat__k">To target</span><span class="rstat__v ${toTarget <= 0 ? 'tone-bull' : ''}">${toTarget >= 0 ? '' : '+'}${toTarget.toFixed(2)}%</span></div>
          <div class="rstat"><span class="rstat__k">Stop (${isDefensive ? '−4%' : '−6%'})</span><span class="rstat__v tone-bear">${fmtINR(stopPrice)}</span></div>
          <div class="rstat"><span class="rstat__k">Entry fill</span><span class="rstat__v">${fmtINR(item.entry)}</span></div>
          ${shares > 0 ? `
          <div class="rstat"><span class="rstat__k">Position value</span><span class="rstat__v">${fmtINR(curVal)}</span></div>
          <div class="rstat"><span class="rstat__k">Qty &amp; Capital</span><span class="rstat__v">${shares} sh (${fmtINR(cap)})</span></div>
          ` : ''}
        </div>

        <div class="watchlist-card__actions">
          <span class="live-meta">${source}</span>
          <div style="display:flex;gap:6px;">
            <button class="btn btn--primary btn--sm btn-card-exit" data-idx="${idx}">
              <svg class="ic" aria-hidden="true"><use href="#i-portfolio"/></svg> Record exit
            </button>
            <button class="btn btn--ghost btn--sm btn-card-remove" data-idx="${idx}" title="Remove from watchlist">
              <svg class="ic" aria-hidden="true"><use href="#i-close"/></svg>
            </button>
          </div>
        </div>
      </div>`;
  }).join('');

  // Wire card buttons
  body.querySelectorAll('.btn-card-exit').forEach(btn => {
    btn.addEventListener('click', () => {
      const idx = parseInt(btn.dataset.idx);
      const item = list[idx];
      if (!item) return;
      const ySym = toYahooSymbol(item.symbol);
      const cached = state.liveWsQuotes && state.liveWsQuotes[ySym];
      const exitPrice = cached ? cached.price : item.entry;
      const cap = parseFloat(item.capital) || 0;
      const shares = (cap > 0 && item.entry > 0) ? Math.floor(cap / item.entry) : 1;
      openExitModal({
        symbol: item.symbol,
        entry: item.entry,
        exit: exitPrice,
        shares: shares
      });
    });
  });

  body.querySelectorAll('.btn-card-remove').forEach(btn => {
    btn.addEventListener('click', () => {
      const idx = parseInt(btn.dataset.idx);
      const item = list[idx];
      if (!item) return;
      list.splice(idx, 1);
      saveTrackedStocks(list);
      showToast(`Removed ${item.symbol} from watchlist`, 'info');
      renderLiveTracker();
    });
  });

  syncAllStreams();
}

function wireLiveTracker() {
  const symInput = document.getElementById('liveSymbol');
  const entryInput = document.getElementById('liveEntry');
  const capInput = document.getElementById('liveCapital');
  const tgtInput = document.getElementById('liveTargetPct');

  const base = store.get(LS.CAPITAL_BASE, DEFAULT_CAPITAL);
  const currentCap = store.get(LS.CURRENT_CAPITAL, base);

  if (capInput && !capInput.value) capInput.value = currentCap;
  if (tgtInput && !tgtInput.value) tgtInput.value = 15;

  const saveBtn = document.getElementById('btnLiveSave');
  if (saveBtn) saveBtn.addEventListener('click', () => {
    let symbol = (symInput && symInput.value || '').trim().toUpperCase();
    symbol = symbol.replace(/^(NSE:|BOM:)/i, '').replace(/\.NS$/i, '');
    let entry = parseFloat(entryInput && entryInput.value);
    const capital = parseFloat(capInput && capInput.value) || currentCap;
    const targetPct = parseFloat(tgtInput && tgtInput.value) || 15;

    // Strict validation
    if (!symbol || !/^[A-Z0-9&\-_]{1,20}$/.test(symbol)) {
      showToast('Enter a valid stock symbol (e.g. REDINGTON, CUPID)', 'error');
      if (symInput) symInput.focus();
      return;
    }

    // Auto-fill CMP from current screener payload if entry was left empty
    if (!(entry > 0)) {
      const all = (state.payload && state.payload.all_qualified) || [];
      const match = all.find(s => s.SYMBOL.toUpperCase() === symbol);
      if (match && parseFloat(match.CMP) > 0) {
        entry = parseFloat(match.CMP);
        showToast(`Auto-filled entry at CMP ₹${entry.toFixed(2)} for ${symbol}`, 'info');
      } else {
        showToast('Please enter an entry fill price (₹)', 'error');
        if (entryInput) entryInput.focus();
        return;
      }
    }

    const list = getTrackedStocks();
    const existing = list.findIndex(x => x.symbol.toUpperCase() === symbol);
    if (existing >= 0) {
      list[existing] = { id: list[existing].id || ('pos_' + Date.now()), symbol, entry, capital, targetPct };
      showToast(`Updated ${symbol} in watchlist`, 'success', '🎯');
    } else {
      list.push({ id: 'pos_' + Date.now(), symbol, entry, capital, targetPct });
      showToast(`Added ${symbol} to watchlist`, 'success', '🎯');
    }
    saveTrackedStocks(list);
    if (symInput) symInput.value = '';
    if (entryInput) entryInput.value = '';
    renderLiveTracker();
  });

  const clearBtn = document.getElementById('btnLiveClear');
  if (clearBtn) clearBtn.addEventListener('click', () => {
    const list = getTrackedStocks();
    if (!list.length) return;
    if (confirm('Clear all stocks from your watchlist?')) {
      saveTrackedStocks([]);
      showToast('Watchlist cleared', 'info');
      renderLiveTracker();
    }
  });

  const refreshBtn = document.getElementById('btnLiveRefresh');
  if (refreshBtn) refreshBtn.addEventListener('click', () => {
    syncAllStreams();
    showToast('Refreshing live stream…', 'info', '⚡');
    renderLiveTracker();
  });

  const proxyInput = document.getElementById('liveProxyUrl');
  if (proxyInput) { const p = store.get(LS_PROXY, ''); if (p) proxyInput.value = p; }

  const keyBtn = document.getElementById('btnLiveSaveKey');
  if (keyBtn) keyBtn.addEventListener('click', () => {
    const keyInput = document.getElementById('liveApiKey');
    const key = (keyInput && keyInput.value || '').trim();
    const proxy = (proxyInput && proxyInput.value || '').trim();
    store.set(LS_TD_KEY, key);
    store.set(LS_PROXY, proxy);
    showToast('Live-quote settings saved', 'success');
    renderLiveTracker();
  });

  // Reconnect stream when browser tab becomes active
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') {
      syncAllStreams();
    }
  });

  // 1-Tap quick track button from Signal execution ticket
  const quickTrackBtn = document.getElementById('btnQuickTrack');
  if (quickTrackBtn) {
    quickTrackBtn.addEventListener('click', () => {
      const leader = state.inspectedStock || (state.signalData && state.signalData[0]) || (state.payload && state.payload.all_qualified && state.payload.all_qualified[0]);
      if (!leader || !leader.SYMBOL) {
        showToast('No active signal to track', 'info');
        return;
      }
      const actualInput = document.getElementById('inputActualEntry');
      const entryPrice = parseFloat(actualInput && actualInput.value) || parseFloat(leader.CMP);
      const cap = store.get(LS.CURRENT_CAPITAL, base);

      const list = getTrackedStocks();
      const existing = list.findIndex(x => x.symbol.toUpperCase() === leader.SYMBOL.toUpperCase());
      if (existing >= 0) {
        list[existing].entry = entryPrice;
        list[existing].capital = cap;
      } else {
        list.push({
          id: 'pos_' + Date.now(),
          symbol: leader.SYMBOL,
          entry: entryPrice,
          capital: cap,
          targetPct: 15
        });
      }
      saveTrackedStocks(list);
      showToast(`Tracking ${leader.SYMBOL} in Portfolio Watchlist`, 'success', '⚡');
      switchTab('Portfolio');
    });
  }

  // Start always-on multi-stream
  syncAllStreams();
  renderLiveTracker();
  if (!state.liveTimer) {
    state.liveTimer = setInterval(() => {
      if (document.visibilityState === 'visible') {
        if (state.currentTab === 'Portfolio') renderLiveTracker();
      }
    }, 1000);
  }
}

/* ─── Extra wiring ─── */
(function wireV2() {
  wireGridSort();
  wireLiveTracker();
  closeInspectorBtn();
  const topClose = document.getElementById('btnCancelExitTop');
  if (topClose) topClose.addEventListener('click', closeExitModal);

  // Restore saved active tab on refresh (e.g. Portfolio)
  try {
    const savedTab = sessionStorage.getItem('nse_active_tab');
    if (savedTab && savedTab !== 'Signal') {
      switchTab(savedTab);
    }
  } catch (_) {}
})();
