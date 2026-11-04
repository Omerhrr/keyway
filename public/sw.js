// Keyway PWA service worker v2
// - navigations: network-first -> cache -> /offline.html
// - build assets (/_nuxt/): stale-while-revalidate (instant loads, bg refresh)
// - other same-origin GETs: network-first with cache fallback
// - API traffic is never cached (operational + financial data must be fresh)
const VERSION = 'keyway-v2'
const SHELL = ['/', '/login', '/offline.html', '/manifest.webmanifest', '/logo.svg',
  '/icons/icon-192.png', '/icons/icon-512.png']

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(VERSION).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()))
})

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  )
})

self.addEventListener('message', (e) => {
  if (e.data?.type === 'SKIP_WAITING') self.skipWaiting()
})

async function staleWhileRevalidate(request) {
  const cache = await caches.open(VERSION)
  const cached = await cache.match(request)
  const network = fetch(request)
    .then((res) => { if (res.ok) cache.put(request, res.clone()); return res })
    .catch(() => cached)
  return cached || network
}

async function networkFirst(request, { fallback = null } = {}) {
  try {
    const res = await fetch(request)
    if (res.ok) {
      const cache = await caches.open(VERSION)
      cache.put(request, res.clone()).catch(() => {})
    }
    return res
  } catch {
    const cache = await caches.open(VERSION)
    return (await cache.match(request)) || (fallback ? await cache.match(fallback) : null) || Response.error()
  }
}

self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url)
  if (url.origin !== self.location.origin) return
  if (url.pathname.startsWith('/api/')) return // never cache API traffic
  if (e.request.method !== 'GET') return
  // dev-mode Vite modules (query-string versions, /@fs/ paths) must bypass the cache
  if (url.search || url.pathname.includes('/@fs/')) return

  if (e.request.mode === 'navigate') {
    e.respondWith(networkFirst(e.request, { fallback: '/offline.html' }))
  } else if (url.pathname.startsWith('/_nuxt/') || url.pathname.startsWith('/icons/')) {
    e.respondWith(staleWhileRevalidate(e.request))
  } else {
    e.respondWith(networkFirst(e.request))
  }
})
