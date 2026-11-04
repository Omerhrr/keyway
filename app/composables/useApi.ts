/** API client: same-origin /api -> Nitro proxy -> FastAPI. Handles auth + refresh. */
export async function api<T = any>(path: string, opts: any = {}): Promise<T> {
  const { access, tryRefresh, logout } = useAuth()
  const headers: Record<string, string> = { ...(opts.headers || {}) }
  if (access.value) headers.Authorization = `Bearer ${access.value}`

  const doFetch = () => $fetch<T>(`/api${path}`, { ...opts, headers })

  try {
    return await doFetch()
  } catch (err: any) {
    if (err?.status === 401 || err?.statusCode === 401 || err?.response?.status === 401) {
      try {
        await tryRefresh()
        if (access.value) {
          headers.Authorization = `Bearer ${access.value}`
          return await $fetch<T>(`/api${path}`, { ...opts, headers })
        }
      } catch { /* fallthrough */ }
      logout()
      if (import.meta.client) navigateTo('/login')
    }
    throw err
  }
}

export async function apiOk(path: string, opts: any = {}) {
  await api(path, opts)
  return true
}

export function errMsg(e: any): string {
  const d = e?.data?.detail ?? e?.detail ?? e?.message ?? e
  if (typeof d === 'string') return d
  if (d?.message) return d.message
  if (Array.isArray(d)) return d.join(', ')
  return 'Something went wrong'
}
