import { ruleFor } from '~/utils/access'

/** Which optional parts of the product are switched on. A switched-off part is gone for everybody. */
export function useModules() {
  const state = useState<Record<string, boolean> | null>('modules', () => null)

  async function load(force = false) {
    if (state.value && !force) return state.value
    try {
      const res = await api<{ modules: { key: string; enabled: boolean }[] }>('/settings/modules')
      state.value = Object.fromEntries(res.modules.map((m) => [m.key, m.enabled]))
    } catch { /* keep everything on if it cannot be read */ }
    return state.value
  }

  const on = (key: string | null | undefined) => !key || !state.value || state.value[key] !== false

  /** True when the page is switched on AND the signed-in person may open it. */
  function canOpen(path: string) {
    const { can } = useAuth()
    const rule = ruleFor(path)
    if (!rule) return true
    return on(rule[2]) && rule[1].some((p) => can(p))
  }
  return { state, load, on, canOpen }
}
