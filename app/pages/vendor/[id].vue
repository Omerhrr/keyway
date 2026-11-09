<script setup lang="ts">
const route = useRoute()
const { printRecord, exportExcel } = useDocs()
const { needs } = useGuard()
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
  } catch (e) { loadError.value = errMsg(e) } finally { loading.value = false }
}
onMounted(load)
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
const stockRows = computed(() => (rec.value?.stock || []).map((x: any) => ({ ...x, price: fmtNaira(x.price_kobo) })))

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
  { label: 'Sales, line by line (Excel)', icon: 'i-lucide-file-spreadsheet', onSelect: excelSales },
  { label: 'Payments made (Excel)', icon: 'i-lucide-file-spreadsheet', onSelect: excelPayments },
]])

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
      <div class="flex items-center gap-2 mb-1">
        <UButton to="/vendors" icon="i-lucide-arrow-left" color="neutral" variant="ghost" size="xs" aria-label="Back to vendors" />
        <h1 class="text-xl sm:text-2xl font-bold">{{ v.name }}</h1>
        <StatusBadge :status="v.status" />
      </div>
      <p class="text-sm text-zinc-500 mb-4 ml-9">{{ v.code }}<template v-if="v.city"> · {{ v.city }}</template><template v-if="v.email"> · {{ v.email }}</template><template v-if="v.phone"> · {{ v.phone }}</template></p>

      <UAlert v-if="paused" class="mb-4" color="warning" variant="subtle" icon="i-lucide-pause-circle"
              :title="`${v.name} is ${titleize(v.status).toLowerCase()}`"
              description="Paused until you reactivate: new orders, new products, stock receipts and transfers, WhatsApp orders and portal sign-in. Orders already on the way, money owed and all history stay as they are." />

      <div class="flex flex-wrap items-end gap-2 mb-4">
        <UFormField label="From"><UInput v-model="from" type="date" class="w-40" /></UFormField>
        <UFormField label="To"><UInput v-model="to" type="date" class="w-40" /></UFormField>
        <UButton variant="soft" @click="load">Show</UButton>
        <UButton v-if="from || to" variant="ghost" color="neutral" @click="clearDates">All time</UButton>
        <div class="flex-1" />
        <UButton icon="i-lucide-printer" color="neutral" variant="outline" @click="printStatement">Print statement (PDF)</UButton>
        <UDropdownMenu :items="exportItems">
          <UButton icon="i-lucide-file-spreadsheet" color="neutral" variant="outline" trailing-icon="i-lucide-chevron-down">Export Excel</UButton>
        </UDropdownMenu>
        <UButton v-if="!paused" icon="i-lucide-pause" color="error" variant="ghost" @click="confirmPause = true">Suspend vendor</UButton>
        <UButton v-else icon="i-lucide-play" @click="setStatus('ACTIVE')">Reactivate vendor</UButton>
      </div>

      <div class="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-5 gap-3 mb-3">
        <StatCard label="Delivered orders" :value="s.delivered" icon="i-lucide-package-check" tone="success" :sub="`${s.open} still open`" />
        <StatCard label="Units sold" :value="s.units_sold" icon="i-lucide-shopping-bag" />
        <StatCard label="Sales after discounts" :value="fmtNaira(s.sales_kobo)" icon="i-lucide-receipt" tone="primary" />
        <StatCard label="Offers and discounts given" :value="fmtNaira(s.offers_kobo)" icon="i-lucide-badge-percent" tone="warning" />
        <StatCard label="Free gifts" :value="s.gift_units" icon="i-lucide-gift" :sub="`worth ${fmtNaira(s.gift_value_kobo)}`" />
      </div>
      <div class="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-5 gap-3 mb-5">
        <StatCard label="Cash collected from customers" :value="fmtNaira(s.collected_kobo)" icon="i-lucide-hand-coins" sub="includes delivery fees" />
        <StatCard label="Our charges" :value="fmtNaira(s.charges_kobo)" icon="i-lucide-scissors" tone="warning" />
        <StatCard label="Earned by vendor" :value="fmtNaira(s.earned_kobo)" icon="i-lucide-wallet" />
        <StatCard label="Paid to vendor" :value="fmtNaira(s.paid_out_kobo)" icon="i-lucide-banknote" tone="success" />
        <StatCard label="Balance still owed" :value="fmtNaira(s.balance_kobo)" icon="i-lucide-hourglass" tone="primary" />
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
        ]" :rows="stlRows" empty-title="No settlements yet">
          <template #orders_text="{ row }"><p class="text-xs max-w-xs whitespace-normal">{{ row.orders_text }}</p></template>
          <template #status="{ row }"><StatusBadge :status="row.status" /></template>
        </DataTable>
      </template>

      <DataTable v-else-if="tab === 'stock'" :export-title="`${v.name} stock`" :columns="[
        { key: 'name', label: 'Product' },
        { key: 'sku', label: 'Code' },
        { key: 'price', label: 'Price', align: 'right' },
        { key: 'physical', label: 'In warehouse', align: 'right' },
        { key: 'reserved', label: 'Promised to orders', align: 'right' },
        { key: 'damaged', label: 'Damaged', align: 'right' },
        { key: 'available', label: 'Free to sell', align: 'right' },
      ]" :rows="stockRows" empty-title="No products yet" />

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
