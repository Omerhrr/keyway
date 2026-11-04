<script setup lang="ts">
const products = ref<any[]>([])
const vendors = ref<any[]>([])
const loading = ref(true)
const q = ref('')
const vendorId = ref(0)
const lowOnly = ref(false)

async function load() {
  loading.value = true
  try {
    const p = new URLSearchParams()
    if (q.value) p.set('q', q.value)
    if (vendorId.value) p.set('vendor_id', String(vendorId.value))
    if (lowOnly.value) p.set('low_stock', 'true')
    products.value = await api(`/catalog/products?${p}&breakdown=true`)
  } finally { loading.value = false }
}
onMounted(async () => {
  load()
  try { vendors.value = await api('/vendors') } catch {}
})

const showNew = ref(false)
const saving = ref(false)
const form = reactive({ vendor_id: 0, sku: '', name: '', category: '', price_naira: '', reorder_level: 5 })

async function create() {
  saving.value = true
  try {
    await api('/catalog/products', {
      method: 'POST',
      body: { vendor_id: form.vendor_id, sku: form.sku, name: form.name, category: form.category, default_sell_price_kobo: toKobo(form.price_naira), reorder_level: Number(form.reorder_level) },
    })
    useToast().add({ title: 'Product created', color: 'success' })
    showNew.value = false
    await load()
  } catch (e) {
    useToast().add({ title: 'Failed', description: errMsg(e), color: 'error' })
  } finally { saving.value = false }
}
</script>

<template>
  <div>
    <PageHeader title="Product Catalog" subtitle="Vendor-owned products with variants and WhatsApp-friendly aliases for natural-language matching.">
      <template #actions>
        <UButton icon="i-lucide-plus" @click="showNew = true">New product</UButton>
      </template>
    </PageHeader>

    <div class="flex gap-2 mb-3 flex-wrap items-center">
      <UInput v-model="q" icon="i-lucide-search" placeholder="Search name, SKU…" @keydown.enter="load" />
      <USelect v-model="vendorId" :items="[{ label: 'All vendors', value: 0 }, ...vendors.map(v => ({ label: v.name, value: v.id }))]" class="w-52" @change="load" />
      <UCheckbox v-model="lowOnly" label="Low stock" @update:model-value="load" />
    </div>

    <DataTable :columns="[
      { key: 'name', label: 'Product' },
      { key: 'vendor_name', label: 'Vendor' },
      { key: 'category', label: 'Category' },
      { key: 'price', label: 'Price', align: 'right' },
      { key: 'stock', label: 'Available', align: 'right' },
      { key: 'variants', label: 'Variants' },
    ]" :rows="products.map(p => ({
      ...p, vendor_name: vendors.find(v => v.id === p.vendor_id)?.name || `#${p.vendor_id}`,
      price: p.default_sell_price_kobo ? fmtNaira(p.default_sell_price_kobo) : '—',
      stock: String(p.qty_available ?? 0) + (p.low_stock ? ' ⚠' : ''),
      variants: (p.variants || []).map(v => v.name).join(', ') || '—',
    }))" :loading="loading" empty-title="No products" empty-hint="Add products per vendor with aliases like 'sneakers' for WhatsApp matching.">
      <template #name="{ row }">
        <p class="font-medium text-zinc-800 dark:text-zinc-200">{{ row.name }}</p>
        <p class="text-[11px] text-zinc-400 font-mono">{{ row.sku }}</p>
      </template>
    </DataTable>

    <UModal v-model:open="showNew" title="New product">
      <template #body>
        <div class="grid sm:grid-cols-2 gap-3">
          <UFormField label="Vendor">
            <USelect v-model="form.vendor_id" class="w-full" :items="vendors.map(v => ({ label: v.name, value: v.id }))" />
          </UFormField>
          <UFormField label="SKU"><UInput v-model="form.sku" class="w-full" /></UFormField>
          <UFormField label="Name"><UInput v-model="form.name" class="w-full" /></UFormField>
          <UFormField label="Category"><UInput v-model="form.category" class="w-full" /></UFormField>
          <UFormField label="Default price (₦)"><UInput v-model="form.price_naira" class="w-full" /></UFormField>
          <UFormField label="Reorder level"><UInput v-model="form.reorder_level" type="number" class="w-full" /></UFormField>
        </div>
      </template>
      <template #footer>
        <div class="flex justify-end gap-2 w-full">
          <UButton variant="ghost" color="neutral" @click="showNew = false">Cancel</UButton>
          <UButton :loading="saving" :disabled="!form.vendor_id || !form.sku || !form.name" @click="create">Create</UButton>
        </div>
      </template>
    </UModal>
  </div>
</template>
