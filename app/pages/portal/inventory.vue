<script setup lang="ts">
definePageMeta({ layout: 'portal' })
const items = ref<any[]>([])
const loading = ref(true)
onMounted(async () => {
  try { items.value = await api('/portal/inventory') } catch { items.value = [] } finally { loading.value = false }
})
</script>

<template>
  <div>
    <p class="text-sm text-zinc-500 mb-4">Stock currently held in our warehouses on your behalf.</p>
    <DataTable export-title="My stock" :columns="[
      { key: 'name', label: 'Product' },
      { key: 'sku', label: 'Product code' },
      { key: 'physical', label: 'Physical', align: 'right' },
      { key: 'reserved', label: 'Reserved', align: 'right' },
      { key: 'available', label: 'Available', align: 'right' },
    ]" :rows="items" :loading="loading" empty-title="No stock on file">
      <template #name="{ row }">
        <span class="font-medium">{{ row.name }}</span>
        <UBadge v-if="row.low_stock" color="warning" variant="subtle" size="xs" class="ml-1.5">Low</UBadge>
      </template>
      <template #sku="{ value }"><span class="font-mono text-xs text-zinc-400">{{ value }}</span></template>
    </DataTable>
  </div>
</template>
