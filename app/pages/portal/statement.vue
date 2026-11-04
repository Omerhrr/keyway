<script setup lang="ts">
definePageMeta({ layout: 'portal' })
const data = ref<any>(null)
const loading = ref(true)
onMounted(async () => {
  try { data.value = await api('/portal/statement') } finally { loading.value = false }
})

const totals = computed(() => {
  const lines = data.value?.lines || []
  const credits = lines.reduce((s: number, l: any) => s + (l.credit_kobo || 0), 0)
  const debits = lines.reduce((s: number, l: any) => s + (l.debit_kobo || 0), 0)
  return { credits, debits, balance: credits - debits }
})
</script>

<template>
  <div>
    <div class="grid grid-cols-3 gap-3 mb-5">
      <StatCard label="Collections" :value="fmtNaira(totals.credits)" icon="i-lucide-banknote" tone="success" />
      <StatCard label="Charges & payouts" :value="fmtNaira(totals.debits)" icon="i-lucide-scissors" />
      <StatCard label="Balance" :value="fmtNaira(totals.balance)" icon="i-lucide-wallet" tone="primary" />
    </div>

    <DataTable :columns="[
      { key: 'date', label: 'Date' },
      { key: 'type', label: 'Type' },
      { key: 'label', label: 'Description' },
      { key: 'credit', label: 'Credit', align: 'right' },
      { key: 'debit', label: 'Debit', align: 'right' },
      { key: 'status', label: 'Status' },
    ]" :rows="(data?.lines || []).map(l => ({
      ...l, date: fmtDate(l.date),
      credit: l.credit_kobo ? fmtNaira(l.credit_kobo) : '—',
      debit: l.debit_kobo ? fmtNaira(l.debit_kobo) : '—',
    }))" :loading="loading" empty-title="No statement lines yet">
      <template #type="{ row }">
        <UBadge :color="row.type === 'COD_COLLECTION' ? 'success' : row.type === 'CHARGE' ? 'warning' : 'primary'" variant="subtle" size="xs">
          {{ titleize(row.type) }}
        </UBadge>
      </template>
      <template #status="{ row }"><StatusBadge :status="row.status" /></template>
    </DataTable>
  </div>
</template>
