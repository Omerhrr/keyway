<script setup lang="ts">
const { needs } = useGuard()
const collections = ref<any[]>([])
const handovers = ref<any[]>([])
const loading = ref(true)
const saving = ref(false)
const tab = ref('collections')
const statusFilter = ref('')

const tabs = [
  { label: 'Collections', value: 'collections', icon: 'i-lucide-hand-coins' },
  { label: 'Cash handovers', value: 'handovers', icon: 'i-lucide-handshake' },
]

async function load() {
  loading.value = true
  try {
    const p = statusFilter.value ? `?status=${statusFilter.value}` : ''
    collections.value = await api(`/cod/collections${p}`)
    handovers.value = await api('/cod/handovers')
  } finally { loading.value = false }
}
onMounted(load)

// record collection
const orders = ref<any[]>([])
const showRecord = ref(false)
const form = reactive({ order_id: 0, collected_naira: '', method: 'CASH' })

async function openRecord() {
  showRecord.value = true
  try { orders.value = await api('/orders?status=DELIVERED') } catch {}
}

async function record() {
  saving.value = true
  try {
    await api('/cod/collections', { method: 'POST', body: { order_id: form.order_id, collected_kobo: toKobo(form.collected_naira), method: form.method } })
    useToast().add({ title: 'Collection recorded', description: 'Pending verification by finance.', color: 'success' })
    showRecord.value = false
    await load()
  } catch (e) {
    useToast().add({ title: 'Failed', description: errMsg(e), color: 'error' })
  } finally { saving.value = false }
}

// verify / flag
const selected = ref<any>(null)
const showVerify = ref(false)
const verifyForm = reactive({ collected_naira: '', method: 'CASH', note: '' })

function askVerify(c: any) {
  selected.value = c
  verifyForm.collected_naira = String((c.collected_kobo || c.expected_kobo || 0) / 100)
  verifyForm.method = c.method || 'CASH'
  verifyForm.note = ''
  showVerify.value = true
}

async function verify() {
  saving.value = true
  try {
    await api(`/cod/collections/${selected.value.id}`, {
      method: 'PATCH',
      body: { collected_kobo: toKobo(verifyForm.collected_naira), method: verifyForm.method },
    })
    await api(`/cod/collections/${selected.value.id}/verify`, { method: 'POST', body: { note: verifyForm.note } })
    useToast().add({ title: 'Collection verified', description: 'Books updated: the cash is recorded and the vendor is credited.', color: 'success', icon: 'i-lucide-book-check' })
    showVerify.value = false
    await load()
  } catch (e) {
    useToast().add({ title: 'Verification blocked', description: errMsg(e), color: 'error' })
  } finally { saving.value = false }
}

// handover
const showHandover = ref(false)
const riders = ref<any[]>([])
const hForm = reactive({ rider_id: 0, amount_expected_naira: '' })
async function openHandover() {
  showHandover.value = true
  try { riders.value = await api('/dispatch/riders') } catch {}
}
async function createHandover() {
  saving.value = true
  try {
    await api('/cod/handovers', { method: 'POST', body: { rider_id: hForm.rider_id || null, amount_expected_kobo: toKobo(hForm.amount_expected_naira) } })
    showHandover.value = false
    useToast().add({ title: 'Handover opened' })
    await load()
  } finally { saving.value = false }
}
const hSelected = ref<any>(null)
const hCounted = ref('')
async function confirmHandover(h: any) {
  try {
    await api(`/cod/handovers/${h.id}/confirm`, { method: 'POST', body: { amount_counted_kobo: toKobo(hCounted.value || '0') } })
    hCounted.value = ''
    useToast().add({ title: 'Handover confirmed' })
    await load()
  } catch (e) { useToast().add({ title: 'Failed', description: errMsg(e), color: 'error' }) }
}
</script>

<template>
  <div>
    <PageHeader title="COD Management">
      <template #actions>
        <UButton icon="i-lucide-plus" @click="openRecord">Record collection</UButton>
      </template>
    </PageHeader>
    <p class="text-sm text-zinc-500 -mt-3 mb-4">Expected and collected amounts are stored separately. Only verified collections become vendor funds.</p>

    <ScrollTabs :items="tabs" v-model="tab" class="mb-4" />

    <template v-if="tab === 'collections'">
      <div class="flex gap-1.5 mb-3 flex-wrap">
        <UButton v-for="s in ['', 'PENDING_VERIFICATION', 'VERIFIED', 'DISCREPANCY']" :key="s" size="xs"
                 :variant="statusFilter === s ? 'solid' : 'soft'" color="neutral"
                 :label="s ? titleize(s) : 'All'" @click="statusFilter = s; load()" />
      </div>
      <DataTable export-title="Cash collections" :columns="[
        { key: 'order_reference', label: 'Order' },
        { key: 'customer_name', label: 'Customer' },
        { key: 'expected', label: 'Expected', align: 'right' },
        { key: 'collected', label: 'Collected', align: 'right' },
        { key: 'method', label: 'Method' },
        { key: 'status', label: 'Status' },
        { key: 'actions', label: '' },
      ]" :rows="collections.map(c => ({
        ...c,
        expected: fmtNaira(c.expected_kobo),
        collected: fmtNaira(c.collected_kobo),
        short: c.expected_kobo - c.collected_kobo,
      }))" :loading="loading" empty-title="No collections" empty-hint="Record collections from delivered COD orders.">
        <template #order_reference="{ row }"><NuxtLink :to="`/orders/${row.order_id}`" class="font-mono font-semibold text-primary-600">{{ row.order_reference }}</NuxtLink></template>
        <template #collected="{ value, row }">
          <span :class="row.short !== 0 ? 'text-amber-600 font-semibold' : 'font-semibold'">{{ value }}</span>
        </template>
        <template #status="{ row }"><StatusBadge :status="row.status" /></template>
        <template #actions="{ row }">
          <UButton v-if="row.status === 'PENDING_VERIFICATION'" size="xs" color="success" variant="soft" icon="i-lucide-book-check" @click.stop="askVerify(row)">Verify</UButton>
        </template>
      </DataTable>
    </template>

    <template v-else>
      <div class="mb-3">
        <UButton size="xs" icon="i-lucide-plus" variant="soft" @click="openHandover">Open handover</UButton>
      </div>
      <DataTable export-title="Cash handovers" :columns="[
        { key: 'reference', label: 'Reference' },
        { key: 'rider_name', label: 'Rider' },
        { key: 'expected', label: 'Expected', align: 'right' },
        { key: 'counted', label: 'Counted', align: 'right' },
        { key: 'status', label: 'Status' },
        { key: 'actions', label: '' },
      ]" :rows="handovers.map(h => ({ ...h, expected: fmtNaira(h.amount_expected_kobo), counted: h.amount_counted_kobo ? fmtNaira(h.amount_counted_kobo) : '-' }))"
        :loading="loading" empty-title="No handovers">
        <template #status="{ row }"><StatusBadge :status="row.status" /></template>
        <template #actions="{ row }">
          <div v-if="row.status === 'PENDING'" class="flex items-center gap-1" @click.stop>
            <UInput v-model="hCounted" size="xs" placeholder="Counted ₦" class="w-28" />
            <UButton size="xs" color="success" variant="soft" @click="confirmHandover(row)">Confirm</UButton>
          </div>
        </template>
      </DataTable>
    </template>

    <!-- record modal -->
    <UModal v-model:open="showRecord" title="Record COD collection">
      <template #body>
        <div class="space-y-3">
          <UFormField label="Delivered COD order">
            <USelect placeholder="Choose..." @update:model-value="(v: any) => { form.order_id = v }" :model-value="form.order_id || undefined" class="w-full" :items="orders.map(o => ({ label: `${o.reference} · ${o.customer_name} · expected ${fmtNaira(o.cod_amount_kobo)}`, value: o.id }))" />
          </UFormField>
          <UFormField label="Amount collected (₦)"><UInput v-model="form.collected_naira" class="w-full" /></UFormField>
          <UFormField label="Method">
            <USelect v-model="form.method" class="w-full" :items="[{ label: 'Cash', value: 'CASH' }, { label: 'Bank transfer', value: 'BANK_TRANSFER' }, { label: 'Digital', value: 'DIGITAL' }]" />
          </UFormField>
        </div>
      </template>
      <template #footer>
        <div class="flex justify-end gap-2 w-full">
          <UButton variant="ghost" color="neutral" @click="showRecord = false">Cancel</UButton>
          <UButton :loading="saving" @click="needs([['Order', form.order_id]]) && record()">Record</UButton>
        </div>
      </template>
    </UModal>

    <!-- verify modal -->
    <UModal v-model:open="showVerify" title="Verify collection">
      <template #body>
        <div class="space-y-3">
          <div class="text-sm text-zinc-500">
            Order {{ selected?.order_reference }} · expected <b>{{ fmtNaira(selected?.expected_kobo) }}</b> ·
            collected <b>{{ fmtNaira(selected?.collected_kobo) }}</b>
            <UBadge v-if="selected && selected.expected_kobo !== selected.collected_kobo" color="warning" variant="subtle" size="xs" class="ml-1">
              short {{ fmtNaira(Math.abs(selected.expected_kobo - selected.collected_kobo)) }}
            </UBadge>
          </div>
          <UAlert color="info" variant="subtle" icon="i-lucide-book-check"
                  title="Posting plan" description="Dr COD Clearing (collected) / Cr Vendor Payables · charges on the order recognized as Logistics Revenue." />
          <UFormField label="Amount actually collected (₦)" help="Stored separately from the expected amount">
            <UInput v-model="verifyForm.collected_naira" class="w-full" />
          </UFormField>
          <UFormField label="Method">
            <USelect v-model="verifyForm.method" class="w-full" :items="[{ label: 'Cash', value: 'CASH' }, { label: 'Bank transfer', value: 'BANK_TRANSFER' }, { label: 'Digital', value: 'DIGITAL' }]" />
          </UFormField>
          <UFormField label="Note" help="Required when the amounts differ">
            <UTextarea v-model="verifyForm.note" :rows="2" class="w-full" />
          </UFormField>
        </div>
      </template>
      <template #footer>
        <div class="flex justify-end gap-2 w-full">
          <UButton variant="ghost" color="neutral" @click="showVerify = false">Cancel</UButton>
          <UButton :loading="saving" color="success" @click="verify">Verify and record</UButton>
        </div>
      </template>
    </UModal>

    <!-- handover modal -->
    <UModal v-model:open="showHandover" title="Open cash handover">
      <template #body>
        <div class="space-y-3">
          <UFormField label="Rider"><USelect v-model="hForm.rider_id" class="w-full" :items="[{ label: 'Staff (no rider)', value: 0 }, ...riders.map(r => ({ label: r.full_name, value: r.id }))]" /></UFormField>
          <UFormField label="Amount expected (₦)" help="This rider's pending collections are attached automatically"><UInput v-model="hForm.amount_expected_naira" class="w-full" /></UFormField>
        </div>
      </template>
      <template #footer>
        <div class="flex justify-end gap-2 w-full">
          <UButton variant="ghost" color="neutral" @click="showHandover = false">Cancel</UButton>
          <UButton :loading="saving" @click="createHandover">Open</UButton>
        </div>
      </template>
    </UModal>
  </div>
</template>
