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
  }
})
