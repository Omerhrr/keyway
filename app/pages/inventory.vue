<script setup lang="ts">
const { canOpen } = useModules()
const tab = ref('balances')
const tabs = [
  { label: 'Stock balances', value: 'balances', icon: 'i-lucide-warehouse' },
  { label: 'Receipts', value: 'receipts', icon: 'i-lucide-package-plus' },
  { label: 'Transfers', value: 'transfers', icon: 'i-lucide-arrow-right-left' },
  { label: 'Movements', value: 'movements', icon: 'i-lucide-arrow-left-right' },
]
const balances = ref<any[]>([])
const receipts = ref<any[]>([])
const movements = ref<any[]>([])
const transfers = ref<any[]>([])
const vendors = ref<any[]>([])
const warehouses = ref<any[]>([])
const loading = ref(true)
const lowOnly = ref(false)
const vendorId = ref(0)
const warehouseId = ref(0)

async function load() {
  loading.value = true
  try {
    const p = new URLSearchParams()
    if (lowOnly.value) p.set('low_stock', 'true')
    if (vendorId.value) p.set('vendor_id', String(vendorId.value))
    if (warehouseId.value) p.set('warehouse_id', String(warehouseId.value))
    const [b, r, m, t, v, w] = await Promise.all([
      api(`/inventory/balances?${p}`), api('/inventory/receipts'), api('/inventory/movements'),
      api('/inventory/transfers'), api('/vendors'), api('/inventory/warehouses'),
    ])
    balances.value = b; receipts.value = r; movements.value = m; transfers.value = t; vendors.value = v; warehouses.value = w
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

// receipt + quick product (shared components)
const showReceipt = ref(false)
const showQuickProduct = ref(false)

// ---- multi-warehouse transfers ----
const showTransfer = ref(false)
const trForm = reactive({ vendor_id: 0, product_id: 0, from_warehouse_id: 0, to_warehouse_id: 0, qty: 1, reason: '' })
const trProducts = ref<any[]>([])

function openTransfer() {
  trForm.vendor_id = 0; trForm.product_id = 0; trForm.from_warehouse_id = 0; trForm.to_warehouse_id = 0
  trForm.qty = 1; trForm.reason = ''; trProducts.value = []
  showTransfer.value = true
}

async function onTrVendor() {
  trProducts.value = []
  trForm.product_id = 0
  if (trForm.vendor_id) {
    try { trProducts.value = await api(`/catalog/products?vendor_id=${trForm.vendor_id}`) } catch {}
  }
}

const trProduct = computed(() => trProducts.value.find(p => p.id === trForm.product_id))
const trFrom = computed(() => warehouses.value.find(w => w.id === trForm.from_warehouse_id))
const trTo = computed(() => warehouses.value.find(w => w.id === trForm.to_warehouse_id))
const trSourceQty = computed(() => {
  if (!trForm.product_id || !trForm.from_warehouse_id) return null
  const b = balances.value.find(x => x.product_id === trForm.product_id && x.warehouse_id === trForm.from_warehouse_id)
  return b ? b.qty_available : 0
})
const trInvalid = computed(() => !trForm.vendor_id || !trForm.product_id || !trForm.from_warehouse_id
  || !trForm.to_warehouse_id || trForm.from_warehouse_id === trForm.to_warehouse_id || !(Number(trForm.qty) > 0)
  || (trSourceQty.value !== null && Number(trForm.qty) > trSourceQty.value))

function checkTransfer() {
  if (!needs([['Vendor', trForm.vendor_id], ['Product', trForm.product_id], ['Sending warehouse', trForm.from_warehouse_id],
              ['Receiving warehouse', trForm.to_warehouse_id], ['Quantity', Number(trForm.qty) > 0]])) return false
  if (trForm.from_warehouse_id === trForm.to_warehouse_id) {
    useToast().add({ title: 'Pick two different warehouses', color: 'warning' }); return false
  }
  if (trSourceQty.value !== null && Number(trForm.qty) > trSourceQty.value) {
    useToast().add({ title: `Only ${trSourceQty.value} available to move`, color: 'warning' }); return false
  }
  return true
}

async function createTransfer() {
  saving.value = true
  try {
    const t = await api('/inventory/transfers', { method: 'POST', body: {
      product_id: trForm.product_id, from_warehouse_id: trForm.from_warehouse_id,
      to_warehouse_id: trForm.to_warehouse_id, qty: Number(trForm.qty), reason: trForm.reason,
    } })
    useToast().add({ title: `Transfer ${t.reference} in transit`, description: 'Receive it at the destination warehouse when goods arrive.', color: 'success' })
    showTransfer.value = false
    tab.value = 'transfers'
    await load()
  } catch (e) {
    useToast().add({ title: 'Failed', description: errMsg(e), color: 'error' })
  } finally { saving.value = false }
}

async function receiveTransfer(t: any) {
  try {
    await api(`/inventory/transfers/${t.id}/receive`, { method: 'POST' })
    useToast().add({ title: `Transfer ${t.reference} received`, color: 'success' })
    await load()
  } catch (e) {
    useToast().add({ title: 'Failed', description: errMsg(e), color: 'error' })
  }
}

async function cancelTransfer(t: any) {
  try {
    await api(`/inventory/transfers/${t.id}/cancel`, { method: 'POST' })
    useToast().add({ title: `Transfer ${t.reference} cancelled - stock returned`, color: 'warning' })
    await load()
  } catch (e) {
    useToast().add({ title: 'Failed', description: errMsg(e), color: 'error' })
  }
}
</script>

<template>
  <div>
    <PageHeader title="Inventory & Warehouse" subtitle="Each vendor's stock across your warehouses. Every movement is recorded and changes need a reason.">
      <template #actions>
        <UButton v-if="canOpen('/catalog')" to="/catalog" icon="i-lucide-book-open" variant="ghost" color="neutral">Product catalog</UButton>
        <UButton icon="i-lucide-sparkles" variant="soft" color="neutral" @click="showQuickProduct = true">Add product</UButton>
        <UButton icon="i-lucide-arrow-right-left" variant="soft" color="neutral" @click="openTransfer">Transfer stock</UButton>
        <UButton icon="i-lucide-package-plus" @click="showReceipt = true">Receive stock</UButton>
      </template>
    </PageHeader>

    <ScrollTabs :items="tabs" v-model="tab" class="mb-4" />

    <template v-if="tab === 'balances'">
      <div class="flex gap-2 mb-3 flex-wrap items-center">
        <USelect v-model="vendorId" :items="[{ label: 'All vendors', value: 0 }, ...vendors.map(v => ({ label: v.name, value: v.id }))]" class="w-52" @update:model-value="load" />
        <USelect v-model="warehouseId" :items="[{ label: 'All warehouses', value: 0 }, ...warehouses.map(w => ({ label: w.name, value: w.id }))]" class="w-56" @update:model-value="load" />
        <UCheckbox v-model="lowOnly" label="Low stock only" @update:model-value="load" />
      </div>
      <DataTable export-title="Stock levels" :columns="[
        { key: 'product_name', label: 'Product' },
        { key: 'vendor_name', label: 'Vendor' },
        { key: 'warehouse_name', label: 'Warehouse' },
        { key: 'physical', label: 'Physical', align: 'right' },
        { key: 'transit', label: 'In transit', align: 'right' },
        { key: 'reserved', label: 'Reserved', align: 'right' },
        { key: 'available', label: 'Available', align: 'right' },
        { key: 'actions', label: '' },
      ]" :rows="balances.map(b => ({
        ...b,
        physical: b.qty_physical, reserved: b.qty_reserved, available: b.qty_available,
        transit: b.qty_in_transit || 0,
      }))" :loading="loading" empty-title="No stock" empty-hint="Receive stock against a vendor first.">
        <template #product_name="{ row }">
          <div class="flex items-center gap-2">
            <span class="font-medium text-zinc-800 dark:text-zinc-200">{{ row.product_name }}</span>
            <UBadge v-if="row.low_stock" color="warning" variant="subtle" size="xs">Low</UBadge>
            <UBadge v-if="row.vendor_status && row.vendor_status !== 'ACTIVE'" color="neutral" variant="subtle" size="xs">Vendor paused</UBadge>
          </div>
          <p class="text-[11px] text-zinc-400 font-mono">{{ row.sku }}</p>
        </template>
        <template #warehouse_name="{ row }">
          <UBadge color="info" variant="subtle" size="xs">{{ row.warehouse_name || '-' }}</UBadge>
        </template>
        <template #actions="{ row }">
          <UButton size="xs" variant="soft" color="warning" icon="i-lucide-sliders-horizontal" @click.stop="askAdjust(row)">Adjust</UButton>
        </template>
      </DataTable>
    </template>

    <template v-else-if="tab === 'receipts'">
      <DataTable export-title="Stock received" :columns="[
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

    <template v-else-if="tab === 'transfers'">
      <DataTable export-title="Stock transfers" :columns="[
        { key: 'reference', label: 'Reference' },
        { key: 'product_name', label: 'Product' },
        { key: 'route', label: 'Route' },
        { key: 'qty', label: 'Qty', align: 'right' },
        { key: 'status', label: 'Status' },
        { key: 'created_at', label: 'Created' },
        { key: 'actions', label: '' },
      ]" :rows="transfers.map(t => ({ ...t, created_at: fmtDateTime(t.created_at) }))" :loading="loading" empty-title="No transfers" empty-hint="Move stock between warehouses with the Transfer stock button.">
        <template #reference="{ row }"><span class="font-mono font-semibold text-primary-600">{{ row.reference }}</span></template>
        <template #product_name="{ row }">
          <span class="font-medium text-zinc-800 dark:text-zinc-200">{{ row.product_name }}</span>
          <p class="text-[11px] text-zinc-400">{{ row.vendor_name }}</p>
        </template>
        <template #route="{ row }">
          <span class="text-sm text-zinc-600 dark:text-zinc-300">{{ row.from_warehouse_name }} → {{ row.to_warehouse_name }}</span>
        </template>
        <template #status="{ row }"><StatusBadge :status="row.status" /></template>
        <template #actions="{ row }">
          <template v-if="row.status === 'IN_TRANSIT'">
            <UButton size="xs" variant="soft" color="success" icon="i-lucide-package-check" @click.stop="receiveTransfer(row)">Receive</UButton>
            <UButton size="xs" variant="ghost" color="error" @click.stop="cancelTransfer(row)">Cancel</UButton>
          </template>
          <span v-else class="text-[11px] text-zinc-400">{{ row.received_at ? fmtDateTime(row.received_at) : '' }}</span>
        </template>
      </DataTable>
    </template>

    <template v-else-if="tab === 'movements'">
      <DataTable export-title="Stock movements" :columns="[
        { key: 'created_at', label: 'When' },
        { key: 'product_name', label: 'Product' },
        { key: 'movement_type', label: 'Type' },
        { key: 'qty', label: 'Qty', align: 'right' },
        { key: 'reason', label: 'Reason' },
      ]" :rows="movements.map(m => ({ ...m, created_at: fmtDateTime(m.created_at) }))" :loading="loading" empty-title="No movements">
        <template #movement_type="{ row }">
          <UBadge :color="['RECEIVE', 'RETURN', 'TRANSFER_IN'].includes(row.movement_type) ? 'success' : ['DEDUCT', 'TRANSFER_OUT'].includes(row.movement_type) ? 'error' : 'neutral'" variant="subtle" size="xs">
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
          <UFormField label="Reason (optional)"><UInput v-model="adjForm.reason" class="w-full" placeholder="e.g. stocktake correction, breakage" /></UFormField>
        </div>
      </template>
      <template #footer>
        <div class="flex justify-end gap-2 w-full">
          <UButton variant="ghost" color="neutral" @click="showAdjust = false">Cancel</UButton>
          <UButton :loading="saving" @click="adjust">Adjust</UButton>
        </div>
      </template>
    </UModal>

    <!-- transfer modal -->
    <UModal v-model:open="showTransfer" title="Transfer stock between warehouses">
      <template #body>
        <div class="grid sm:grid-cols-2 gap-3">
          <UFormField label="Vendor">
            <USelect placeholder="Choose..." @update:model-value="(v: any) => { trForm.vendor_id = v; onTrVendor(v) }" :model-value="trForm.vendor_id || undefined" class="w-full" :items="vendors.filter(v => v.status === 'ACTIVE').map(v => ({ label: v.name, value: v.id }))"  />
          </UFormField>
          <UFormField label="Product">
            <USelect placeholder="Choose..." @update:model-value="(v: any) => { trForm.product_id = v }" :model-value="trForm.product_id || undefined" class="w-full" :items="trProducts.map(p => ({ label: `${p.name} (${p.sku})`, value: p.id }))" />
          </UFormField>
          <UFormField label="From warehouse">
            <USelect placeholder="Choose..." @update:model-value="(v: any) => { trForm.from_warehouse_id = v }" :model-value="trForm.from_warehouse_id || undefined" class="w-full" :items="warehouses.map(w => ({ label: w.name, value: w.id }))" />
          </UFormField>
          <UFormField label="To warehouse">
            <USelect placeholder="Choose..." @update:model-value="(v: any) => { trForm.to_warehouse_id = v }" :model-value="trForm.to_warehouse_id || undefined" class="w-full" :items="warehouses.filter(w => w.id !== trForm.from_warehouse_id).map(w => ({ label: w.name, value: w.id }))" />
          </UFormField>
          <UFormField label="Quantity"><UInput v-model="trForm.qty" type="number" min="1" class="w-full" /></UFormField>
          <UFormField label="Reason (optional)"><UInput v-model="trForm.reason" class="w-full" placeholder="e.g. restock annex ahead of promo" /></UFormField>
        </div>
        <div class="mt-3 text-sm rounded-lg bg-zinc-50 dark:bg-zinc-800/60 border border-zinc-200 dark:border-zinc-700 p-3">
          <p v-if="trSourceQty !== null" class="text-zinc-600 dark:text-zinc-300">Available at source: <b>{{ trSourceQty }}</b></p>
          <p v-if="trForm.from_warehouse_id && trForm.from_warehouse_id === trForm.to_warehouse_id" class="text-red-500">Source and destination must differ.</p>
          <p v-else-if="trSourceQty !== null && Number(trForm.qty) > trSourceQty" class="text-red-500">Not enough stock at source for this transfer.</p>
          <p v-else class="text-xs text-zinc-400">Stock leaves the source immediately (marked in transit) and lands in the destination when a warehouse manager receives the transfer. Both legs are recorded as movements.</p>
        </div>
      </template>
      <template #footer>
        <div class="flex justify-end gap-2 w-full">
          <UButton variant="ghost" color="neutral" @click="showTransfer = false">Cancel</UButton>
          <UButton :loading="saving" @click="checkTransfer() && createTransfer()">Dispatch transfer</UButton>
        </div>
      </template>
    </UModal>

    <ReceiveStock v-model:open="showReceipt" :vendors="vendors" :warehouses="warehouses" @done="load" />
    <QuickProduct v-model:open="showQuickProduct" :vendors="vendors.filter(v => v.status === 'ACTIVE')" @created="load" />
  </div>
</template>
