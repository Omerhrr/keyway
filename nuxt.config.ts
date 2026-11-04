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
      ],
      link: [
        { rel: 'icon', type: 'image/svg+xml', href: '/logo.svg' },
        { rel: 'manifest', href: '/manifest.webmanifest' },
        { rel: 'apple-touch-icon', href: '/icons/icon-192.png' },
      ],
    },
  },
  css: ['~/assets/css/main.css'],
  nitro: {
    // Proxy /api to the FastAPI modular monolith (server-side, same-origin for the browser)
    routeRules: {},
  },
})
