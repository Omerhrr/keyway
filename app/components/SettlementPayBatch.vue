<script setup lang="ts">
// Pay several approved settlements in one go. Each is paid what is still owed on it.
const props = defineProps<{ rows: { id: number, reference: string, vendor_name?: string, owed_kobo: number }[] }>()
const open = defineModel<boolean>('open', { default: false })
const emit = defineEmits<{ changed: [] }>()
const saving = ref(false)
const form = reactive({ method: 'BANK_TRANSFER', bank_ref: '', note: '' })
const total = computed(() => props.rows.reduce((a, r) => a + r.owed_kobo, 0))
watch(open, (o) => { if (o) { form.method = 'BANK_TRANSFER'; form.bank_ref = ''; form.note = '' } })

async function pay() {
  saving.value = true
  try {
    const r = await api('/settlements/pay-batch', { method: 'POST', body: { settlement_ids: props.rows.map(x => x.id), ...form } })
    useToast().add({ title: `${r.paid.length} settlement${r.paid.length === 1 ? '' : 's'} paid`, description: `${fmtNaira(r.total_kobo)} recorded.`, color: 'success', icon: 'i-lucide-book-check' })
    open.value = false
    emit('changed')
  } catch (e) {
    useToast().add({ title: 'Payment failed - nothing was recorded', description: errMsg(e), color: 'error' })
  } finally { saving.value = false }
}
</script>

<template>
  <UModal v-model:open="open" :title="`Pay ${rows.length} settlement${rows.length === 1 ? '' : 's'} together`">
    <template #body>
      <div class="space-y-3">
        <div class="rounded-lg border border-zinc-200 dark:border-zinc-800 divide-y divide-zinc-100 dark:divide-zinc-800 text-sm max-h-56 overflow-y-auto">
          <div v-for="r in rows" :key="r.id" class="flex justify-between gap-3 px-3 py-2">
            <span><span class="font-mono font-semibold text-primary-600">{{ r.reference }}</span><span v-if="r.vendor_name" class="text-zinc-500"> · {{ r.vendor_name }}</span></span>
            <span class="font-semibold tabular-nums">{{ fmtNaira(r.owed_kobo) }}</span>
          </div>
          <div class="flex justify-between gap-3 px-3 py-2.5 bg-primary-50/60 dark:bg-primary-950/30 font-bold"><span>Total</span><span class="tabular-nums">{{ fmtNaira(total) }}</span></div>
        </div>
        <UAlert color="info" variant="subtle" icon="i-lucide-info" description="Each settlement is paid in full (what is still owed on it). If one can't be paid, none are recorded." />
        <UFormField label="Method">
          <USelect v-model="form.method" class="w-full" :items="[{ label: 'Bank transfer', value: 'BANK_TRANSFER' }, { label: 'Cash', value: 'CASH' }]" />
        </UFormField>
        <UFormField label="Bank reference"><UInput v-model="form.bank_ref" class="w-full" placeholder="e.g. TRF-88213 (shared by all)" /></UFormField>
        <UFormField label="Note (optional)"><UInput v-model="form.note" class="w-full" /></UFormField>
      </div>
    </template>
    <template #footer>
      <div class="flex justify-end gap-2 w-full">
        <UButton variant="ghost" color="neutral" @click="open = false">Cancel</UButton>
        <UButton :loading="saving" icon="i-lucide-banknote" @click="pay">Pay {{ fmtNaira(total) }}</UButton>
      </div>
    </template>
  </UModal>
</template>
