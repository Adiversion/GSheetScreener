/* ═══════════════════════════════════════════════════════
   NSE Signal – Service Worker (sw.js)
   Cache-first for assets, Network-first for CSV
═══════════════════════════════════════════════════════ */

const CACHE_NAME   = 'nse-signal-v1';
const DATA_CACHE   = 'nse-signal-data-v1';

const STATIC_ASSETS = [
  './',
  './index.html',
  './css/style.css',
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

/* ── Activate: clean old caches ── */
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys
          .filter(k => k !== CACHE_NAME && k !== DATA_CACHE)
          .map(k => caches.delete(k))
      )
    ).then(() => self.clients.claim())
  );
});

/* ── Fetch strategy ── */
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);

  // Network-first for Google Sheets CSV (always try to get fresh signal data)
  if (
    url.hostname === 'docs.google.com' ||
    url.hostname === 'spreadsheets.google.com' ||
    url.searchParams.has('tqx')
  ) {
    event.respondWith(networkFirstDataStrategy(event.request));
    return;
  }

  // Cache-first for all other static assets
  event.respondWith(cacheFirstStrategy(event.request));
});

/** Network-first: try network, fall back to data cache */
async function networkFirstDataStrategy(request) {
  try {
    const networkResponse = await fetch(request);
    if (networkResponse.ok) {
      const cache = await caches.open(DATA_CACHE);
      // Clone so we can store and return
      cache.put('last-signal-csv', networkResponse.clone());
    }
    return networkResponse;
  } catch (_) {
    // Offline fallback: return last known CSV
    const cached = await caches.match('last-signal-csv', { cacheName: DATA_CACHE });
    if (cached) return cached;
    return new Response('STATUS,TIMESTAMP\nCASH,offline', {
      headers: { 'Content-Type': 'text/csv' }
    });
  }
}

/** Cache-first: return cache, update in background, fall back to network */
async function cacheFirstStrategy(request) {
  const cached = await caches.match(request);
  if (cached) {
    // Update cache in background (stale-while-revalidate)
    fetch(request).then(response => {
      if (response && response.ok) {
        caches.open(CACHE_NAME).then(cache => cache.put(request, response));
      }
    }).catch(() => {});
    return cached;
  }
  try {
    const response = await fetch(request);
    if (response && response.ok) {
      const cache = await caches.open(CACHE_NAME);
      cache.put(request, response.clone());
    }
    return response;
  } catch (err) {
    // Return a minimal offline page for navigation requests
    if (request.mode === 'navigate') {
      const cached = await caches.match('./index.html');
      if (cached) return cached;
    }
    throw err;
  }
}
