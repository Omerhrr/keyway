<script setup lang="ts">
const queue = ref<any[]>([])
const loading = ref(true)
const saving = ref(false)
const selected = ref<any>(null)
const showAttempt = ref(false)
const form = reactive({ outcome: 'CALL_ATTEMPTED', note: '' })

const outcomes = ['CALL_ATTEMPTED', 'NO_ANSWER', 'CUSTOMER_CONFIRMED', 'CUSTOMER_REQUESTED_RESCHEDULE', 'ADDRESS_NEEDS_CORRECTION', 'CUSTOMER_REJECTED', 'INVALID_PHONE_NUMBER']

async function load() {
  loading.value = true
  try { queue.value = await api('/confirmations/queue') } finally { loading.value = false }
}
onMounted(load)

async function submit() {
  saving.value = true
  try {
    await api(`/confirmations/${selected.value.id}/attempt`, { method: 'POST', body: { ...form } })
    useToast().add({ title: 'Attempt recorded', color: 'success' })
    showAttempt.value = false
    await load()
  } catch (e) {
    useToast().add({ title: 'Failed', description: errMsg(e), color: 'error' })
  } finally { saving.value = false }
}
</script>

<template>
  <div>
    <PageHeader title="Customer Confirmations" subtitle="Confirm product, amount, address and availability before dispatch. Every attempt is recorded." />

    <DataTable :columns="[
      { key: 'reference', label: 'Order' },
      { key: 'vendor_name', label: 'Vendor' },
      { key: 'customer_name', label: 'Customer' },
      { key: 'customer_phone', label: 'Phone' },
      { key: 'cod', label: 'COD to confirm', align: 'right' },
      { key: 'confirmation_status', label: 'Status' },
      { key: 'attempts', label: 'Attempts', align: 'right' },
      { key: 'actions', label: '' },
    ]" :rows="queue.map(o => ({ ...o, cod: fmtNaira(o.cod) }))" :loading="loading"
      empty-title="Queue is clear" empty-hint="Orders needing customer confirmation will appear here.">
      <template #reference="{ row }"><span class="font-mono font-semibold text-primary-600">{{ row.reference }}</span></template>
      <template #confirmation_status="{ row }"><StatusBadge :status="row.confirmation_status" /></template>
      <template #actions="{ row }">
        <UButton size="xs" variant="soft" icon="i-lucide-phone" @click.stop="selected = row; showAttempt = true">Log attempt</UButton>
      </template>
    </DataTable>

    <UModal v-model:open="showAttempt" :title="`Confirmation call - ${selected?.reference || ''}`">
      <template #body>
        <div class="space-y-3">
          <div class="text-sm text-zinc-500">
            {{ selected?.customer_name }} · <span class="font-mono">{{ selected?.customer_phone }}</span> ·
            {{ selected?.delivery_city }}, {{ selected?.delivery_state }}
          </div>
          <UFormField label="Outcome"><USelect v-model="form.outcome" class="w-full" :items="outcomes.map(o => ({ label: titleize(o), value: o }))" /></UFormField>
          <UFormField label="Note"><UTextarea v-model="form.note" :rows="2" class="w-full" /></UFormField>
          <UAlert v-if="form.outcome === 'CUSTOMER_REJECTED'" color="error" variant="subtle" title="Customer rejection cancels the order and releases reserved stock." />
        </div>
      </template>
      <template #footer>
        <div class="flex justify-end gap-2 w-full">
          <UButton variant="ghost" color="neutral" @click="showAttempt = false">Cancel</UButton>
          <UButton :loading="saving" @click="submit">Record</UButton>
        </div>
      </template>
    </UModal>
  </div>
</template>
