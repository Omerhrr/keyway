/** PWA install prompt + service-worker update flow. */
export function usePwa() {
  const canInstall = useState('pwa-can-install', () => false)
  const updateReady = useState('pwa-update-ready', () => false)
  let deferred: any = null
  let bound = false

  function bind() {
    if (!import.meta.client || bound) return
    bound = true

    window.addEventListener('beforeinstallprompt', (e: any) => {
      e.preventDefault()
      deferred = e
      canInstall.value = true
    })

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

  function applyUpdate() {
    if (!import.meta.client) return
    navigator.serviceWorker.getRegistration().then((reg) => {
      reg?.waiting?.postMessage({ type: 'SKIP_WAITING' })
    }).catch(() => {})
    // SW responds by claiming clients; reload shortly after
    setTimeout(() => window.location.reload(), 600)
  }

  return { canInstall, updateReady, bind, install, applyUpdate }
}
