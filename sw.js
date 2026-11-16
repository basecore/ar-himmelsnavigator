// AR Himmelsnavigator: network-first HTML and ephemerides
const CACHE_NAME = 'himmelsnavigator-v3-20261116';
const CORE = ['./', './index.html', './coordinates.js', './manifest.json', './icon-192.png', './icon-512.png'];
self.addEventListener('install', event => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE_NAME);
    await Promise.all(CORE.map(async path => {
      try {
        const request = new Request(new URL(path, self.registration.scope), {cache: 'reload'});
        const response = await fetch(request);
        if (response.ok) await cache.put(request, response);
      } catch (error) { console.warn('[SW] Precache skipped:', path, error); }
    }));
    await self.skipWaiting();
  })());
});
self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.filter(key => key.startsWith('himmelsnavigator-') && key !== CACHE_NAME).map(key => caches.delete(key)));
    await self.clients.claim();
  })());
});
self.addEventListener('message', event => {
  if (event.data && event.data.type === 'SKIP_WAITING') self.skipWaiting();
});
self.addEventListener('fetch', event => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== 'GET' || url.origin !== self.location.origin || !url.href.startsWith(self.registration.scope)) return;
  const fresh = request.mode === 'navigate' || url.pathname.endsWith('.html') || url.pathname.endsWith('/coordinates.js') || url.pathname.endsWith('/sw.js');
  event.respondWith((async () => {
    const cache = await caches.open(CACHE_NAME);
    if (!fresh) {
      const cached = await cache.match(request);
      if (cached) return cached;
    }
    try {
      const response = await fetch(request, {cache: 'no-store'});
      if (response.ok && response.type === 'basic') await cache.put(request, response.clone());
      return response;
    } catch (error) {
      const cached = await cache.match(request);
      if (cached) return cached;
      if (request.mode === 'navigate') {
        const html = await cache.match(new URL('./index.html', self.registration.scope).href);
        if (html) return html;
      }
      return new Response('Offline: resource unavailable', {status: 503, headers: {'Content-Type': 'text/plain; charset=utf-8'}});
    }
  })());
});
