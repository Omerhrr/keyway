/** Required-input check: when something is missing, a popup names exactly what to fill in. */
export function useGuard() {
  const missing = useState<string[]>('guard-missing', () => [])
  const open = useState('guard-open', () => false)

  /** needs([['Vendor', form.vendor_id], ['Quantity', qty > 0]]) is true when every value is filled in. */
  function needs(fields: [string, any][]): boolean {
    const bad = fields
      .filter(([, v]) => v === undefined || v === null || v === false || v === 0 || v === '' || (typeof v === 'string' && !v.trim()) || (typeof v === 'number' && Number.isNaN(v)))
      .map(([label]) => label)
    if (!bad.length) return true
    missing.value = bad
    open.value = true
    return false
  }
  return { needs, missing, open }
}
