/** Copy / PDF / Excel for one or several settlements at once. */
export function useSettlementExport() {
  const { printRecord, exportExcel } = useDocs()
  const busy = ref(false)
  const day = (v: any) => fmtDate(v)

  async function load(ids: number[]) {
    const all = await Promise.all(ids.map(id => api(`/settlements/${id}`)))
    return all.sort((a: any, b: any) => a.reference.localeCompare(b.reference)) as any[]
  }
  const lines = (s: any) => [...(s.items || [])].sort((x: any, y: any) =>
    (x.type === 'COLLECTION' ? 0 : 1) - (y.type === 'COLLECTION' ? 0 : 1) || String(x.date || '').localeCompare(String(y.date || '')))
  const sum = (list: any[], k: string) => list.reduce((a, s) => a + (s[k] || 0), 0)
  const title = (list: any[]) => list.length === 1 ? `Settlement ${list[0].reference} - ${list[0].vendor_name}` : `${list.length} settlements`

  function text(list: any[]) {
    const L: string[] = []
    if (list.length > 1) {
      L.push(`*${list.length} settlements*`, `Collected: ${fmtNaira(sum(list, 'gross_kobo'))}`, `Our charges: -${fmtNaira(sum(list, 'charges_kobo'))}`,
        `*Net payable: ${fmtNaira(sum(list, 'net_kobo'))}*`, `Paid so far: ${fmtNaira(sum(list, 'paid_kobo'))}`,
        `Still to pay: ${fmtNaira(sum(list, 'net_kobo') - sum(list, 'paid_kobo'))}`, '')
    }
    list.forEach((s, n) => {
      if (n) L.push('', '------------------', '')
      L.push(`*Settlement ${s.reference} - ${s.vendor_name}*`, titleize(s.status), '',
        `Collected: ${fmtNaira(s.gross_kobo)}`, `Our charges: -${fmtNaira(s.charges_kobo)}`, `*Net payable: ${fmtNaira(s.net_kobo)}*`,
        `Paid so far: ${fmtNaira(s.paid_kobo)}`, `Still to pay: ${fmtNaira(s.net_kobo - s.paid_kobo)}`)
      const cols = lines(s).filter((i: any) => i.type === 'COLLECTION')
      const chs = lines(s).filter((i: any) => i.type !== 'COLLECTION')
      if (cols.length) { L.push('', '*Orders*'); cols.forEach((i: any) => L.push(`• ${day(i.date)} · ${i.order_reference} · ${i.note || ''} · ${fmtNaira(i.gross_kobo)}`)) }
      if (chs.length) { L.push('', '*Our charges*'); chs.forEach((i: any) => L.push(`• ${day(i.date)} · ${i.order_reference ? i.order_reference + ' · ' : ''}${i.note || 'Charge'} · -${fmtNaira(i.deduction_kobo)}`)) }
      if (s.payments?.length) { L.push('', '*Payments*'); s.payments.forEach((p: any) => L.push(`• ${day(p.paid_at || p.created_at)} · ${fmtNaira(p.amount_kobo)} · ${titleize(p.method)}${p.bank_ref ? ' · ref ' + p.bank_ref : ''}`)) }
    })
    return L.join('\n')
  }

  async function copy(ids: number[]) {
    busy.value = true
    try {
      const t = text(await load(ids))
      try { await navigator.clipboard.writeText(t) }
      catch {
        const ta = document.createElement('textarea'); ta.value = t; ta.style.cssText = 'position:fixed;opacity:0'
        document.body.appendChild(ta); ta.select(); document.execCommand('copy'); ta.remove()
      }
      useToast().add({ title: 'Copied', description: 'Paste it into WhatsApp for the vendor.', color: 'success', icon: 'i-lucide-clipboard-check' })
    } catch (e) { useToast().add({ title: 'Could not copy', description: errMsg(e), color: 'error' }) } finally { busy.value = false }
  }

  async function pdf(ids: number[]) {
    busy.value = true
    try {
      const list = await load(ids)
      const owed = sum(list, 'net_kobo') - sum(list, 'paid_kobo')
      await printRecord({
        title: title(list),
        subtitle: `${list.length} settlement${list.length === 1 ? '' : 's'} · prepared ${fmtDate(new Date().toISOString())}`,
        fields: [['Settlements', list.map(s => s.reference).join(', ')], ['Collected', fmtNaira(sum(list, 'gross_kobo'))],
          ['Our charges', fmtNaira(sum(list, 'charges_kobo'))], ['Net payable', fmtNaira(sum(list, 'net_kobo'))],
          ['Paid so far', fmtNaira(sum(list, 'paid_kobo'))], ['Still to pay', fmtNaira(owed)]],
        tables: list.map(s => ({
          heading: `${s.reference} · ${s.vendor_name} · ${titleize(s.status)} · net ${fmtNaira(s.net_kobo)}, paid ${fmtNaira(s.paid_kobo)}`,
          columns: ['Date', 'Type', 'Order', 'Details', 'Gross', 'Deduction'],
          rows: lines(s).map((i: any) => [day(i.date), i.type === 'COLLECTION' ? 'Collection' : 'Our charge', i.order_reference || '-', i.note || '',
            i.gross_kobo ? fmtNaira(i.gross_kobo) : '-', i.deduction_kobo ? `-${fmtNaira(i.deduction_kobo)}` : '-']),
        })),
      })
    } catch (e) { useToast().add({ title: 'Could not print', description: errMsg(e), color: 'error' }) } finally { busy.value = false }
  }

  async function excel(ids: number[]) {
    busy.value = true
    try {
      const list = await load(ids)
      const rows: (string | number)[][] = []
      list.forEach(s => lines(s).forEach((i: any) => rows.push([s.reference, s.vendor_name, titleize(s.status), day(i.date),
        i.type === 'COLLECTION' ? 'Collection' : 'Our charge', i.order_reference || '-', i.note || '',
        i.gross_kobo ? fmtNaira(i.gross_kobo) : '-', i.deduction_kobo ? `-${fmtNaira(i.deduction_kobo)}` : '-'])))
      rows.push([], ['TOTAL', '', '', '', '', '', `Net ${fmtNaira(sum(list, 'net_kobo'))} · paid ${fmtNaira(sum(list, 'paid_kobo'))}`,
        fmtNaira(sum(list, 'gross_kobo')), `-${fmtNaira(sum(list, 'charges_kobo'))}`])
      await exportExcel(title(list), ['Settlement', 'Vendor', 'Status', 'Date', 'Type', 'Order', 'Details', 'Gross', 'Deduction'], rows, `${list.length} settlement(s)`)
    } catch (e) { useToast().add({ title: 'Could not export', description: errMsg(e), color: 'error' }) } finally { busy.value = false }
  }
  return { busy, copy, pdf, excel }
}
