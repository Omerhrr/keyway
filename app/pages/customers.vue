<script setup lang="ts">
const customers = ref<any[]>([])
const loading = ref(true)
const q = ref('')

async function load() {
  loading.value = true
  try { customers.value = await api(`/customers?q=${encodeURIComponent(q.value)}`) }
  catch (e) { useToast().add({ title: 'Could not load customers', description: errMsg(e), color: 'error', icon: 'i-lucide-circle-alert' }) } finally { loading.value = false }
}
onMounted(load)
</script>

<template>
  <div>
    <PageHeader title="Customers" subtitle="Delivery recipients per vendor - phone numbers are unique within each vendor's book." />
    <div class="mb-3">
      <UInput v-model="q" icon="i-lucide-search" placeholder="Name or phone…" @keydown.enter="load" />
    </div>
    <DataTable export-title="Customers" :columns="[
      { key: 'name', label: 'Customer' },
      { key: 'phone', label: 'Phone' },
      { key: 'alt_phone', label: 'Alt phone' },
      { key: 'vendor_name', label: 'Vendor' },
      { key: 'created_at', label: 'Added' },
    ]" :rows="customers.map(c => ({ ...c, created_at: fmtDate(c.created_at) }))" :loading="loading"
      empty-title="No customers" empty-hint="Customers are created automatically from WhatsApp orders.">
      <template #phone="{ row }"><span class="font-mono">{{ row.phone }}</span></template>
    </DataTable>
  </div>
</template>
