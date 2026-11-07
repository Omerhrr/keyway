import { DEFAULT_BRANDING, themeCss, type Branding } from '~/utils/theme'

export default defineNuxtPlugin(async () => {
  const branding = useBranding()

  useHead({
    style: [{ key: 'brand-theme', innerHTML: () => themeCss(branding.value) }],
    meta: [{ key: 'theme-color', name: 'theme-color', content: () => branding.value.primary }],
  })

  // Fetched on the server so the very first paint already has the right colours.
  if (import.meta.server) {
    try {
      branding.value = { ...DEFAULT_BRANDING, ...(await $fetch<Branding>('/api/public/branding')) }
    } catch { /* keep defaults when the API is unreachable */ }
  }

  // First visit only: start in the mode the business chose. After that, each person's own choice wins.
  if (import.meta.client) {
    const colorMode = useColorMode()
    let stored: string | null = null
    try { stored = localStorage.getItem('nuxt-color-mode') } catch { /* private mode */ }
    if (!stored && branding.value.default_mode !== 'system') colorMode.preference = branding.value.default_mode
  }
})
