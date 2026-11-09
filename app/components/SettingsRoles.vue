<script setup lang="ts">
const { needs } = useGuard()
const emit = defineEmits<{ (e: 'changed'): void }>()
const data = ref<any>(null)
const loading = ref(true)
const saving = ref(false)
const showEdit = ref(false)
const editing = ref<any>(null)
const form = reactive({ name: '', description: '', permissions: [] as string[] })
const PROTECTED = ['Business Owner', 'Administrator', 'Vendor']

const GROUPS: Record<string, string> = {
  dashboard: 'Dashboard', vendors: 'Vendors', catalog: 'Products', inventory: 'Stock', orders: 'Orders',
  confirmations: 'Customer confirmations', conversations: 'WhatsApp inbox', whatsapp: 'WhatsApp settings',
  dispatch: 'Dispatch and delivery', cod: 'Cash on delivery', charges: 'Pricing rules', settlements: 'Vendor settlements',
  finance: 'Finance', reports: 'Reports', settings: 'Settings and staff', audit: 'Activity log',
}
const LABELS: Record<string, string> = {
  'dashboard.view': 'See the dashboard',
  'vendors.view': 'See vendors', 'vendors.manage': 'Add and edit vendors',
  'catalog.view': 'See products', 'catalog.manage': 'Add and edit products',
  'inventory.view': 'See stock', 'inventory.manage': 'Receive, move and count stock',
  'orders.view': 'See orders', 'orders.manage': 'Create and update orders',
  'confirmations.manage': 'Confirm orders with customers',
  'conversations.view': 'Read WhatsApp messages', 'conversations.manage': 'Reply and assign chats',
  'whatsapp.manage': 'Change WhatsApp connection',
  'dispatch.view': 'See deliveries', 'dispatch.manage': 'Assign riders and update deliveries',
  'cod.manage': 'Check and record cash collected',
  'charges.manage': 'Change pricing rules',
  'settlements.manage': 'Prepare vendor settlements', 'settlements.approve': 'Approve vendor payments',
  'finance.manage': 'See and post finance entries',
  'reports.view': 'See reports',
  'settings.manage': 'Change settings and manage staff',
  'audit.view': 'See the activity log',
}

const groups = computed(() => {
  const out: Record<string, any[]> = {}
  for (const p of data.value?.permission_catalog || []) (out[p.module] ||= []).push(p)
  const order = Object.keys(GROUPS)
  return Object.entries(out).sort((a, b) => (order.indexOf(a[0]) + 100) % 100 - (order.indexOf(b[0]) + 100) % 100).map(([m, list]) => ({ module: m, title: GROUPS[m] || m, list }))
})

async function load() {
  loading.value = true
  try { data.value = await api('/roles') } finally { loading.value = false }
}
onMounted(load)

function openNew(copy?: any) {
  editing.value = null
  form.name = ''
  form.description = ''
  form.permissions = copy ? [...(data.value.role_permissions[String(copy.id)] || [])] : []
  showEdit.value = true
}
function openEdit(r: any) {
  editing.value = r
  form.name = r.name
  form.description = r.description || ''
  form.permissions = [...(data.value.role_permissions[String(r.id)] || [])]
  showEdit.value = true
}
function toggle(code: string, on: boolean) {
  const s = new Set(form.permissions)
  on ? s.add(code) : s.delete(code)
  form.permissions = [...s]
}
function toggleGroup(list: any[], on: boolean) {
  const s = new Set(form.permissions)
  list.forEach((p) => (on ? s.add(p.codename) : s.delete(p.codename)))
  form.permissions = [...s]
}
const allOn = (list: any[]) => list.every((p) => form.permissions.includes(p.codename))

async function save() {
  saving.value = true
  try {
    const body = { name: form.name, description: form.description, permissions: form.permissions }
    if (editing.value) await api(`/roles/${editing.value.id}`, { method: 'PATCH', body })
    else await api('/roles', { method: 'POST', body })
    useToast().add({ title: editing.value ? 'Role updated' : 'Role created', color: 'success' })
    showEdit.value = false
    await load()
    emit('changed')
  } catch (e: any) {
    useToast().add({ title: 'Could not save', description: errMsg(e), color: 'error' })
  } finally { saving.value = false }
}

const delTarget = ref<any>(null)
async function remove() {
  try {
    await api(`/roles/${delTarget.value.id}`, { method: 'DELETE' })
    useToast().add({ title: 'Role deleted', color: 'success' })
    delTarget.value = null
    await load()
    emit('changed')
  } catch (e: any) {
    useToast().add({ title: 'Could not delete', description: errMsg(e), color: 'error' })
    delTarget.value = null
  }
}
const permsOf = (r: any) => data.value?.role_permissions[String(r.id)] || []
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-3 gap-2 flex-wrap">
      <p class="text-sm text-zinc-500 dark:text-zinc-400">Each person only sees the pages and information their role allows.</p>
      <UButton icon="i-lucide-plus" @click="openNew()">New role</UButton>
    </div>

    <div v-if="loading" class="py-10 text-center text-zinc-400"><UIcon name="i-lucide-loader-circle" class="animate-spin" /></div>
    <div v-else class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
      <div v-for="r in data.roles" :key="r.id" class="bg-white dark:bg-zinc-900 rounded-xl border border-zinc-200 dark:border-zinc-800 p-4 flex flex-col">
        <div class="flex items-center gap-2 mb-1">
          <p class="font-semibold text-zinc-800 dark:text-zinc-200">{{ r.name }}</p>
          <UBadge v-if="PROTECTED.includes(r.name)" color="neutral" variant="subtle" size="xs">Fixed</UBadge>
        </div>
        <p class="text-xs text-zinc-500 dark:text-zinc-400 mb-2">{{ PROTECTED.includes(r.name) && r.name !== 'Vendor' ? 'Full access to everything' : (permsOf(r).length + ' things they can do') }}</p>
        <div class="flex flex-wrap gap-1 mb-3 flex-1">
          <template v-if="!(PROTECTED.includes(r.name) && r.name !== 'Vendor')">
            <UBadge v-for="p in permsOf(r).slice(0, 6)" :key="p" color="primary" variant="soft" size="xs">{{ LABELS[p] || p }}</UBadge>
            <UBadge v-if="permsOf(r).length > 6" color="neutral" variant="subtle" size="xs">+{{ permsOf(r).length - 6 }} more</UBadge>
          </template>
        </div>
        <div class="flex gap-2">
          <UButton v-if="!PROTECTED.includes(r.name)" size="xs" variant="soft" icon="i-lucide-pencil" @click="openEdit(r)">Edit</UButton>
          <UButton size="xs" variant="ghost" color="neutral" icon="i-lucide-copy" @click="openNew(r)">Copy</UButton>
          <UButton v-if="!PROTECTED.includes(r.name)" size="xs" variant="ghost" color="error" icon="i-lucide-trash-2" @click="delTarget = r">Delete</UButton>
        </div>
      </div>
    </div>

    <UModal v-model:open="showEdit" :title="editing ? `Edit ${editing.name}` : 'New role'" :ui="{ content: 'max-w-3xl' }">
      <template #body>
        <div class="space-y-4">
          <div class="grid sm:grid-cols-2 gap-3">
            <UFormField label="Role name"><UInput v-model="form.name" class="w-full" maxlength="80" placeholder="e.g. Packing supervisor" /></UFormField>
            <UFormField label="What this role is for"><UInput v-model="form.description" class="w-full" maxlength="255" /></UFormField>
          </div>
          <div class="grid sm:grid-cols-2 gap-3 max-h-[50vh] overflow-y-auto thin-scroll pr-1">
            <div v-for="g in groups" :key="g.module" class="rounded-lg border border-zinc-200 dark:border-zinc-800 p-3">
              <div class="flex items-center justify-between mb-2">
                <p class="text-sm font-semibold text-zinc-800 dark:text-zinc-200">{{ g.title }}</p>
                <button type="button" class="text-xs text-primary-600" @click="toggleGroup(g.list, !allOn(g.list))">{{ allOn(g.list) ? 'Clear' : 'Select all' }}</button>
              </div>
              <div class="space-y-1.5">
                <UCheckbox v-for="p in g.list" :key="p.codename" :model-value="form.permissions.includes(p.codename)"
                           :label="LABELS[p.codename] || p.codename" @update:model-value="(v: any) => toggle(p.codename, !!v)" />
              </div>
            </div>
          </div>
        </div>
      </template>
      <template #footer>
        <div class="flex justify-end gap-2 w-full">
          <UButton color="neutral" variant="ghost" @click="showEdit = false">Cancel</UButton>
          <UButton :loading="saving" @click="needs([['Role name', form.name]]) && save()">{{ editing ? 'Save changes' : 'Create role' }}</UButton>
        </div>
      </template>
    </UModal>

    <UModal :open="!!delTarget" title="Delete this role?" @update:open="(v: boolean) => { if (!v) delTarget = null }">
      <template #body>
        <p class="text-sm text-zinc-600 dark:text-zinc-300">"{{ delTarget?.name }}" will be removed. Staff must be moved to another role first.</p>
      </template>
      <template #footer>
        <div class="flex justify-end gap-2 w-full">
          <UButton color="neutral" variant="ghost" @click="delTarget = null">Keep it</UButton>
          <UButton color="error" @click="remove">Delete role</UButton>
        </div>
      </template>
    </UModal>
  </div>
</template>
