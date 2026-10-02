/* ═══════════════════════════════════════════════════════
   NSE Signal – Service Worker (sw.js)
   Serverless Native Quant Screener (Zero Google Sheets)
   Cache-first for static assets, Network-first for static JSON
═══════════════════════════════════════════════════════ */

const CACHE_NAME = 'nse-signal-v36';
const DATA_CACHE = 'nse-signal-data-v36';

const STATIC_ASSETS = [
  './',
  './index.html',
  './css/style.css',
  './js/research-engine.js',
  './js/research-lab.js',
  './js/app.js',
  './manifest.json',
];

/* ── Install: pre-cache static shell ── */
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(STATIC_ASSETS))
      .then(() => self.skipWaiting())
  );
});

/* ── Activate: clean ALL old caches and claim clients immediately ── */
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys
          .filter(k => k !== CACHE_NAME && k !== DATA_CACHE)
          .map(k => {
            console.log('[SW] Purging old cache:', k);
            return caches.delete(k);
          })
      )
    ).then(() => self.clients.claim())
  );
});

/* ── Fetch strategy ── */
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);

  // Network-first for dynamic quant data (data/signal.json, data/history/, data/screener.json)
  if (url.pathname.includes('/data/')) {
    event.respondWith(networkFirstDataStrategy(event.request));
    return;
  }

  // Network-first for navigation requests (HTML) to ensure instant UI updates
  if (event.request.mode === 'navigate') {
    event.respondWith(networkFirstNavigationStrategy(event.request));
    return;
  }

  // Network-first for app JS and CSS so new commits are immediately reflected
  if (url.pathname.endsWith('.js') || url.pathname.endsWith('.css')) {
    event.respondWith(networkFirstAssetStrategy(event.request));
    return;
  }

  // Cache-first for static icons/manifest
  event.respondWith(cacheFirstStrategy(event.request));
});

/** Network-first for JS and CSS: fetch freshest from network, cache for offline fallback */
async function networkFirstAssetStrategy(request) {
  try {
    const networkResponse = await fetch(request);
    if (networkResponse.ok) {
      const cache = await caches.open(CACHE_NAME);
      cache.put(request, networkResponse.clone());
    }
    return networkResponse;
  } catch (_) {
    const cached = await caches.match(request);
    if (cached) return cached;
    return caches.match(request.url);
  }
}

/** Network-first navigation strategy: fetches fresh HTML, falls back to cache */
async function networkFirstNavigationStrategy(request) {
  try {
    const networkResponse = await fetch(request);
    if (networkResponse.ok) {
      const cache = await caches.open(CACHE_NAME);
      cache.put(request, networkResponse.clone());
    }
    return networkResponse;
  } catch (_) {
    const cached = await caches.match('./index.html');
    if (cached) return cached;
    return caches.match(request);
  }
}

/** Network-first: try network, fall back to data cache */
async function networkFirstDataStrategy(request) {
  try {
    const networkResponse = await fetch(request);
    if (networkResponse.ok) {
      const cache = await caches.open(DATA_CACHE);
      cache.put(request.url, networkResponse.clone());
    }
    return networkResponse;
  } catch (_) {
    // Offline fallback: return cached JSON if available
    const cached = await caches.match(request.url, { cacheName: DATA_CACHE });
    if (cached) return cached;
    return new Response(JSON.stringify({ status: 'OFFLINE', rows: [] }), {
      headers: { 'Content-Type': 'application/json' }
    });
  }
}

/** Cache-first: return cached asset, fetch from network if missing */
async function cacheFirstStrategy(request) {
  const cached = await caches.match(request);
  if (cached) return cached;

  try {
    const networkResponse = await fetch(request);
    if (networkResponse.ok) {
      const cache = await caches.open(CACHE_NAME);
      cache.put(request, networkResponse.clone());
    }
    return networkResponse;
  } catch (err) {
    if (request.mode === 'navigate') {
      const fallback = await caches.match('./index.html');
      if (fallback) return fallback;
    }
    throw err;
  }
}
