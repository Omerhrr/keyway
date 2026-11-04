<script setup lang="ts">
const route = useRoute()
const order = ref<any>(null)
const loading = ref(true)
const saving = ref(false)

async function load() {
  loading.value = true
  try { order.value = await api(`/orders/${route.params.id}`) } finally { loading.value = false }
}
onMounted(load)

const nexts = computed(() => order.value ? (ORDER_TRANSITIONS[order.value.status] || []) : [])
const showStatus = ref(false)
const toStatus = ref('')
const note = ref('')

async function changeStatus() {
  saving.value = true
  try {
    await api(`/orders/${order.value.id}/status`, { method: 'POST', body: { to_status: toStatus.value, note: note.value } })
    useToast().add({ title: `Order moved to ${titleize(toStatus.value)}`, color: 'success' })
    showStatus.value = false
    note.value = ''
    await load()
  } catch (e) {
    useToast().add({ title: 'Not allowed', description: errMsg(e), color: 'error' })
  } finally { saving.value = false }
}

function askStatus(s: string) {
  toStatus.value = s
  note.value = ''
  showStatus.value = true
}

const riders = ref<any[]>([])
const zones = ref<any[]>([])
const showDispatch = ref(false)
const dispatchForm = reactive({ mode: 'IN_HOUSE_RIDER', rider_id: 0, zone_id: 0, fee_naira: '' })

async function openDispatch() {
  showDispatch.value = true
  try {
    riders.value = await api('/dispatch/riders')
    zones.value = await api('/dispatch/zones')
  } catch {}
}

async function dispatchOrder() {
  saving.value = true
  try {
    await api('/dispatch/deliveries', {
      method: 'POST',
      body: {
        order_id: order.value.id, mode: dispatchForm.mode,
        rider_id: dispatchForm.mode === 'IN_HOUSE_RIDER' ? dispatchForm.rider_id || null : null,
        zone_id: dispatchForm.zone_id || null,
        fee_kobo: dispatchForm.fee_naira ? toKobo(dispatchForm.fee_naira) : 0,
      },
    })
    useToast().add({ title: 'Order dispatched', description: 'Delivery charge applied through the charge engine.', color: 'success' })
    showDispatch.value = false
    await load()
  } catch (e) {
    useToast().add({ title: 'Dispatch failed', description: errMsg(e), color: 'error' })
  } finally { saving.value = false }
}

// record COD
const showCod = ref(false)
const codForm = reactive({ collected_naira: '', method: 'CASH' })

async function recordCod() {
  saving.value = true
  try {
    await api('/cod/collections', {
      method: 'POST',
      body: { order_id: order.value.id, collected_kobo: toKobo(codForm.collected_naira), method: codForm.method },
    })
    useToast().add({ title: 'COD recorded', description: 'Awaiting finance verification before it becomes vendor funds.', color: 'success' })
    showCod.value = false
    await load()
  } catch (e) {
    useToast().add({ title: 'Failed', description: errMsg(e), color: 'error' })
  } finally { saving.value = false }
}

const confirmationOutcomes = ['CALL_ATTEMPTED', 'NO_ANSWER', 'CUSTOMER_CONFIRMED', 'CUSTOMER_REQUESTED_RESCHEDULE', 'ADDRESS_NEEDS_CORRECTION', 'CUSTOMER_REJECTED', 'INVALID_PHONE_NUMBER']
const showConfirm = ref(false)
const confirmForm = reactive({ outcome: 'CALL_ATTEMPTED', note: '' })

async function recordAttempt() {
  saving.value = true
  try {
    await api(`/confirmations/${order.value.id}/attempt`, { method: 'POST', body: { ...confirmForm } })
    useToast().add({ title: 'Confirmation attempt recorded', color: 'success' })
    showConfirm.value = false
    await load()
  } catch (e) {
    useToast().add({ title: 'Failed', description: errMsg(e), color: 'error' })
  } finally { saving.value = false }
}
</script>

<template>
  <div>
    <div v-if="loading" class="py-20 text-center text-zinc-400"><UIcon name="i-lucide-loader-circle" class="animate-spin w-6 h-6" /></div>
    <template v-else-if="order">
      <div class="flex items-center gap-2 mb-1">
        <UButton to="/orders" icon="i-lucide-arrow-left" variant="ghost" color="neutral" size="xs" aria-label="Back to orders" />
        <h1 class="text-2xl font-bold font-mono text-zinc-900 dark:text-white">{{ order.reference }}</h1>
        <StatusBadge :status="order.status" />
      </div>
      <p class="text-sm text-zinc-500 mb-5">
        {{ order.vendor_name }} · created {{ fmtDateTime(order.created_at) }} · source {{ titleize(order.source) }}
      </p>

      <!-- Actions -->
      <div class="flex flex-wrap gap-2 mb-6">
        <UButton v-if="nexts.length" icon="i-lucide-git-branch" variant="outline" @click="showStatus = true">Change status</UButton>
        <UButton v-if="['CONFIRMED', 'PENDING_CUSTOMER_CONFIRMATION', 'CUSTOMER_CONFIRMED'].includes(order.status)" icon="i-lucide-phone-call" color="info" variant="soft" @click="showConfirm = true">Record confirmation</UButton>
        <UButton v-if="order.status === 'READY_FOR_DISPATCH'" icon="i-lucide-truck" @click="openDispatch">Dispatch</UButton>
        <UButton v-if="order.status === 'DELIVERED' && order.payment_method === 'COD'" icon="i-lucide-banknote" color="warning" variant="soft" @click="showCod = true">Record COD</UButton>
        <UButton v-for="n in nexts.filter(s => s === 'CANCELLED')" :key="n" icon="i-lucide-ban" color="error" variant="soft" @click="askStatus(n)">Cancel order</UButton>
      </div>

      <div class="grid lg:grid-cols-3 gap-5">
        <!-- left column -->
        <div class="lg:col-span-2 space-y-5">
          <!-- items -->
          <div class="bg-white dark:bg-zinc-900 rounded-xl border border-zinc-200 dark:border-zinc-800 overflow-hidden">
            <p class="px-4 pt-4 font-semibold text-sm text-zinc-700 dark:text-zinc-200">Items</p>
            <table class="w-full text-sm mt-2">
              <thead><tr class="text-[11px] uppercase text-zinc-400"><th class="px-4 py-2 text-left">Product</th><th class="px-4 py-2 text-right">Qty</th><th class="px-4 py-2 text-right">Unit</th><th class="px-4 py-2 text-right pr-4">Total</th></tr></thead>
              <tbody>
                <tr v-for="it in order.items" :key="it.id" class="border-t border-zinc-100 dark:border-zinc-800">
                  <td class="px-4 py-2.5">
                    <p class="font-medium text-zinc-800 dark:text-zinc-200">{{ it.name_snapshot }}</p>
                    <p class="text-[11px] text-zinc-400 font-mono">{{ it.sku_snapshot }} · price {{ titleize(it.price_source) }}</p>
                  </td>
                  <td class="px-4 py-2.5 text-right">{{ it.qty }}</td>
                  <td class="px-4 py-2.5 text-right">{{ fmtNaira(it.unit_price_kobo) }}</td>
                  <td class="px-4 py-2.5 text-right pr-4 font-semibold">{{ fmtNaira(it.line_total_kobo) }}</td>
                </tr>
              </tbody>
              <tfoot>
                <tr class="border-t border-zinc-200 dark:border-zinc-700 font-semibold">
                  <td colspan="3" class="px-4 py-2 text-right text-zinc-500">Items total</td>
                  <td class="px-4 py-2 text-right pr-4">{{ fmtNaira(order.items_total_kobo) }}</td>
                </tr>
                <tr v-if="order.delivery_fee_kobo" class="text-zinc-500">
                  <td colspan="3" class="px-4 py-1 text-right">Delivery fee</td>
                  <td class="px-4 py-1 text-right pr-4">{{ fmtNaira(order.delivery_fee_kobo) }}</td>
                </tr>
                <tr class="text-primary-700 dark:text-primary-400">
                  <td colspan="3" class="px-4 py-2 text-right font-semibold">COD to collect</td>
                  <td class="px-4 py-2 text-right pr-4 font-bold">{{ fmtNaira(order.cod_amount_kobo) }}</td>
                </tr>
              </tfoot>
            </table>
          </div>

          <!-- timeline -->
          <div class="bg-white dark:bg-zinc-900 rounded-xl border border-zinc-200 dark:border-zinc-800 p-4">
            <p class="font-semibold text-sm text-zinc-700 dark:text-zinc-200 mb-3">Activity timeline</p>
            <div class="space-y-0">
              <div v-for="(ev, i) in [...order.events].reverse()" :key="ev.id" class="flex gap-3">
                <div class="flex flex-col items-center">
                  <div class="w-2.5 h-2.5 rounded-full bg-primary-500 mt-1.5" />
                  <div v-if="i < order.events.length - 1" class="w-px flex-1 bg-zinc-200 dark:bg-zinc-700" />
                </div>
                <div class="pb-4">
                  <p class="text-sm text-zinc-700 dark:text-zinc-300">
                    <template v-if="ev.to_status"><StatusBadge :status="ev.to_status" /></template>
                    <template v-else><UBadge color="neutral" variant="subtle" size="sm">{{ titleize(ev.event_type) }}</UBadge></template>
                    <span v-if="ev.note" class="ml-2 text-zinc-500">{{ ev.note }}</span>
                  </p>
                  <p class="text-[11px] text-zinc-400">{{ ev.actor_label }} · {{ fmtDateTime(ev.created_at) }}</p>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- right column -->
        <div class="space-y-5">
          <div class="bg-white dark:bg-zinc-900 rounded-xl border border-zinc-200 dark:border-zinc-800 p-4">
            <p class="font-semibold text-sm mb-2 text-zinc-700 dark:text-zinc-200">Customer & destination</p>
            <p class="text-sm font-medium text-zinc-800 dark:text-zinc-200">{{ order.customer?.name }}</p>
            <p class="text-sm text-zinc-500 font-mono">{{ order.customer?.phone }}</p>
            <p class="text-sm text-zinc-500 mt-2">
              {{ [order.delivery_street, order.delivery_area, order.delivery_city, order.delivery_state].filter(Boolean).join(', ') || 'No address on file' }}
            </p>
            <p v-if="order.instructions" class="text-xs text-zinc-400 mt-2 italic">"{{ order.instructions }}"</p>
            <USeparator class="my-3" />
            <p class="text-[10px] uppercase tracking-wide text-zinc-400 mb-0.5">Fulfilment warehouse</p>
            <p class="text-sm font-medium text-zinc-700 dark:text-zinc-300 flex items-center gap-1.5">
              <UIcon name="i-lucide-warehouse" class="w-4 h-4 text-primary-500" />
              {{ order.warehouse_name || 'Not assigned' }}
            </p>
          </div>

          <div v-if="order.original_message" class="bg-white dark:bg-zinc-900 rounded-xl border border-zinc-200 dark:border-zinc-800 p-4">
            <p class="text-[10px] uppercase tracking-wide text-zinc-400 mb-1">Source message</p>
            <p class="text-sm text-zinc-600 dark:text-zinc-300 italic">"{{ order.original_message.body_text }}"</p>
            <p class="text-[11px] text-zinc-400 mt-1">{{ fmtDateTime(order.original_message.created_at) }}</p>
          </div>

          <div class="bg-white dark:bg-zinc-900 rounded-xl border border-zinc-200 dark:border-zinc-800 p-4">
            <p class="font-semibold text-sm mb-2 text-zinc-700 dark:text-zinc-200">Customer confirmation</p>
            <template v-if="order.confirmation">
              <StatusBadge :status="order.confirmation.status" />
              <p class="text-xs text-zinc-400 mt-1.5">{{ order.confirmation.attempts_count }} attempt(s) · {{ order.confirmation.outcome_note || 'no notes' }}</p>
            </template>
            <p v-else class="text-sm text-zinc-400">Not started</p>
          </div>

          <div v-if="order.deliveries?.length" class="bg-white dark:bg-zinc-900 rounded-xl border border-zinc-200 dark:border-zinc-800 p-4">
            <p class="font-semibold text-sm mb-2 text-zinc-700 dark:text-zinc-200">Deliveries</p>
            <div v-for="d in order.deliveries" :key="d.id" class="text-sm py-1 flex justify-between gap-2">
              <span class="text-zinc-500">{{ titleize(d.mode) }} · attempt {{ d.attempt_no }}</span>
              <StatusBadge :status="d.status" />
            </div>
          </div>

          <div class="bg-white dark:bg-zinc-900 rounded-xl border border-zinc-200 dark:border-zinc-800 p-4">
            <p class="font-semibold text-sm mb-2 text-zinc-700 dark:text-zinc-200">COD collections</p>
            <div v-if="order.collections?.length">
              <div v-for="c in order.collections" :key="c.id" class="text-sm py-1.5 border-b last:border-0 border-zinc-100 dark:border-zinc-800">
                <div class="flex justify-between">
                  <span class="text-zinc-500">Collected {{ fmtNaira(c.collected_kobo) }}</span>
                  <StatusBadge :status="c.status" />
                </div>
                <p class="text-[11px] text-zinc-400">expected {{ fmtNaira(c.expected_kobo) }} · {{ titleize(c.method) }} · {{ fmtDateTime(c.collected_at) }}</p>
              </div>
            </div>
            <p v-else class="text-sm text-zinc-400">No collection recorded yet</p>
          </div>

          <div v-if="order.charges?.length" class="bg-white dark:bg-zinc-900 rounded-xl border border-zinc-200 dark:border-zinc-800 p-4">
            <p class="font-semibold text-sm mb-2 text-zinc-700 dark:text-zinc-200">Charges</p>
            <div v-for="c in order.charges" :key="c.id" class="flex justify-between text-sm py-1">
              <span class="text-zinc-500">{{ titleize(c.charge_type) }} <span class="text-[10px]">(v{{ c.rule_version ?? '-' }})</span></span>
              <span class="font-medium">{{ fmtNaira(c.amount_kobo) }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- status modal -->
      <UModal v-model:open="showStatus" title="Change order status">
        <template #body>
          <div class="space-y-3">
            <UAlert v-if="toStatus === 'CANCELLED'" color="error" variant="subtle" title="Cancellation requires a reason and releases reserved stock." />
            <UAlert v-else-if="toStatus === 'DELIVERED'" color="warning" variant="subtle" title="Marking delivered consumes reserved stock. Delivery should normally be confirmed from Dispatch." />
            <USelect v-model="toStatus" :items="nexts.map(s => ({ label: titleize(s), value: s }))" class="w-full" />
            <UFormField label="Note / reason"><UTextarea v-model="note" class="w-full" :rows="2" /></UFormField>
          </div>
        </template>
        <template #footer>
          <div class="flex justify-end gap-2 w-full">
            <UButton variant="ghost" color="neutral" @click="showStatus = false">Close</UButton>
            <UButton :loading="saving" @click="changeStatus">Move order</UButton>
          </div>
        </template>
      </UModal>

      <!-- dispatch modal -->
      <UModal v-model:open="showDispatch" title="Dispatch order">
        <template #body>
          <div class="grid sm:grid-cols-2 gap-3">
            <UFormField label="Delivery mode">
              <USelect v-model="dispatchForm.mode" class="w-full" :items="[
                { label: 'In-house rider', value: 'IN_HOUSE_RIDER' },
                { label: 'Local third-party', value: 'LOCAL_3P' },
                { label: 'Interstate transport', value: 'INTERSTATE' },
                { label: 'Waybill dispatch', value: 'WAYBILL' },
              ]" />
            </UFormField>
            <UFormField v-if="dispatchForm.mode === 'IN_HOUSE_RIDER'" label="Rider">
              <USelect v-model="dispatchForm.rider_id" class="w-full" :items="riders.map(r => ({ label: `${r.full_name} · ${r.zone_name || ''}`, value: r.id }))" />
            </UFormField>
            <UFormField label="Delivery zone">
              <USelect v-model="dispatchForm.zone_id" class="w-full" :items="[{ label: 'No zone (manual fee)', value: 0 }, ...zones.map(z => ({ label: `${z.name} · ${fmtNaira(z.base_fee_kobo)}`, value: z.id }))]" />
            </UFormField>
            <UFormField label="Fee override (₦)" hint="Empty = zone base fee or matched pricing rule">
              <UInput v-model="dispatchForm.fee_naira" class="w-full" />
            </UFormField>
          </div>
        </template>
        <template #footer>
          <div class="flex justify-end gap-2 w-full">
            <UButton variant="ghost" color="neutral" @click="showDispatch = false">Cancel</UButton>
            <UButton :loading="saving" icon="i-lucide-truck" @click="dispatchOrder">Dispatch</UButton>
          </div>
        </template>
      </UModal>

      <!-- COD modal -->
      <UModal v-model:open="showCod" title="Record COD collection">
        <template #body>
          <div class="space-y-3">
            <UAlert color="info" variant="subtle" title="Expected COD" :description="fmtNaira(order.cod_amount_kobo) + ' - actual amount is stored separately and verified by finance.'" />
            <UFormField label="Amount collected (₦)"><UInput v-model="codForm.collected_naira" class="w-full" /></UFormField>
            <UFormField label="Method">
              <USelect v-model="codForm.method" class="w-full" :items="[
                { label: 'Cash', value: 'CASH' }, { label: 'Bank transfer', value: 'BANK_TRANSFER' }, { label: 'Digital payment', value: 'DIGITAL' },
              ]" />
            </UFormField>
          </div>
        </template>
        <template #footer>
          <div class="flex justify-end gap-2 w-full">
            <UButton variant="ghost" color="neutral" @click="showCod = false">Cancel</UButton>
            <UButton :loading="saving" @click="recordCod">Record</UButton>
          </div>
        </template>
      </UModal>

      <!-- confirmation modal -->
      <UModal v-model:open="showConfirm" title="Record customer confirmation">
        <template #body>
          <div class="space-y-3">
            <UFormField label="Outcome">
              <USelect v-model="confirmForm.outcome" class="w-full" :items="confirmationOutcomes.map(o => ({ label: titleize(o), value: o }))" />
            </UFormField>
            <UFormField label="Call note"><UTextarea v-model="confirmForm.note" class="w-full" :rows="2" /></UFormField>
            <UAlert v-if="confirmForm.outcome === 'CUSTOMER_REJECTED'" color="error" variant="subtle" title="Customer rejection will cancel the order and release stock." />
          </div>
        </template>
        <template #footer>
          <div class="flex justify-end gap-2 w-full">
            <UButton variant="ghost" color="neutral" @click="showConfirm = false">Close</UButton>
            <UButton :loading="saving" @click="recordAttempt">Save attempt</UButton>
          </div>
        </template>
      </UModal>
    </template>
  </div>
</template>
