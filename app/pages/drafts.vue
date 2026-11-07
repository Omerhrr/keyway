<script setup lang="ts">
const drafts = ref<any[]>([])
const loading = ref(true)
const filter = ref('PENDING_REVIEW')
const filters = [
  { label: 'Pending review', value: 'PENDING_REVIEW' },
  { label: 'Awaiting vendor', value: 'AWAITING_VENDOR' },
  { label: 'All active', value: '' },
]

async function load() {
  loading.value = true
  try {
    const params = filter.value ? `?status=${filter.value}` : ''
    drafts.value = await api(`/orders/drafts${params}`)
  } catch (e) {
    useToast().add({ title: 'Could not load drafts', description: errMsg(e), color: 'error', icon: 'i-lucide-circle-alert' })
  } finally { loading.value = false }
}
onMounted(load)

const selected = ref<any>(null)
const showReview = ref(false)
const saving = ref(false)

// editable fields
const form = reactive({
  customer_name: '', customer_phone: '', quantity: 1, unit_price_naira: '',
  state: '', city: '', street: '', product_id: 0,
})
const products = ref<any[]>([])

async function review(d: any) {
  selected.value = d
  const x = d.extracted || {}
  form.customer_name = x.customer_name || ''
  form.customer_phone = x.customer_phone || ''
  form.quantity = x.quantity || 1
  form.unit_price_naira = x.unit_price_kobo ? String(x.unit_price_kobo / 100) : ''
  form.state = x.state || ''
  form.city = x.city || ''
  form.street = x.street || ''
  form.product_id = (x.product || {}).product_id || 0
  showReview.value = true
  try {
    products.value = await api(`/catalog/products?vendor_id=${d.vendor_id}`)
  } catch { products.value = [] }
}

const candidateOptions = computed(() => (selected.value?.product_candidates || []).map((c: any) => ({
  label: `${c.matched_label || c.name} · ${Math.round(c.score)}% match`,
  value: c.product_id,
})))
const productOptions = computed(() => products.value.map(p => ({ label: `${p.name} (${p.sku})`, value: p.id })))

async function saveEdits() {
  saving.value = true
  try {
    const body: any = {
      customer_name: form.customer_name,
      customer_phone: form.customer_phone,
      quantity: Number(form.quantity) || 1,
      state: form.state, city: form.city, street: form.street,
      review_notes: 'Corrected by staff during review',
    }
    if (form.unit_price_naira) body.unit_price_kobo = toKobo(form.unit_price_naira)
    if (form.product_id) body.product_id = form.product_id
    await api(`/orders/drafts/${selected.value.id}`, { method: 'PATCH', body })
    useToast().add({ title: 'Draft updated', color: 'success' })
    await load()
    const fresh = drafts.value.find(d => d.id === selected.value.id)
    if (fresh) { selected.value = fresh; Object.assign(selected.value, {}) }
    // refresh selected detail
    selected.value = await api(`/orders/drafts/${selected.value.id}`)
  } catch (e) {
    useToast().add({ title: 'Update failed', description: errMsg(e), color: 'error' })
  } finally { saving.value = false }
}

async function confirmDraft() {
  saving.value = true
  try {
    await saveEditsSilent()
    const order = await api(`/orders/drafts/${selected.value.id}/confirm`, { method: 'POST' })
    useToast().add({ title: `Order ${order.reference} created`, description: 'Stock reserved and vendor notified.', color: 'success', icon: 'i-lucide-package-check' })
    showReview.value = false
    await load()
  } catch (e: any) {
    useToast().add({ title: 'Cannot confirm', description: errMsg(e), color: 'error' })
  } finally { saving.value = false }
}

async function saveEditsSilent() {
  const body: any = {
    customer_name: form.customer_name, customer_phone: form.customer_phone,
    quantity: Number(form.quantity) || 1, state: form.state, city: form.city, street: form.street,
  }
  if (form.unit_price_naira) body.unit_price_kobo = toKobo(form.unit_price_naira)
  if (form.product_id) body.product_id = form.product_id
  await api(`/orders/drafts/${selected.value.id}`, { method: 'PATCH', body })
}

async function discard() {
  try {
    await api(`/orders/drafts/${selected.value.id}/discard`, { method: 'POST' })
    showReview.value = false
    useToast().add({ title: 'Draft discarded' })
    await load()
  } catch (e) { useToast().add({ title: 'Failed', description: errMsg(e), color: 'error' }) }
}

const missingList = computed(() => selected.value?.missing_fields || [])
</script>

<template>
  <div>
    <PageHeader title="Order Drafts" subtitle="Orders picked up from WhatsApp messages. Check the details, match the products, then confirm to create each order.">
      <template #actions>
        <div class="overflow-x-auto thin-scroll max-w-full"><UTabs :content="false" class="min-w-max" :ui="{ list: 'w-max', trigger: 'shrink-0 whitespace-nowrap' }" :items="filters" :model-value="filter" size="xs" @update:model-value="(v: any) => { filter = typeof v === 'string' ? v : filter; load() }" /></div>
      </template>
    </PageHeader>

    <DataTable export-title="Draft orders" :columns="[
      { key: 'draft_ref', label: 'Draft' },
      { key: 'vendor_name', label: 'Vendor' },
      { key: 'message', label: 'Message' },
      { key: 'product_label', label: 'Product' },
      { key: 'customer', label: 'Customer' },
      { key: 'confidence', label: 'Confidence', align: 'right' },
      { key: 'status', label: 'Status' },
    ]" :rows="drafts.map(d => ({
      ...d,
      message: (d.extracted?.original_text || '').slice(0, 60) || '-',
      product_label: d.product_label || 'Unresolved',
      customer: d.customer_name ? `${d.customer_name}` : '-',
    }))" :loading="loading" clickable empty-title="No drafts in this view" empty-hint="Send a vendor message from the inbox practice box." @row-click="review">
      <template #confidence="{ row }">
        <div class="flex items-center gap-1.5 justify-end">
          <div class="w-14 h-1.5 rounded-full bg-zinc-100 dark:bg-zinc-800 overflow-hidden">
            <div class="h-full rounded-full" :class="row.confidence >= 0.75 ? 'bg-emerald-500' : row.confidence >= 0.45 ? 'bg-amber-500' : 'bg-red-400'"
                 :style="{ width: `${Math.round(row.confidence * 100)}%` }" />
          </div>
          <span class="text-xs text-zinc-500">{{ Math.round(row.confidence * 100) }}%</span>
        </div>
      </template>
      <template #status="{ row }">
        <div class="flex gap-1.5">
          <StatusBadge :status="row.status" />
          <UBadge v-if="row.duplicate_of_order_id" color="warning" variant="outline" size="xs">Dup?</UBadge>
        </div>
      </template>
    </DataTable>

    <!-- Review modal -->
    <UModal v-model:open="showReview" :ui="{ content: 'max-w-2xl' }" title="Review order draft">
      <template #body>
        <div v-if="selected" class="space-y-4">
          <div class="flex items-center gap-2 flex-wrap">
            <UBadge color="primary" variant="subtle">{{ selected.draft_ref }}</UBadge>
            <UBadge color="neutral" variant="subtle">{{ selected.vendor_name }}</UBadge>
            <UBadge color="neutral" variant="outline" size="xs">confidence {{ Math.round((selected.confidence || 0) * 100) }}%</UBadge>
            <UBadge v-if="selected.extracted?.extracted_by" color="info" variant="subtle" size="xs">parsed by {{ selected.extracted.extracted_by }}</UBadge>
          </div>

          <UAlert v-if="missingList.length" color="warning" variant="subtle" icon="i-lucide-triangle-alert"
                  title="Missing information" :description="`Still needed: ${missingList.map(titleize).join(', ')}`" />
          <UAlert v-if="selected.duplicate_of_order_id" color="warning" variant="subtle" icon="i-lucide-copy"
                  title="Possible duplicate" :description="`Similar order detected (order id ${selected.duplicate_of_order_id}). Confirm carefully.`" />

          <div v-if="selected.original_message" class="rounded-lg bg-zinc-50 dark:bg-zinc-800/60 p-3 text-sm text-zinc-600 dark:text-zinc-300 border border-zinc-200 dark:border-zinc-700">
            <p class="text-[10px] uppercase tracking-wide text-zinc-400 mb-1">Original WhatsApp message (immutable)</p>
            "{{ selected.original_message.body_text }}"
            <p class="text-[10px] text-zinc-400 mt-1">{{ fmtDateTime(selected.original_message.created_at) }}</p>
          </div>

          <div class="grid sm:grid-cols-2 gap-3">
            <UFormField label="Customer name"><UInput v-model="form.customer_name" class="w-full" /></UFormField>
            <UFormField label="Customer phone"><UInput v-model="form.customer_phone" class="w-full" /></UFormField>
            <UFormField label="Product">
              <USelect v-model="form.product_id" class="w-full" :items="[...(candidateOptions.length ? [{ label: 'From the message', value: 0 }] : []), ...candidateOptions, ...productOptions]" />
            </UFormField>
            <div class="grid grid-cols-2 gap-3">
              <UFormField label="Quantity"><UInput v-model="form.quantity" type="number" min="1" class="w-full" /></UFormField>
              <UFormField label="Price (₦)"><UInput v-model="form.unit_price_naira" class="w-full" placeholder="e.g. 45000" /></UFormField>
            </div>
            <UFormField label="State"><UInput v-model="form.state" class="w-full" /></UFormField>
            <UFormField label="City / Area"><UInput v-model="form.city" class="w-full" /></UFormField>
            <UFormField label="Street / Landmark" class="sm:col-span-2"><UInput v-model="form.street" class="w-full" /></UFormField>
          </div>
          <p class="text-[11px] text-zinc-400">Provenance: the original message is preserved and every correction is recorded on the draft.</p>
        </div>
      </template>
      <template #footer>
        <div class="flex justify-between w-full">
          <UButton color="error" variant="soft" icon="i-lucide-trash-2" :disabled="saving" @click="discard">Discard</UButton>
          <div class="flex gap-2">
            <UButton variant="ghost" color="neutral" :disabled="saving" @click="saveEdits">Save corrections</UButton>
            <UButton :loading="saving" icon="i-lucide-check" @click="confirmDraft">Confirm & create order</UButton>
          </div>
        </div>
      </template>
    </UModal>
  </div>
</template>
