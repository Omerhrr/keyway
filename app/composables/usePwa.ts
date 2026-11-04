/** PWA install prompt + service-worker update flow. */
export function usePwa() {
  const canInstall = useState('pwa-can-install', () => false)
  const updateReady = useState('pwa-update-ready', () => false)
  const isIOS = useState('pwa-is-ios', () => false)
  const standalone = useState('pwa-standalone', () => false)
  let deferred: any = null
  let bound = false

  function bind() {
    if (!import.meta.client || bound) return
    bound = true

    // iOS Safari never fires beforeinstallprompt - offer manual A2HS steps instead
    isIOS.value = /iphone|ipad|ipod/i.test(navigator.userAgent)
      || (navigator.platform === 'MacIntel' && (navigator as any).maxTouchPoints > 1)
    standalone.value = window.matchMedia('(display-mode: standalone)').matches
      || (navigator as any).standalone === true

    window.addEventListener('beforeinstallprompt', (e: any) => {
      e.preventDefault()
      deferred = e
      canInstall.value = true
    })
    window.addEventListener('appinstalled', () => { canInstall.value = false })

    // a waiting service worker means a new version is ready to activate
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.getRegistration().then((reg) => {
        if (reg?.waiting && navigator.serviceWorker.controller) updateReady.value = true
        reg?.addEventListener('updatefound', () => {
          const sw = reg.installing
          sw?.addEventListener('statechange', () => {
            if (sw.state === 'installed' && navigator.serviceWorker.controller) updateReady.value = true
          })
        })
      }).catch(() => {})
    }
  }

  async function install(): Promise<boolean> {
    if (!deferred) return false
    deferred.prompt()
    const { outcome } = await deferred.userChoice
    deferred = null
    canInstall.value = false
    return outcome === 'accepted'
  }

  /** True when the app can offer an install path right now. */
  const installable = computed(() =>
    !standalone.value && (canInstall.value || isIOS.value))

  function applyUpdate() {
    if (!import.meta.client) return
    navigator.serviceWorker.getRegistration().then((reg) => {
      reg?.waiting?.postMessage({ type: 'SKIP_WAITING' })
    }).catch(() => {})
    // SW responds by claiming clients; reload shortly after
    setTimeout(() => window.location.reload(), 600)
  }

  return { canInstall, updateReady, isIOS, standalone, installable, bind, install, applyUpdate }
}
