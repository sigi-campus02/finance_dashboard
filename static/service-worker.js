const CACHE_NAME = 'finance-dashboard-v2';

// URLs die gecacht werden sollen
const urlsToCache = [
  '/',
  '/login/',
  // CDN Resources (Bootstrap, Icons, Chart.js)
  'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css',
  'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js',
  'https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.0/font/bootstrap-icons.css',
  'https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js',
  // Manifest
  '/manifest.json',
  // Icons (passe die Namen an deine tatsächlichen Icon-Dateien an)
  '/static/icons/icon-192x192.png',
  '/static/icons/icon-512x512.png'
];

// Installation - Caching
self.addEventListener('install', event => {
  console.log('[Service Worker] Installation gestartet');
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => {
        console.log('[Service Worker] Cache wird befüllt');
        // Cache einzeln hinzufügen und Fehler ignorieren
        return Promise.allSettled(
          urlsToCache.map(url =>
            cache.add(url).catch(err =>
              console.warn(`[Service Worker] Fehler beim Cachen von ${url}:`, err)
            )
          )
        );
      })
      .then(() => {
        console.log('[Service Worker] Installation abgeschlossen');
        // Aktiviere sofort den neuen Service Worker
        return self.skipWaiting();
      })
  );
});

// Aktivierung - Alte Caches löschen
self.addEventListener('activate', event => {
  console.log('[Service Worker] Aktivierung gestartet');
  event.waitUntil(
    caches.keys().then(cacheNames => {
      return Promise.all(
        cacheNames.map(cacheName => {
          if (cacheName !== CACHE_NAME) {
            console.log('[Service Worker] Lösche alten Cache:', cacheName);
            return caches.delete(cacheName);
          }
        })
      );
    })
    .then(() => {
      console.log('[Service Worker] Aktivierung abgeschlossen');
      // Übernimm sofort die Kontrolle über alle Clients
      return self.clients.claim();
    })
  );
});

// Auf Nachrichten vom Client hören, um Updates sofort zu aktivieren
self.addEventListener('message', event => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    console.log('[Service Worker] Skip waiting angefordert');
    self.skipWaiting();
  }
});

// Fetch - Network First für HTML, Cache First für Assets
self.addEventListener('fetch', event => {
  const { request } = event;
  const url = new URL(request.url);

  // Ignoriere chrome-extension und andere nicht-http(s) URLs
  if (!url.protocol.startsWith('http')) {
    return;
  }

  // Ignoriere POST, PUT, DELETE requests
  if (request.method !== 'GET') {
    return;
  }

  event.respondWith(
    (async () => {
      // Für HTML-Seiten: Network First Strategy
      if (request.headers.get('accept')?.includes('text/html')) {
        try {
          const networkResponse = await fetch(request);
          // Update cache im Hintergrund
          const cache = await caches.open(CACHE_NAME);
          cache.put(request, networkResponse.clone());
          return networkResponse;
        } catch (error) {
          // Falls offline, nutze Cache
          const cachedResponse = await caches.match(request);
          if (cachedResponse) {
            return cachedResponse;
          }
          // Fallback zu Offline-Seite
          return caches.match('/');
        }
      }

      // Für Assets (CSS, JS, Bilder): Cache First Strategy
      const cachedResponse = await caches.match(request);
      if (cachedResponse) {
        return cachedResponse;
      }

      try {
        const networkResponse = await fetch(request);
        // Füge erfolgreiche Responses zum Cache hinzu
        if (networkResponse.ok) {
          const cache = await caches.open(CACHE_NAME);
          cache.put(request, networkResponse.clone());
        }
        return networkResponse;
      } catch (error) {
        console.warn('[Service Worker] Fetch fehlgeschlagen:', error);
        // Gib einen Fehler zurück wenn nichts funktioniert
        return new Response('Network error', {
          status: 408,
          headers: { 'Content-Type': 'text/plain' },
        });
      }
    })()
  );
});

// Push Notifications (optional für später)
self.addEventListener('push', event => {
  const options = {
    body: event.data ? event.data.text() : 'Neue Benachrichtigung',
    icon: '/static/icons/icon-192x192.png',
    badge: '/static/icons/icon-96x96.png'
  };

  event.waitUntil(
    self.registration.showNotification('Finance Dashboard', options)
  );
});