<script setup lang="ts">
const tab = ref('balances')
const tabs = [
  { label: 'Stock balances', value: 'balances', icon: 'i-lucide-warehouse' },
  { label: 'Receipts', value: 'receipts', icon: 'i-lucide-package-plus' },
  { label: 'Movements', value: 'movements', icon: 'i-lucide-arrow-left-right' },
]
const balances = ref<any[]>([])
const receipts = ref<any[]>([])
const movements = ref<any[]>([])
const vendors = ref<any[]>([])
const warehouses = ref<any[]>([])
const loading = ref(true)
const lowOnly = ref(false)
const vendorId = ref(0)

async function load() {
  loading.value = true
  try {
    const p = new URLSearchParams()
    if (lowOnly.value) p.set('low_stock', 'true')
    if (vendorId.value) p.set('vendor_id', String(vendorId.value))
    const [b, r, m, v, w] = await Promise.all([
      api(`/inventory/balances?${p}`), api('/inventory/receipts'), api('/inventory/movements'),
      api('/vendors'), api('/inventory/warehouses'),
    ])
    balances.value = b; receipts.value = r; movements.value = m; vendors.value = v; warehouses.value = w
  } finally { loading.value = false }
}
onMounted(load)

// adjust modal
const selected = ref<any>(null)
const showAdjust = ref(false)
const adjForm = reactive({ delta_physical: '0', delta_damaged: '0', reason: '' })

function askAdjust(b: any) {
  selected.value = b
  adjForm.delta_physical = '0'
  adjForm.delta_damaged = '0'
  adjForm.reason = ''
  showAdjust.value = true
}

const saving = ref(false)
async function adjust() {
  saving.value = true
  try {
    await api('/inventory/adjust', {
      method: 'POST',
      body: { balance_id: selected.value.id, delta_physical: Number(adjForm.delta_physical) || 0, delta_damaged: Number(adjForm.delta_damaged) || 0, reason: adjForm.reason },
    })
    useToast().add({ title: 'Stock adjusted', description: 'Movement recorded with reason.', color: 'success' })
    showAdjust.value = false
    await load()
  } catch (e) {
    useToast().add({ title: 'Failed', description: errMsg(e), color: 'error' })
  } finally { saving.value = false }
}

// receipt modal
const showReceipt = ref(false)
const rcForm = reactive({ vendor_id: 0, warehouse_id: 0, batch_ref: '', product_id: 0, qty: 10 })
const rcProducts = ref<any[]>([])

async function openReceipt() {
  showReceipt.value = true
}
async function onRcVendor() {
  rcProducts.value = []
  rcForm.product_id = 0
  if (rcForm.vendor_id) {
    try { rcProducts.value = await api(`/catalog/products?vendor_id=${rcForm.vendor_id}`) } catch {}
  }
}
async function createReceipt() {
  saving.value = true
  try {
    const r = await api('/inventory/receipts', {
      method: 'POST',
      body: {
        vendor_id: rcForm.vendor_id, warehouse_id: rcForm.warehouse_id, batch_ref: rcForm.batch_ref,
        lines: [{ product_id: rcForm.product_id, expected_qty: Number(rcForm.qty), received_qty: Number(rcForm.qty) }],
      },
    })
    await api(`/inventory/receipts/${r.id}/confirm`, { method: 'POST' })
    useToast().add({ title: `Stock received (${r.reference})`, color: 'success' })
    showReceipt.value = false
    await load()
  } catch (e) {
    useToast().add({ title: 'Failed', description: errMsg(e), color: 'error' })
  } finally { saving.value = false }
}
</script>

<template>
  <div>
    <PageHeader title="Inventory & Warehouse" subtitle="Vendor-owned stock across warehouses. Every movement is auditable; adjustments need a reason.">
      <template #actions>
        <UButton icon="i-lucide-package-plus" @click="openReceipt">Receive stock</UButton>
      </template>
    </PageHeader>

    <UTabs :items="tabs" v-model:model-value="tab" class="mb-4" />

    <template v-if="tab === 'balances'">
      <div class="flex gap-2 mb-3 flex-wrap items-center">
        <USelect v-model="vendorId" :items="[{ label: 'All vendors', value: 0 }, ...vendors.map(v => ({ label: v.name, value: v.id }))]" class="w-52" @change="load" />
        <UCheckbox v-model="lowOnly" label="Low stock only" @update:model-value="load" />
      </div>
      <DataTable :columns="[
        { key: 'product_name', label: 'Product' },
        { key: 'vendor_name', label: 'Vendor' },
        { key: 'physical', label: 'Physical', align: 'right' },
        { key: 'reserved', label: 'Reserved', align: 'right' },
        { key: 'available', label: 'Available', align: 'right' },
        { key: 'value', label: 'Value', align: 'right' },
        { key: 'actions', label: '' },
      ]" :rows="balances.map(b => ({
        ...b,
        physical: b.qty_physical, reserved: b.qty_reserved, available: b.qty_available,
        value: fmtNaira(b.value_kobo),
      }))" :loading="loading" empty-title="No stock" empty-hint="Receive stock against a vendor first.">
        <template #product_name="{ row }">
          <div class="flex items-center gap-2">
            <span class="font-medium text-zinc-800 dark:text-zinc-200">{{ row.product_name }}</span>
            <UBadge v-if="row.low_stock" color="warning" variant="subtle" size="xs">Low</UBadge>
          </div>
          <p class="text-[11px] text-zinc-400 font-mono">{{ row.sku }}</p>
        </template>
        <template #actions="{ row }">
          <UButton size="xs" variant="soft" color="warning" icon="i-lucide-sliders-horizontal" @click.stop="askAdjust(row)">Adjust</UButton>
        </template>
      </DataTable>
    </template>

    <template v-else-if="tab === 'receipts'">
      <DataTable :columns="[
        { key: 'reference', label: 'Reference' },
        { key: 'vendor_name', label: 'Vendor' },
        { key: 'warehouse_name', label: 'Warehouse' },
        { key: 'batch_ref', label: 'Batch' },
        { key: 'lines', label: 'Lines', align: 'right' },
        { key: 'status', label: 'Status' },
      ]" :rows="receipts" :loading="loading" empty-title="No receipts">
        <template #reference="{ row }"><span class="font-mono font-semibold text-primary-600">{{ row.reference }}</span></template>
        <template #status="{ row }"><StatusBadge :status="row.status" /></template>
      </DataTable>
    </template>

    <template v-else>
      <DataTable :columns="[
        { key: 'created_at', label: 'When' },
        { key: 'product_name', label: 'Product' },
        { key: 'movement_type', label: 'Type' },
        { key: 'qty', label: 'Qty', align: 'right' },
        { key: 'reason', label: 'Reason' },
      ]" :rows="movements.map(m => ({ ...m, created_at: fmtDateTime(m.created_at) }))" :loading="loading" empty-title="No movements">
        <template #movement_type="{ row }">
          <UBadge :color="['RECEIVE', 'RETURN', 'TRANSFER_IN'].includes(row.movement_type) ? 'success' : row.movement_type === 'DEDUCT' ? 'error' : 'neutral'" variant="subtle" size="xs">
            {{ titleize(row.movement_type) }}
          </UBadge>
        </template>
        <template #qty="{ value }">
          <span :class="value >= 0 ? 'text-emerald-600' : 'text-red-500'" class="font-semibold">{{ value > 0 ? `+${value}` : value }}</span>
        </template>
      </DataTable>
    </template>

    <!-- adjust modal -->
    <UModal v-model:open="showAdjust" :title="`Adjust stock - ${selected?.product_name || ''}`">
      <template #body>
        <div class="space-y-3">
          <div class="text-sm text-zinc-500">Currently: physical {{ selected?.qty_physical }} · reserved {{ selected?.qty_reserved }} · damaged {{ selected?.qty_damaged }}</div>
          <div class="grid grid-cols-2 gap-3">
            <UFormField label="Physical Δ (+/-)"><UInput v-model="adjForm.delta_physical" type="number" class="w-full" /></UFormField>
            <UFormField label="Damaged Δ (+/-)"><UInput v-model="adjForm.delta_damaged" type="number" class="w-full" /></UFormField>
          </div>
          <UFormField label="Reason (required)"><UInput v-model="adjForm.reason" class="w-full" placeholder="e.g. stocktake correction, breakage" /></UFormField>
        </div>
      </template>
      <template #footer>
        <div class="flex justify-end gap-2 w-full">
          <UButton variant="ghost" color="neutral" @click="showAdjust = false">Cancel</UButton>
          <UButton :loading="saving" @click="adjust">Adjust</UButton>
        </div>
      </template>
    </UModal>

    <!-- receipt modal -->
    <UModal v-model:open="showReceipt" title="Receive stock">
      <template #body>
        <div class="grid sm:grid-cols-2 gap-3">
          <UFormField label="Vendor">
            <USelect v-model="rcForm.vendor_id" class="w-full" :items="vendors.map(v => ({ label: v.name, value: v.id }))" @update:model-value="onRcVendor" />
          </UFormField>
          <UFormField label="Warehouse">
            <USelect v-model="rcForm.warehouse_id" class="w-full" :items="warehouses.map(w => ({ label: w.name, value: w.id }))" />
          </UFormField>
          <UFormField label="Product" class="sm:col-span-2">
            <USelect v-model="rcForm.product_id" class="w-full" :items="rcProducts.map(p => ({ label: `${p.name} (${p.sku})`, value: p.id }))" />
          </UFormField>
          <UFormField label="Quantity"><UInput v-model="rcForm.qty" type="number" min="1" class="w-full" /></UFormField>
          <UFormField label="Batch / shipment ref"><UInput v-model="rcForm.batch_ref" class="w-full" /></UFormField>
        </div>
      </template>
      <template #footer>
        <div class="flex justify-end gap-2 w-full">
          <UButton variant="ghost" color="neutral" @click="showReceipt = false">Cancel</UButton>
          <UButton :loading="saving" :disabled="!rcForm.vendor_id || !rcForm.warehouse_id || !rcForm.product_id" @click="createReceipt">Receive & confirm</UButton>
        </div>
      </template>
    </UModal>
  </div>
</template>
