<script setup lang="ts">
// Settlement detail + approve + add our charge + record payment. Used by /settlements and the vendor page.
const props = defineProps<{ id: number | null }>()
const open = defineModel<boolean>('open', { default: false })
const emit = defineEmits<{ changed: [] }>()
const saving = ref(false)
const detail = ref<any>(null)
const selected = computed(() => detail.value || {})
const { printRecord, exportExcel } = useDocs()
const from = ref('')
const to = ref('')
const day = (v: any) => (v ? String(v).slice(0, 10) : '')
const shownItems = computed(() => [...(detail.value?.items || [])]
  .filter((i: any) => (!from.value || day(i.date) >= from.value) && (!to.value || day(i.date) <= to.value))
  .sort((x: any, y: any) => (x.type === 'COLLECTION' ? 0 : 1) - (y.type === 'COLLECTION' ? 0 : 1) || day(x.date).localeCompare(day(y.date))))
const filtered = computed(() => !!(from.value || to.value))
const shownGross = computed(() => shownItems.value.reduce((a: number, i: any) => a + (i.gross_kobo || 0), 0))
const shownCharges = computed(() => shownItems.value.reduce((a: number, i: any) => a + (i.deduction_kobo || 0), 0))
const periodText = computed(() => filtered.value ? `${from.value ? fmtDate(from.value) : 'the start'} to ${to.value ? fmtDate(to.value) : 'today'}` : 'All dates')
const itemRows = computed(() => shownItems.value.map((i: any) => [
  fmtDate(i.date), i.type === 'COLLECTION' ? 'Collection' : 'Our charge', i.order_reference || '-', i.note || '',
  i.gross_kobo ? fmtNaira(i.gross_kobo) : '-', i.deduction_kobo ? `-${fmtNaira(i.deduction_kobo)}` : '-'] as (string | number)[]))
const itemCols = ['Date', 'Type', 'Order', 'Details', 'Gross', 'Deduction']
const payRows = computed(() => (detail.value?.payments || []).map((p: any) => [fmtDate(p.paid_at || p.created_at), fmtNaira(p.amount_kobo), titleize(p.method), p.bank_ref || '-']))
const stTitle = computed(() => `Settlement ${detail.value?.reference} - ${detail.value?.vendor_name}`)

async function printIt() {
  const d = detail.value
  await printRecord({
    title: stTitle.value,
    subtitle: `${titleize(d.status)} · ${periodText.value} · prepared ${fmtDate(new Date().toISOString())}`,
    fields: [['Vendor', d.vendor_name], ['Settlement', d.reference], ['Status', titleize(d.status)],
      [filtered.value ? 'Collected (shown)' : 'Gross collected', fmtNaira(filtered.value ? shownGross.value : d.gross_kobo)],
      [filtered.value ? 'Our charges (shown)' : 'Our charges', fmtNaira(filtered.value ? shownCharges.value : d.charges_kobo)],
      ['Net payable to vendor', fmtNaira(d.net_kobo)], ['Paid so far', fmtNaira(d.paid_kobo)], ['Still to pay', fmtNaira(d.net_kobo - d.paid_kobo)]],
    tables: [{ heading: 'What this settlement covers', columns: itemCols, rows: itemRows.value },
      ...(payRows.value.length ? [{ heading: 'Payments made', columns: ['Date', 'Amount', 'Method', 'Bank reference'], rows: payRows.value }] : [])],
  })
}
async function excelIt() {
  try { await exportExcel(stTitle.value, itemCols, itemRows.value, `${titleize(detail.value.status)} · ${periodText.value}`) }
  catch (e) { useToast().add({ title: 'Could not export', description: errMsg(e), color: 'error' }) }
}
function whatsappText() {
  const d = detail.value
  const L: string[] = [`*Settlement ${d.reference} - ${d.vendor_name}*`, `${titleize(d.status)}${filtered.value ? ' · ' + periodText.value : ''}`, '']
  L.push(`Collected: ${fmtNaira(filtered.value ? shownGross.value : d.gross_kobo)}`)
  L.push(`Our charges: -${fmtNaira(filtered.value ? shownCharges.value : d.charges_kobo)}`)
  L.push(`*Net payable: ${fmtNaira(d.net_kobo)}*`, `Paid so far: ${fmtNaira(d.paid_kobo)}`, `Still to pay: ${fmtNaira(d.net_kobo - d.paid_kobo)}`)
  const cols = shownItems.value.filter((i: any) => i.type === 'COLLECTION')
  const chs = shownItems.value.filter((i: any) => i.type !== 'COLLECTION')
  if (cols.length) { L.push('', '*Orders*'); cols.forEach((i: any) => L.push(`• ${fmtDate(i.date)} · ${i.order_reference} · ${i.note || ''} · ${fmtNaira(i.gross_kobo)}`)) }
  if (chs.length) { L.push('', '*Our charges*'); chs.forEach((i: any) => L.push(`• ${fmtDate(i.date)} · ${i.order_reference ? i.order_reference + ' · ' : ''}${i.note || 'Charge'} · -${fmtNaira(i.deduction_kobo)}`)) }
  if (detail.value.payments?.length) { L.push('', '*Payments*'); detail.value.payments.forEach((p: any) => L.push(`• ${fmtDate(p.paid_at || p.created_at)} · ${fmtNaira(p.amount_kobo)} · ${titleize(p.method)}${p.bank_ref ? ' · ref ' + p.bank_ref : ''}`)) }
  return L.join('\n')
}
async function copyIt() {
  const text = whatsappText()
  try { await navigator.clipboard.writeText(text) }
  catch {
    const ta = document.createElement('textarea'); ta.value = text; ta.style.cssText = 'position:fixed;opacity:0'
    document.body.appendChild(ta); ta.select(); document.execCommand('copy'); ta.remove()
  }
  useToast().add({ title: 'Copied', description: 'Paste it into WhatsApp for the vendor.', color: 'success', icon: 'i-lucide-clipboard-check' })
}
const canCharge = computed(() => ['READY_FOR_APPROVAL', 'APPROVED', 'PARTIALLY_PAID'].includes(detail.value?.status))

async function fetchDetail() { if (props.id) detail.value = await api(`/settlements/${props.id}`) }
watch(open, async (o) => {
  if (o && props.id) { detail.value = null; from.value = ''; to.value = ''; try { await fetchDetail() } catch (e) { useToast().add({ title: 'Could not open settlement', description: errMsg(e), color: 'error' }); open.value = false } }
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
const chargeOrder = ref<{ id: number, ref: string } | null>(null)
function openCharge(order?: { id: number, ref: string }) { chargeOrder.value = order || null; chargeForm.charge_type = 'OTHER'; chargeForm.amount = ''; chargeForm.reason = ''; showCharge.value = true }
async function addCharge() {
  const amount = toKobo(chargeForm.amount)
  if (!amount || amount <= 0) { useToast().add({ title: 'Enter the charge amount', color: 'warning' }); return }
  saving.value = true
  try {
    await api(`/settlements/${props.id}/charges`, { method: 'POST', body: { order_id: chargeOrder.value?.id || null, charge_type: chargeForm.charge_type, amount_kobo: amount, reason: chargeForm.reason } })
    useToast().add({ title: 'Charge added', color: 'success' })
    showCharge.value = false
    await fetchDetail(); emit('changed')
  } catch (e) { useToast().add({ title: 'Could not add charge', description: errMsg(e), color: 'error' }) } finally { saving.value = false }
}
</script>

<template>
  <div>
    <!-- detail modal -->
    <UModal v-model:open="open" :ui="{ content: 'max-w-3xl' }" :title="`Settlement ${detail?.reference || ''}`">
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
          <p v-if="!canCharge" class="text-xs text-zinc-400">This settlement is fully paid, so charges can no longer be added.</p>
          <div class="flex flex-wrap items-end gap-2">
            <UFormField label="From"><UInput v-model="from" type="date" size="sm" class="w-36" /></UFormField>
            <UFormField label="To"><UInput v-model="to" type="date" size="sm" class="w-36" /></UFormField>
            <UButton v-if="filtered" size="sm" variant="ghost" color="neutral" @click="from = ''; to = ''">All dates</UButton>
            <div class="flex flex-wrap gap-1.5 ml-auto">
              <UButton size="sm" color="neutral" variant="outline" icon="i-lucide-clipboard-copy" @click="copyIt">Copy for WhatsApp</UButton>
              <UButton size="sm" color="neutral" variant="outline" icon="i-lucide-printer" @click="printIt">PDF</UButton>
              <UButton size="sm" color="neutral" variant="outline" icon="i-lucide-file-spreadsheet" @click="excelIt">Excel</UButton>
            </div>
          </div>
          <p v-if="filtered" class="text-xs text-zinc-500">Showing {{ shownItems.length }} of {{ detail.items.length }} lines ({{ periodText }}): collected {{ fmtNaira(shownGross) }}, our charges {{ fmtNaira(shownCharges) }}. The totals above are for the whole settlement.</p>
          <div class="rounded-lg border border-zinc-200 dark:border-zinc-800 overflow-x-auto">
            <table class="w-full text-sm">
              <thead><tr class="bg-zinc-50 dark:bg-zinc-800/60 text-[11px] uppercase text-zinc-400">
                <th class="px-3 py-2 text-left">Date</th><th class="px-3 py-2 text-left">Type</th><th class="px-3 py-2 text-left">Order</th>
                <th class="px-3 py-2 text-right">Gross</th><th class="px-3 py-2 text-right pr-3">Deduction</th>
              </tr></thead>
              <tbody>
                <tr v-for="i in shownItems" :key="i.id" class="border-t border-zinc-100 dark:border-zinc-800">
                  <td class="px-3 py-2 text-xs whitespace-nowrap text-zinc-500">{{ fmtDate(i.date) }}</td>
                  <td class="px-3 py-2"><UBadge :color="i.type === 'COLLECTION' ? 'success' : 'warning'" variant="subtle" size="xs">{{ i.type === 'COLLECTION' ? 'COLLECTION' : 'CHARGE' }}</UBadge></td>
                  <td class="px-3 py-2">
                    <p class="font-mono text-xs">{{ i.order_reference || '-' }}</p>
                    <p v-if="i.note" class="text-[11px] text-zinc-400 max-w-[16rem] whitespace-normal leading-snug">{{ i.note }}</p>
                    <button v-if="i.type === 'COLLECTION' && canCharge && i.order_id" type="button"
                            class="mt-1 text-[11px] font-medium text-amber-600 hover:underline inline-flex items-center gap-0.5"
                            @click="openCharge({ id: i.order_id, ref: i.order_reference })"><UIcon name="i-lucide-plus" class="w-3 h-3" />Add our charge to this order</button>
                  </td>
                  <td class="px-3 py-2 text-right">{{ i.gross_kobo ? fmtNaira(i.gross_kobo) : '-' }}</td>
                  <td class="px-3 py-2 text-right pr-3 text-amber-600">{{ i.deduction_kobo ? `-${fmtNaira(i.deduction_kobo)}` : '-' }}</td>
                </tr>
                <tr v-if="!shownItems.length"><td colspan="5" class="px-3 py-6 text-center text-sm text-zinc-400">Nothing in this date range</td></tr>
              </tbody>
            </table>
          </div>
          <div v-if="detail.payments?.length" class="rounded-lg border border-zinc-200 dark:border-zinc-800 overflow-hidden">
            <p class="px-3 py-2 text-[11px] uppercase text-zinc-400 bg-zinc-50 dark:bg-zinc-800/60">Payments made</p>
            <div v-for="p in detail.payments" :key="p.id" class="flex flex-wrap gap-x-3 px-3 py-2 text-sm border-t border-zinc-100 dark:border-zinc-800">
              <span class="text-zinc-500 text-xs">{{ fmtDate(p.paid_at || p.created_at) }}</span>
              <span class="font-semibold tabular-nums text-emerald-600">{{ fmtNaira(p.amount_kobo) }}</span>
              <span class="text-xs text-zinc-500">{{ titleize(p.method) }}<template v-if="p.bank_ref"> · ref {{ p.bank_ref }}</template></span>
            </div>
          </div>
        </div>
      </template>
      <template #footer>
        <div class="flex flex-wrap justify-between gap-2 w-full">
          <div class="flex flex-wrap gap-2">
            <UButton v-if="detail?.status === 'READY_FOR_APPROVAL'" :loading="saving" color="primary" variant="soft" icon="i-lucide-check-check" @click="approve">Approve settlement</UButton>
            <UButton v-if="canCharge" color="warning" variant="soft" icon="i-lucide-plus" @click="openCharge()">Add our charge</UButton>
          </div>
          <UButton v-if="['APPROVED', 'PARTIALLY_PAID'].includes(detail?.status)" icon="i-lucide-banknote" @click="openPay">Record payment</UButton>
        </div>
      </template>
    </UModal>

    <!-- add charge modal -->
    <UModal v-model:open="showCharge" :title="chargeOrder ? `Add our charge to order ${chargeOrder.ref}` : 'Add our charge to this settlement'">
      <template #body>
        <div class="space-y-3">
          <UAlert color="info" variant="subtle" icon="i-lucide-info" title="Deducted from what the vendor is owed" description="Use this for anything not already charged on the orders, such as storage or special handling. Every charge is recorded with its reason." />
          <UFormField label="Charge type"><USelect v-model="chargeForm.charge_type" class="w-full" :items="chargeTypes.map(t => ({ label: titleize(t), value: t }))" /></UFormField>
          <UFormField label="Amount (₦)"><UInput v-model="chargeForm.amount" inputmode="decimal" class="w-full" /></UFormField>
          <UFormField label="Reason (optional)"><UTextarea v-model="chargeForm.reason" :rows="2" class="w-full" /></UFormField>
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
