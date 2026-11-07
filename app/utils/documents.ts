// Printable documents. Everything here is plain HTML so the browser can print it or save it as a PDF.

export interface DocSettings {
  template: 'classic' | 'modern' | 'compact' | 'minimal'
  accent: string
  company_name: string
  address: string
  phone: string
  email: string
  footer_text: string
  paper: 'A4' | 'A5' | 'Letter'
  orientation: 'auto' | 'portrait' | 'landscape'
  show_logo: boolean
  show_date: boolean
  show_prepared_by: boolean
  show_signatures: boolean
  show_row_numbers: boolean
}

export const DEFAULT_DOCS: DocSettings = {
  template: 'classic', accent: '#059669', company_name: '', address: '', phone: '', email: '',
  footer_text: 'Thank you for your business.', paper: 'A4', orientation: 'auto',
  show_logo: true, show_date: true, show_prepared_by: true, show_signatures: false, show_row_numbers: false,
}

export const TEMPLATE_INFO = [
  { value: 'classic', label: 'Classic', hint: 'Coloured header bar, striped rows' },
  { value: 'modern', label: 'Modern', hint: 'Bold title, soft colour accents' },
  { value: 'compact', label: 'Compact', hint: 'Small text, fits more rows per page' },
  { value: 'minimal', label: 'Minimal', hint: 'Plain black and white, ink friendly' },
]

export function esc(v: any): string {
  return String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c] as string))
}

const safeHex = (h: string) => (/^#[0-9a-fA-F]{6}$/.test(h) ? h : '#059669')

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

function css(s: DocSettings, landscape: boolean) {
  const a = safeHex(s.accent)
  const t = s.template
  const size = t === 'compact' ? 10 : 12
  const pad = t === 'compact' ? '3px 6px' : '7px 10px'
  const orient = s.orientation === 'auto' ? (landscape ? 'landscape' : 'portrait') : s.orientation
  const th = t === 'classic' ? `background:${a};color:#fff;` : t === 'modern' ? `background:${a}1f;color:${a};` : t === 'compact' ? `background:#eee;color:#222;` : `border-bottom:2px solid #000;color:#000;`
  const stripe = t === 'classic' ? 'tbody tr:nth-child(even){background:#f6f6f6}' : ''
  const h1 = t === 'modern' ? `font-size:28px;color:${a};` : t === 'minimal' ? 'font-size:22px;color:#000;' : t === 'compact' ? 'font-size:17px;' : `font-size:22px;`
  const head = t === 'classic' ? `border-bottom:3px solid ${a};padding-bottom:10px;` : t === 'modern' ? `border-left:6px solid ${a};padding-left:12px;` : 'border-bottom:1px solid #999;padding-bottom:8px;'
  return `@page{size:${s.paper} ${orient};margin:14mm}
*{box-sizing:border-box}body{font-family:Arial,Helvetica,sans-serif;font-size:${size}px;color:#1a1a1a;margin:0}
.head{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;margin-bottom:14px;${head}}
.co{font-weight:700;font-size:${t === 'compact' ? 13 : 15}px}.muted{color:#666;font-size:${size - 1}px;line-height:1.5}
h1{margin:0 0 2px;${h1}}h2{font-size:${size + 2}px;margin:16px 0 6px}
table{width:100%;border-collapse:collapse;margin-top:8px}
th{${th}text-align:left;padding:${pad};font-size:${size - 1}px;text-transform:uppercase;letter-spacing:.03em}
td{padding:${pad};border-bottom:1px solid #ddd;vertical-align:top}${stripe}
.r{text-align:right}.kv{display:grid;grid-template-columns:repeat(2,1fr);gap:6px 24px;margin:10px 0}
.kv div span{display:block;color:#666;font-size:${size - 2}px;text-transform:uppercase;letter-spacing:.03em}
.kv div b{font-weight:600}
.sig{display:flex;gap:40px;margin-top:48px}.sig div{flex:1;border-top:1px solid #333;padding-top:4px;font-size:${size - 1}px;color:#555}
.foot{margin-top:22px;padding-top:8px;border-top:1px solid #ccc;text-align:center;color:#666;font-size:${size - 1}px}
.logo{display:inline-block;vertical-align:middle;margin-right:8px}
thead{display:table-header-group}tr{page-break-inside:avoid}`
}

function header(ctx: DocContext, title: string, subtitle?: string) {
  const s = ctx.settings
  const a = safeHex(s.accent)
  const name = s.company_name || ctx.fallbackName || ''
  const logo = s.show_logo
    ? `<svg class="logo" width="30" height="30" viewBox="0 0 64 64"><rect x="2" y="2" width="60" height="60" rx="14" fill="${a}"/><circle cx="26" cy="26" r="10" fill="none" stroke="#fff" stroke-width="5"/><line x1="33" y1="33" x2="48" y2="48" stroke="#fff" stroke-width="6" stroke-linecap="round"/></svg>`
    : ''
  const contact = [s.address, s.phone, s.email].filter(Boolean).map(esc).join('<br>')
  const meta: string[] = []
  if (s.show_date) meta.push(new Date().toLocaleDateString('en-NG', { day: 'numeric', month: 'long', year: 'numeric' }))
  if (s.show_prepared_by && ctx.preparedBy) meta.push(`Prepared by ${esc(ctx.preparedBy)}`)
  return `<div class="head"><div><h1>${esc(title)}</h1>${subtitle ? `<div class="muted">${esc(subtitle)}</div>` : ''}<div class="muted">${meta.join(' · ')}</div></div>
<div style="text-align:right"><div class="co">${logo}${esc(name)}</div><div class="muted">${contact}</div></div></div>`
}

function footer(ctx: DocContext) {
  const s = ctx.settings
  const sig = s.show_signatures ? '<div class="sig"><div>Prepared by</div><div>Checked by</div><div>Received by</div></div>' : ''
  return `${sig}${s.footer_text ? `<div class="foot">${esc(s.footer_text)}</div>` : ''}`
}

function tableHtml(ctx: DocContext, columns: string[], rows: any[][], right?: boolean[]) {
  const num = ctx.settings.show_row_numbers
  const isRight = (i: number) => (right?.[i] ? ' class="r"' : '')
  return `<table><thead><tr>${num ? '<th>#</th>' : ''}${columns.map((c, i) => `<th${isRight(i)}>${esc(c)}</th>`).join('')}</tr></thead><tbody>${
    rows.map((r, n) => `<tr>${num ? `<td>${n + 1}</td>` : ''}${r.map((v, i) => `<td${isRight(i)}>${esc(v)}</td>`).join('')}</tr>`).join('')
  }</tbody></table>`
}

const wrap = (title: string, style: string, body: string) =>
  `<!doctype html><html><head><meta charset="utf-8"><title>${esc(title)}</title><style>${style}</style></head><body>${body}</body></html>`

export function buildTableDoc(d: TableDoc, ctx: DocContext): string {
  const body = header(ctx, d.title, d.subtitle) + tableHtml(ctx, d.columns, d.rows, d.rightAlign) + footer(ctx)
  return wrap(d.title, css(ctx.settings, d.columns.length > 5), body)
}

export function buildRecordDoc(d: RecordDoc, ctx: DocContext): string {
  const kv = `<div class="kv">${d.fields.map(([k, v]) => `<div><span>${esc(k)}</span><b>${esc(v)}</b></div>`).join('')}</div>`
  const tables = (d.tables || []).map((t) => `<h2>${esc(t.heading)}</h2>${tableHtml(ctx, t.columns, t.rows)}`).join('')
  return wrap(d.title, css(ctx.settings, false), header(ctx, d.title, d.subtitle) + kv + tables + footer(ctx))
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
  setTimeout(go, 250)
}
