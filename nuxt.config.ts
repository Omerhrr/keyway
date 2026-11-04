export default defineNuxtConfig({
  compatibilityDate: '2026-11-01',
  devtools: { enabled: false },
  modules: ['@nuxt/ui'],
  ssr: true,
  app: {
    head: {
      title: 'Keyway - Logistics Operations',
      htmlAttrs: { lang: 'en' },
      meta: [
        { name: 'viewport', content: 'width=device-width, initial-scale=1, viewport-fit=cover' },
        { name: 'theme-color', content: '#059669' },
        { name: 'description', content: 'Keyway - WhatsApp-first logistics, inventory, COD and vendor settlement platform' },
        { name: 'mobile-web-app-capable', content: 'yes' },
        { name: 'apple-mobile-web-app-capable', content: 'yes' },
        { name: 'apple-mobile-web-app-status-bar-style', content: 'default' },
        { name: 'apple-mobile-web-app-title', content: 'Keyway' },
      ],
      link: [
        { rel: 'icon', type: 'image/svg+xml', href: '/logo.svg' },
        { rel: 'manifest', href: '/manifest.webmanifest' },
        { rel: 'apple-touch-icon', href: '/icons/icon-192.png' },
        { rel: 'icon', type: 'image/png', sizes: '192x192', href: '/icons/icon-192.png' },
        { rel: 'icon', type: 'image/png', sizes: '512x512', href: '/icons/icon-512.png' },
      ],
    },
  },
  css: ['~/assets/css/main.css'],
  // Dev-server only: allow access through sandbox preview proxies whose
  // hostnames change on every restart (Vite blocks unknown Host headers).
  vite: {
    server: {
      allowedHosts: true,
    },
  },
  nitro: {
    // Proxy /api to the FastAPI modular monolith (server-side, same-origin for the browser)
    routeRules: {},
  },
})
