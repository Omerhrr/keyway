<script setup lang="ts">
const deliveries = ref<any[]>([])
const riders = ref<any[]>([])
const carriers = ref<any[]>([])
const zones = ref<any[]>([])
const loading = ref(true)
const saving = ref(false)
const tab = ref('deliveries')

const tabs = [
  { label: 'Deliveries', value: 'deliveries', icon: 'i-lucide-truck' },
  { label: 'Riders', value: 'riders', icon: 'i-lucide-bike' },
  { label: 'Carriers & Zones', value: 'network', icon: 'i-lucide-building-2' },
]

async function load() {
  loading.value = true
  try {
    const [d, r, c, z] = await Promise.all([
      api('/dispatch/deliveries'), api('/dispatch/riders'), api('/dispatch/carriers'), api('/dispatch/zones'),
    ])
    deliveries.value = d; riders.value = r; carriers.value = c; zones.value = z
  } catch (e) {
    useToast().add({ title: 'Could not load dispatch board', description: errMsg(e), color: 'error', icon: 'i-lucide-circle-alert' })
  } finally { loading.value = false }
}
onMounted(load)

// dispatch modal (orders that are READY_FOR_DISPATCH)
const readyOrders = ref<any[]>([])
const showDispatch = ref(false)
const form = reactive({ order_id: 0, mode: 'IN_HOUSE_RIDER', rider_id: 0, zone_id: 0, fee_naira: '' })

async function openDispatch() {
  showDispatch.value = true
  try { readyOrders.value = await api('/orders?status=READY_FOR_DISPATCH') } catch {}
}

async function dispatch() {
  saving.value = true
  try {
    await api('/dispatch/deliveries', {
      method: 'POST',
      body: {
        order_id: form.order_id, mode: form.mode,
        rider_id: form.mode === 'IN_HOUSE_RIDER' ? form.rider_id || null : null,
        zone_id: form.zone_id || null, fee_kobo: form.fee_naira ? toKobo(form.fee_naira) : 0,
      },
    })
    useToast().add({ title: 'Dispatched', color: 'success' })
    showDispatch.value = false
    await load()
  } catch (e) {
    useToast().add({ title: 'Failed', description: errMsg(e), color: 'error' })
  } finally { saving.value = false }
}

const selected = ref<any>(null)
const showOutcome = ref(false)
const outcomeForm = reactive({ to_status: 'DELIVERED', failure_reason: '', proof_ref: '', note: '' })

function askOutcome(d: any, to: string) {
  selected.value = d
  outcomeForm.to_status = to
  outcomeForm.failure_reason = ''
  outcomeForm.proof_ref = ''
  outcomeForm.note = ''
  showOutcome.value = true
}

async function submitOutcome() {
  saving.value = true
  try {
    await api(`/dispatch/deliveries/${selected.value.id}/status`, { method: 'POST', body: { ...outcomeForm } })
    useToast().add({ title: `Delivery ${titleize(outcomeForm.to_status)}`, color: 'success' })
    showOutcome.value = false
    await load()
  } catch (e) {
    useToast().add({ title: 'Failed', description: errMsg(e), color: 'error' })
  } finally { saving.value = false }
}

// rider / carrier / zone creation
const showRider = ref(false)
const riderForm = reactive({ full_name: '', phone: '', vehicle: '' })
async function createRider() {
  await api('/dispatch/riders', { method: 'POST', body: { ...riderForm } })
  showRider.value = false
  useToast().add({ title: 'Rider added', color: 'success' })
  await load()
}
const showCarrier = ref(false)
const carrierForm = reactive({ name: '', kind: 'INTERSTATE', contact_phone: '' })
async function createCarrier() {
  await api('/dispatch/carriers', { method: 'POST', body: { ...carrierForm } })
  showCarrier.value = false
  useToast().add({ title: 'Carrier added', color: 'success' })
  await load()
}
const showZone = ref(false)
const zoneForm = reactive({ name: '', state: '', base_fee_naira: '' })
async function createZone() {
  await api('/dispatch/zones', { method: 'POST', body: { name: zoneForm.name, state: zoneForm.state, cities: [], base_fee_kobo: toKobo(zoneForm.base_fee_naira) } })
  showZone.value = false
  useToast().add({ title: 'Zone added', color: 'success' })
  await load()
}
</script>

<template>
  <div>
    <PageHeader title="Dispatch & Delivery" subtitle="Riders, outside carriers and long-distance waybills, with proof of delivery and failed delivery handling.">
      <template #actions>
        <UButton icon="i-lucide-plus" @click="openDispatch">Dispatch an order</UButton>
      </template>
    </PageHeader>

    <ScrollTabs :items="tabs" v-model="tab" class="mb-4" />

    <DataTable export-title="Deliveries" v-if="tab === 'deliveries'" :columns="[
      { key: 'order_reference', label: 'Order' },
      { key: 'vendor_name', label: 'Vendor' },
      { key: 'destination', label: 'Destination' },
      { key: 'mode', label: 'Mode' },
      { key: 'rider_name', label: 'Rider' },
      { key: 'cod_expected', label: 'COD', align: 'right' },
      { key: 'status', label: 'Status' },
      { key: 'actions', label: '' },
    ]" :rows="deliveries.map(d => ({ ...d, destination: [d.delivery_city, d.delivery_state].filter(Boolean).join(', '), cod_expected: fmtNaira(d.cod_expected) }))"
      :loading="loading" empty-title="No deliveries yet" empty-hint="Move an order to READY_FOR_DISPATCH, then dispatch it.">
      <template #order_reference="{ row }"><NuxtLink :to="`/orders/${row.order_id}`" class="font-mono font-semibold text-primary-600">{{ row.order_reference }}</NuxtLink></template>
      <template #mode="{ row }"><UBadge color="neutral" variant="subtle" size="xs">{{ titleize(row.mode) }}</UBadge></template>
      <template #cod_expected="{ row }"><span class="font-medium">{{ row.cod_expected }}</span></template>
      <template #status="{ row }"><StatusBadge :status="row.status" /></template>
      <template #actions="{ row }">
        <div v-if="['ASSIGNED', 'DISPATCHED', 'IN_TRANSIT', 'OUT_FOR_DELIVERY'].includes(row.status)" class="flex gap-1" @click.stop>
          <UButton size="xs" color="success" variant="soft" icon="i-lucide-check" @click="askOutcome(row, 'DELIVERED')">Delivered</UButton>
          <UButton size="xs" color="error" variant="soft" icon="i-lucide-x" @click="askOutcome(row, 'FAILED')">Failed</UButton>
        </div>
      </template>
    </DataTable>

    <DataTable export-title="Riders" v-else-if="tab === 'riders'" :columns="[
      { key: 'full_name', label: 'Rider' },
      { key: 'phone', label: 'Phone' },
      { key: 'vehicle', label: 'Vehicle' },
      { key: 'zone_name', label: 'Zone' },
      { key: 'status', label: 'Status' },
    ]" :rows="riders" :loading="loading" @row-click="() => {}">
      <template #actions_slot><span /></template>
      <template #status="{ row }"><StatusBadge :status="row.status" /></template>
    </DataTable>

    <div v-else class="grid grid-cols-1 lg:grid-cols-2 gap-5">
      <div>
        <div class="flex items-center justify-between mb-3">
          <h3 class="font-semibold text-zinc-700 dark:text-zinc-200">Carriers</h3>
          <UButton size="xs" icon="i-lucide-plus" variant="soft" @click="showCarrier = true">Add</UButton>
        </div>
        <DataTable export-title="Carriers" :columns="[{ key: 'name', label: 'Name' }, { key: 'kind', label: 'Kind' }, { key: 'contact_phone', label: 'Contact' }]" :rows="carriers" :loading="loading" />
      </div>
      <div>
        <div class="flex items-center justify-between mb-3">
          <h3 class="font-semibold text-zinc-700 dark:text-zinc-200">Delivery zones</h3>
          <UButton size="xs" icon="i-lucide-plus" variant="soft" @click="showZone = true">Add</UButton>
        </div>
        <DataTable export-title="Delivery zones" :columns="[{ key: 'name', label: 'Zone' }, { key: 'state', label: 'State' }, { key: 'fee', label: 'Base fee', align: 'right' }]"
                   :rows="zones.map(z => ({ ...z, fee: fmtNaira(z.base_fee_kobo) }))" :loading="loading" />
      </div>
    </div>

    <!-- dispatch modal -->
    <UModal v-model:open="showDispatch" title="Dispatch an order">
      <template #body>
        <div class="grid sm:grid-cols-2 gap-3">
          <UFormField label="Ready order" class="sm:col-span-2">
            <USelect placeholder="Choose..." @update:model-value="(v: any) => { form.order_id = v }" :model-value="form.order_id || undefined" class="w-full" :items="readyOrders.map(o => ({ label: `${o.reference} · ${o.customer_name} · ${[o.delivery_city, o.delivery_state].filter(Boolean).join(', ')}`, value: o.id }))" />
          </UFormField>
          <UFormField label="Mode">
            <USelect v-model="form.mode" class="w-full" :items="[
              { label: 'In-house rider', value: 'IN_HOUSE_RIDER' },
              { label: 'Local third-party', value: 'LOCAL_3P' },
              { label: 'Interstate transport', value: 'INTERSTATE' },
              { label: 'Waybill', value: 'WAYBILL' },
            ]" />
          </UFormField>
          <UFormField v-if="form.mode === 'IN_HOUSE_RIDER'" label="Rider">
            <USelect placeholder="Choose..." @update:model-value="(v: any) => { form.rider_id = v }" :model-value="form.rider_id || undefined" class="w-full" :items="riders.map(r => ({ label: `${r.full_name} · ${r.zone_name || ''}`, value: r.id }))" />
          </UFormField>
          <UFormField label="Zone">
            <USelect v-model="form.zone_id" class="w-full" :items="[{ label: 'No zone', value: 0 }, ...zones.map(z => ({ label: `${z.name} · ${fmtNaira(z.base_fee_kobo)}`, value: z.id }))]" />
          </UFormField>
          <UFormField label="Fee override (₦)"><UInput v-model="form.fee_naira" class="w-full" /></UFormField>
        </div>
      </template>
      <template #footer>
        <div class="flex justify-end gap-2 w-full">
          <UButton variant="ghost" color="neutral" @click="showDispatch = false">Cancel</UButton>
          <UButton :loading="saving" :disabled="!form.order_id" icon="i-lucide-truck" @click="dispatch">Dispatch</UButton>
        </div>
      </template>
    </UModal>

    <!-- outcome modal -->
    <UModal v-model:open="showOutcome" :title="`Delivery outcome - ${selected?.order_reference || ''}`">
      <template #body>
        <div class="space-y-3">
          <USelect v-model="outcomeForm.to_status" class="w-full" :items="[
            { label: 'Delivered', value: 'DELIVERED' }, { label: 'Failed', value: 'FAILED' },
            { label: 'Out for delivery', value: 'OUT_FOR_DELIVERY' }, { label: 'Returning', value: 'RETURNING' },
          ]" />
          <UFormField v-if="outcomeForm.to_status === 'FAILED'" label="Failure reason">
            <UInput v-model="outcomeForm.failure_reason" class="w-full" placeholder="e.g. Customer unreachable" />
          </UFormField>
          <UFormField v-if="outcomeForm.to_status === 'DELIVERED'" label="Proof reference" help="Photo/receipt reference from the rider">
            <UInput v-model="outcomeForm.proof_ref" class="w-full" />
          </UFormField>
          <UFormField label="Note"><UTextarea v-model="outcomeForm.note" :rows="2" class="w-full" /></UFormField>
          <UAlert v-if="outcomeForm.to_status === 'DELIVERED'" color="info" variant="subtle"
                  title="Delivered consumes reserved stock. COD still needs a separate collection record." />
        </div>
      </template>
      <template #footer>
        <div class="flex justify-end gap-2 w-full">
          <UButton variant="ghost" color="neutral" @click="showOutcome = false">Cancel</UButton>
          <UButton :loading="saving" @click="submitOutcome">Save outcome</UButton>
        </div>
      </template>
    </UModal>

    <!-- add rider/carrier/zone modals -->
    <UModal v-model:open="showRider" title="Add rider">
      <template #body>
        <div class="space-y-3">
          <UFormField label="Full name"><UInput v-model="riderForm.full_name" class="w-full" /></UFormField>
          <UFormField label="Phone"><UInput v-model="riderForm.phone" class="w-full" /></UFormField>
          <UFormField label="Vehicle"><UInput v-model="riderForm.vehicle" class="w-full" /></UFormField>
        </div>
      </template>
      <template #footer><div class="w-full flex justify-end"><UButton @click="createRider">Save</UButton></div></template>
    </UModal>
    <UModal v-model:open="showCarrier" title="Add carrier">
      <template #body>
        <div class="space-y-3">
          <UFormField label="Name"><UInput v-model="carrierForm.name" class="w-full" /></UFormField>
          <UFormField label="Kind"><USelect v-model="carrierForm.kind" class="w-full" :items="[{ label: 'Interstate', value: 'INTERSTATE' }, { label: 'Local third-party', value: 'LOCAL_3P' }]" /></UFormField>
          <UFormField label="Contact phone"><UInput v-model="carrierForm.contact_phone" class="w-full" /></UFormField>
        </div>
      </template>
      <template #footer><div class="w-full flex justify-end"><UButton @click="createCarrier">Save</UButton></div></template>
    </UModal>
    <UModal v-model:open="showZone" title="Add delivery zone">
      <template #body>
        <div class="space-y-3">
          <UFormField label="Zone name"><UInput v-model="zoneForm.name" class="w-full" /></UFormField>
          <UFormField label="State"><UInput v-model="zoneForm.state" class="w-full" /></UFormField>
          <UFormField label="Base fee (₦)"><UInput v-model="zoneForm.base_fee_naira" class="w-full" /></UFormField>
        </div>
      </template>
      <template #footer><div class="w-full flex justify-end"><UButton @click="createZone">Save</UButton></div></template>
    </UModal>
  </div>
</template>
