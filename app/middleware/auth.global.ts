// Route -> permission (mirrors the sidebar). The API enforces the same rules; this just stops
// users landing on pages that would only show 403 errors.
const ROUTE_PERMS: [string, string][] = [
  ['/dashboard', 'dashboard.view'], ['/drafts', 'orders.view'], ['/orders', 'orders.view'],
  ['/dispatch', 'dispatch.view'], ['/vendors', 'vendors.view'], ['/catalog', 'catalog.view'],
  ['/inventory', 'inventory.view'], ['/cod', 'cod.manage'], ['/settlements', 'settlements.manage'],
  ['/finance', 'finance.manage'], ['/reports', 'reports.view'], ['/settings', 'settings.manage'],
  ['/audit', 'audit.view'],
]

export default defineNuxtRouteMiddleware(async (to) => {
  const { isLoggedIn, fetchMe, user, logout, can } = useAuth()
  if (to.path === '/login') return
  // restore session client-side
  if (!user.value) await fetchMe()
  if (!isLoggedIn.value) {
    if (import.meta.client) {
      logout()
      return navigateTo(`/login?next=${encodeURIComponent(to.fullPath)}`)
    }
    return
  }

  // role-based routing: vendors live in the self-service portal, staff in the
  // operations workspace. Prevents cross-role 403 crashes (e.g. a staff user
  // opening /portal would hit vendor-only endpoints).
  const isPortal = to.path.startsWith('/portal')
  if (user.value?.is_vendor && !isPortal) {
    return navigateTo('/portal')
  }
  if (!user.value?.is_vendor && isPortal) {
    return navigateTo('/dashboard')
  }
  if (!user.value?.is_vendor) {
    const rule = ROUTE_PERMS.find(([prefix]) => to.path === prefix || to.path.startsWith(prefix + '/'))
    if (rule && !can(rule[1])) {
      const home = ROUTE_PERMS.find(([, perm]) => can(perm))
      return navigateTo(home && home[0] !== to.path ? home[0] : '/conversations', { replace: true })
    }
  }
})
