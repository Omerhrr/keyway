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

    <SettlementDetail v-model:open="showDetail" :id="selected?.id ?? null" @changed="load" />
  </div>
</template>
