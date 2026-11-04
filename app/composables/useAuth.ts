/** Auth store backed by cookies (readable during SSR) + user state. */
interface KeywayUser {
  id: number
  email: string
  full_name: string
  role_name?: string | null
  role_id?: number | null
  permissions: string[] | ['*']
  is_superuser: boolean
  is_vendor: boolean
  vendor_id?: number | null
}

export function useAuth() {
  const user = useState<KeywayUser | null>('kw-user', () => null)
  const access = useCookie<string | null>('kw_access', { maxAge: 60 * 60 * 12, sameSite: 'lax' })
  const refresh = useCookie<string | null>('kw_refresh', { maxAge: 60 * 60 * 24 * 14, sameSite: 'lax' })

  const isLoggedIn = computed(() => !!user.value || !!access.value)

  async function login(email: string, password: string) {
    const res = await $fetch<{ access_token: string; refresh_token: string; user: KeywayUser }>('/api/auth/login', {
      method: 'POST',
      body: { email, password },
    })
    access.value = res.access_token
    refresh.value = res.refresh_token
    user.value = res.user
    return res.user
  }

  async function fetchMe() {
    if (!access.value) return null
    try {
      user.value = await $fetch<KeywayUser>('/api/auth/me', {
        headers: { Authorization: `Bearer ${access.value}` },
      })
    } catch {
      await tryRefresh()
    }
    return user.value
  }

  async function tryRefresh() {
    if (!refresh.value) return logout()
    try {
      const res = await $fetch<{ access_token: string; refresh_token: string; user: KeywayUser }>('/api/auth/refresh', {
        method: 'POST',
        body: { refresh_token: refresh.value },
      })
      access.value = res.access_token
      refresh.value = res.refresh_token
      user.value = res.user
    } catch {
      logout()
    }
  }

  function logout() {
    access.value = null
    refresh.value = null
    user.value = null
  }

  function can(perm: string): boolean {
    if (!user.value) return false
    if (user.value.is_superuser) return true
    const perms = user.value.permissions || []
    return perms.includes('*') || perms.includes(perm)
  }

  return { user, isLoggedIn, login, fetchMe, tryRefresh, logout, can, access, refresh }
}
