import { ROUTE_RULES } from '~/utils/access'

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

  const mods = useModules()
  await mods.load()

  // Vendors live in the portal, staff in the main workspace.
  const isPortal = to.path.startsWith('/portal')
  if (user.value?.is_vendor && !isPortal) return navigateTo('/portal')
  if (!user.value?.is_vendor && isPortal) return navigateTo('/dashboard')
  if (user.value?.is_vendor && !mods.on('portal')) {
    logout()
    return navigateTo('/login')
  }
  if (!user.value?.is_vendor) {
    const rule = ROUTE_RULES.find(([p]) => to.path === p || to.path.startsWith(p + '/'))
    if (rule && !(mods.on(rule[2]) && rule[1].some((p) => can(p)))) {
      const home = ROUTE_RULES.find(([p, perms, key]) => mods.on(key) && perms.some((x) => can(x)))
      return navigateTo(home && home[0] !== to.path ? home[0] : '/login', { replace: true })
    }
  }
})
