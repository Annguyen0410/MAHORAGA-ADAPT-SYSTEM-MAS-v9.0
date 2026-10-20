// Offline shell only: never cache personal APIs or clear another app's cache.
const CACHE_NAME = 'linklumina-shell-v4';
const APP_SHELL = ['index.html', 'styles.css', 'chain.js', 'chain.json', 'search-engine.js', 'backup-core.js',
    'eventbus.js', 'modules.js', 'sync.js', 'neural.js', 'folders.js', 'timeline.js', 'layout.js', 'laws.js',
    'contextmenu.js', 'living_bg.js', 'migrations.js', 'features.js', 'script.js', 'tools.js', 'analytics.js',
    'sidepeek.js', 'artifact-features.js', 'manifest.json', 'vendor/tailwind.js', 'vendor/lucide.min.js',
    'vendor/three.min.js', 'vendor/outfit.css', 'vendor/outfit-latin.woff2', 'vendor/outfit-latin-ext.woff2'];
const STATIC_URLS = new Set(APP_SHELL.map(path => new URL(path, self.registration.scope).href));
function offlineFallback() { return new Response('', { status: 504, statusText: 'Offline' }); }
self.addEventListener('install', event => {
    event.waitUntil(caches.open(CACHE_NAME).then(cache => Promise.all(APP_SHELL.map(path =>
        cache.add(path).catch(error => console.warn('SW asset unavailable:', path, error.message))
    ))).then(() => self.skipWaiting()));
});
self.addEventListener('activate', event => {
    event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key =>
        key.startsWith('linklumina-shell-') && key !== CACHE_NAME
    ).map(key => caches.delete(key)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', event => {
    const request = event.request;
    if (request.method !== 'GET' || request.headers.has('Authorization')) return;
    const url = new URL(request.url);
    const shellIndex = new URL('index.html', self.registration.scope).href;
    const key = request.mode === 'navigate' && url.href === self.registration.scope ? shellIndex : url.href;
    if (url.origin !== self.location.origin || !STATIC_URLS.has(key)) return;
    // Start revalidation synchronously so waitUntil extends this fetch event.
    const refresh = caches.open(CACHE_NAME).then(async cache => {
        const response = await fetch(request);
        if (response.ok && !response.headers.get('Cache-Control')?.includes('no-store')) {
            await cache.put(key, response.clone()).catch(error => console.warn('SW cache write failed', error));
        }
        return response;
    });
    event.waitUntil(refresh.then(() => undefined).catch(() => undefined));
    event.respondWith(caches.open(CACHE_NAME).then(cache => cache.match(key)).then(cached =>
        cached || refresh.catch(() => offlineFallback())
    ).catch(() => refresh.catch(() => offlineFallback())));
});
