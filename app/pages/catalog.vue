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

// ---- Phase 6D: bulk import (CSV/XLSX) + CSV export ----
const showImport = ref(false)
const importVendorId = ref<number | null>(null)
const importFile = ref<File | null>(null)
const importing = ref(false)
const importResult = ref<any>(null)
function onImportFile(e: Event) {
  importFile.value = (e.target as HTMLInputElement)?.files?.[0] || null
  importResult.value = null
}
async function runImport() {
  if (!importVendorId.value || !importFile.value) return
  importing.value = true
  try {
    const fd = new FormData()
    fd.append('file', importFile.value)
    const { access } = useAuth()
    importResult.value = await $fetch(`/api/catalog/import?vendor_id=${importVendorId.value}`, {
      method: 'POST', body: fd,
      headers: access.value ? { Authorization: `Bearer ${access.value}` } : {},
    })
    useToast().add({ title: 'Import finished', color: 'success' })
    await load()
  } catch (e) {
    useToast().add({ title: 'Import failed', description: errMsg(e), color: 'error' })
  } finally { importing.value = false }
}
const exporting = ref(false)
async function exportCatalog() {
  exporting.value = true
  try {
    const { access, logout } = useAuth()
    const res = await $fetch.raw(`/api/catalog/export${vendorId.value ? `?vendor_id=${vendorId.value}` : ''}`, {
      headers: access.value ? { Authorization: `Bearer ${access.value}` } : {},
      responseType: 'blob',
      onResponseError({ response }) { if (response.status === 401) logout() },
    })
    const url = URL.createObjectURL(res._data as Blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'keyway-catalog.csv'
    a.click()
    URL.revokeObjectURL(url)
    useToast().add({ title: 'Catalog exported', color: 'success' })
  } catch (e) {
    useToast().add({ title: 'Export failed', description: errMsg(e), color: 'error' })
  } finally { exporting.value = false }
}
</script>

<template>
  <div>
    <PageHeader title="Product Catalog" subtitle="Vendor-owned products with variants and WhatsApp-friendly aliases for natural-language matching.">
      <template #actions>
        <UButton variant="soft" color="neutral" icon="i-lucide-download" :loading="exporting" @click="exportCatalog">Export</UButton>
        <UButton variant="soft" color="neutral" icon="i-lucide-upload" @click="showImport = true">Import CSV</UButton>
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

    <!-- Import CSV/XLSX modal (Phase 6D) -->
    <UModal v-model:open="showImport" title="Import catalog (CSV / Excel)">
      <template #body>
        <div class="space-y-3">
          <UFormField label="Vendor" description="Products are imported into this vendor's own catalog.">
            <USelect v-model="importVendorId" placeholder="Choose vendor" class="w-full" :items="vendors.map(v => ({ label: v.name, value: v.id }))" />
          </UFormField>
          <UFormField label="File" hint=".csv or .xlsx, up to 5MB">
            <input type="file" accept=".csv,.xlsx,.xlsm,text/csv"
                   class="w-full text-xs text-zinc-500 file:mr-2 file:rounded-md file:border-0 file:bg-zinc-100 dark:file:bg-zinc-800 file:px-3 file:py-1.5 file:text-xs"
                   @change="onImportFile" aria-label="Catalog file" />
          </UFormField>
          <UAlert color="neutral" variant="subtle" icon="i-lucide-table-2"
                  title="Expected columns"
                  description="sku*, name*, category, aliases (pipe-separated), sell_price (naira), opening_stock, reorder_level. Existing SKUs are updated; aliases are added without duplicates." />
          <div v-if="importResult" class="text-xs bg-zinc-50 dark:bg-zinc-800/60 rounded-lg p-3 space-y-1">
            <p><span class="text-emerald-600 font-semibold">{{ importResult.created }}</span> created ·
               <span class="font-semibold">{{ importResult.updated }}</span> updated ·
               {{ importResult.aliases_added }} aliases · {{ importResult.stock_rows }} stock rows seeded</p>
            <p v-if="importResult.errors?.length" class="text-red-500">
              {{ importResult.errors.length }} row issues: {{ importResult.errors.slice(0, 3).join('; ') }}
            </p>
          </div>
        </div>
      </template>
      <template #footer>
        <div class="flex justify-end gap-2 w-full">
          <UButton variant="ghost" color="neutral" @click="showImport = false">Close</UButton>
          <UButton :loading="importing" :disabled="!importVendorId || !importFile" icon="i-lucide-upload-cloud" @click="runImport">Import</UButton>
        </div>
      </template>
    </UModal>
  </div>
</template>
