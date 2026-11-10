/** Money + date helpers - amounts cross the API as integer kobo. */
export function fmtNaira(kobo: number | null | undefined, withSymbol = true): string {
  const value = (kobo || 0) / 100
  const sign = value < 0 ? '-' : ''
  const s = Math.abs(value).toLocaleString('en-NG', { maximumFractionDigits: 2 })
  return `${sign}${withSymbol ? '₦' : ''}${s}`
}

export function toKobo(naira: number | string | null | undefined): number {
  const n = typeof naira === 'string' ? parseFloat(String(naira).replace(/[^0-9.]/g, '')) : (naira || 0)
  return Math.round((n || 0) * 100)
}

export function fmtDate(v: string | null | undefined): string {
  if (!v) return '-'
  const d = new Date(v.endsWith('Z') || v.includes('+') ? v : v + 'Z')
  if (isNaN(d.getTime())) return v
  return d.toLocaleDateString('en-NG', { day: '2-digit', month: 'short', year: 'numeric' })
}

export function fmtDateTime(v: string | null | undefined): string {
  if (!v) return '-'
  const d = new Date(v.endsWith('Z') || v.includes('+') ? v : v + 'Z')
  if (isNaN(d.getTime())) return v
  return d.toLocaleString('en-NG', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })
}

export function titleize(s: string | null | undefined): string {
  if (!s) return '-'
  return s.replace(/_/g, ' ').toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase())
}

export const ORDER_STATUSES = [
  'DRAFT', 'PENDING_REVIEW', 'AWAITING_INFORMATION', 'PENDING_VENDOR_CONFIRMATION',
  'CONFIRMED', 'PENDING_CUSTOMER_CONFIRMATION', 'CUSTOMER_CONFIRMED', 'PROCESSING',
  'READY_FOR_DISPATCH', 'DISPATCHED', 'IN_TRANSIT', 'DELIVERED', 'DELIVERY_FAILED',
  'RETURN_REQUESTED', 'RETURN_IN_TRANSIT', 'RETURNED_TO_WAREHOUSE', 'CANCELLED',
]

export const ORDER_TRANSITIONS: Record<string, string[]> = {
  DRAFT: ['PENDING_REVIEW', 'CONFIRMED', 'CANCELLED'],
  PENDING_REVIEW: ['CONFIRMED', 'AWAITING_INFORMATION', 'PENDING_VENDOR_CONFIRMATION', 'CANCELLED'],
  AWAITING_INFORMATION: ['PENDING_REVIEW', 'CONFIRMED', 'CANCELLED'],
  PENDING_VENDOR_CONFIRMATION: ['CONFIRMED', 'CANCELLED'],
  CONFIRMED: ['PENDING_CUSTOMER_CONFIRMATION', 'PROCESSING', 'READY_FOR_DISPATCH', 'CANCELLED'],
  PENDING_CUSTOMER_CONFIRMATION: ['CUSTOMER_CONFIRMED', 'CANCELLED'],
  CUSTOMER_CONFIRMED: ['PROCESSING', 'READY_FOR_DISPATCH', 'CANCELLED'],
  PROCESSING: ['READY_FOR_DISPATCH', 'PENDING_CUSTOMER_CONFIRMATION', 'CANCELLED'],
  READY_FOR_DISPATCH: ['DISPATCHED', 'IN_TRANSIT', 'DELIVERED', 'CANCELLED'],
  DISPATCHED: ['IN_TRANSIT', 'DELIVERED', 'DELIVERY_FAILED', 'RETURN_REQUESTED'],
  IN_TRANSIT: ['DELIVERED', 'DELIVERY_FAILED', 'RETURN_REQUESTED'],
  DELIVERED: ['RETURN_REQUESTED'],
  DELIVERY_FAILED: ['RETURN_REQUESTED', 'RETURN_IN_TRANSIT', 'READY_FOR_DISPATCH', 'CANCELLED'],
  RETURN_REQUESTED: ['RETURN_IN_TRANSIT', 'RETURNED_TO_WAREHOUSE'],
  RETURN_IN_TRANSIT: ['RETURNED_TO_WAREHOUSE'],
  RETURNED_TO_WAREHOUSE: [],
  CANCELLED: [],
}

export function statusColor(status: string): string {
  const s = (status || '').toUpperCase()
  if (['DELIVERED', 'CUSTOMER_CONFIRMED', 'VERIFIED', 'CONFIRMED', 'PAID', 'APPROVED'].includes(s)) return 'success'
  if (['CANCELLED', 'DELIVERY_FAILED', 'FAILED', 'DISCREPANCY', 'CUSTOMER_REJECTED', 'REJECTED', 'REVERSED'].includes(s)) return 'error'
  if (['IN_TRANSIT', 'DISPATCHED', 'OUT_FOR_DELIVERY', 'PROCESSING', 'PICKED_UP', 'RETURN_IN_TRANSIT', 'SENT'].includes(s)) return 'info'
  if (['READY_FOR_DISPATCH', 'READY_FOR_APPROVAL', 'PENDING_REVIEW', 'CONVERTED'].includes(s)) return 'primary'
  return 'neutral'
}

for (const st of ['CONFIRMED', 'PENDING_CUSTOMER_CONFIRMATION', 'CUSTOMER_CONFIRMED', 'PROCESSING', 'READY_FOR_DISPATCH', 'DISPATCHED', 'IN_TRANSIT', 'DELIVERY_FAILED']) {
  const l = ORDER_TRANSITIONS[st]
  if (!l.includes('DELIVERED')) l.splice(l[l.length - 1] === 'CANCELLED' ? l.length - 1 : l.length, 0, 'DELIVERED')
}
