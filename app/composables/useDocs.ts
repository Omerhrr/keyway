import { DEFAULT_DOCS, buildTableDoc, buildRecordDoc, printHtml, type DocSettings, type TableDoc, type RecordDoc } from '~/utils/documents'

/** Print layouts chosen in Settings, plus Excel download. */
export function useDocs() {
  const settings = useState<DocSettings>('doc-settings', () => ({ ...DEFAULT_DOCS }))
  const loaded = useState<boolean>('doc-settings-loaded', () => false)
  const { user } = useAuth()
  const brand = useBranding()

  async function load(force = false) {
    if (loaded.value && !force) return settings.value
    try {
      settings.value = { ...DEFAULT_DOCS, ...(await api<DocSettings>('/settings/documents')) }
      loaded.value = true
    } catch { /* keep defaults */ }
    return settings.value
  }

  const ctx = () => ({ settings: settings.value, preparedBy: user.value?.full_name, fallbackName: brand.value.brand_name })

  async function printTable(d: TableDoc) {
    await load()
    printHtml(buildTableDoc(d, ctx()))
  }
  async function printRecord(d: RecordDoc) {
    await load()
    printHtml(buildRecordDoc(d, ctx()))
  }

  async function exportExcel(title: string, columns: string[], rows: any[][], subtitle = '') {
    const { access } = useAuth()
    const res = await $fetch.raw<Blob>('/api/export/xlsx', {
      method: 'POST',
      headers: access.value ? { Authorization: `Bearer ${access.value}` } : {},
      body: { title, columns, rows, subtitle },
      responseType: 'blob',
    })
    const url = URL.createObjectURL(res._data as Blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${title.replace(/[^\w\- ]+/g, '').trim().replace(/\s+/g, '-') || 'export'}-${new Date().toISOString().slice(0, 10)}.xlsx`
    document.body.appendChild(a); a.click(); a.remove()
    setTimeout(() => URL.revokeObjectURL(url), 5000)
  }

  return { settings, load, printTable, printRecord, exportExcel }
}
