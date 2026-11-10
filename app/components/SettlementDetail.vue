<script setup lang="ts">
// Settlement detail + approve + add our charge + record payment. Used by /settlements and the vendor page.
const props = defineProps<{ id: number | null }>()
const open = defineModel<boolean>('open', { default: false })
const emit = defineEmits<{ changed: [] }>()
const saving = ref(false)
const detail = ref<any>(null)
const selected = computed(() => detail.value || {})

async function fetchDetail() { if (props.id) detail.value = await api(`/settlements/${props.id}`) }
watch(open, async (o) => {
  if (o && props.id) { detail.value = null; try { await fetchDetail() } catch (e) { useToast().add({ title: 'Could not open settlement', description: errMsg(e), color: 'error' }); open.value = false } }
})

async function approve() {
  saving.value = true
  try {
    await api(`/settlements/${props.id}/approve`, { method: 'POST' })
    useToast().add({ title: 'Settlement approved', description: 'Ready for payment recording.', color: 'success' })
    await fetchDetail(); emit('changed')
  } catch (e) {
    useToast().add({ title: 'Not allowed', description: errMsg(e), color: 'error' })
  } finally { saving.value = false }
}

const showPay = ref(false)
const payForm = reactive({ amount_naira: '', bank_ref: '', method: 'BANK_TRANSFER' })
function openPay() {
  payForm.amount_naira = String((detail.value.net_kobo - detail.value.paid_kobo) / 100)
  payForm.bank_ref = ''
  showPay.value = true
}
async function pay() {
  saving.value = true
  try {
    await api(`/settlements/${props.id}/pay`, {
      method: 'POST',
      body: { amount_kobo: toKobo(payForm.amount_naira), bank_ref: payForm.bank_ref, method: payForm.method },
    })
    useToast().add({ title: 'Payment recorded', description: 'Vendor payable settled through the bank account.', color: 'success', icon: 'i-lucide-book-check' })
    showPay.value = false
    await fetchDetail(); emit('changed')
  } catch (e) {
    useToast().add({ title: 'Payment failed', description: errMsg(e), color: 'error' })
  } finally { saving.value = false }
}

const showCharge = ref(false)
const chargeTypes = ['OTHER', 'STORAGE', 'SPECIAL_HANDLING', 'RETURN_HANDLING', 'ORDER_PROCESSING', 'COD_HANDLING', 'WAYBILL']
const chargeForm = reactive({ charge_type: 'OTHER', amount: '', reason: '' })
function openCharge() { chargeForm.charge_type = 'OTHER'; chargeForm.amount = ''; chargeForm.reason = ''; showCharge.value = true }
async function addCharge() {
  const amount = toKobo(chargeForm.amount)
  if (!amount || amount <= 0) { useToast().add({ title: 'Enter the charge amount', color: 'warning' }); return }
  if (!chargeForm.reason.trim()) { useToast().add({ title: 'Say why this charge applies', color: 'warning' }); return }
  saving.value = true
  try {
    await api(`/settlements/${props.id}/charges`, { method: 'POST', body: { charge_type: chargeForm.charge_type, amount_kobo: amount, reason: chargeForm.reason } })
    useToast().add({ title: 'Charge added', color: 'success' })
    showCharge.value = false
    await fetchDetail(); emit('changed')
  } catch (e) { useToast().add({ title: 'Could not add charge', description: errMsg(e), color: 'error' }) } finally { saving.value = false }
}
</script>

<template>
  <div>
    <!-- detail modal -->
    <UModal v-model:open="open" :ui="{ content: 'max-w-2xl' }" :title="`Settlement ${detail?.reference || ''}`">
      <template #body>
        <div v-if="detail" class="space-y-4">
          <div class="flex flex-wrap items-center gap-2">
            <StatusBadge :status="detail.status" />
            <UBadge color="neutral" variant="subtle">{{ detail.vendor_name }}</UBadge>
            <UBadge v-if="detail.approved_by_user_id" color="success" variant="outline" size="xs">approved by user #{{ detail.approved_by_user_id }}</UBadge>
          </div>
          <div class="rounded-xl border border-zinc-200 dark:border-zinc-800 divide-y divide-zinc-100 dark:divide-zinc-800 text-sm">
            <div class="flex justify-between gap-3 px-4 py-2.5"><span class="text-zinc-500">Gross collected</span><span class="font-semibold tabular-nums">{{ fmtNaira(detail.gross_kobo) }}</span></div>
            <div class="flex justify-between gap-3 px-4 py-2.5"><span class="text-zinc-500">Our charges</span><span class="font-semibold tabular-nums text-amber-600">-{{ fmtNaira(detail.charges_kobo) }}</span></div>
            <div class="flex justify-between gap-3 px-4 py-3 bg-primary-50/60 dark:bg-primary-950/30 rounded-b-xl"><span class="font-semibold">Net payable to vendor</span><span class="text-lg font-bold tabular-nums text-primary-700 dark:text-primary-400">{{ fmtNaira(detail.net_kobo) }}</span></div>
            <div class="flex justify-between gap-3 px-4 py-2.5"><span class="text-zinc-500">Paid so far</span><span class="font-semibold tabular-nums text-emerald-600">{{ fmtNaira(detail.paid_kobo) }}</span></div>
          </div>
          <div class="rounded-lg border border-zinc-200 dark:border-zinc-800 overflow-hidden">
            <table class="w-full text-sm">
              <thead><tr class="bg-zinc-50 dark:bg-zinc-800/60 text-[11px] uppercase text-zinc-400">
                <th class="px-3 py-2 text-left">Type</th><th class="px-3 py-2 text-left">Order</th>
                <th class="px-3 py-2 text-right">Gross</th><th class="px-3 py-2 text-right pr-3">Deduction</th>
              </tr></thead>
              <tbody>
                <tr v-for="i in [...detail.items].sort((x, y) => (x.type === 'COLLECTION' ? 0 : 1) - (y.type === 'COLLECTION' ? 0 : 1))" :key="i.id" class="border-t border-zinc-100 dark:border-zinc-800">
                  <td class="px-3 py-2"><UBadge :color="i.type === 'COLLECTION' ? 'success' : 'warning'" variant="subtle" size="xs">{{ i.type }}</UBadge></td>
                  <td class="px-3 py-2 font-mono text-xs">{{ i.order_reference || '-' }}</td>
                  <td class="px-3 py-2 text-right">{{ i.gross_kobo ? fmtNaira(i.gross_kobo) : '-' }}</td>
                  <td class="px-3 py-2 text-right pr-3 text-amber-600">{{ i.deduction_kobo ? `-${fmtNaira(i.deduction_kobo)}` : '-' }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </template>
      <template #footer>
        <div class="flex justify-between w-full">
          <div v-if="detail?.status === 'READY_FOR_APPROVAL'" class="flex gap-2">
            <UButton :loading="saving" color="primary" variant="soft" icon="i-lucide-check-check" @click="approve">Approve settlement</UButton>
            <UButton color="warning" variant="soft" icon="i-lucide-plus" @click="openCharge">Add our charge</UButton>
          </div>
          <span v-else />
          <UButton v-if="['APPROVED', 'PARTIALLY_PAID'].includes(detail?.status)" icon="i-lucide-banknote" @click="openPay">Record payment</UButton>
        </div>
      </template>
    </UModal>

    <!-- add charge modal -->
    <UModal v-model:open="showCharge" title="Add our charge to this settlement">
      <template #body>
        <div class="space-y-3">
          <UAlert color="info" variant="subtle" icon="i-lucide-info" title="Deducted from what the vendor is owed" description="Use this for anything not already charged on the orders, such as storage or special handling. Every charge is recorded with its reason." />
          <UFormField label="Charge type"><USelect v-model="chargeForm.charge_type" class="w-full" :items="chargeTypes.map(t => ({ label: titleize(t), value: t }))" /></UFormField>
          <UFormField label="Amount (₦)"><UInput v-model="chargeForm.amount" inputmode="decimal" class="w-full" /></UFormField>
          <UFormField label="Reason"><UTextarea v-model="chargeForm.reason" :rows="2" class="w-full" /></UFormField>
        </div>
      </template>
      <template #footer>
        <div class="flex justify-end gap-2 w-full">
          <UButton variant="ghost" color="neutral" @click="showCharge = false">Cancel</UButton>
          <UButton :loading="saving" @click="addCharge">Add charge</UButton>
        </div>
      </template>
    </UModal>

    <!-- pay modal -->
    <UModal v-model:open="showPay" title="Record vendor payment">
      <template #body>
        <div class="space-y-3">
          <UAlert color="info" variant="subtle" icon="i-lucide-book-check"
                  title="Posting plan" description="Dr Vendor Payables / Cr Bank - supports partial payments." />
          <UFormField label="Amount (₦)"><UInput v-model="payForm.amount_naira" class="w-full" /></UFormField>
          <UFormField label="Method">
            <USelect v-model="payForm.method" class="w-full" :items="[{ label: 'Bank transfer', value: 'BANK_TRANSFER' }, { label: 'Cash', value: 'CASH' }]" />
          </UFormField>
          <UFormField label="Bank reference"><UInput v-model="payForm.bank_ref" class="w-full" placeholder="e.g. TRF-88213" /></UFormField>
        </div>
      </template>
      <template #footer>
        <div class="flex justify-end gap-2 w-full">
          <UButton variant="ghost" color="neutral" @click="showPay = false">Cancel</UButton>
          <UButton :loading="saving" @click="pay">Record payment</UButton>
        </div>
      </template>
    </UModal>
  </div>
</template>
