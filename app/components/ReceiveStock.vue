<script setup lang="ts">
/** Receive stock for a vendor: several products at once, with a shortcut to add a brand-new product. */
const props = defineProps<{ open: boolean; vendors: any[]; warehouses: any[]; vendorId?: number; productId?: number }>()
const emit = defineEmits<{ (e: 'update:open', v: boolean): void; (e: 'done'): void; (e: 'product-added'): void }>()
const { needs } = useGuard()
type Line = { product_id: number; qty: string; damaged: string }
const blank = (): Line => ({ product_id: 0, qty: '', damaged: '' })
const saving = ref(false)
const showQuick = ref(false)
const form = reactive({ vendor_id: 0, warehouse_id: 0, batch_ref: '' })
const lines = ref<Line[]>([blank()])
const products = ref<any[]>([])

const activeVendors = computed(() => props.vendors.filter(v => v.status === 'ACTIVE'))

async function loadProducts() {
  products.value = form.vendor_id ? await api(`/catalog/products?vendor_id=${form.vendor_id}`).catch(() => []) : []
  products.value = products.value.filter((p: any) => p.status !== 'ARCHIVED')
}
watch(() => props.open, async (o) => {
  if (!o) return
  Object.assign(form, { vendor_id: props.vendorId || 0, warehouse_id: props.warehouses.length === 1 ? props.warehouses[0].id : 0, batch_ref: '' })
  lines.value = [{ ...blank(), product_id: props.productId || 0 }]
  products.value = []
  if (form.vendor_id) await loadProducts()
})
async function onVendor() { lines.value = [blank()]; await loadProducts() }
async function onProductAdded(p: any) {
  await loadProducts()
  const empty = lines.value.find(l => !l.product_id)
  if (empty) empty.product_id = p.id
  else lines.value.push({ ...blank(), product_id: p.id })
  emit('product-added')
}
const onHand = (pid: number) => products.value.find(p => p.id === pid)?.qty_physical

async function save() {
  const filled = lines.value.filter(l => l.product_id || l.qty)
  const checks: [string, any][] = [['Vendor', form.vendor_id], ['Warehouse', form.warehouse_id]]
  if (!filled.length) checks.push(['At least one product', ''])
  filled.forEach((l, i) => {
    const name = products.value.find(p => p.id === l.product_id)?.name
    const tag = filled.length > 1 ? ` (line ${i + 1})` : ''
    checks.push([`Product${tag}`, l.product_id])
    checks.push([`Quantity received${name ? ' for ' + name : tag}`, Number(l.qty) > 0])
  })
  if (!needs(checks)) return
  saving.value = true
  try {
    const r = await api('/inventory/receipts', {
      method: 'POST',
      body: {
        vendor_id: form.vendor_id, warehouse_id: form.warehouse_id, batch_ref: form.batch_ref,
        lines: filled.map(l => ({ product_id: l.product_id, expected_qty: Number(l.qty) + (Number(l.damaged) || 0),
                                  received_qty: Number(l.qty), damaged_qty: Number(l.damaged) || 0 })),
      },
    })
    await api(`/inventory/receipts/${r.id}/confirm`, { method: 'POST' })
    useToast().add({ title: `Stock received (${r.reference})`, color: 'success' })
    emit('update:open', false)
    emit('done')
  } catch (e) {
    useToast().add({ title: 'Could not receive the stock', description: errMsg(e), color: 'error' })
  } finally { saving.value = false }
}
</script>

<template>
  <UModal :open="open" title="Receive stock" :ui="{ content: 'max-w-2xl' }" @update:open="(v: boolean) => emit('update:open', v)">
    <template #body>
      <div class="grid sm:grid-cols-2 gap-3">
        <UFormField label="Vendor">
          <USelect placeholder="Choose..." :model-value="form.vendor_id || undefined" class="w-full" :disabled="!!vendorId"
                   :items="activeVendors.map(v => ({ label: v.name, value: v.id }))" @update:model-value="(v: any) => { form.vendor_id = v; onVendor() }" />
        </UFormField>
        <UFormField label="Warehouse">
          <USelect placeholder="Choose..." :model-value="form.warehouse_id || undefined" class="w-full"
                   :items="warehouses.map(w => ({ label: w.name, value: w.id }))" @update:model-value="(v: any) => form.warehouse_id = v" />
        </UFormField>
        <UFormField label="Batch / shipment ref (optional)" class="sm:col-span-2" help="Leave empty and the receipt number is used">
          <UInput v-model="form.batch_ref" class="w-full" />
        </UFormField>
      </div>

      <div class="flex items-center justify-between mt-5 mb-2">
        <p class="text-sm font-semibold">Products received</p>
        <div class="flex gap-2">
          <UButton size="xs" variant="soft" icon="i-lucide-sparkles" @click="needs([['Vendor', form.vendor_id]]) && (showQuick = true)">New product</UButton>
          <UButton size="xs" variant="soft" color="neutral" icon="i-lucide-plus" @click="lines.push(blank())">Add line</UButton>
        </div>
      </div>
      <div class="space-y-2">
        <div v-for="(l, i) in lines" :key="i" class="grid grid-cols-[1fr_5rem_5rem_2rem] gap-2 items-end">
          <UFormField :label="i === 0 ? 'Product' : undefined" :help="l.product_id && onHand(l.product_id) !== undefined ? `${onHand(l.product_id)} in stock now` : undefined">
            <USelect placeholder="Choose..." :model-value="l.product_id || undefined" class="w-full"
                     :items="products.map(p => ({ label: `${p.name} (${p.sku})`, value: p.id }))" @update:model-value="(v: any) => l.product_id = v" />
          </UFormField>
          <UFormField :label="i === 0 ? 'Received' : undefined"><UInput v-model="l.qty" type="number" min="1" class="w-full" /></UFormField>
          <UFormField :label="i === 0 ? 'Damaged' : undefined"><UInput v-model="l.damaged" type="number" min="0" placeholder="0" class="w-full" /></UFormField>
          <UButton v-if="lines.length > 1" icon="i-lucide-x" size="xs" color="neutral" variant="ghost" aria-label="Remove line" @click="lines.splice(i, 1)" />
          <span v-else />
        </div>
      </div>
    </template>
    <template #footer>
      <div class="flex justify-end gap-2 w-full">
        <UButton variant="ghost" color="neutral" @click="emit('update:open', false)">Cancel</UButton>
        <UButton :loading="saving" @click="save">Receive & confirm</UButton>
      </div>
    </template>
  </UModal>
  <QuickProduct v-model:open="showQuick" :vendor-id="form.vendor_id || undefined" :vendors="activeVendors" @created="onProductAdded" />
</template>
