<script setup lang="ts">
const { needs } = useGuard()
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

</script>

<template>
  <div>
    <PageHeader title="Vendors" subtitle="The businesses whose products you store and deliver.">
      <template #actions>
        <UButton icon="i-lucide-plus" @click="showNew = true">Register vendor</UButton>
      </template>
    </PageHeader>

    <div class="mb-3">
      <UInput v-model="q" icon="i-lucide-search" placeholder="Search vendors…" @keydown.enter="load" />
    </div>

    <DataTable export-title="Vendors" :columns="[
      { key: 'name', label: 'Vendor' },
      { key: 'contact', label: 'Primary WhatsApp' },
      { key: 'product_count', label: 'Products', align: 'right' },
      { key: 'order_count', label: 'Orders', align: 'right' },
      { key: 'payable', label: 'Est. payable', align: 'right' },
      { key: 'status', label: 'Status' },
    ]" :rows="vendors" :loading="loading" clickable empty-title="No vendors" @row-click="(r: any) => navigateTo(`/vendor/${r.id}`)">
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
      <template #status="{ row }"><StatusBadge :status="row.status" /></template>
    </DataTable>

    <!-- new vendor -->
    <UModal v-model:open="showNew" title="Register vendor">
      <template #body>
        <div class="grid sm:grid-cols-2 gap-3">
          <UFormField label="Business name"><UInput v-model="form.name" class="w-full" /></UFormField>
          <UFormField label="Registered business name"><UInput v-model="form.business_name" class="w-full" placeholder="optional" /></UFormField>
          <UFormField label="Email"><UInput v-model="form.email" type="email" class="w-full" /></UFormField>
          <UFormField label="Phone"><UInput v-model="form.phone" class="w-full" /></UFormField>
          <UFormField label="City"><UInput v-model="form.city" class="w-full" /></UFormField>
          <UFormField label="State"><UInput v-model="form.state" class="w-full" /></UFormField>
        </div>
      </template>
      <template #footer>
        <div class="flex justify-end gap-2 w-full">
          <UButton variant="ghost" color="neutral" @click="showNew = false">Cancel</UButton>
          <UButton :loading="saving" @click="needs([['Business name', form.name]]) && create()">Register</UButton>
        </div>
      </template>
    </UModal>

  </div>
</template>
