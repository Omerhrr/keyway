<script setup lang="ts">
const queue = ref<any[]>([])
const loading = ref(true)
const saving = ref(false)
const selected = ref<any>(null)
const showAttempt = ref(false)
const form = reactive({ outcome: 'NO_ANSWER', note: '', follow_up_date: '' })

const outcomes = [
  { value: 'CUSTOMER_CONFIRMED', label: 'Customer confirmed' },
  { value: 'NO_ANSWER', label: 'Not picking calls' },
  { value: 'PHONE_SWITCHED_OFF', label: 'Phone switched off' },
  { value: 'CUSTOMER_AWAY', label: 'Not around - will take it in a few days' },
  { value: 'CUSTOMER_REQUESTED_RESCHEDULE', label: 'Asked to call back / reschedule' },
  { value: 'ADDRESS_NEEDS_CORRECTION', label: 'Address needs correction' },
  { value: 'INVALID_PHONE_NUMBER', label: 'Wrong / invalid number' },
  { value: 'CUSTOMER_REJECTED', label: 'Customer rejected (cancels order)' },
]
const needsDate = computed(() => ['CUSTOMER_AWAY', 'NO_ANSWER', 'PHONE_SWITCHED_OFF'].includes(form.outcome))
const dateRequired = computed(() => form.outcome === 'CUSTOMER_AWAY')
function openAttempt(row: any) { selected.value = row; form.outcome = 'NO_ANSWER'; form.note = ''; form.follow_up_date = ''; showAttempt.value = true }

async function load() {
  loading.value = true
  try { queue.value = await api('/confirmations/queue') } finally { loading.value = false }
}
onMounted(load)

async function submit() {
  saving.value = true
  try {
    if (dateRequired.value && !form.follow_up_date) { useToast().add({ title: 'Pick the date the customer will be back', color: 'warning' }); saving.value = false; return }
    await api(`/confirmations/${selected.value.id}/attempt`, { method: 'POST', body: { outcome: form.outcome, note: form.note, follow_up_date: form.follow_up_date || null } })
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

    <DataTable export-title="Order confirmations" :columns="[
      { key: 'reference', label: 'Order' },
      { key: 'vendor_name', label: 'Vendor' },
      { key: 'customer_name', label: 'Customer' },
      { key: 'customer_phone', label: 'Phone' },
      { key: 'cod', label: 'COD to confirm', align: 'right' },
      { key: 'confirmation_status', label: 'Status' },
      { key: 'follow_up', label: 'Follow up' },
      { key: 'attempts', label: 'Attempts', align: 'right' },
      { key: 'actions', label: '' },
    ]" :rows="queue.map(o => ({ ...o, cod: fmtNaira(o.cod) }))" :loading="loading"
      empty-title="Queue is clear" empty-hint="Orders needing customer confirmation will appear here.">
      <template #reference="{ row }"><span class="font-mono font-semibold text-primary-600">{{ row.reference }}</span></template>
      <template #confirmation_status="{ row }"><StatusBadge :status="row.confirmation_status" /></template>
      <template #follow_up="{ row }">
        <span v-if="row.follow_up_at" :class="row.follow_up_due ? 'text-red-600 font-semibold' : 'text-zinc-500'" class="text-xs">
          {{ row.follow_up_due ? 'Due · ' : '' }}{{ fmtDateTime(row.follow_up_at).split(',')[0] }}
        </span>
        <span v-else class="text-zinc-300">-</span>
      </template>
      <template #actions="{ row }">
        <UButton size="xs" variant="soft" icon="i-lucide-phone" @click.stop="openAttempt(row)">Log attempt</UButton>
      </template>
    </DataTable>

    <UModal v-model:open="showAttempt" :title="`Confirmation call - ${selected?.reference || ''}`">
      <template #body>
        <div class="space-y-3">
          <div class="text-sm text-zinc-500">
            {{ selected?.customer_name }} · <span class="font-mono">{{ selected?.customer_phone }}</span> ·
            {{ selected?.delivery_city }}, {{ selected?.delivery_state }}
          </div>
          <UFormField label="Outcome"><USelect v-model="form.outcome" class="w-full" :items="outcomes" /></UFormField>
          <UFormField v-if="needsDate" :label="dateRequired ? 'Customer will be back on' : 'Call again on (optional)'">
            <UInput v-model="form.follow_up_date" type="date" class="w-full" />
          </UFormField>
          <UAlert v-if="['NO_ANSWER','PHONE_SWITCHED_OFF','CUSTOMER_AWAY'].includes(form.outcome)" color="info" variant="subtle" title="The order stays on hold as pending customer confirmation and reappears here when the follow-up date arrives." />
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
