<script setup lang="ts">
const vendors = ref<any[]>([])
const loading = ref(true)
const q = ref('')
const saving = ref(false)

async function load() {
  loading.value = true
  try { vendors.value = await api(`/vendors?q=${q.value}`) } finally { loading.value = false }
}
onMounted(load)

const showNew = ref(false)
const form = reactive({ name: '', business_name: '', email: '', phone: '', city: '', state: '' })

async function create() {
  saving.value = true
  try {
    await api('/vendors', { method: 'POST', body: { ...form } })
    useToast().add({ title: 'Vendor registered', color: 'success' })
    showNew.value = false
    await load()
  } catch (e) {
    useToast().add({ title: 'Failed', description: errMsg(e), color: 'error' })
  } finally { saving.value = false }
}

const selected = ref<any>(null)
const detail = ref<any>(null)
const showDetail = ref(false)

async function open(v: any) {
  selected.value = v
  detail.value = await api(`/vendors/${v.id}`)
  showDetail.value = true
}

const contactForm = reactive({ name: '', phone: '' })
async function addContact() {
  if (!contactForm.name || !contactForm.phone) return
  try {
    await api(`/vendors/${detail.value.id}/contacts`, { method: 'POST', body: { name: contactForm.name, phone: contactForm.phone } })
    contactForm.name = ''; contactForm.phone = ''
    useToast().add({ title: 'Contact added - WhatsApp number registered', color: 'success' })
    detail.value = await api(`/vendors/${detail.value.id}`)
    await load()
  } catch (e) {
    useToast().add({ title: 'Failed', description: errMsg(e), color: 'error' })
  }
}

async function toggleStatus(v: any) {
  const next = v.status === 'ACTIVE' ? 'SUSPENDED' : 'ACTIVE'
  await api(`/vendors/${v.id}`, { method: 'PATCH', body: { status: next } })
  await load()
  if (detail.value) detail.value = await api(`/vendors/${v.id}`)
}
</script>

<template>
  <div>
    <PageHeader title="Vendors" subtitle="Ecommerce businesses storing products and fulfilling orders through your warehouses.">
      <template #actions>
        <UButton icon="i-lucide-plus" @click="showNew = true">Register vendor</UButton>
      </template>
    </PageHeader>

    <div class="mb-3">
      <UInput v-model="q" icon="i-lucide-search" placeholder="Search vendors…" @keydown.enter="load" />
    </div>

    <DataTable :columns="[
      { key: 'name', label: 'Vendor' },
      { key: 'contact', label: 'Primary WhatsApp' },
      { key: 'product_count', label: 'Products', align: 'right' },
      { key: 'order_count', label: 'Orders', align: 'right' },
      { key: 'payable', label: 'Est. payable', align: 'right' },
      { key: 'status', label: 'Status' },
    ]" :rows="vendors" :loading="loading" clickable empty-title="No vendors" @row-click="open">
      <template #name="{ row }">
        <p class="font-semibold text-zinc-800 dark:text-zinc-200">{{ row.name }}</p>
        <p class="text-[11px] text-zinc-400 font-mono">{{ row.code }} · {{ row.city }}</p>
      </template>
      <template #contact="{ row }">
        <div class="flex items-center gap-1.5" v-if="row.primary_contact">
          <UIcon name="i-lucide-message-circle" class="w-3.5 h-3.5 text-emerald-500" />
          <span class="font-mono text-xs">{{ row.primary_contact.phone }}</span>
        </div>
        <span v-else class="text-zinc-400 text-xs">No WhatsApp number</span>
      </template>
      <template #status="{ row }">
        <div class="flex items-center gap-1.5">
          <StatusBadge :status="row.status" />
          <UButton size="xs" variant="ghost" color="neutral" :icon="row.status === 'ACTIVE' ? 'i-lucide-pause' : 'i-lucide-play'"
                   :aria-label="row.status === 'ACTIVE' ? 'Suspend' : 'Activate'" @click.stop="toggleStatus(row)" />
        </div>
      </template>
    </DataTable>

    <!-- new vendor -->
    <UModal v-model:open="showNew" title="Register vendor">
      <template #body>
        <div class="grid sm:grid-cols-2 gap-3">
          <UFormField label="Business name"><UInput v-model="form.name" class="w-full" /></UFormField>
          <UFormField label="Contact person"><UInput v-model="form.business_name" class="w-full" placeholder="optional" /></UFormField>
          <UFormField label="Email"><UInput v-model="form.email" type="email" class="w-full" /></UFormField>
          <UFormField label="Phone"><UInput v-model="form.phone" class="w-full" /></UFormField>
          <UFormField label="City"><UInput v-model="form.city" class="w-full" /></UFormField>
          <UFormField label="State"><UInput v-model="form.state" class="w-full" /></UFormField>
        </div>
      </template>
      <template #footer>
        <div class="flex justify-end gap-2 w-full">
          <UButton variant="ghost" color="neutral" @click="showNew = false">Cancel</UButton>
          <UButton :loading="saving" :disabled="!form.name" @click="create">Register</UButton>
        </div>
      </template>
    </UModal>

    <!-- detail -->
    <UModal v-model:open="showDetail" :ui="{ content: 'max-w-2xl' }" :title="selected?.name || ''">
      <template #body>
        <div v-if="detail" class="space-y-5">
          <div class="flex flex-wrap items-center gap-2">
            <StatusBadge :status="detail.status" />
            <UBadge color="neutral" variant="subtle" size="xs">{{ detail.code }}</UBadge>
            <UBadge color="neutral" variant="outline" size="xs">Settlements: {{ titleize(detail.settlement_frequency) }}</UBadge>
            <UBadge v-if="detail.auto_confirm_orders" color="warning" variant="subtle" size="xs">Auto-confirm ON</UBadge>
          </div>

          <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <StatCard label="Verified collections" :value="fmtNaira(detail.financial_summary?.verified_collections_kobo)" icon="i-lucide-banknote" />
            <StatCard label="Charges" :value="fmtNaira(detail.financial_summary?.charges_kobo)" icon="i-lucide-scissors" tone="warning" />
            <StatCard label="Outstanding payable" :value="fmtNaira(detail.financial_summary?.outstanding_payable_kobo)" icon="i-lucide-wallet" tone="primary" />
            <StatCard label="Settled" :value="fmtNaira(detail.financial_summary?.settled_kobo)" icon="i-lucide-check" tone="success" />
          </div>

          <div>
            <p class="font-semibold text-sm text-zinc-700 dark:text-zinc-200 mb-2">Authorized contacts & WhatsApp numbers</p>
            <div class="space-y-2">
              <div v-for="c in detail.contacts" :key="c.id" class="flex items-center gap-2 text-sm bg-zinc-50 dark:bg-zinc-800/60 rounded-lg px-3 py-2">
                <UIcon name="i-lucide-message-circle" class="w-4 h-4 text-emerald-500" />
                <span class="font-medium">{{ c.name }}</span>
                <span class="font-mono text-zinc-500">{{ c.phone }}</span>
                <UBadge v-if="c.wa_verified" color="success" variant="subtle" size="xs">verified · {{ titleize(c.verification_method) }}</UBadge>
                <UBadge v-if="c.is_primary" color="primary" variant="subtle" size="xs">primary</UBadge>
              </div>
            </div>
            <div class="flex gap-2 mt-2">
              <UInput v-model="contactForm.name" placeholder="Contact name" size="sm" class="w-44" />
              <UInput v-model="contactForm.phone" placeholder="08012345678" size="sm" class="w-44" />
              <UButton size="sm" variant="soft" @click="addContact">Add number</UButton>
            </div>
          </div>

          <div v-if="detail.agreements?.length">
            <p class="font-semibold text-sm text-zinc-700 dark:text-zinc-200 mb-2">Agreements</p>
            <div v-for="a in detail.agreements" :key="a.id" class="text-sm border border-zinc-200 dark:border-zinc-800 rounded-lg p-3">
              <p class="font-medium">{{ a.title }} <UBadge :color="a.status === 'ACTIVE' ? 'success' : 'neutral'" variant="subtle" size="xs" class="ml-1">{{ a.status }}</UBadge></p>
              <p class="text-zinc-500 text-xs mt-1">{{ a.terms }}</p>
            </div>
          </div>

          <div v-if="detail.order_stats?.length">
            <p class="font-semibold text-sm text-zinc-700 dark:text-zinc-200 mb-2">Order stats</p>
            <div class="flex flex-wrap gap-1.5">
              <UBadge v-for="s in detail.order_stats" :key="s.status" :color="statusColor(s.status) as any" variant="subtle" size="sm">
                {{ titleize(s.status) }}: {{ s.count }}
              </UBadge>
            </div>
          </div>
        </div>
      </template>
      <template #footer>
        <div class="flex justify-between w-full">
          <UButton variant="link" :to="`/vendors`" @click="showDetail = false">Close</UButton>
          <UButton variant="soft" icon="i-lucide-receipt-text" to="/settlements">Settlements</UButton>
        </div>
      </template>
    </UModal>
  </div>
</template>
