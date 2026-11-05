export default defineNuxtRouteMiddleware(async (to) => {
  const { isLoggedIn, fetchMe, user, logout } = useAuth()
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
})
