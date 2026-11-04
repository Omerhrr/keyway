<script setup lang="ts">
definePageMeta({ layout: 'portal' })
const orders = ref<any[]>([])
const loading = ref(true)
const q = ref('')

async function load() {
  loading.value = true
  try { orders.value = await api(`/portal/orders?q=${q.value}`) } finally { loading.value = false }
}
onMounted(load)

const selected = ref<any>(null)
const showDetail = ref(false)
async function open(o: any) {
  selected.value = await api(`/portal/orders/${o.id}`)
  showDetail.value = true
}
</script>

<template>
  <div>
    <div class="flex items-center gap-2 mb-4">
      <UInput v-model="q" icon="i-lucide-search" placeholder="Reference or customer…" class="flex-1" @keydown.enter="load" />
    </div>
    <DataTable :columns="[
      { key: 'reference', label: 'Order' },
      { key: 'customer_name', label: 'Customer' },
      { key: 'destination', label: 'Destination' },
      { key: 'cod', label: 'COD', align: 'right' },
      { key: 'status', label: 'Status' },
    ]" :rows="orders.map(o => ({
      ...o,
      destination: [o.delivery_city, o.delivery_state].filter(Boolean).join(', ') || '—',
      cod: fmtNaira(o.cod_amount_kobo),
    }))" :loading="loading" clickable empty-title="No orders yet"
      empty-hint="Send us an order on WhatsApp and it will appear here." @row-click="open">
      <template #reference="{ row }"><span class="font-mono font-semibold text-primary-600">{{ row.reference }}</span></template>
      <template #status="{ row }"><StatusBadge :status="row.status" /></template>
    </DataTable>

    <UModal v-model:open="showDetail" :title="selected?.reference || ''">
      <template #body>
        <div v-if="selected" class="space-y-3 text-sm">
          <div class="flex items-center gap-2"><StatusBadge :status="selected.status" /><UBadge color="neutral" variant="subtle" size="xs">{{ fmtDate(selected.created_at) }}</UBadge></div>
          <div class="rounded-lg bg-zinc-50 dark:bg-zinc-800/60 p-3">
            <p class="font-medium">{{ selected.customer_name }}</p>
            <p class="text-zinc-500">{{ [selected.delivery_street, selected.delivery_city, selected.delivery_state].filter(Boolean).join(', ') }}</p>
          </div>
          <table class="w-full text-sm">
            <tbody>
              <tr v-for="i in selected.items" :key="i.id" class="border-b border-zinc-100 dark:border-zinc-800">
                <td class="py-2">{{ i.name_snapshot }} × {{ i.qty }}</td>
                <td class="py-2 text-right font-medium">{{ fmtNaira(i.line_total_kobo) }}</td>
              </tr>
              <tr class="font-bold text-primary-600">
                <td class="py-2">COD to collect</td><td class="py-2 text-right">{{ fmtNaira(selected.cod_amount_kobo) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>
    </UModal>
  </div>
</template>
