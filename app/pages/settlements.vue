<script setup lang="ts">
const { needs } = useGuard()
const settlements = ref<any[]>([])
const loading = ref(true)
const saving = ref(false)
const vendors = ref<any[]>([])

async function load() {
  loading.value = true
  try { settlements.value = await api('/settlements') }
  catch (e) { useToast().add({ title: 'Could not load settlements', description: errMsg(e), color: 'error', icon: 'i-lucide-circle-alert' }) } finally { loading.value = false }
}
onMounted(async () => {
  load()
  try { vendors.value = await api('/vendors') } catch {}
})

const showBuild = ref(false)
const buildVendor = ref(0)

async function build() {
  saving.value = true
  try {
    const s = await api('/settlements/build', { method: 'POST', body: { vendor_id: buildVendor.value } })
    useToast().add({ title: `Settlement ${s.reference} built`, description: `${fmtNaira(s.net_kobo)} net payable.`, color: 'success' })
    showBuild.value = false
    await load()
  } catch (e) {
    useToast().add({ title: 'Nothing to settle', description: errMsg(e), color: 'error' })
  } finally { saving.value = false }
}

const selected = ref<any>(null)
const detail = ref<any>(null)
const showDetail = ref(false)

async function open(s: any) {
  selected.value = s
  detail.value = await api(`/settlements/${s.id}`)
  showDetail.value = true
}

async function approve() {
  saving.value = true
  try {
    await api(`/settlements/${selected.value.id}/approve`, { method: 'POST' })
    useToast().add({ title: 'Settlement approved', description: 'Ready for payment recording.', color: 'success' })
    await load()
    detail.value = await api(`/settlements/${selected.value.id}`)
  } catch (e) {
    useToast().add({ title: 'Not allowed', description: errMsg(e), color: 'error' })
  } finally { saving.value = false }
}

const showPay = ref(false)
const payForm = reactive({ amount_naira: '', bank_ref: '', method: 'BANK_TRANSFER' })

function openPay() {
  payForm.amount_naira = String((selected.value.net_kobo - selected.value.paid_kobo) / 100)
  payForm.bank_ref = ''
  showPay.value = true
}

async function pay() {
  saving.value = true
  try {
    await api(`/settlements/${selected.value.id}/pay`, {
      method: 'POST',
      body: { amount_kobo: toKobo(payForm.amount_naira), bank_ref: payForm.bank_ref, method: payForm.method },
    })
    useToast().add({ title: 'Payment recorded', description: 'Vendor payable settled through the bank account.', color: 'success', icon: 'i-lucide-book-check' })
    showPay.value = false
    detail.value = await api(`/settlements/${selected.value.id}`)
    await load()
  } catch (e) {
    useToast().add({ title: 'Payment failed', description: errMsg(e), color: 'error' })
  } finally { saving.value = false }
}
</script>

<template>
  <div>
    <PageHeader title="Vendor Settlements" subtitle="What a vendor is owed = verified cash collected, minus charges and adjustments. Approving and paying are recorded separately.">
      <template #actions>
        <UButton icon="i-lucide-calculator" @click="showBuild = true">Build settlement</UButton>
      </template>
    </PageHeader>

    <DataTable export-title="Settlements" :columns="[
      { key: 'reference', label: 'Reference' },
      { key: 'vendor_name', label: 'Vendor' },
      { key: 'gross', label: 'Gross collections', align: 'right' },
      { key: 'charges', label: 'Charges', align: 'right' },
      { key: 'net', label: 'Net payable', align: 'right' },
      { key: 'paid', label: 'Paid', align: 'right' },
      { key: 'status', label: 'Status' },
    ]" :rows="settlements.map(s => ({
      ...s,
      gross: fmtNaira(s.gross_kobo), charges: fmtNaira(s.charges_kobo),
      net: fmtNaira(s.net_kobo), paid: s.paid_kobo ? fmtNaira(s.paid_kobo) : '-',
    }))" :loading="loading" clickable empty-title="No settlements yet"
      empty-hint="Build one from verified collections and applied charges." @row-click="open">
      <template #reference="{ row }"><span class="font-mono font-semibold text-primary-600">{{ row.reference }}</span></template>
      <template #net="{ value }"><span class="font-bold">{{ value }}</span></template>
      <template #status="{ row }"><StatusBadge :status="row.status" /></template>
    </DataTable>

    <!-- build modal -->
    <UModal v-model:open="showBuild" title="Build settlement batch">
      <template #body>
        <div class="space-y-3">
          <UFormField label="Vendor">
            <USelect v-model="buildVendor" class="w-full" :items="vendors.map(v => ({ label: v.name, value: v.id }))" />
          </UFormField>
          <UAlert color="info" variant="subtle" icon="i-lucide-calculator"
                  title="Reproducible calculation"
                  description="Verified collections not yet settled, minus charges on those same orders. Every item is traceable to its order and collection." />
        </div>
      </template>
      <template #footer>
        <div class="flex justify-end gap-2 w-full">
          <UButton variant="ghost" color="neutral" @click="showBuild = false">Cancel</UButton>
          <UButton :loading="saving" @click="needs([['Vendor', buildVendor]]) && build()">Build batch</UButton>
        </div>
      </template>
    </UModal>

    <!-- detail modal -->
    <UModal v-model:open="showDetail" :ui="{ content: 'max-w-2xl' }" :title="`Settlement ${selected?.reference || ''}`">
      <template #body>
        <div v-if="detail" class="space-y-4">
          <div class="flex flex-wrap items-center gap-2">
            <StatusBadge :status="detail.status" />
            <UBadge color="neutral" variant="subtle">{{ detail.vendor_name }}</UBadge>
            <UBadge v-if="detail.approved_by_user_id" color="success" variant="outline" size="xs">approved by user #{{ detail.approved_by_user_id }}</UBadge>
          </div>
          <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <StatCard label="Gross" :value="fmtNaira(detail.gross_kobo)" icon="i-lucide-banknote" />
            <StatCard label="Charges" :value="fmtNaira(detail.charges_kobo)" icon="i-lucide-scissors" tone="warning" />
            <StatCard label="Net" :value="fmtNaira(detail.net_kobo)" icon="i-lucide-wallet" tone="primary" />
            <StatCard label="Paid" :value="fmtNaira(detail.paid_kobo)" icon="i-lucide-check" tone="success" />
          </div>
          <div class="rounded-lg border border-zinc-200 dark:border-zinc-800 overflow-hidden">
            <table class="w-full text-sm">
              <thead><tr class="bg-zinc-50 dark:bg-zinc-800/60 text-[11px] uppercase text-zinc-400">
                <th class="px-3 py-2 text-left">Type</th><th class="px-3 py-2 text-left">Order</th>
                <th class="px-3 py-2 text-right">Gross</th><th class="px-3 py-2 text-right pr-3">Deduction</th>
              </tr></thead>
              <tbody>
                <tr v-for="i in detail.items" :key="i.id" class="border-t border-zinc-100 dark:border-zinc-800">
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
          <UButton v-if="detail?.status === 'READY_FOR_APPROVAL'" :loading="saving" color="primary" variant="soft" icon="i-lucide-check-check" @click="approve">Approve settlement</UButton>
          <span v-else />
          <UButton v-if="['APPROVED', 'PARTIALLY_PAID'].includes(detail?.status)" icon="i-lucide-banknote" @click="openPay">Record payment</UButton>
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
