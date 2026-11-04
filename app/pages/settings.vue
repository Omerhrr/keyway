<script setup lang="ts">
const tab = ref('users')
const tabs = [
  { label: 'Staff & access', value: 'users', icon: 'i-lucide-users' },
  { label: 'Roles', value: 'roles', icon: 'i-lucide-shield' },
  { label: 'Pricing rules', value: 'charges', icon: 'i-lucide-tags' },
  { label: 'WhatsApp', value: 'whatsapp', icon: 'i-lucide-message-circle' },
]

const users = ref<any[]>([])
const roles = ref<any>(null)
const rules = ref<any[]>([])
const account = ref<any>(null)
const templates = ref<any[]>([])
const vendorsList = ref<any[]>([])
const loading = ref(true)
const saving = ref(false)

async function load() {
  loading.value = true
  try {
    const [u, r, c, a, t, v] = await Promise.all([
      api('/users'), api('/roles'), api('/charges/rules'), api('/whatsapp/account'), api('/whatsapp/templates'), api('/vendors'),
    ])
    users.value = u; roles.value = r; rules.value = c; account.value = a; templates.value = t; vendorsList.value = v
  } finally { loading.value = false }
}
onMounted(load)

const showUser = ref(false)
const form = reactive({ full_name: '', email: '', password: '', role_id: 0 })
async function createUser() {
  saving.value = true
  try {
    await api('/users', { method: 'POST', body: { ...form, role_id: form.role_id || null } })
    useToast().add({ title: 'Staff account created', color: 'success' })
    showUser.value = false
    await load()
  } catch (e) {
    useToast().add({ title: 'Failed', description: errMsg(e), color: 'error' })
  } finally { saving.value = false }
}

const showRule = ref(false)
const ruleForm = reactive({ name: '', charge_type: 'ORDER_PROCESSING', scope: 'GLOBAL', vendor_id: 0, amount_naira: '', basis: 'FIXED' })
async function createRule() {
  saving.value = true
  try {
    await api('/charges/rules', {
      method: 'POST',
      body: { name: ruleForm.name, charge_type: ruleForm.charge_type, scope: ruleForm.scope,
              vendor_id: ruleForm.scope === 'VENDOR' ? ruleForm.vendor_id : null,
              basis: ruleForm.basis, amount_kobo: toKobo(ruleForm.amount_naira) },
    })
    useToast().add({ title: 'Pricing rule created', color: 'success' })
    showRule.value = false
    await load()
  } catch (e) {
    useToast().add({ title: 'Failed', description: errMsg(e), color: 'error' })
  } finally { saving.value = false }
}

async function toggleUser(u: any) {
  await api(`/users/${u.id}`, { method: 'PATCH', body: { is_active: !u.is_active } })
  await load()
}
</script>

<template>
  <div>
    <PageHeader title="Settings" subtitle="Staff access, role permissions, pricing rules and the WhatsApp channel." />
    <UTabs :items="tabs" v-model:model-value="tab" class="mb-4" />

    <!-- USERS -->
    <template v-if="tab === 'users'">
      <div class="mb-3">
        <UButton icon="i-lucide-user-plus" @click="showUser = true">Add staff</UButton>
      </div>
      <DataTable :columns="[
        { key: 'full_name', label: 'Name' },
        { key: 'email', label: 'Email' },
        { key: 'role_name', label: 'Role' },
        { key: 'vendor_scope', label: 'Data scope' },
        { key: 'active', label: 'Status' },
        { key: 'actions', label: '' },
      ]" :rows="users.map(u => ({
        ...u,
        vendor_scope: u.is_vendor ? `Vendor #${u.vendor_id}` : 'All (staff)',
        active: u.is_active ? 'Active' : 'Suspended',
      }))" :loading="loading" empty-title="No users">
        <template #active="{ row }"><StatusBadge :status="row.is_active ? 'ACTIVE' : 'CANCELLED'" /></template>
        <template #actions="{ row }">
          <UButton size="xs" variant="soft" :color="row.is_active ? 'error' : 'success'" @click.stop="toggleUser(row)">
            {{ row.is_active ? 'Suspend' : 'Activate' }}
          </UButton>
        </template>
      </DataTable>
    </template>

    <!-- ROLES -->
    <template v-else-if="tab === 'roles' && roles">
      <div class="grid md:grid-cols-2 xl:grid-cols-3 gap-4">
        <div v-for="r in roles.roles" :key="r.id" class="bg-white dark:bg-zinc-900 rounded-xl border border-zinc-200 dark:border-zinc-800 p-4">
          <div class="flex items-center gap-2 mb-2">
            <p class="font-semibold text-zinc-800 dark:text-zinc-200">{{ r.name }}</p>
            <UBadge v-if="r.is_system" color="neutral" variant="subtle" size="xs">system</UBadge>
          </div>
          <p class="text-xs text-zinc-400 mb-2">{{ roles.role_permissions[String(r.id)]?.length || 0 }} permissions</p>
          <div class="flex flex-wrap gap-1">
            <UBadge v-for="p in (roles.role_permissions[String(r.id)] || []).slice(0, 8)" :key="p" color="primary" variant="soft" size="xs">{{ p }}</UBadge>
            <UBadge v-if="(roles.role_permissions[String(r.id)] || []).length > 8" color="neutral" variant="subtle" size="xs">+{{ roles.role_permissions[String(r.id)].length - 8 }} more</UBadge>
          </div>
        </div>
      </div>
    </template>

    <!-- CHARGES -->
    <template v-else-if="tab === 'charges'">
      <div class="mb-3">
        <UButton icon="i-lucide-plus" @click="showRule = true">New pricing rule</UButton>
      </div>
      <DataTable :columns="[
        { key: 'name', label: 'Rule' },
        { key: 'charge_type', label: 'Type' },
        { key: 'scope', label: 'Scope' },
        { key: 'vendor_name', label: 'Vendor' },
        { key: 'amount', label: 'Amount', align: 'right' },
        { key: 'version', label: 'Version', align: 'right' },
        { key: 'is_active', label: 'Active' },
      ]" :rows="rules.map(r => ({ ...r, amount: fmtNaira(r.amount_kobo), version: `v${r.version}` }))" :loading="loading" empty-title="No rules">
        <template #charge_type="{ row }"><UBadge color="primary" variant="subtle" size="xs">{{ titleize(row.charge_type) }}</UBadge></template>
        <template #scope="{ row }"><UBadge :color="row.scope === 'VENDOR' ? 'warning' : 'neutral'" variant="subtle" size="xs">{{ row.scope }}</UBadge></template>
        <template #is_active="{ row }"><UBadge :color="row.is_active ? 'success' : 'neutral'" variant="subtle" size="xs">{{ row.is_active ? 'yes' : 'no' }}</UBadge></template>
      </DataTable>
    </template>

    <!-- WHATSAPP -->
    <template v-else-if="tab === 'whatsapp'">
      <div class="grid lg:grid-cols-2 gap-5">
        <div class="bg-white dark:bg-zinc-900 rounded-xl border border-zinc-200 dark:border-zinc-800 p-5" v-if="account">
          <h3 class="font-semibold text-zinc-700 dark:text-zinc-200 mb-2">Channel account</h3>
          <div class="space-y-2 text-sm">
            <div class="flex justify-between"><span class="text-zinc-500">Display name</span><span class="font-medium">{{ account.display_name }}</span></div>
            <div class="flex justify-between"><span class="text-zinc-500">Mode</span>
              <UBadge :color="account.mode === 'SIMULATOR' ? 'warning' : 'success'" variant="subtle" size="xs">{{ account.mode }}</UBadge>
            </div>
            <div class="flex justify-between"><span class="text-zinc-500">Status</span><StatusBadge :status="account.status" /></div>
          </div>
          <UAlert class="mt-4" color="info" variant="subtle" icon="i-lucide-info"
                  title="Simulator mode" description="Inbound vendor messages enter through the inbox simulator and flow through the exact pipeline a WhatsApp Cloud API webhook would drive. The webhook endpoint is stubbed and ready for credentials." />
        </div>
        <div class="bg-white dark:bg-zinc-900 rounded-xl border border-zinc-200 dark:border-zinc-800 p-5">
          <h3 class="font-semibold text-zinc-700 dark:text-zinc-200 mb-2">Message templates</h3>
          <div v-for="t in templates" :key="t.id" class="text-sm py-2 border-b last:border-0 border-zinc-100 dark:border-zinc-800">
            <p class="font-medium text-zinc-700 dark:text-zinc-300">{{ t.name }} <UBadge color="success" variant="subtle" size="xs">{{ t.status }}</UBadge></p>
            <p class="text-xs text-zinc-400 mt-0.5">{{ t.body }}</p>
          </div>
        </div>
      </div>
    </template>

    <!-- new user modal -->
    <UModal v-model:open="showUser" title="Add staff account">
      <template #body>
        <div class="grid sm:grid-cols-2 gap-3">
          <UFormField label="Full name"><UInput v-model="form.full_name" class="w-full" /></UFormField>
          <UFormField label="Email"><UInput v-model="form.email" type="email" class="w-full" /></UFormField>
          <UFormField label="Password"><UInput v-model="form.password" type="password" class="w-full" /></UFormField>
          <UFormField label="Role">
            <USelect v-model="form.role_id" class="w-full" :items="(roles?.roles || []).map(r => ({ label: r.name, value: r.id }))" />
          </UFormField>
        </div>
      </template>
      <template #footer>
        <div class="flex justify-end gap-2 w-full">
          <UButton variant="ghost" color="neutral" @click="showUser = false">Cancel</UButton>
          <UButton :loading="saving" :disabled="!form.email || !form.password" @click="createUser">Create</UButton>
        </div>
      </template>
    </UModal>

    <!-- new rule modal -->
    <UModal v-model:open="showRule" title="New pricing rule">
      <template #body>
        <div class="grid sm:grid-cols-2 gap-3">
          <UFormField label="Rule name" class="sm:col-span-2"><UInput v-model="ruleForm.name" class="w-full" /></UFormField>
          <UFormField label="Charge type">
            <USelect v-model="ruleForm.charge_type" class="w-full" :items="['ORDER_PROCESSING', 'LOCAL_DELIVERY', 'INTERSTATE_DISPATCH', 'WAYBILL', 'STORAGE', 'COD_HANDLING', 'RETURN_HANDLING', 'SPECIAL_HANDLING', 'OTHER'].map(t => ({ label: titleize(t), value: t }))" />
          </UFormField>
          <UFormField label="Scope">
            <USelect v-model="ruleForm.scope" class="w-full" :items="[{ label: 'Global (default schedule)', value: 'GLOBAL' }, { label: 'Vendor override', value: 'VENDOR' }]" />
          </UFormField>
          <UFormField v-if="ruleForm.scope === 'VENDOR'" label="Vendor">
            <USelect v-model="ruleForm.vendor_id" class="w-full" :items="(vendorsList || []).map(v => ({ label: v.name, value: v.id }))" />
          </UFormField>
          <UFormField label="Amount (₦)"><UInput v-model="ruleForm.amount_naira" class="w-full" /></UFormField>
        </div>
      </template>
      <template #footer>
        <div class="flex justify-end gap-2 w-full">
          <UButton variant="ghost" color="neutral" @click="showRule = false">Cancel</UButton>
          <UButton :loading="saving" @click="createRule">Create</UButton>
        </div>
      </template>
    </UModal>
  </div>
</template>
