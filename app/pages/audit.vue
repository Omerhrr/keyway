<script setup lang="ts">
const logs = ref<any[]>([])
const loading = ref(true)
const entityType = ref('ALL')

async function load() {
  loading.value = true
  try { logs.value = await api(`/audit?entity_type=${entityType.value === 'ALL' ? '' : entityType.value}`) } finally { loading.value = false }
}
onMounted(load)

const types = computed(() => ['', 'order', 'vendor', 'order_draft', 'cod_collection', 'settlement', 'user', 'inventory_balance', 'journal_entry', 'delivery', 'stock_receipt', 'charge_rule', 'charge', 'expense', 'conversation'])
</script>

<template>
  <div>
    <PageHeader title="Audit Trail" subtitle="Who did what, when - across operations and finance." />
    <div class="mb-3">
      <USelect v-model="entityType" :items="types.map(t => ({ label: t ? titleize(t) : 'All entities', value: t || 'ALL' }))" class="w-56" @change="load" />
    </div>
    <DataTable export-title="Activity log" :columns="[
      { key: 'created_at', label: 'When' },
      { key: 'actor_label', label: 'Actor' },
      { key: 'action', label: 'Action' },
      { key: 'entity', label: 'Entity' },
      { key: 'summary', label: 'Summary' },
    ]" :rows="logs.map(l => ({
      ...l,
      created_at: fmtDateTime(l.created_at),
      entity: `${titleize(l.entity_type)}${l.entity_id ? ' #' + l.entity_id : ''}`,
      action: titleize(l.action),
    }))" :loading="loading" empty-title="No audit entries" />
  </div>
</template>
