/* ═══════════════════════════════════════════════════════
   NSE Signal – app.js
   Full application logic for the PWA
═══════════════════════════════════════════════════════ */

'use strict';

/* ─── Constants ─── */
const LS = {
  SHEET_URL:       'nse_sheet_url',
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

document.querySelectorAll('.nav-item').forEach(item => {
  item.addEventListener('click', () => switchTab(item.dataset.tab));
});

function switchTab(name) {
  state.currentTab = name;
  document.querySelectorAll('.nav-item').forEach(n => {
    n.classList.toggle('active', n.dataset.tab === name);
  });
  document.querySelectorAll('.tab-panel').forEach(p => {
    p.classList.toggle('active', p.id === 'tab' + name);
  });
  if (name === 'Portfolio') renderPortfolio();
  if (name === 'History')   renderHistory();
  if (name === 'Settings')  populateSettings();
}

/* ══════════════════════════════════════════════════════
   DATA FETCHING
══════════════════════════════════════════════════════ */

async function fetchSignal(showLoading = true) {
  if (state.refreshing) return;
  if (showLoading) { setRefreshing(true); showSkeleton(true); }

  // Purge legacy Google Sheets setting to ensure 100% native serverless pipeline
  try {
    localStorage.removeItem(LS.SHEET_URL);
  } catch (_) {}

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
      let manifest = payload.history_manifest;
      renderSessionSwitcher(manifest, payload.trade_date);
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
        renderSessionSwitcher(cached.payload.history_manifest, cached.payload.trade_date);
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
  const banner = document.getElementById('regimeBanner');
  if (!banner) return;
  if (!regime) {
    banner.style.display = 'none';
    return;
  }
  banner.style.display = 'block';
  const title = document.getElementById('regimeTitle');
  const badge = document.getElementById('regimeBadge');
  const desc = document.getElementById('regimeDesc');

  banner.className = 'card regime-card';
  badge.className = 'badge';

  const cmpStr = regime.nifty_cmp ? '₹' + Number(regime.nifty_cmp).toLocaleString('en-IN') : '–';

  if (regime.regime === 'BULL_MARKET') {
    banner.classList.add('bull');
    badge.classList.add('badge-bull');
    badge.textContent = '🟢 BULL REGIME';
    title.textContent = `Nifty 50: ${cmpStr}`;
    desc.textContent = regime.description || 'Confirmed uptrend. Aggressive momentum active.';
  } else if (regime.regime === 'CORRECTION_WATCH') {
    banner.classList.add('caution');
    badge.classList.add('badge-caution');
    badge.textContent = '🟡 CORRECTION WATCH';
    title.textContent = `Nifty 50: ${cmpStr}`;
    desc.textContent = regime.description || 'Market pullback. Conservative entries only.';
  } else {
    banner.classList.add('defensive');
    badge.classList.add('badge-defensive');
    badge.textContent = '🛡️ DEFENSIVE CASH';
    title.textContent = `Nifty 50: ${cmpStr}`;
    desc.textContent = regime.description || 'Nifty below moving averages. 100% Capital preserved in CASH.';
  }
}

/* ══════════════════════════════════════════════════════
   SIGNAL RENDERING
══════════════════════════════════════════════════════ */

function renderSignal(rows, overrideReason = null) {
  showSkeleton(false);
  const hero  = rows[0];
  const alts  = rows.slice(1);
  const total = hero ? (hero.TOTAL_QUALIFIED || '–') : '–';

  // Qualified banner
  const qBanner = document.getElementById('qualBanner');
  qBanner.style.display = 'flex';
  document.getElementById('totalQualified').textContent = total;

  if (!hero || hero.STATUS === 'CASH' || !hero.SYMBOL || hero.SYMBOL === '—') {
    renderCashState(hero, overrideReason);
    return;
  }

  renderActiveSignal(hero, alts);
}

function renderCashState(hero, overrideMsg = null) {
  const heroCard = document.getElementById('heroCard');
  heroCard.className = 'card signal-hero';
  heroCard.innerHTML = `
    <div class="status-badge cash">🛡️ 100% CASH</div>
    <div class="cash-state">
      <div class="cash-icon">🏦</div>
      <div class="cash-label">${overrideMsg || 'Preserve Capital: Market in Defensive Mode'}</div>
      <div class="cash-sub">${hero && hero.TIMESTAMP ? 'Screened: ' + hero.TIMESTAMP : 'Stay patient. Momentum will come.'}</div>
    </div>
  `;
  document.getElementById('rsiCard').style.display  = 'none';
  document.getElementById('gttCard').style.display  = 'none';
  document.getElementById('altsCard').style.display = 'none';
  showSkeleton(false);
}

function renderActiveSignal(h, alts) {
  const heroCard = document.getElementById('heroCard');
  heroCard.className = 'card signal-hero glowing';

  const cmp = parseFloat(h.CMP);
  const cms = parseFloat(h.CMS_SCORE);
  const roc1 = fmtPct(h.ROC_1M);
  const roc2 = fmtPct(h.ROC_2M);
  const roc3 = fmtPct(h.ROC_3M);

  heroCard.innerHTML = `
    <div class="status-badge active">🟢 ACTIVE SIGNAL</div>
    <div class="hero-symbol">${h.SYMBOL}</div>
    <div class="hero-cmp">${fmtINR(cmp)}</div>
    <div class="hero-meta">
      <span class="meta-chip cms-chip">🏆 CMS ${isNaN(cms) ? h.CMS_SCORE : cms.toFixed(1)}</span>
      <span class="meta-chip"><span style="color:var(--text-dim); font-size:0.65rem;">RSI</span> ${parseFloat(h.RSI_14).toFixed(1)}</span>
      <span class="meta-chip"><span style="color:var(--text-dim); font-size:0.65rem;">52W High</span> ${fmtINR(h.HIGH_52W)}</span>
      <span class="meta-chip"><span style="color:var(--text-dim); font-size:0.65rem;">ATR</span> ${parseFloat(h.ATR_14).toFixed(2)}</span>
    </div>
  `;

  // RSI Gauge
  const rsiVal = parseFloat(h.RSI_14);
  renderRSIGauge(rsiVal);
  document.getElementById('rsiCard').style.display = 'block';

  // ROC Row
  const rocRow = document.getElementById('rocRow');
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

  // SMA Row
  const smaRow = document.getElementById('smaRow');
  const sma50  = parseFloat(h.SMA_50);
  const sma200 = parseFloat(h.SMA_200);
  const aboveSma50  = cmp > sma50;
  const aboveSma200 = cmp > sma200;
  smaRow.innerHTML = `
    <div class="sma-item">
      <div class="sma-label">SMA 50</div>
      <div class="sma-val" style="color:${aboveSma50 ? 'var(--accent)' : 'var(--red)'}">
        ${fmtINR(sma50)}</div>
    </div>
    <div class="sma-item">
      <div class="sma-label">SMA 200</div>
      <div class="sma-val" style="color:${aboveSma200 ? 'var(--accent)' : 'var(--red)'}">
        ${fmtINR(sma200)}</div>
    </div>
  `;

  // GTT Table
  renderGTT(h);

  // Alternates
  renderAlternates(alts);
}

function renderRSIGauge(rsi) {
  const needle = document.getElementById('rsiNeedle');
  const label  = document.getElementById('rsiValueLabel');
  if (!needle || isNaN(rsi)) return;

  // Map RSI 0–100 → -90° to +90° (semicircle)
  const angle = ((Math.min(Math.max(rsi, 0), 100) / 100) * 180) - 90;
  needle.setAttribute('transform', `rotate(${angle}, 80, 80)`);

  let color = 'var(--text)';
  if (rsi < 30)       color = 'var(--red)';
  else if (rsi > 70)  color = 'var(--yellow)';
  else                color = 'var(--accent)';

  label.textContent = rsi.toFixed(1);
  label.style.color = color;
}

function renderGTT(h) {
  state.activeStock = h;
  const gttCard = document.getElementById('gttCard');
  const entryInput = document.getElementById('inputActualEntry');
  const currentEntry = parseFloat(h.ACTUAL_ENTRY || h.CMP);

  if (entryInput) {
    entryInput.value = currentEntry;
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

  // 1. Calculate gap pct
  const gapPct = ((entry - cmp) / cmp) * 100;
  const gapBadge = document.getElementById('gapBadge');
  const adviceBox = document.getElementById('gapAdviceBox');
  const basisBadge = document.getElementById('gttEntryBasisBadge');

  if (gapBadge) {
    const sign = gapPct >= 0 ? '+' : '';
    gapBadge.textContent = `${sign}${gapPct.toFixed(1)}% Gap`;
    if (gapPct <= 3.0) {
      gapBadge.style.background = 'rgba(0,200,150,0.15)';
      gapBadge.style.color = 'var(--accent)';
    } else if (gapPct <= 5.0) {
      gapBadge.style.background = 'rgba(255,215,0,0.15)';
      gapBadge.style.color = '#ffd700';
    } else {
      gapBadge.style.background = 'rgba(255,71,87,0.15)';
      gapBadge.style.color = 'var(--red)';
    }
  }

  if (adviceBox) {
    if (gapPct <= 3.0) {
      adviceBox.innerHTML = `🟢 <strong>Ideal Entry (0–3% Gap):</strong> Optimal risk-reward. Stop Loss is calibrated at -7% from ₹${entry.toFixed(2)}.`;
      adviceBox.style.color = 'var(--accent)';
    } else if (gapPct <= 5.0) {
      adviceBox.innerHTML = `🟡 <strong>Extended Gap (+3% to +5%):</strong> Chasing increases pullback risk. Consider scaling in with 50% shares.`;
      adviceBox.style.color = '#ffd700';
    } else {
      adviceBox.innerHTML = `🔴 <strong>Over-Extended Gap (>+5% / Circuit):</strong> DO NOT CHASE! High risk of reversal. Switch to <strong>Alternate #1</strong>.`;
      adviceBox.style.color = 'var(--red)';
    }
  }

  if (basisBadge) {
    basisBadge.textContent = `Entry: ₹${entry.toFixed(2)}`;
  }

  // 2. Recalculate GTT levels based on entry
  const stopPct = 0.07;
  const initStop = Math.max(Math.round((entry * (1 - stopPct)) * 100) / 100, Math.round((entry - 2 * atr) * 100) / 100);
  const m1Target = Math.round((entry * 1.15) * 100) / 100;
  const m1Stop   = Math.round((entry * 1.025) * 100) / 100;
  const m2Target = Math.round((entry * 1.30) * 100) / 100;
  const m2Stop   = Math.round((entry * 1.15) * 100) / 100;
  const m3Target = Math.round((entry * 1.50) * 100) / 100;

  const levels = [
    { cls: 'stop-row', name: 'Initial Stop', nameClass: 'level-stop', target: initStop, stop: null, chg: pctChange(entry, initStop) },
    { cls: 'm1-row', name: 'M1', nameClass: 'level-m1', target: m1Target, stop: m1Stop, chg: pctChange(entry, m1Target) },
    { cls: 'm2-row', name: 'M2', nameClass: 'level-m2', target: m2Target, stop: m2Stop, chg: pctChange(entry, m2Target) },
    { cls: 'm3-row', name: 'M3', nameClass: 'level-m3', target: m3Target, stop: null, chg: pctChange(entry, m3Target) },
  ];

  const body = document.getElementById('gttBody');
  if (body) {
    body.innerHTML = levels.map(lv => {
      const pct = fmtPct(lv.chg);
      return `
        <tr class="${lv.cls}">
          <td><span class="level-name ${lv.nameClass}">${lv.name}</span></td>
          <td>${fmtINR(lv.target)}</td>
          <td>${lv.stop ? fmtINR(lv.stop) : '–'}</td>
          <td><span class="${pct.cls}">${pct.text}</span></td>
        </tr>
      `;
    }).join('');
  }

  // 3. Recalculate Shares & Capital based on entry
  const affordableShares = Math.max(Math.floor((capital - 26) / entry), 1);
  const capRequired = affordableShares * entry;

  const pills = document.getElementById('tradePills');
  if (pills) {
    pills.innerHTML = `
      <div class="trade-pill">
        <div class="pill-label">🛒 Shares</div>
        <div class="pill-value">${affordableShares}</div>
      </div>
      <div class="trade-pill">
        <div class="pill-label">💰 Capital</div>
        <div class="pill-value">${fmtINR(capRequired)}</div>
      </div>
      <div class="trade-pill">
        <div class="pill-label">🏦 Base</div>
        <div class="pill-value">${fmtINR(capital)}</div>
      </div>
    `;
  }

  // 4. Update Zerodha Guide
  const guideStop = document.getElementById('guideStopLoss');
  const guideTarget = document.getElementById('guideTarget');
  if (guideStop) guideStop.textContent = `${fmtINR(initStop)} (-7.00%)`;
  if (guideTarget) guideTarget.textContent = `${fmtINR(m1Target)} (+15.00%)`;

  s.ACTUAL_ENTRY = entry;
  s.CALC_SHARES = affordableShares;
  s.CALC_STOP = initStop;
  s.CALC_M1 = m1Target;
}

function renderAlternates(alts) {
  const altsCard = document.getElementById('altsCard');
  const altsBody = document.getElementById('altsBody');
  if (!alts || !alts.length) { altsCard.style.display = 'none'; return; }

  altsCard.style.display = 'block';
  altsBody.innerHTML = alts.map((a, i) => `
    <div class="alt-stock-row">
      <div class="alt-rank">#${i + 2}</div>
      <div class="alt-symbol">${a.SYMBOL || '–'}</div>
      <div style="text-align:right;">
        <div class="alt-cmp">${fmtINR(a.CMP)}</div>
        <div class="alt-cms">CMS ${parseFloat(a.CMS_SCORE || 0).toFixed(1)}</div>
      </div>
    </div>
  `).join('');

  const toggle = document.getElementById('altsToggle');
  toggle.onclick = () => {
    toggle.classList.toggle('open');
    altsBody.classList.toggle('open');
  };
}

/* ══════════════════════════════════════════════════════
   PORTFOLIO TAB
══════════════════════════════════════════════════════ */

function renderPortfolio() {
  const base    = store.get(LS.CAPITAL_BASE, DEFAULT_CAPITAL);
  const current = store.get(LS.CURRENT_CAPITAL, base);
  const history = store.get(LS.CAPITAL_HISTORY, []);
  const sigHist = store.get(LS.SIGNAL_HISTORY, []);

  // Capital display
  document.getElementById('capitalDisplay').textContent = fmtINR(current);
  document.getElementById('capitalBaseDisp').textContent = `Base: ${fmtINR(base)}`;

  const gain = current - base;
  const gainPct = (gain / base) * 100;
  const gainEl = document.getElementById('capitalGain');
  if (base > 0) {
    gainEl.style.display = 'inline-block';
    gainEl.className = 'capital-gain ' + (gain >= 0 ? 'pos' : 'neg');
    gainEl.textContent = `${gain >= 0 ? '+' : ''}${fmtINR(gain)} (${gainPct >= 0 ? '+' : ''}${gainPct.toFixed(1)}%)`;
  }

  // Stats
  const trades   = sigHist.length;
  const wins     = sigHist.filter(s => s.pnl > 0).length;
  const winRate  = trades ? ((wins / trades) * 100).toFixed(0) + '%' : '–';
  document.getElementById('statTrades').textContent  = trades;
  document.getElementById('statWins').textContent    = wins;
  document.getElementById('statWinRate').textContent = winRate;

  // Chart
  drawCapitalChart(history, base);
}

function drawCapitalChart(history, base) {
  const canvas = document.getElementById('capitalChart');
  const empty  = document.getElementById('chartEmpty');

  if (!history || history.length < 2) {
    canvas.style.display = 'none';
    empty.style.display  = 'flex';
    return;
  }
  canvas.style.display = 'block';
  empty.style.display  = 'none';

  const dpr = window.devicePixelRatio || 1;
  const W   = canvas.parentElement.clientWidth;
  const H   = 140;
  canvas.width  = W * dpr;
  canvas.height = H * dpr;
  canvas.style.width  = W + 'px';
  canvas.style.height = H + 'px';

  const ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);

  const values = history.map(e => e.capital);
  const minV   = Math.min(...values, base) * 0.98;
  const maxV   = Math.max(...values, base) * 1.02;
  const range  = maxV - minV || 1;

  const PAD_L = 12, PAD_R = 12, PAD_T = 16, PAD_B = 28;
  const chartW = W - PAD_L - PAD_R;
  const chartH = H - PAD_T - PAD_B;

  const xOf = i  => PAD_L + (i / (values.length - 1)) * chartW;
  const yOf = v  => PAD_T + chartH - ((v - minV) / range) * chartH;

  // Gradient fill
  const grad = ctx.createLinearGradient(0, PAD_T, 0, H - PAD_B);
  grad.addColorStop(0,   'rgba(0,200,150,0.25)');
  grad.addColorStop(1,   'rgba(0,200,150,0.0)');

  ctx.beginPath();
  ctx.moveTo(xOf(0), yOf(values[0]));
  values.forEach((v, i) => { if (i > 0) ctx.lineTo(xOf(i), yOf(v)); });
  ctx.lineTo(xOf(values.length - 1), H - PAD_B);
  ctx.lineTo(xOf(0), H - PAD_B);
  ctx.closePath();
  ctx.fillStyle = grad;
  ctx.fill();

  // Line
  ctx.beginPath();
  ctx.moveTo(xOf(0), yOf(values[0]));
  values.forEach((v, i) => { if (i > 0) ctx.lineTo(xOf(i), yOf(v)); });
  ctx.strokeStyle = '#00C896';
  ctx.lineWidth   = 2;
  ctx.lineJoin    = 'round';
  ctx.stroke();

  // Base line
  const baseY = yOf(base);
  ctx.beginPath();
  ctx.setLineDash([4, 4]);
  ctx.moveTo(PAD_L, baseY);
  ctx.lineTo(W - PAD_R, baseY);
  ctx.strokeStyle = 'rgba(122,153,187,0.3)';
  ctx.lineWidth   = 1;
  ctx.stroke();
  ctx.setLineDash([]);

  // Dots
  values.forEach((v, i) => {
    ctx.beginPath();
    ctx.arc(xOf(i), yOf(v), 3, 0, Math.PI * 2);
    ctx.fillStyle = v >= base ? '#00C896' : '#FF4757';
    ctx.fill();
  });

  // X-axis labels
  ctx.font       = '9px -apple-system, sans-serif';
  ctx.fillStyle  = '#4A6A8A';
  ctx.textAlign  = 'center';
  const step = Math.max(1, Math.floor(history.length / 4));
  history.forEach((e, i) => {
    if (i % step === 0 || i === history.length - 1) {
      const d = new Date(e.date);
      const label = d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' });
      ctx.fillText(label, xOf(i), H - PAD_B + 14);
    }
  });
}

/* ══════════════════════════════════════════════════════
   EXIT MODAL
══════════════════════════════════════════════════════ */

document.getElementById('btnRecordExit').addEventListener('click', openExitModal);
document.getElementById('btnCancelExit').addEventListener('click', closeExitModal);
document.getElementById('exitModal').addEventListener('click', e => {
  if (e.target === document.getElementById('exitModal')) closeExitModal();
});

// Pre-fill symbol from current signal
function openExitModal() {
  const modal = document.getElementById('exitModal');
  modal.classList.add('open');
  if (state.signalData && state.signalData[0] && state.signalData[0].STATUS === 'ACTIVE_SIGNAL') {
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
});

document.getElementById('btnResetCapital').addEventListener('click', () => {
  const base = store.get(LS.CAPITAL_BASE, DEFAULT_CAPITAL);
  store.set(LS.CURRENT_CAPITAL, base);
  store.set(LS.CAPITAL_HISTORY, []);
  renderPortfolio();
  showToast('Capital reset to base', 'info', '🔄');
});

/* ══════════════════════════════════════════════════════
   HISTORY TAB
══════════════════════════════════════════════════════ */

function renderHistory() {
  const list    = document.getElementById('historyList');
  const history = store.get(LS.SIGNAL_HISTORY, []);

  if (!history.length) {
    list.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">📋</div>
        <p>No trade history yet.<br>Record exits in the Portfolio tab.</p>
      </div>`;
    return;
  }

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
    if (state.currentTab === 'Portfolio') renderPortfolio();
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

/** Open Kite web with the stock pre-searched */
function openInKite(symbol) {
  const url = `${KITE.WEB_URL}/search?q=${encodeURIComponent(symbol + ':NSE')}`;
  window.open(url, '_blank', 'noopener');
}

/** Format GTT details as copy-paste text */
function buildGTTClipboardText(sig) {
  const entry = sig.ACTUAL_ENTRY || sig.CMP;
  const shares = sig.CALC_SHARES || sig.SHARES;
  const stop = sig.CALC_STOP || sig.INITIAL_STOP;
  const m1 = sig.CALC_M1 || sig.M1_TARGET;
  const cap = shares * entry;

  return [
    `═══ NSE Signal GTT Order ═══`,
    `Stock   : ${sig.SYMBOL} (NSE)`,
    `Entry   : ₹${fmt(entry)}`,
    `Shares  : ${shares} shares`,
    `Capital : ₹${fmt(cap)}`,
    ``,
    `── Initial Stop (-7%) ────────`,
    `Trigger : ₹${fmt(stop)} (hard stop)`,
    ``,
    `── Milestone 1 (+15%) ────────`,
    `Target  : ₹${fmt(m1)}`,
    `→ Move stop to +2.5% Breakeven after M1 hit`,
    ``,
    `── Milestone 2 (+30%) ────────`,
    `Target  : ₹${fmt(sig.M2_TARGET)}`,
    `→ Move stop to +15% after M2 hit`,
    ``,
    `── Milestone 3 (+50%) ────────`,
    `Target  : ₹${fmt(sig.M3_TARGET)}`,
    `→ Trail via 20-DMA after M3 hit`,
    ``,
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
      window.open(`https://groww.in/stocks/${encodeURIComponent(sig.SYMBOL.toLowerCase())}`, '_blank', 'noopener');
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

function onCapitalChange(newCapital) {
  state.userCapital = newCapital;
  store.set(LS.CURRENT_CAPITAL, newCapital);
  updatePillActive(newCapital);

  const allStocks = (state.payload && state.payload.all_qualified) || [];
  if (allStocks.length > 0) {
    const affordable = allStocks.filter(s => parseFloat(s.CMP) <= (newCapital - 26));
    if (affordable.length > 0) {
      const winner = Object.assign({}, affordable[0]);
      const shares = Math.max(Math.floor((newCapital - 26) / parseFloat(winner.CMP)), 1);
      winner.SHARES = shares;
      winner.CAPITAL_REQUIRED = shares * parseFloat(winner.CMP);
      winner.CAPITAL_BASE = newCapital;
      renderActiveSignal(winner, affordable.slice(1, 4));
    } else {
      renderCashState(null, `No stocks fit your entered budget of ₹${newCapital.toLocaleString('en-IN')}. Lowest priced leader is ₹${allStocks[allStocks.length-1].CMP}.`);
    }
    renderAllStocksTable(allStocks, newCapital);
  }
}

function renderAllStocksTable(stocks, userCapital) {
  const card = document.getElementById('allStocksCard');
  const tbody = document.getElementById('allStocksBody');
  const countBadge = document.getElementById('allStocksCountBadge');
  if (!card || !tbody) return;

  if (!stocks || !stocks.length) {
    card.style.display = 'none';
    return;
  }
  card.style.display = 'block';
  if (countBadge) countBadge.textContent = `${stocks.length} Leaders`;

  tbody.innerHTML = '';
  stocks.forEach((s, idx) => {
    const cmp = parseFloat(s.CMP);
    const affordable = cmp <= (userCapital - 26);
    const shares = affordable ? Math.floor((userCapital - 26) / cmp) : 0;
    const tr = document.createElement('tr');
    tr.className = 'stock-table-row';
    tr.innerHTML = `
      <td style="font-weight:700; color:var(--text-muted);">${idx + 1}</td>
      <td style="font-weight:800; color:var(--accent); font-size:13px;">${s.SYMBOL}</td>
      <td style="font-weight:700;">₹${cmp.toFixed(2)}</td>
      <td><span class="meta-chip cms-chip" style="padding:1px 6px; font-size:10px;">${parseFloat(s.CMS_SCORE).toFixed(1)}</span></td>
      <td style="color:${s.RSI_14 >= 70 ? '#ffd700' : (s.RSI_14 <= 45 ? '#ff4757' : '#00c896')}; font-weight:700;">${parseFloat(s.RSI_14).toFixed(1)}</td>
      <td>
        ${affordable 
          ? `<span class="badge" style="background:rgba(0,200,150,0.15); color:var(--accent); font-size:10px; padding:2px 6px; border-radius:6px;">✅ Buy ${shares}</span>` 
          : `<span class="badge" style="background:rgba(255,71,87,0.12); color:var(--red); font-size:10px; padding:2px 6px; border-radius:6px;">Needs ₹${Math.ceil(cmp + 26)}</span>`
        }
      </td>
      <td>
        <button class="btn-select-stock" style="background:transparent; border:1px solid var(--accent); color:var(--accent); border-radius:6px; padding:3px 8px; font-size:11px; font-weight:700; cursor:pointer;">
          Trade 🎯
        </button>
      </td>
    `;
    tr.onclick = () => selectStockForTrading(s, userCapital);
    tbody.appendChild(tr);
  });
}

function selectStockForTrading(s, userCapital) {
  const stock = Object.assign({}, s);
  const cmp = parseFloat(stock.CMP);
  const shares = Math.max(Math.floor((userCapital - 26) / cmp), 1);
  stock.SHARES = shares;
  stock.CAPITAL_REQUIRED = shares * cmp;
  stock.CAPITAL_BASE = userCapital;

  renderActiveSignal(stock, []);
  showToast(`Selected ${stock.SYMBOL} for trading!`, 'success', '🎯');

  const hero = document.getElementById('heroCard');
  if (hero) hero.scrollIntoView({ behavior: 'smooth', block: 'start' });
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
   SESSION DATE SWITCHER
══════════════════════════════════════════════════════ */

function renderSessionSwitcher(manifest, currentTradeDate) {
  const sessionCard = document.getElementById('sessionCard');
  const pillsContainer = document.getElementById('sessionPills');
  const pendingNotice = document.getElementById('bhavcopyPendingNotice');
  if (!sessionCard || !pillsContainer) return;

  if (!manifest || manifest.length <= 1) {
    sessionCard.style.display = 'none';
    return;
  }
  sessionCard.style.display = 'block';

  if (state.payload && state.payload.bhavcopy_status === 'PREVIOUS_SESSION_FALLBACK') {
    if (pendingNotice) pendingNotice.style.display = 'block';
  } else {
    if (pendingNotice) pendingNotice.style.display = 'none';
  }

  pillsContainer.innerHTML = '';
  manifest.slice(0, 5).forEach(m => {
    const btn = document.createElement('button');
    const isActive = (m.date === (state.selectedDate || currentTradeDate));
    btn.className = `pill-session ${isActive ? 'active' : ''}`;
    btn.innerHTML = `${m.is_today ? '🟢' : '📅'} ${m.display_date || m.date}`;
    btn.onclick = () => selectSessionDate(m.date);
    pillsContainer.appendChild(btn);
  });
}

async function selectSessionDate(dateStr) {
  state.selectedDate = dateStr;
  try {
    showSkeleton(true);
    const res = await fetch(`data/history/${dateStr}.json?_t=` + Date.now(), { cache: 'no-store' });
    if (!res.ok) throw new Error(`Could not load session ${dateStr}`);
    const payload = await res.json();
    state.payload = payload;
    state.signalData = payload.rows || [];

    renderMarketRegime(payload.regime);
    renderSignal(payload.rows, payload.reason);
    if (payload.all_qualified) {
      renderAllStocksTable(payload.all_qualified, state.userCapital || store.get(LS.CURRENT_CAPITAL, DEFAULT_CAPITAL));
    }
    renderSessionSwitcher(payload.history_manifest || (state.payload && state.payload.history_manifest), dateStr);
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
    btnOpen.onclick = () => modal.classList.add('open');
  }
  if (btnClose && modal) {
    btnClose.onclick = () => modal.classList.remove('open');
  }
  if (btnCloseBottom && modal) {
    btnCloseBottom.onclick = () => modal.classList.remove('open');
  }
  if (modal) {
    modal.onclick = e => {
      if (e.target === modal) modal.classList.remove('open');
    };
  }
}

/* ══════════════════════════════════════════════════════
   BOOT
══════════════════════════════════════════════════════ */

(function init() {
  // Purge legacy caches and legacy Google Sheet setting
  try {
    localStorage.removeItem(LS.SHEET_URL);
    const cached = store.get(LS.LAST_SIGNAL, null);
    if (cached && (!cached.rows || cached.rows.length === 0 || cached.rows[0].STATUS === 'CASH')) {
      localStorage.removeItem(LS.LAST_SIGNAL);
    }
  } catch (_) {}

  updateOfflineBadge(navigator.onLine);
  wireCapitalController();
  wireEntryPriceController();
  wireGlossaryModal();
  fetchSignal(true);
})();
