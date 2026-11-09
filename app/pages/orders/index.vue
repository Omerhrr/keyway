<script setup lang="ts">
const orders = ref<any[]>([])
const loading = ref(true)
const status = ref('')
const q = ref('')
const vendors = ref<any[]>([])
const vendorId = ref(0)
const warehouses = ref<any[]>([])

async function load() {
  loading.value = true
  try {
    const p = new URLSearchParams()
    if (status.value) p.set('status', status.value)
    if (q.value) p.set('q', q.value)
    if (vendorId.value) p.set('vendor_id', String(vendorId.value))
    orders.value = await api(`/orders?${p}`)
  } finally { loading.value = false }
}

onMounted(async () => {
  load()
  try { vendors.value = await api('/vendors') } catch {}
  try { warehouses.value = (await api('/inventory/warehouses')).filter((w: any) => w.is_active) } catch {}
})

const chips = ['', 'PENDING_REVIEW', 'CONFIRMED', 'PROCESSING', 'READY_FOR_DISPATCH', 'IN_TRANSIT', 'DELIVERED', 'DELIVERY_FAILED', 'CANCELLED']

// manual order creation
const showNew = ref(false)
const saving = ref(false)
const vendorsOptions = computed(() => vendors.value.map(v => ({ label: v.name, value: v.id })))
const activeVendorsOptions = computed(() => vendors.value.filter(v => v.status === 'ACTIVE').map(v => ({ label: v.name, value: v.id })))
const products = ref<any[]>([])
const { needs } = useGuard()
type Line = { product_id: number; qty: string; price: string; line: string; gift: boolean }
const blank = (): Line => ({ product_id: 0, qty: '1', price: '', line: '', gift: false })
const form = reactive({ vendor_id: 0, customer_name: '', customer_phone: '', city: '', state: '', street: '', instructions: '', warehouse_id: 0, payment_method: 'COD',
                        discount_type: 'AMOUNT', discount_value: '', discount_note: '' })
const lines = ref<Line[]>([blank()])

function openNew() {
  Object.assign(form, { vendor_id: 0, customer_name: '', customer_phone: '', city: '', state: '', street: '', instructions: '', warehouse_id: 0,
                        payment_method: 'COD', discount_type: 'AMOUNT', discount_value: '', discount_note: '' })
  lines.value = [blank()]
  products.value = []
  showNew.value = true
}

async function onVendorChange() {
  products.value = []
  lines.value = [blank()]
  if (form.vendor_id) {
    try { products.value = await api(`/catalog/products?vendor_id=${form.vendor_id}`) } catch {}
  }
}

const prod = (id: number) => products.value.find(p => p.id === id)
// all money below is in kobo
function calc(l: Line) {
  const p = prod(l.product_id)
  const unit = l.price ? toKobo(l.price) : (p?.default_sell_price_kobo || 0)
  const qty = Math.max(0, Number(l.qty) || 0)
  const gross = unit * qty
  const total = l.gift ? 0 : (l.line !== '' ? toKobo(l.line) : gross)
  return { unit, qty, gross, total }
}
const subtotal = computed(() => lines.value.reduce((n, l) => n + calc(l).total, 0))
const lineSavings = computed(() => lines.value.reduce((n, l) => n + (calc(l).gross - calc(l).total), 0))
const orderDiscount = computed(() => {
  const v = Number(form.discount_value) || 0
  if (!v) return 0
  return form.discount_type === 'PERCENT' ? Math.round(subtotal.value * Math.min(v, 100) / 100) : toKobo(form.discount_value)
})
const grandTotal = computed(() => Math.max(0, subtotal.value - orderDiscount.value))

async function createOrder() {
  const checks: [string, any][] = [['Vendor', form.vendor_id], ['Customer name', form.customer_name], ['Customer phone', form.customer_phone]]
  lines.value.forEach((l, i) => {
    const p = prod(l.product_id)
    const tag = lines.value.length > 1 ? ` (item ${i + 1})` : ''
    checks.push([`Product${tag}`, l.product_id])
    checks.push([`Quantity${p ? ' for ' + p.name : tag}`, Number(l.qty) > 0])
    if (p && !l.gift && !l.price && !p.default_sell_price_kobo) checks.push([`Price for ${p.name}`, ''])
  })
  if (!needs(checks)) return
  if (lines.value.every(l => l.gift)) {
    useToast().add({ title: 'Add at least one item that is not free', color: 'warning' }); return
  }
  for (const l of lines.value) {
    const c = calc(l)
    if (!l.gift && l.line !== '' && c.total > c.gross) {
      useToast().add({ title: `The special price for ${prod(l.product_id)?.name} is higher than the normal price`, color: 'warning' }); return
    }
  }
  if (orderDiscount.value > subtotal.value) {
    useToast().add({ title: 'The discount is more than the order total', color: 'warning' }); return
  }
  saving.value = true
  try {
    const body: any = {
      vendor_id: form.vendor_id, customer_name: form.customer_name, customer_phone: form.customer_phone,
      delivery_city: form.city, delivery_state: form.state, delivery_street: form.street,
      payment_method: form.payment_method, instructions: form.instructions,
      items: lines.value.map(l => ({
        product_id: l.product_id, qty: Number(l.qty) || 1, is_gift: l.gift,
        unit_price_kobo: l.price ? toKobo(l.price) : null,
        line_total_kobo: !l.gift && l.line !== '' ? toKobo(l.line) : null,
      })),
      discount_note: form.discount_note,
    }
    if (orderDiscount.value) {
      if (form.discount_type === 'PERCENT') body.discount_percent = Number(form.discount_value)
      else body.discount_kobo = toKobo(form.discount_value)
    }
    if (form.warehouse_id) body.warehouse_id = form.warehouse_id
    const o = await api('/orders', { method: 'POST', body })
    useToast().add({ title: `Order ${o.reference} created`, description: `Fulfilment warehouse: ${o.warehouse_name || 'auto'}`, color: 'success' })
    showNew.value = false
    await load()
  } catch (e) {
    useToast().add({ title: 'Could not create order', description: errMsg(e), color: 'error' })
  } finally { saving.value = false }
}
</script>

<template>
  <div>
    <PageHeader title="Orders" subtitle="Every order, whether it came from WhatsApp, the vendor portal, was typed in or imported.">
      <template #actions>
        <UButton icon="i-lucide-plus" @click="openNew">New manual order</UButton>
      </template>
    </PageHeader>

    <div class="flex gap-1.5 flex-wrap mb-3">
      <UChip v-for="c in chips" :key="c" :text="''" :show="false">
        <UButton size="xs" :variant="status === c ? 'solid' : 'soft'" color="neutral"
                 :label="c ? titleize(c) : 'All'" @click="status = c; load()" />
      </UChip>
    </div>

    <div class="flex gap-2 mb-3 flex-wrap">
      <UInput v-model="q" icon="i-lucide-search" placeholder="Reference, customer…" @keydown.enter="load" />
      <USelect v-model="vendorId" :items="[{ label: 'All vendors', value: 0 }, ...vendorsOptions]" class="w-52" @change="load" />
    </div>

    <DataTable export-title="Orders" :columns="[
      { key: 'reference', label: 'Order' },
      { key: 'vendor_name', label: 'Vendor' },
      { key: 'customer_name', label: 'Customer' },
      { key: 'warehouse_name', label: 'Warehouse' },
      { key: 'destination', label: 'Destination' },
      { key: 'cod', label: 'COD', align: 'right' },
      { key: 'source', label: 'Source' },
      { key: 'status', label: 'Status' },
    ]" :rows="orders.map(o => ({ ...o, destination: [o.delivery_city, o.delivery_state].filter(Boolean).join(', ') || '-', cod: fmtNaira(o.cod_amount_kobo), warehouse_name: o.warehouse_name || '-' }))"
      :loading="loading" clickable empty-title="No orders" empty-hint="Create one manually or simulate a WhatsApp order." @row-click="r => navigateTo(`/orders/${r.id}`)">
      <template #reference="{ row }">
        <span class="font-mono font-semibold text-primary-600">{{ row.reference }}</span>
      </template>
      <template #source="{ row }">
        <UBadge :color="row.source === 'WHATSAPP' ? 'success' : 'neutral'" variant="subtle" size="xs">{{ titleize(row.source) }}</UBadge>
      </template>
      <template #status="{ row }"><StatusBadge :status="row.status" /></template>
    </DataTable>

    <UModal v-model:open="showNew" :ui="{ content: 'max-w-3xl' }" title="Manual order entry">
      <template #body>
        <div class="grid sm:grid-cols-2 gap-3">
          <UFormField label="Vendor"><USelect placeholder="Choose..." @update:model-value="(v: any) => { form.vendor_id = v; onVendorChange() }" :model-value="form.vendor_id || undefined" class="w-full" :items="activeVendorsOptions" /></UFormField>
          <UFormField label="Fulfilment warehouse" help="Leave on Auto and the warehouse holding the stock is used">
            <USelect v-model="form.warehouse_id" class="w-full" :items="[{ label: `Auto (best stock)`, value: 0 }, ...warehouses.map(w => ({ label: w.name, value: w.id }))]" />
          </UFormField>
          <UFormField label="Customer name"><UInput v-model="form.customer_name" class="w-full" /></UFormField>
          <UFormField label="Customer phone"><UInput v-model="form.customer_phone" inputmode="tel" class="w-full" /></UFormField>
          <UFormField label="City"><UInput v-model="form.city" class="w-full" /></UFormField>
          <UFormField label="State"><UInput v-model="form.state" class="w-full" /></UFormField>
          <UFormField label="Street / landmark" class="sm:col-span-2"><UInput v-model="form.street" class="w-full" /></UFormField>
        </div>

        <div class="flex items-center justify-between mt-5 mb-2">
          <p class="text-sm font-semibold">Items</p>
          <UButton size="xs" variant="soft" color="neutral" icon="i-lucide-plus" @click="lines.push(blank())">Add item</UButton>
        </div>
        <div class="space-y-2">
          <div v-for="(l, i) in lines" :key="i" class="rounded-lg border border-zinc-200 dark:border-zinc-800 p-3">
            <div class="grid grid-cols-2 sm:grid-cols-[1fr_5rem_7rem_8rem] gap-2 items-end">
              <UFormField label="Product" class="col-span-2 sm:col-span-1">
                <USelect placeholder="Choose..." :model-value="l.product_id || undefined" class="w-full"
                         :items="products.map(p => ({ label: `${p.name} · ${fmtNaira(p.default_sell_price_kobo)} · ${p.qty_available} in stock`, value: p.id }))"
                         @update:model-value="(v: any) => l.product_id = v" />
              </UFormField>
              <UFormField label="Qty"><UInput v-model="l.qty" type="number" min="1" class="w-full" /></UFormField>
              <UFormField label="Price each (₦)"><UInput v-model="l.price" inputmode="decimal" :disabled="l.gift" :placeholder="prod(l.product_id) ? String((prod(l.product_id).default_sell_price_kobo || 0) / 100) : ''" class="w-full" /></UFormField>
              <UFormField label="Special price for all (₦)"><UInput v-model="l.line" inputmode="decimal" :disabled="l.gift" placeholder="e.g. 50000" class="w-full" /></UFormField>
            </div>
            <div class="flex items-center justify-between mt-2 gap-2 flex-wrap">
              <UCheckbox v-model="l.gift" label="Free gift (no charge)" />
              <p class="text-xs text-right">
                <span v-if="l.gift" class="text-emerald-600 font-medium">Free gift</span>
                <template v-else>
                  <span class="font-semibold">{{ fmtNaira(calc(l).total) }}</span>
                  <span v-if="calc(l).gross > calc(l).total" class="text-emerald-600 ml-2">customer saves {{ fmtNaira(calc(l).gross - calc(l).total) }}</span>
                </template>
                <UButton v-if="lines.length > 1" icon="i-lucide-trash-2" size="xs" color="error" variant="ghost" class="ml-2" aria-label="Remove item" @click="lines.splice(i, 1)" />
              </p>
            </div>
          </div>
        </div>
        <p class="text-xs text-zinc-500 mt-2">Buy two, pay one price? Type the price for the whole line under "Special price". Giving something free with the order? Add it as another item and tick "Free gift". Free gifts still leave your stock.</p>

        <div class="grid sm:grid-cols-3 gap-3 mt-5">
          <UFormField label="Discount on the whole order">
            <div class="flex gap-2">
              <USelect v-model="form.discount_type" class="w-24 shrink-0" :items="[{ label: '₦', value: 'AMOUNT' }, { label: '%', value: 'PERCENT' }]" />
              <UInput v-model="form.discount_value" inputmode="decimal" placeholder="0" class="w-full" />
            </div>
          </UFormField>
          <UFormField label="Reason for discount" class="sm:col-span-2"><UInput v-model="form.discount_note" placeholder="e.g. loyal customer, launch promo" class="w-full" /></UFormField>
          <UFormField label="Payment"><USelect v-model="form.payment_method" class="w-full" :items="[{ label: 'Cash on delivery', value: 'COD' }, { label: 'Already paid', value: 'PREPAID' }, { label: 'Bank transfer', value: 'TRANSFER' }, { label: 'POS', value: 'POS' }]" /></UFormField>
          <UFormField label="Instructions" class="sm:col-span-2"><UInput v-model="form.instructions" class="w-full" /></UFormField>
        </div>

        <div class="mt-4 rounded-lg bg-zinc-50 dark:bg-zinc-900 p-3 text-sm space-y-1">
          <div class="flex justify-between"><span class="text-zinc-500">Items</span><span>{{ fmtNaira(subtotal + lineSavings) }}</span></div>
          <div v-if="lineSavings" class="flex justify-between text-emerald-600"><span>Item offers</span><span>- {{ fmtNaira(lineSavings) }}</span></div>
          <div v-if="orderDiscount" class="flex justify-between text-emerald-600"><span>Order discount</span><span>- {{ fmtNaira(orderDiscount) }}</span></div>
          <div class="flex justify-between font-semibold text-base pt-1 border-t border-zinc-200 dark:border-zinc-800"><span>Customer pays for items</span><span>{{ fmtNaira(grandTotal) }}</span></div>
          <p class="text-xs text-zinc-500">The delivery fee is added when the order is dispatched.</p>
        </div>
      </template>
      <template #footer>
        <div class="flex justify-end gap-2 w-full">
          <UButton variant="ghost" color="neutral" @click="showNew = false">Cancel</UButton>
          <UButton :loading="saving" @click="createOrder">Create order</UButton>
        </div>
      </template>
    </UModal>
  </div>
</template>
