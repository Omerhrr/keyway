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

const picked = ref<number[]>([])
const payable = computed(() => settlements.value.filter((x: any) => ['APPROVED', 'PARTIALLY_PAID'].includes(x.status)))
const pickedRows = computed(() => payable.value.filter((x: any) => picked.value.includes(x.id))
  .map((x: any) => ({ id: x.id, reference: x.reference, vendor_name: x.vendor_name, owed_kobo: x.net_kobo - x.paid_kobo })))
const pickedTotal = computed(() => pickedRows.value.reduce((a: number, r: any) => a + r.owed_kobo, 0))
const showBatch = ref(false)
function toggle(id: number) { picked.value = picked.value.includes(id) ? picked.value.filter(x => x !== id) : [...picked.value, id] }
function afterBatch() { picked.value = []; load() }
const selected = ref<any>(null)
const showDetail = ref(false)
function open(s: any) { selected.value = s; showDetail.value = true }
</script>

<template>
  <div>
    <PageHeader title="Vendor Settlements" subtitle="What a vendor is owed = verified cash collected, minus charges and adjustments. Approving and paying are recorded separately.">
      <template #actions>
        <UButton icon="i-lucide-calculator" @click="showBuild = true">Build settlement</UButton>
      </template>
    </PageHeader>

    <div v-if="payable.length" class="flex flex-wrap items-center gap-2 mb-3 rounded-xl border border-primary-200 dark:border-primary-900 bg-primary-50/50 dark:bg-primary-950/20 px-3 py-2">
      <p class="text-sm text-zinc-600 dark:text-zinc-300 mr-auto">
        <template v-if="picked.length"><b>{{ picked.length }}</b> selected · <b>{{ fmtNaira(pickedTotal) }}</b> to pay</template>
        <template v-else>{{ payable.length }} approved settlement{{ payable.length === 1 ? '' : 's' }} waiting for payment. Tick the ones to pay together.</template>
      </p>
      <UButton size="xs" variant="ghost" color="neutral" @click="picked = picked.length === payable.length ? [] : payable.map((x: any) => x.id)">{{ picked.length === payable.length ? 'Clear' : 'Select all' }}</UButton>
      <UButton size="xs" icon="i-lucide-banknote" :disabled="!picked.length" @click="showBatch = true">Pay selected</UButton>
    </div>

    <DataTable export-title="Settlements" :columns="[
      { key: 'sel', label: ' ' },
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
      <template #sel="{ row }">
        <UCheckbox v-if="['APPROVED', 'PARTIALLY_PAID'].includes(row.status)" :model-value="picked.includes(row.id)" @click.stop @update:model-value="toggle(row.id)" />
      </template>
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

    <SettlementPayBatch v-model:open="showBatch" :rows="pickedRows" @changed="afterBatch" />
    <SettlementDetail v-model:open="showDetail" :id="selected?.id ?? null" @changed="load" />
  </div>
</template>
