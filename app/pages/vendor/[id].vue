<script setup lang="ts">
const route = useRoute()
const { printRecord, exportExcel } = useDocs()
const { needs } = useGuard()
const warehouses = ref<any[]>([])
const showReceive = ref(false)
const showAddProduct = ref(false)
const receiveProduct = ref(0)
const id = route.params.id
const rec = ref<any>(null)
const detail = ref<any>(null)
const loading = ref(true)
const loadError = ref('')
const tab = ref('sales')
const from = ref('')
const to = ref('')
const tabs = [
  { label: 'Sales', value: 'sales', icon: 'i-lucide-shopping-bag' },
  { label: 'Money paid to vendor', value: 'money', icon: 'i-lucide-banknote' },
  { label: 'Stock held', value: 'stock', icon: 'i-lucide-warehouse' },
  { label: 'Contacts', value: 'contacts', icon: 'i-lucide-contact' },
]

async function load() {
  loading.value = true; loadError.value = ''
  try {
    const p = new URLSearchParams()
    if (from.value) p.set('date_from', from.value)
    if (to.value) p.set('date_to', to.value)
    const [r, d] = await Promise.all([api(`/vendors/${id}/record?${p}`), api(`/vendors/${id}`)])
    rec.value = r; detail.value = d
    preview.value = await api(`/settlements/preview?vendor_id=${id}`).catch(() => null)
    if (!warehouses.value.length) warehouses.value = (await api('/inventory/warehouses').catch(() => [])).filter((w: any) => w.is_active)
  } catch (e) { loadError.value = errMsg(e) } finally { loading.value = false }
}
onMounted(load)

// settlement from this page
const preview = ref<any>(null)
const building = ref(false)
const stlId = ref<number | null>(null)
const showStl = ref(false)
const openStl = computed(() => (rec.value?.settlements || []).filter((x: any) => x.status !== 'PAID' && x.status !== 'REVERSED'))
const { busy: exporting, copy: copySel, pdf: pdfSel, excel: excelSel } = useSettlementExport()
const picked = ref<number[]>([])
const payableStl = computed(() => openStl.value.filter((x: any) => ['APPROVED', 'PARTIALLY_PAID'].includes(x.status)))
const pickedRows = computed(() => payableStl.value.filter((x: any) => picked.value.includes(x.id))
  .map((x: any) => ({ id: x.id, reference: x.reference, owed_kobo: x.net_kobo - x.paid_kobo })))
const showBatch = ref(false)
function toggleStl(id: number) { picked.value = picked.value.includes(id) ? picked.value.filter(x => x !== id) : [...picked.value, id] }
function afterBatch() { picked.value = []; load() }
function openSettlement(row: any) { stlId.value = row.id; showStl.value = true }
async function buildSettlement() {
  building.value = true
  try {
    const r = await api('/settlements/build', { method: 'POST', body: { vendor_id: Number(id) } })
    useToast().add({ title: `Settlement ${r.reference} built`, description: `${fmtNaira(r.net_kobo)} net payable. Review it, add any charge, then approve.`, color: 'success' })
    await load()
    stlId.value = r.id; showStl.value = true
  } catch (e) { useToast().add({ title: 'Nothing to settle', description: errMsg(e), color: 'error' }) } finally { building.value = false }
}
function clearDates() { from.value = ''; to.value = ''; load() }

const s = computed(() => rec.value?.summary || {})
const periodText = computed(() => from.value || to.value
  ? `${from.value ? fmtDate(from.value) : 'the beginning'} to ${to.value ? fmtDate(to.value) : 'today'}` : 'All time')

const salesRows = computed(() => (rec.value?.sales || []).map((o: any) => ({
  ...o, when: fmtDate(o.date), items_value: fmtNaira(o.items_total_kobo),
  charges: o.status === 'DELIVERED' ? fmtNaira(o.charges_kobo) : '-',
  net: o.status === 'DELIVERED' ? fmtNaira(o.net_kobo) : '-',
})))
const payRows = computed(() => (rec.value?.remittances || []).map((p: any) => ({
  ...p, when: fmtDate(p.date), amount: fmtNaira(p.amount_kobo), method_label: titleize(p.method),
  settlement_ref: p.settlement || '-', bank_ref: p.bank_ref || '-',
})))
const stlRows = computed(() => (rec.value?.settlements || []).map((x: any) => ({
  ...x, when: fmtDate(x.date), orders_text: (x.orders || []).join(', ') || '-',
  gross: fmtNaira(x.gross_kobo), charges: fmtNaira(x.charges_kobo), net: fmtNaira(x.net_kobo), paid: fmtNaira(x.paid_kobo),
})))
const stockRows = computed(() => (rec.value?.stock || []).map((x: any) => ({ ...x, price: fmtNaira(x.price_kobo), low: x.available <= x.reorder_level })))
const lowCount = computed(() => stockRows.value.filter((x: any) => x.low).length)
const initials = computed(() => (v.value.name || '?').split(/\s+/).filter(Boolean).slice(0, 2).map((w: string) => w[0]).join('').toUpperCase())
function receiveMore(productId = 0) { receiveProduct.value = productId; showReceive.value = true }

const v = computed(() => rec.value?.vendor || {})
const fileTitle = computed(() => `${v.value.name || 'Vendor'} statement`)

async function printStatement() {
  const r = rec.value
  await printRecord({
    title: `Vendor statement: ${v.value.name}`,
    subtitle: `${v.value.code} · ${periodText.value} · prepared ${fmtDate(new Date().toISOString())}`,
    fields: [
      ['Vendor', v.value.name], ['Period', periodText.value],
      ['Delivered orders', String(s.value.delivered)], ['Units sold', String(s.value.units_sold)],
      ['Normal price value', fmtNaira(s.value.normal_value_kobo)],
      ['Offers and discounts given', fmtNaira(s.value.offers_kobo)],
      ['Sales after discounts', fmtNaira(s.value.sales_kobo)],
      ['Free gifts given', `${s.value.gift_units} item(s) worth ${fmtNaira(s.value.gift_value_kobo)}`],
      ['Cash collected from customers', fmtNaira(s.value.collected_kobo)],
      ['Our charges', fmtNaira(s.value.charges_kobo)],
      ['Earned by vendor', fmtNaira(s.value.earned_kobo)],
      ['Paid to vendor', fmtNaira(s.value.paid_out_kobo)],
      ['Balance still owed', fmtNaira(s.value.balance_kobo)],
    ],
    tables: [
      { heading: 'What was sold', columns: ['Order', 'Date', 'Customer', 'Details', 'Items value', 'Charges', 'Net to vendor', 'Status'],
        rows: r.sales.map((o: any) => [o.reference, fmtDate(o.date), o.customer, o.narration,
          fmtNaira(o.items_total_kobo), o.status === 'DELIVERED' ? fmtNaira(o.charges_kobo) : '-',
          o.status === 'DELIVERED' ? fmtNaira(o.net_kobo) : '-', titleize(o.status)]) },
      { heading: 'Money paid to the vendor', columns: ['Date', 'Settlement', 'Amount', 'Method', 'Bank reference'],
        rows: r.remittances.map((p: any) => [fmtDate(p.date), p.settlement || '-', fmtNaira(p.amount_kobo), titleize(p.method), p.bank_ref || '-']) },
      { heading: 'Settlements', columns: ['Settlement', 'Date', 'Orders covered', 'Collected', 'Charges', 'Net', 'Paid', 'Status'],
        rows: r.settlements.map((x: any) => [x.reference, fmtDate(x.date), (x.orders || []).join(', ') || '-',
          fmtNaira(x.gross_kobo), fmtNaira(x.charges_kobo), fmtNaira(x.net_kobo), fmtNaira(x.paid_kobo), titleize(x.status)]) },
    ],
  })
}
async function excelSales() {
  await exportExcel(`${v.value.name} sales detail`,
    ['Order', 'Date', 'Customer', 'Product', 'Code', 'Qty', 'Price each', 'Line total', 'Saved on this line', 'Free gift', 'Order status'],
    rec.value.lines.map((l: any) => [l.order, fmtDate(l.date), l.customer, l.product, l.sku, l.qty, fmtNaira(l.unit_price_kobo),
      fmtNaira(l.line_total_kobo), fmtNaira(l.line_discount_kobo), l.is_gift ? 'Yes' : 'No', titleize(l.status)]),
    `${v.value.name} · ${periodText.value}`)
}
async function excelPayments() {
  await exportExcel(`${v.value.name} payments`,
    ['Date', 'Settlement', 'Amount', 'Method', 'Bank reference', 'Recorded by', 'Note'],
    rec.value.remittances.map((p: any) => [fmtDate(p.date), p.settlement || '-', fmtNaira(p.amount_kobo), titleize(p.method), p.bank_ref || '-', p.recorded_by, p.note]),
    `${v.value.name} · ${periodText.value}`)
}
const exportItems = computed(() => [[
  { label: 'Print statement (PDF)', icon: 'i-lucide-printer', onSelect: printStatement },
  { label: 'Sales, line by line (Excel)', icon: 'i-lucide-file-spreadsheet', onSelect: excelSales },
  { label: 'Payments made (Excel)', icon: 'i-lucide-file-spreadsheet', onSelect: excelPayments },
]])
const moreItems = computed(() => [[paused.value
  ? { label: 'Reactivate vendor', icon: 'i-lucide-play', onSelect: () => setStatus('ACTIVE') }
  : { label: 'Suspend vendor', icon: 'i-lucide-pause', color: 'error' as const, onSelect: () => { confirmPause.value = true } }]])

const confirmPause = ref(false)
const pausing = ref(false)
async function setStatus(next: string) {
  pausing.value = true
  try {
    await api(`/vendors/${id}`, { method: 'PATCH', body: { status: next } })
    confirmPause.value = false
    useToast().add({ title: next === 'ACTIVE' ? 'Vendor reactivated' : 'Vendor suspended', color: 'success' })
    await load()
  } catch (e) { useToast().add({ title: 'Could not change the status', description: errMsg(e), color: 'error' }) } finally { pausing.value = false }
}
const paused = computed(() => v.value.status && v.value.status !== 'ACTIVE')
const contactForm = reactive({ name: '', phone: '' })
async function addContact() {
  if (!needs([['Contact name', contactForm.name], ['Phone number', contactForm.phone]])) return
  try {
    await api(`/vendors/${id}/contacts`, { method: 'POST', body: { name: contactForm.name, phone: contactForm.phone } })
    contactForm.name = ''; contactForm.phone = ''
    useToast().add({ title: 'Contact added and WhatsApp number registered', color: 'success' })
    await load()
  } catch (e) { useToast().add({ title: 'Could not add the contact', description: errMsg(e), color: 'error' }) }
}
</script>

<template>
  <div>
    <div v-if="loading && !rec" class="flex items-center gap-2 text-zinc-400 py-20 justify-center">
      <UIcon name="i-lucide-loader-circle" class="animate-spin" /> Loading vendor…
    </div>
    <div v-else-if="loadError" class="py-20 text-center">
      <p class="text-sm text-zinc-500 mb-4">Could not load this vendor. {{ loadError }}</p>
      <UButton variant="outline" color="neutral" @click="load">Try again</UButton>
    </div>

    <template v-else-if="rec">
      <UButton to="/vendors" icon="i-lucide-arrow-left" color="neutral" variant="link" size="xs" class="mb-2 -ml-2">All vendors</UButton>

      <!-- identity + actions -->
      <div class="rounded-2xl border border-zinc-200 dark:border-zinc-800 bg-gradient-to-br from-primary-50 via-white to-white dark:from-primary-950/40 dark:via-zinc-900 dark:to-zinc-900 p-4 sm:p-5 mb-4">
        <div class="flex flex-wrap items-start gap-4">
          <div class="w-14 h-14 rounded-2xl bg-primary-600 text-white grid place-items-center text-xl font-bold shrink-0 shadow-sm">{{ initials }}</div>
          <div class="min-w-0 flex-1 basis-56">
            <div class="flex flex-wrap items-center gap-2">
              <h1 class="text-xl sm:text-2xl font-bold leading-tight">{{ v.name }}</h1>
              <StatusBadge :status="v.status" />
            </div>
            <div class="flex flex-wrap gap-x-4 gap-y-1 mt-1.5 text-sm text-zinc-500">
              <span class="font-mono">{{ v.code }}</span>
              <span v-if="v.city" class="inline-flex items-center gap-1"><UIcon name="i-lucide-map-pin" class="w-3.5 h-3.5" />{{ [v.city, v.state].filter(Boolean).join(', ') }}</span>
              <span v-if="v.phone" class="inline-flex items-center gap-1"><UIcon name="i-lucide-phone" class="w-3.5 h-3.5" />{{ v.phone }}</span>
              <span v-if="v.email" class="inline-flex items-center gap-1"><UIcon name="i-lucide-mail" class="w-3.5 h-3.5" />{{ v.email }}</span>
            </div>
          </div>
          <div class="flex flex-wrap items-center gap-2">
            <UButton icon="i-lucide-package-plus" :disabled="paused" @click="receiveMore()">Receive stock</UButton>
            <UButton icon="i-lucide-sparkles" color="neutral" variant="outline" :disabled="paused" @click="showAddProduct = true">Add product</UButton>
            <UDropdownMenu :items="exportItems">
              <UButton icon="i-lucide-file-text" color="neutral" variant="outline" trailing-icon="i-lucide-chevron-down">Statement</UButton>
            </UDropdownMenu>
            <UDropdownMenu :items="moreItems">
              <UButton icon="i-lucide-ellipsis" color="neutral" variant="ghost" aria-label="More actions" />
            </UDropdownMenu>
          </div>
        </div>
      </div>

      <UAlert v-if="paused" class="mb-4" color="warning" variant="subtle" icon="i-lucide-pause-circle"
              :title="`${v.name} is ${titleize(v.status).toLowerCase()}`"
              description="Paused until you reactivate: new orders, new products, stock receipts and transfers, WhatsApp orders and portal sign-in. Orders already on the way, money owed and all history stay as they are." />

      <!-- period -->
      <div class="flex flex-wrap items-end gap-2 mb-3">
        <div class="mr-auto">
          <p class="text-[11px] font-semibold uppercase tracking-wider text-zinc-400">Showing</p>
          <p class="text-sm font-medium">{{ periodText }}</p>
        </div>
        <div class="flex items-end gap-2 w-full sm:w-auto">
          <UFormField label="From" class="flex-1 sm:flex-none"><UInput v-model="from" type="date" size="sm" class="w-full sm:w-36" /></UFormField>
          <UFormField label="To" class="flex-1 sm:flex-none"><UInput v-model="to" type="date" size="sm" class="w-full sm:w-36" /></UFormField>
          <UButton size="sm" variant="soft" @click="load">Show</UButton>
          <UButton v-if="from || to" size="sm" variant="ghost" color="neutral" @click="clearDates">All time</UButton>
        </div>
      </div>

      <!-- the money, as a sum that adds up -->
      <div class="rounded-2xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-3 sm:p-4 mb-3">
        <p class="text-[11px] font-semibold uppercase tracking-wider text-zinc-400 mb-3">The money</p>
        <div class="grid grid-cols-2 lg:grid-cols-[1fr_auto_1fr_auto_1fr_auto_1fr_auto_1fr] gap-x-2 gap-y-3 items-center">
          <div><p class="text-xs text-zinc-500">Collected from customers</p><p class="text-lg sm:text-xl font-bold tabular-nums">{{ fmtNaira(s.collected_kobo) }}</p><p class="text-[11px] text-zinc-400">includes delivery fees</p></div>
          <span class="hidden lg:block text-zinc-300 text-xl">−</span>
          <div><p class="text-xs text-zinc-500">Our charges</p><p class="text-lg sm:text-xl font-bold tabular-nums text-amber-600">{{ fmtNaira(s.charges_kobo) }}</p><p v-if="s.other_charges_kobo" class="text-[11px] text-zinc-400">includes {{ fmtNaira(s.other_charges_kobo) }} added on settlements</p></div>
          <span class="hidden lg:block text-zinc-300 text-xl">=</span>
          <div><p class="text-xs text-zinc-500">Earned by vendor</p><p class="text-lg sm:text-xl font-bold tabular-nums">{{ fmtNaira(s.earned_kobo) }}</p></div>
          <span class="hidden lg:block text-zinc-300 text-xl">−</span>
          <div><p class="text-xs text-zinc-500">Paid to vendor</p><p class="text-lg sm:text-xl font-bold tabular-nums text-emerald-600">{{ fmtNaira(s.paid_out_kobo) }}</p></div>
          <span class="hidden lg:block text-zinc-300 text-xl">=</span>
          <div class="rounded-xl px-3 py-2 col-span-2 lg:col-span-1" :class="s.balance_kobo > 0 ? 'bg-primary-50 dark:bg-primary-950/40' : 'bg-zinc-50 dark:bg-zinc-800/60'">
            <p class="text-xs text-zinc-500">Still owed to vendor</p>
            <p class="text-lg sm:text-xl font-bold tabular-nums" :class="s.balance_kobo > 0 ? 'text-primary-700 dark:text-primary-400' : ''">{{ fmtNaira(s.balance_kobo) }}</p>
          </div>
        </div>
      </div>

      <!-- settle -->
      <div class="rounded-2xl border border-primary-200 dark:border-primary-900 bg-primary-50/50 dark:bg-primary-950/20 p-3 sm:p-4 mb-3">
        <div class="flex flex-wrap items-center gap-3">
          <div class="min-w-0 flex-1 basis-60">
            <p class="text-[11px] font-semibold uppercase tracking-wider text-zinc-400">Settlement</p>
            <template v-if="preview?.collections">
              <p class="text-sm mt-0.5"><span class="font-bold text-lg tabular-nums">{{ fmtNaira(preview.net_kobo) }}</span> ready to pay {{ v.name }}</p>
              <p class="text-xs text-zinc-500">{{ preview.collections }} delivered order{{ preview.collections === 1 ? '' : 's' }} ({{ preview.orders.join(', ') }}) · collected {{ fmtNaira(preview.gross_kobo) }} less our charges {{ fmtNaira(preview.charges_kobo) }}</p>
            </template>
            <p v-else class="text-sm text-zinc-500 mt-0.5">Nothing waiting to be settled. Delivered COD orders appear here automatically.</p>
          </div>
          <UButton v-if="preview?.can_build" icon="i-lucide-calculator" :loading="building" @click="buildSettlement">Settle now</UButton>
        </div>
        <div v-if="openStl.length" class="mt-3 pt-3 border-t border-primary-100 dark:border-primary-900 space-y-1.5">
          <p class="text-xs text-zinc-500">Open settlements</p>
          <div v-for="x in openStl" :key="x.id" class="flex items-center gap-2">
            <UCheckbox :model-value="picked.includes(x.id)" @update:model-value="toggleStl(x.id)" />
            <button type="button" class="flex-1 min-w-0 flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 px-3 py-2 text-left hover:border-primary-400" @click="openSettlement(x)">
              <UTooltip :ui="{ content: 'max-w-sm h-auto whitespace-normal py-2' }">
                <span class="font-mono font-semibold text-primary-600 text-sm">{{ x.reference }}</span>
                <template #content><div class="space-y-1.5 text-xs"><p v-for="n in x.notes" :key="n">{{ n }}</p><p v-if="!x.notes?.length">No orders attached</p></div></template>
              </UTooltip>
              <StatusBadge :status="x.status" />
              <span class="text-sm font-semibold tabular-nums ml-auto">{{ fmtNaira(x.net_kobo - x.paid_kobo) }} <span class="text-xs font-normal text-zinc-400">to pay</span></span>
            </button>
          </div>
          <div class="flex flex-wrap items-center gap-2 pt-1">
            <UButton size="xs" variant="ghost" color="neutral" @click="picked = picked.length === openStl.length ? [] : openStl.map((x: any) => x.id)">{{ picked.length === openStl.length ? 'Clear' : 'Select all' }}</UButton>
            <UButton size="xs" color="neutral" variant="outline" icon="i-lucide-clipboard-copy" :disabled="!picked.length || exporting" @click="copySel(picked)">Copy</UButton>
            <UButton size="xs" color="neutral" variant="outline" icon="i-lucide-printer" :disabled="!picked.length || exporting" @click="pdfSel(picked)">PDF</UButton>
            <UButton size="xs" color="neutral" variant="outline" icon="i-lucide-file-spreadsheet" :disabled="!picked.length || exporting" @click="excelSel(picked)">Excel</UButton>
            <UButton size="xs" icon="i-lucide-banknote" :disabled="!pickedRows.length" @click="showBatch = true">Pay selected ({{ pickedRows.length }})</UButton>
          </div>
        </div>
      </div>

      <!-- sales numbers -->
      <div class="rounded-2xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 mb-5 grid grid-cols-2 sm:grid-cols-5 divide-zinc-100 dark:divide-zinc-800 sm:divide-x">
        <div class="p-3 sm:p-4"><p class="text-xs text-zinc-500">Delivered orders</p><p class="text-xl font-bold">{{ s.delivered }}</p><p class="text-[11px] text-zinc-400">{{ s.open }} still open</p></div>
        <div class="p-3 sm:p-4"><p class="text-xs text-zinc-500">Units sold</p><p class="text-xl font-bold">{{ s.units_sold }}</p></div>
        <div class="p-3 sm:p-4"><p class="text-xs text-zinc-500">Sales after discounts</p><p class="text-xl font-bold tabular-nums">{{ fmtNaira(s.sales_kobo) }}</p></div>
        <div class="p-3 sm:p-4"><p class="text-xs text-zinc-500">Discounts given</p><p class="text-xl font-bold tabular-nums">{{ fmtNaira(s.offers_kobo) }}</p></div>
        <div class="p-3 sm:p-4 col-span-2 sm:col-span-1"><p class="text-xs text-zinc-500">Free gifts</p><p class="text-xl font-bold">{{ s.gift_units }}</p><p class="text-[11px] text-zinc-400">worth {{ fmtNaira(s.gift_value_kobo) }}</p></div>
      </div>

      <ScrollTabs :items="tabs" v-model="tab" class="mb-4" />

      <DataTable v-if="tab === 'sales'" :export-title="`${v.name} sales`" :columns="[
        { key: 'reference', label: 'Order' },
        { key: 'when', label: 'Date' },
        { key: 'customer', label: 'Customer' },
        { key: 'narration', label: 'What was sold' },
        { key: 'items_value', label: 'Items value', align: 'right' },
        { key: 'charges', label: 'Charges', align: 'right' },
        { key: 'net', label: 'Net to vendor', align: 'right' },
        { key: 'status', label: 'Status' },
      ]" :rows="salesRows" clickable empty-title="No orders for this vendor in this period" @row-click="(r: any) => navigateTo(`/orders/${r.id}`)">
        <template #reference="{ row }"><span class="font-mono font-semibold text-primary-600">{{ row.reference }}</span></template>
        <template #narration="{ row }"><p class="text-xs max-w-md whitespace-normal">{{ row.narration }}</p></template>
        <template #status="{ row }">
          <StatusBadge :status="row.status" />
          <p v-if="row.settled" class="text-[11px] text-emerald-600 mt-0.5">in a settlement</p>
        </template>
      </DataTable>

      <template v-else-if="tab === 'money'">
        <p class="text-sm font-semibold mb-2">Payments made to {{ v.name }}</p>
        <DataTable :export-title="`${v.name} payments`" :columns="[
          { key: 'when', label: 'Date' },
          { key: 'settlement_ref', label: 'Settlement' },
          { key: 'amount', label: 'Amount', align: 'right' },
          { key: 'method_label', label: 'Method' },
          { key: 'bank_ref', label: 'Bank reference' },
          { key: 'recorded_by', label: 'Recorded by' },
        ]" :rows="payRows" empty-title="Nothing has been paid to this vendor yet" />
        <p class="text-sm font-semibold mt-6 mb-2">Settlements and the orders they cover</p>
        <DataTable :export-title="`${v.name} settlements`" :columns="[
          { key: 'reference', label: 'Settlement' },
          { key: 'when', label: 'Date' },
          { key: 'orders_text', label: 'Orders covered' },
          { key: 'gross', label: 'Collected', align: 'right' },
          { key: 'charges', label: 'Charges', align: 'right' },
          { key: 'net', label: 'Net', align: 'right' },
          { key: 'paid', label: 'Paid', align: 'right' },
          { key: 'status', label: 'Status' },
        ]" :rows="stlRows" clickable empty-title="No settlements yet" @row-click="openSettlement">
          <template #reference="{ row }">
            <UTooltip :ui="{ content: 'max-w-sm h-auto whitespace-normal py-2' }">
              <span class="font-mono font-semibold text-primary-600">{{ row.reference }}</span>
              <template #content><div class="space-y-1.5 text-xs"><p v-for="n in row.notes" :key="n">{{ n }}</p><p v-if="!row.notes?.length">No orders attached</p></div></template>
            </UTooltip>
          </template>
          <template #orders_text="{ row }"><p class="text-xs max-w-xs whitespace-normal">{{ row.orders_text }}</p></template>
          <template #status="{ row }"><StatusBadge :status="row.status" /></template>
        </DataTable>
      </template>

      <template v-else-if="tab === 'stock'">
        <div class="flex flex-wrap items-center gap-2 mb-3">
          <p class="text-sm text-zinc-500 mr-auto">
            {{ stockRows.length }} product{{ stockRows.length === 1 ? '' : 's' }}
            <template v-if="lowCount"> · <span class="text-amber-600 font-medium">{{ lowCount }} running low</span></template>
          </p>
          <UButton size="sm" icon="i-lucide-package-plus" :disabled="paused" @click="receiveMore()">Receive stock</UButton>
          <UButton size="sm" icon="i-lucide-sparkles" color="neutral" variant="outline" :disabled="paused" @click="showAddProduct = true">Add product</UButton>
        </div>
        <DataTable :export-title="`${v.name} stock`" :columns="[
          { key: 'name', label: 'Product' },
          { key: 'price', label: 'Price', align: 'right' },
          { key: 'physical', label: 'In warehouse', align: 'right' },
          { key: 'reserved', label: 'Promised to orders', align: 'right' },
          { key: 'damaged', label: 'Damaged', align: 'right' },
          { key: 'available', label: 'Free to sell', align: 'right' },
          { key: 'actions', label: '' },
        ]" :rows="stockRows" empty-title="No products yet" empty-hint="Add the first product, then receive stock against it.">
          <template #name="{ row }">
            <p class="font-medium">{{ row.name }}</p>
            <p class="text-[11px] text-zinc-400 font-mono">{{ row.sku }}</p>
          </template>
          <template #available="{ row }">
            <span :class="row.low ? 'text-amber-600 font-semibold' : ''">{{ row.available }}</span>
            <UBadge v-if="row.low" color="warning" variant="subtle" size="xs" class="ml-1.5">Low</UBadge>
          </template>
          <template #actions="{ row }">
            <UButton size="xs" variant="soft" icon="i-lucide-plus" :disabled="paused" @click.stop="receiveMore(row.id)">Receive</UButton>
          </template>
        </DataTable>
      </template>

      <div v-else-if="tab === 'contacts'" class="max-w-2xl space-y-4">
        <p class="font-semibold text-sm">Authorized contacts and WhatsApp numbers</p>
        <div class="space-y-2">
          <div v-for="c in detail?.contacts || []" :key="c.id" class="flex flex-wrap items-center gap-2 text-sm bg-zinc-50 dark:bg-zinc-800/60 rounded-lg px-3 py-2">
            <UIcon name="i-lucide-message-circle" class="w-4 h-4 text-emerald-500" />
            <span class="font-medium">{{ c.name }}</span>
            <span class="font-mono text-zinc-500">{{ c.phone }}</span>
            <UBadge v-if="c.wa_verified" color="success" variant="subtle" size="xs">verified</UBadge>
            <UBadge v-if="c.is_primary" color="primary" variant="subtle" size="xs">primary</UBadge>
          </div>
          <p v-if="!(detail?.contacts || []).length" class="text-sm text-zinc-500">No contacts yet.</p>
        </div>
        <div class="flex flex-wrap gap-2">
          <UInput v-model="contactForm.name" placeholder="Contact name" size="sm" class="w-44" />
          <UInput v-model="contactForm.phone" placeholder="08012345678" size="sm" class="w-44" />
          <UButton size="sm" variant="soft" @click="addContact">Add number</UButton>
        </div>
        <div v-if="detail?.agreements?.length">
          <p class="font-semibold text-sm mb-2">Agreements</p>
          <div v-for="a in detail.agreements" :key="a.id" class="text-sm border border-zinc-200 dark:border-zinc-800 rounded-lg p-3">
            <p class="font-medium">{{ a.title }} <UBadge :color="a.status === 'ACTIVE' ? 'success' : 'neutral'" variant="subtle" size="xs" class="ml-1">{{ titleize(a.status) }}</UBadge></p>
            <p class="text-zinc-500 text-xs mt-1">{{ a.terms }}</p>
          </div>
        </div>
      </div>
    </template>

    <SettlementPayBatch v-model:open="showBatch" :rows="pickedRows" @changed="afterBatch" />
    <SettlementDetail v-model:open="showStl" :id="stlId" @changed="load" />
    <ReceiveStock v-model:open="showReceive" :vendors="rec ? [v] : []" :warehouses="warehouses" :vendor-id="Number(id)" :product-id="receiveProduct" @done="load" />
    <QuickProduct v-model:open="showAddProduct" :vendors="rec ? [v] : []" :vendor-id="Number(id)" @created="load" />

    <UModal v-model:open="confirmPause" title="Suspend this vendor?" :ui="{ content: 'max-w-md' }">
      <template #body>
        <p class="text-sm text-zinc-600 dark:text-zinc-300 mb-2">While {{ v.name }} is suspended:</p>
        <ul class="text-sm list-disc pl-5 space-y-1 text-zinc-600 dark:text-zinc-300">
          <li>No new orders, products, stock receipts or transfers can be made for them.</li>
          <li>Their WhatsApp messages wait in the unknown-sender list.</li>
          <li>They cannot sign in to the vendor portal.</li>
          <li>Their products and stock are marked as paused in the catalog and inventory.</li>
        </ul>
        <p class="text-sm mt-3">Orders already placed, money owed and history are not touched. Reactivate any time and everything comes back.</p>
      </template>
      <template #footer>
        <div class="flex justify-end gap-2 w-full">
          <UButton variant="ghost" color="neutral" @click="confirmPause = false">Keep active</UButton>
          <UButton color="error" :loading="pausing" @click="setStatus('SUSPENDED')">Suspend vendor</UButton>
        </div>
      </template>
    </UModal>
  </div>
</template>
