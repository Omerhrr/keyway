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
const products = ref<any[]>([])
const form = reactive({ vendor_id: 0, customer_name: '', customer_phone: '', city: '', state: '', street: '', product_id: 0, qty: 1, price_naira: '', instructions: '', warehouse_id: 0 })

async function onVendorChange() {
  products.value = []
  form.product_id = 0
  if (form.vendor_id) {
    try { products.value = await api(`/catalog/products?vendor_id=${form.vendor_id}`) } catch {}
  }
}

async function createOrder() {
  saving.value = true
  try {
    const body: any = {
      vendor_id: form.vendor_id, customer_name: form.customer_name, customer_phone: form.customer_phone,
      delivery_city: form.city, delivery_state: form.state, delivery_street: form.street,
      items: [{ product_id: form.product_id, qty: Number(form.qty) || 1,
                unit_price_kobo: form.price_naira ? toKobo(form.price_naira) : null }],
      instructions: form.instructions,
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
    <PageHeader title="Orders" subtitle="Every order from every channel - WhatsApp, portal, manual and imports.">
      <template #actions>
        <UButton icon="i-lucide-plus" @click="showNew = true">New manual order</UButton>
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

    <UModal v-model:open="showNew" :ui="{ content: 'max-w-2xl' }" title="Manual order entry">
      <template #body>
        <div class="grid sm:grid-cols-2 gap-3">
          <UFormField label="Vendor"><USelect v-model="form.vendor_id" class="w-full" :items="vendorsOptions" @update:model-value="onVendorChange" /></UFormField>
          <UFormField label="Product"><USelect v-model="form.product_id" class="w-full" :items="products.map(p => ({ label: `${p.name} · avail ${p.qty_available}`, value: p.id }))" /></UFormField>
          <UFormField label="Fulfilment warehouse" hint="Pick a branch or leave on Auto and the warehouse holding the stock is used">
            <USelect v-model="form.warehouse_id" class="w-full" :items="[{ label: `Auto (best stock)`, value: 0 }, ...warehouses.map(w => ({ label: w.name, value: w.id }))]" />
          </UFormField>
          <UFormField label="Customer name"><UInput v-model="form.customer_name" class="w-full" /></UFormField>
          <UFormField label="Customer phone"><UInput v-model="form.customer_phone" class="w-full" /></UFormField>
          <UFormField label="City"><UInput v-model="form.city" class="w-full" /></UFormField>
          <UFormField label="State"><UInput v-model="form.state" class="w-full" /></UFormField>
          <UFormField label="Street / landmark" class="sm:col-span-2"><UInput v-model="form.street" class="w-full" /></UFormField>
          <UFormField label="Quantity"><UInput v-model="form.qty" type="number" min="1" class="w-full" /></UFormField>
          <UFormField label="Unit price (₦)" hint="Leave empty to use the product's default price"><UInput v-model="form.price_naira" class="w-full" /></UFormField>
          <UFormField label="Instructions" class="sm:col-span-2"><UTextarea v-model="form.instructions" class="w-full" :rows="2" /></UFormField>
        </div>
      </template>
      <template #footer>
        <div class="flex justify-end gap-2 w-full">
          <UButton variant="ghost" color="neutral" @click="showNew = false">Cancel</UButton>
          <UButton :loading="saving" :disabled="!form.vendor_id || !form.product_id || !form.customer_phone" @click="createOrder">Create order</UButton>
        </div>
      </template>
    </UModal>
  </div>
</template>
