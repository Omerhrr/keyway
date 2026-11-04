/** Reactive online/offline state (PWA polish: surfaces connectivity loss). */
export function useOnline() {
  const online = useState('net-online', () => true)

  if (import.meta.client) {
    const sync = () => { online.value = navigator.onLine }
    // idempotent: window listeners are cheap, but guard against duplicates
    const w = window as any
    if (!w.__kwOnlineBound) {
      w.__kwOnlineBound = true
      online.value = navigator.onLine
      window.addEventListener('online', sync)
      window.addEventListener('offline', sync)
    }
  }

  return { online }
}
