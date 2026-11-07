// Printable documents. Everything here is plain HTML so the browser can print it or save it as a PDF.

export type Template = 'classic' | 'modern' | 'executive' | 'bold' | 'elegant' | 'ledger' | 'compact' | 'minimal' | 'receipt'
export type HeaderStyle = 'split' | 'centered' | 'banner' | 'stacked'
export type TableStyle = 'striped' | 'lines' | 'boxed' | 'clean'
export type FontKey = 'sans' | 'serif' | 'mono' | 'rounded'

export interface DocSettings {
  template: Template
  accent: string
  company_name: string
  address: string
  phone: string
  email: string
  footer_text: string
  paper: 'A4' | 'A5' | 'A3' | 'Letter' | 'Legal' | 'Receipt'
  orientation: 'auto' | 'portrait' | 'landscape'
  show_logo: boolean
  show_date: boolean
  show_prepared_by: boolean
  show_signatures: boolean
  show_row_numbers: boolean
  show_totals: boolean
  logo: string
  font: FontKey
  header_style: HeaderStyle
  table_style: TableStyle
  density: 'comfortable' | 'compact'
  watermark: string
}

export const DEFAULT_DOCS: DocSettings = {
  template: 'classic', accent: '#059669', company_name: '', address: '', phone: '', email: '',
  footer_text: 'Thank you for doing business with us.', paper: 'A4', orientation: 'auto',
  show_logo: true, show_date: true, show_prepared_by: true, show_signatures: false, show_row_numbers: true,
  show_totals: true, logo: '', font: 'sans', header_style: 'split', table_style: 'striped', density: 'comfortable', watermark: '',
}

/** Ready-made looks. Picking one fills in the options below it, which can then be changed one by one. */
export const TEMPLATE_INFO: { value: Template; label: string; hint: string; preset: Partial<DocSettings> }[] = [
  { value: 'classic', label: 'Classic', hint: 'Coloured table header, striped rows', preset: { header_style: 'split', table_style: 'striped', font: 'sans', density: 'comfortable' } },
  { value: 'modern', label: 'Modern', hint: 'Big colour title, soft tinted header', preset: { header_style: 'split', table_style: 'lines', font: 'rounded', density: 'comfortable' } },
  { value: 'executive', label: 'Executive', hint: 'Full colour banner across the top', preset: { header_style: 'banner', table_style: 'lines', font: 'sans', density: 'comfortable' } },
  { value: 'bold', label: 'Bold', hint: 'Heavy title, black header, strong contrast', preset: { header_style: 'stacked', table_style: 'striped', font: 'sans', density: 'comfortable' } },
  { value: 'elegant', label: 'Elegant', hint: 'Centered, serif, fine rules', preset: { header_style: 'centered', table_style: 'clean', font: 'serif', density: 'comfortable' } },
  { value: 'ledger', label: 'Ledger', hint: 'Ruled grid like an account book', preset: { header_style: 'split', table_style: 'boxed', font: 'mono', density: 'compact' } },
  { value: 'compact', label: 'Compact', hint: 'Small text, more rows per page', preset: { header_style: 'split', table_style: 'lines', font: 'sans', density: 'compact' } },
  { value: 'minimal', label: 'Minimal', hint: 'Plain black and white, ink friendly', preset: { header_style: 'stacked', table_style: 'clean', font: 'sans', density: 'comfortable' } },
  { value: 'receipt', label: 'Receipt', hint: 'Narrow slip for a receipt printer', preset: { header_style: 'centered', table_style: 'clean', font: 'mono', density: 'compact', paper: 'Receipt', orientation: 'portrait' } },
]

export function esc(v: any): string {
  return String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c] as string))
}

const safeHex = (h: string) => (/^#[0-9a-fA-F]{6}$/.test(h) ? h : '#059669')
const safeLogo = (l: string) => (/^data:image\/(png|jpeg|webp);base64,[A-Za-z0-9+/=]+$/.test(l || '') ? l : '')

export interface TableDoc {
  title: string
  subtitle?: string
  columns: string[]
  rows: (string | number | null)[][]
  rightAlign?: boolean[]
}
export interface RecordDoc {
  title: string
  subtitle?: string
  fields: [string, string][]
  tables?: { heading: string; columns: string[]; rows: (string | number | null)[][] }[]
}
export interface DocContext { settings: DocSettings; preparedBy?: string; fallbackName?: string }

const FONTS: Record<FontKey, string> = {
  sans: "'Segoe UI', Roboto, Helvetica, Arial, sans-serif",
  serif: "Georgia, 'Times New Roman', serif",
  mono: "'Courier New', Consolas, monospace",
  rounded: "'Trebuchet MS', 'Segoe UI', Verdana, sans-serif",
}

function css(s: DocSettings, landscape: boolean, preview = false) {
  const a = safeHex(s.accent)
  const t = s.template
  const receipt = s.paper === 'Receipt' || t === 'receipt'
  const small = s.density === 'compact' || t === 'compact'
  const size = receipt ? 11 : small ? 10.5 : 12.5
  const pad = receipt ? '2px 0' : small ? '4px 7px' : '8px 11px'
  const page = receipt ? '@page{size:80mm auto;margin:4mm}' : `@page{size:${s.paper} ${s.orientation === 'auto' ? (landscape ? 'landscape' : 'portrait') : s.orientation};margin:${small ? 11 : 15}mm}`

  // header cell colours per template
  const thBy: Record<string, string> = {
    classic: `background:${a};color:#fff;`,
    modern: `background:${a}1f;color:${a};`,
    executive: `background:#f4f5f7;color:#111;border-bottom:2px solid ${a};`,
    bold: 'background:#111;color:#fff;',
    elegant: `color:${a};border-top:1px solid ${a};border-bottom:3px double ${a};`,
    ledger: 'background:#e9e9e9;color:#111;border:1px solid #888;',
    compact: 'background:#eee;color:#222;',
    minimal: 'color:#000;border-bottom:2px solid #000;',
    receipt: 'color:#000;border-top:1px dashed #000;border-bottom:1px dashed #000;',
  }
  const titleBy: Record<string, string> = {
    classic: 'font-size:24px;font-weight:700;',
    modern: `font-size:30px;font-weight:800;color:${a};`,
    executive: 'font-size:22px;font-weight:600;letter-spacing:.02em;',
    bold: 'font-size:34px;font-weight:900;text-transform:uppercase;letter-spacing:-.01em;',
    elegant: 'font-size:26px;font-weight:400;letter-spacing:.12em;text-transform:uppercase;',
    ledger: 'font-size:20px;font-weight:700;',
    compact: 'font-size:17px;font-weight:700;',
    minimal: 'font-size:22px;font-weight:600;',
    receipt: 'font-size:14px;font-weight:700;text-transform:uppercase;',
  }
  const rule = '#d6d6d6'
  const body: Record<TableStyle, string> = {
    striped: `td{border-bottom:1px solid #e4e4e4}tbody tr:nth-child(even) td{background:${t === 'bold' ? a + '14' : '#f6f7f8'}}`,
    lines: `td{border-bottom:1px solid ${rule}}`,
    boxed: 'td,th{border:1px solid #aaa}',
    clean: 'td{border-bottom:0}',
  }
  const wm = s.watermark
    ? `.wm{position:fixed;top:42%;left:0;right:0;text-align:center;font-size:96px;font-weight:900;letter-spacing:.1em;color:#000;opacity:.06;transform:rotate(-24deg);pointer-events:none;z-index:0;text-transform:uppercase}`
    : ''

  const pv = preview ? `body{padding:${receipt ? 4 : small ? 11 : 15}mm;${receipt ? 'width:80mm;' : 'width:210mm;'}}` : ''
  return `${page}
*{box-sizing:border-box}html{-webkit-print-color-adjust:exact;print-color-adjust:exact}
body{font-family:${FONTS[s.font] || FONTS.sans};font-size:${size}px;color:#1b1b1b;margin:0;line-height:1.45;${receipt ? 'width:72mm;' : ''}}
.page{position:relative;z-index:1}
.muted{color:#666;font-size:${size - 1}px;line-height:1.5}
.title{margin:0;${titleBy[t] || titleBy.classic}}
.sub{color:#666;margin-top:2px}
.co{font-weight:700;font-size:${size + 3}px}
.logo{max-height:${receipt ? 36 : 54}px;max-width:${receipt ? 120 : 190}px;object-fit:contain;display:block}
.mark{display:inline-block;vertical-align:middle}
.head{margin-bottom:${receipt ? 8 : 18}px}
.h-split{display:flex;justify-content:space-between;align-items:flex-start;gap:18px;padding-bottom:12px;border-bottom:${t === 'classic' ? `3px solid ${a}` : t === 'modern' ? `0` : '1px solid #bbb'}}
.h-split .right{text-align:right;display:flex;flex-direction:column;align-items:flex-end;gap:4px}
.h-centered{text-align:center;display:flex;flex-direction:column;align-items:center;gap:4px;padding-bottom:10px;border-bottom:${t === 'elegant' ? `3px double ${a}` : '1px dashed #888'}}
.h-centered .title{margin-top:8px}
.h-banner{background:${a};color:#fff;margin:-${small ? 11 : 15}mm -${small ? 11 : 15}mm 18px;padding:${small ? 12 : 20}px ${small ? 11 : 15}mm;display:flex;justify-content:space-between;align-items:center;gap:18px}
.h-banner .muted,.h-banner .sub{color:rgba(255,255,255,.82)}.h-banner .title{color:#fff}.h-banner .right{text-align:right;display:flex;flex-direction:column;align-items:flex-end;gap:4px}
.h-stacked{padding-bottom:12px;border-bottom:${t === 'bold' ? `6px solid ${a}` : '2px solid #111'}}
.h-stacked .top{display:flex;align-items:center;gap:12px;margin-bottom:14px}
h2{font-size:${size + 2}px;margin:18px 0 4px;${t === 'elegant' ? `color:${a};letter-spacing:.08em;text-transform:uppercase;` : ''}}
table{width:100%;border-collapse:collapse;margin-top:8px}
th{${thBy[t] || thBy.classic}text-align:left;padding:${pad};font-size:${size - 1.5}px;text-transform:uppercase;letter-spacing:.04em;font-weight:700}
td{padding:${pad};vertical-align:top}
${body[s.table_style]}
${t === 'modern' && s.table_style !== 'boxed' ? 'thead th:first-child{border-top-left-radius:6px}thead th:last-child{border-top-right-radius:6px}' : ''}
.r{text-align:right;font-variant-numeric:tabular-nums}
tr.total td{font-weight:700;border-top:2px solid ${t === 'minimal' || t === 'receipt' ? '#000' : a};background:${t === 'modern' ? a + '14' : 'transparent'} !important}
.kv{display:grid;grid-template-columns:repeat(${receipt ? 1 : 2},1fr);gap:${receipt ? 3 : 10}px ${receipt ? 0 : 28}px;margin:12px 0;${t === 'modern' ? `background:${a}0f;padding:12px 14px;border-radius:8px;` : t === 'ledger' ? 'border:1px solid #888;padding:10px;' : ''}}
.kv div span{display:block;color:#777;font-size:${size - 2.5}px;text-transform:uppercase;letter-spacing:.05em}
.kv div b{font-weight:600}
.sig{display:flex;gap:44px;margin-top:${receipt ? 20 : 56}px}.sig div{flex:1;border-top:1px solid #333;padding-top:4px;font-size:${size - 1.5}px;color:#555;text-align:center}
.foot{margin-top:${receipt ? 12 : 24}px;padding-top:9px;border-top:${receipt ? '1px dashed #000' : '1px solid #ccc'};text-align:center;color:#666;font-size:${size - 1}px}
thead{display:table-header-group}tr{page-break-inside:avoid}
${wm}
${pv}`
}

function logoHtml(ctx: DocContext, onDark = false) {
  const s = ctx.settings
  if (!s.show_logo) return ''
  const img = safeLogo(s.logo)
  if (img) return `<img class="logo" src="${img}" alt="">`
  const a = onDark ? '#ffffff' : safeHex(s.accent)
  const fg = onDark ? safeHex(s.accent) : '#fff'
  return `<svg class="mark" width="34" height="34" viewBox="0 0 64 64"><rect x="2" y="2" width="60" height="60" rx="14" fill="${a}"/><circle cx="26" cy="26" r="10" fill="none" stroke="${fg}" stroke-width="5"/><line x1="33" y1="33" x2="48" y2="48" stroke="${fg}" stroke-width="6" stroke-linecap="round"/></svg>`
}

function header(ctx: DocContext, title: string, subtitle?: string) {
  const s = ctx.settings
  const name = s.company_name || ctx.fallbackName || ''
  const contact = [s.address, s.phone, s.email].filter(Boolean).map(esc).join('<br>')
  const meta: string[] = []
  if (s.show_date) meta.push(new Date().toLocaleDateString('en-NG', { day: 'numeric', month: 'long', year: 'numeric' }))
  if (s.show_prepared_by && ctx.preparedBy) meta.push(`Prepared by ${esc(ctx.preparedBy)}`)
  const titleBlock = `<h1 class="title">${esc(title)}</h1>${subtitle ? `<div class="sub muted">${esc(subtitle)}</div>` : ''}${meta.length ? `<div class="muted">${meta.join(' · ')}</div>` : ''}`
  const company = (dark = false) => `${logoHtml(ctx, dark)}<div class="co">${esc(name)}</div><div class="muted">${contact}</div>`
  const h = s.paper === 'Receipt' || s.template === 'receipt' ? 'centered' : s.header_style
  if (h === 'centered') return `<div class="head h-centered">${company()}<h1 class="title">${esc(title)}</h1>${subtitle ? `<div class="sub muted">${esc(subtitle)}</div>` : ''}<div class="muted">${meta.join(' · ')}</div></div>`
  if (h === 'banner') return `<div class="head h-banner"><div>${titleBlock}</div><div class="right">${company(true)}</div></div>`
  if (h === 'stacked') return `<div class="head h-stacked"><div class="top">${logoHtml(ctx)}<div><div class="co">${esc(name)}</div><div class="muted">${contact}</div></div></div>${titleBlock}</div>`
  return `<div class="head h-split"><div>${titleBlock}</div><div class="right">${company()}</div></div>`
}

function footer(ctx: DocContext) {
  const s = ctx.settings
  const sig = s.show_signatures ? '<div class="sig"><div>Prepared by</div><div>Checked by</div><div>Received by</div></div>' : ''
  return `${sig}${s.footer_text ? `<div class="foot">${esc(s.footer_text)}</div>` : ''}`
}

const MONEY = /^-?₦\s?[\d,]+(\.\d+)?$/
const parseMoney = (v: any) => Number(String(v).replace(/[₦,\s]/g, ''))
const fmtMoney = (n: number) => `${n < 0 ? '-' : ''}₦${Math.abs(n).toLocaleString('en-NG', { maximumFractionDigits: 2 })}`

function totalsRow(columns: string[], rows: any[][]) {
  if (rows.length < 2) return null
  const sums: (string | null)[] = columns.map((_, i) => {
    const vals = rows.map((r) => r[i]).filter((v) => v !== '' && v != null && v !== '-')
    if (vals.length && vals.every((v) => MONEY.test(String(v).trim()))) return fmtMoney(vals.reduce((t, v) => t + parseMoney(v), 0))
    return null
  })
  if (!sums.some(Boolean)) return null
  return columns.map((_, i) => (i === 0 && !sums[0] ? 'Total' : sums[i] ?? ''))
}

function tableHtml(ctx: DocContext, columns: string[], rows: any[][], right?: boolean[], withTotals = true) {
  const num = ctx.settings.show_row_numbers
  const isRight = (i: number) => (right?.[i] ? ' class="r"' : '')
  const tot = withTotals && ctx.settings.show_totals ? totalsRow(columns, rows) : null
  const totHtml = tot
    ? `<tr class="total">${num ? '<td></td>' : ''}${tot.map((v, i) => `<td${right?.[i] || MONEY.test(String(v)) ? ' class="r"' : ''}>${esc(v)}</td>`).join('')}</tr>`
    : ''
  return `<table><thead><tr>${num ? '<th>#</th>' : ''}${columns.map((c, i) => `<th${isRight(i)}>${esc(c)}</th>`).join('')}</tr></thead><tbody>${
    rows.map((r, n) => `<tr>${num ? `<td>${n + 1}</td>` : ''}${r.map((v, i) => `<td${right?.[i] || MONEY.test(String(v ?? '').trim()) ? ' class="r"' : ''}>${esc(v)}</td>`).join('')}</tr>`).join('')
  }${totHtml}</tbody></table>`
}

const wrap = (title: string, style: string, ctx: DocContext, body: string) =>
  `<!doctype html><html><head><meta charset="utf-8"><title>${esc(title)}</title><style>${style}</style></head><body>${ctx.settings.watermark ? `<div class="wm">${esc(ctx.settings.watermark)}</div>` : ''}<div class="page">${body}</div></body></html>`

export function buildTableDoc(d: TableDoc, ctx: DocContext, preview = false): string {
  const body = header(ctx, d.title, d.subtitle) + tableHtml(ctx, d.columns, d.rows, d.rightAlign) + footer(ctx)
  return wrap(d.title, css(ctx.settings, d.columns.length > 5, preview), ctx, body)
}

export function buildRecordDoc(d: RecordDoc, ctx: DocContext, preview = false): string {
  const kv = `<div class="kv">${d.fields.map(([k, v]) => `<div><span>${esc(k)}</span><b>${esc(v)}</b></div>`).join('')}</div>`
  const tables = (d.tables || []).map((t) => `<h2>${esc(t.heading)}</h2>${tableHtml(ctx, t.columns, t.rows, undefined, true)}`).join('')
  return wrap(d.title, css(ctx.settings, false, preview), ctx, header(ctx, d.title, d.subtitle) + kv + tables + footer(ctx))
}

/** Print through a hidden frame so the page behind stays as it is. The browser's print window offers "Save as PDF". */
export function printHtml(html: string) {
  const frame = document.createElement('iframe')
  frame.style.cssText = 'position:fixed;right:0;bottom:0;width:0;height:0;border:0'
  document.body.appendChild(frame)
  const doc = frame.contentDocument!
  doc.open(); doc.write(html); doc.close()
  const go = () => {
    frame.contentWindow?.focus()
    frame.contentWindow?.print()
    setTimeout(() => frame.remove(), 60000)
  }
  setTimeout(go, 300)
}
