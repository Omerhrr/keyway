/** Shared notification state: polls unread count + recent notifications, scoped
 *  to the signed-in user (staff-wide rows have user_id null; vendor portal rows
 *  are filtered server-side). Idempotent by design - one timer per session. */
export function useNotifications() {
  const { user } = useAuth()
  const items = useState<any[]>('notifications', () => [])
  const unread = useState<number>('notifications-unread', () => 0)
  let timer: ReturnType<typeof setInterval> | null = null

  async function refresh() {
    if (!user.value) return
    try {
      const [list, cnt] = await Promise.all([
        api('/notifications?limit=30'),
        api('/notifications/unread-count'),
      ])
      items.value = list
      unread.value = cnt?.count ?? 0
      syncBadge(unread.value)
    } catch { /* offline or logged out - keep last state */ }
  }

  /** Mirror the unread count onto the PWA/app icon badge where supported. */
  function syncBadge(count: number) {
    if (!import.meta.client) return
    try {
      const nav = navigator as any
      if (count > 0) nav.setAppBadge?.(count)
      else nav.clearAppBadge?.()
    } catch { /* badge API unsupported - ignore */ }
  }

  async function markAllRead() {
    try {
      await api('/notifications/read-all', { method: 'POST' })
      unread.value = 0
      await refresh()
    } catch {}
  }

  async function markRead(n: any) {
    if (n.status !== 'UNREAD') return
    try {
      await api(`/notifications/${n.id}/read`, { method: 'POST' })
      await refresh()
    } catch {}
  }

  function startPolling() {
    if (timer || !import.meta.client) return
    refresh()
    timer = setInterval(refresh, 30_000)
  }

  function stopPolling() {
    if (timer) { clearInterval(timer); timer = null }
  }

  function targetFor(n: any): string {
    const et = n.entity_type, id = n.entity_id
    if (et === 'order' && id) return `/orders/${id}`
    if (et === 'draft' && id) return '/drafts'
    if (et === 'conversation' && id) return `/conversations?id=${id}`
    if (et === 'inventory_balance' || et === 'stock_transfer') return '/inventory'
    if (et === 'settlement' && id) return '/settlements'
    if (et === 'cod' || et === 'collection') return '/cod'
    return ''
  }

  return { items, unread, refresh, markAllRead, markRead, startPolling, stopPolling, targetFor }
}
