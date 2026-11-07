<script setup lang="ts">
const { can } = useAuth()
const tab = ref('users')
const { on } = useModules()
const allTabs = [
  { label: 'Staff & access', value: 'users', icon: 'i-lucide-users' },
  { label: 'Warehouses', value: 'warehouses', icon: 'i-lucide-warehouse' },
  { label: 'Roles', value: 'roles', icon: 'i-lucide-shield' },
  { label: 'Pricing rules', value: 'charges', icon: 'i-lucide-tags' },
  { label: 'Notifications', value: 'notify', icon: 'i-lucide-bell-ring' },
  { label: 'WhatsApp', value: 'whatsapp', icon: 'i-lucide-message-circle' },
  { label: 'Appearance', value: 'appearance', icon: 'i-lucide-palette' },
  { label: 'Features', value: 'modules', icon: 'i-lucide-toggle-right' },
  { label: 'Printed documents', value: 'documents', icon: 'i-lucide-file-text' },
  { label: 'Install app', value: 'install', icon: 'i-lucide-download' },
]

const tabs = computed(() => allTabs.filter((t) => t.value !== 'whatsapp' || on('whatsapp')))

const users = ref<any[]>([])
const roles = ref<any>(null)
const rules = ref<any[]>([])
const account = ref<any>(null)
const templates = ref<any[]>([])
const vendorsList = ref<any[]>([])
const warehouses = ref<any[]>([])
const loading = ref(true)
const saving = ref(false)

async function load() {
  loading.value = true
  try {
    const soft = (p: Promise<any>, empty: any = null) => p.catch(() => empty)
    const [u, r, c, a, t, v, w] = await Promise.all([
      api('/users'), api('/roles'), api('/charges/rules'),
      on('whatsapp') ? soft(api('/whatsapp/account')) : Promise.resolve(null),
      on('whatsapp') ? soft(api('/whatsapp/templates'), []) : Promise.resolve([]),
      api('/vendors'), api('/inventory/warehouses'),
    ])
    users.value = u; roles.value = r; rules.value = c; account.value = a; templates.value = t; vendorsList.value = v
    warehouses.value = w
    await loadNotifications()
  } finally { loading.value = false }
}
onMounted(load)

const showUser = ref(false)
const form = reactive({ full_name: '', email: '', password: '', role_id: 0, warehouse_id: 0 })
async function createUser() {
  saving.value = true
  try {
    await api('/users', { method: 'POST', body: { ...form, role_id: form.role_id || null, warehouse_id: form.warehouse_id || null } })
    useToast().add({ title: 'Staff account created', color: 'success' })
    showUser.value = false
    await load()
  } catch (e) {
    useToast().add({ title: 'Failed', description: errMsg(e), color: 'error' })
  } finally { saving.value = false }
}

async function setUserWarehouse(u: any, warehouseId: number) {
  try {
    await api(`/users/${u.id}`, { method: 'PATCH', body: { warehouse_id: warehouseId || null } })
    useToast().add({ title: 'Home warehouse updated', color: 'success' })
    await load()
  } catch (e) {
    useToast().add({ title: 'Failed', description: errMsg(e), color: 'error' })
  }
}

// ---- Warehouses (multi-warehouse ops) ----
const canManageInventory = computed(() => can('inventory.manage'))
const showWh = ref(false)
const whForm = reactive({ code: '', name: '', address: '', city: '', state: '', is_default: false })
const editWh = ref<any>(null)
const editWhForm = reactive({ name: '', address: '', city: '', state: '', is_default: false })
const locForm = reactive({ code: '', kind: 'SHELF' })
const whSaving = ref(false)

async function createWarehouse() {
  whSaving.value = true
  try {
    await api('/inventory/warehouses', { method: 'POST', body: { ...whForm, code: whForm.code.toUpperCase() } })
    useToast().add({ title: 'Warehouse created', color: 'success' })
    showWh.value = false
    Object.assign(whForm, { code: '', name: '', address: '', city: '', state: '', is_default: false })
    await load()
  } catch (e) {
    useToast().add({ title: 'Failed', description: errMsg(e), color: 'error' })
  } finally { whSaving.value = false }
}

function openEditWh(w: any) {
  editWh.value = w
  Object.assign(editWhForm, { name: w.name, address: w.address || '', city: w.city || '', state: w.state || '', is_default: !!w.is_default })
}

async function saveWarehouse() {
  if (!editWh.value) return
  whSaving.value = true
  try {
    await api(`/inventory/warehouses/${editWh.value.id}`, { method: 'PATCH', body: { ...editWhForm } })
    useToast().add({ title: 'Warehouse updated', color: 'success' })
    editWh.value = null
    await load()
  } catch (e) {
    useToast().add({ title: 'Failed', description: errMsg(e), color: 'error' })
  } finally { whSaving.value = false }
}

async function makeDefault(w: any) {
  try {
    await api(`/inventory/warehouses/${w.id}`, { method: 'PATCH', body: { is_default: true } })
    useToast().add({ title: `${w.name} is now the default warehouse`, color: 'success' })
    await load()
  } catch (e) {
    useToast().add({ title: 'Failed', description: errMsg(e), color: 'error' })
  }
}

async function toggleWarehouse(w: any) {
  try {
    await api(`/inventory/warehouses/${w.id}`, { method: 'PATCH', body: { is_active: !w.is_active } })
    await load()
  } catch (e) {
    useToast().add({ title: 'Failed', description: errMsg(e), color: 'error' })
  }
}

async function addLocation() {
  if (!editWh.value || !locForm.code.trim()) return
  whSaving.value = true
  try {
    await api('/inventory/locations', { method: 'POST', body: { warehouse_id: editWh.value.id, code: locForm.code.toUpperCase(), kind: locForm.kind } })
    locForm.code = ''
    locForm.kind = 'SHELF'
    const fresh = await api('/inventory/warehouses')
    warehouses.value = fresh
    editWh.value = fresh.find((x: any) => x.id === editWh.value.id) || editWh.value
    useToast().add({ title: 'Location added', color: 'success' })
  } catch (e) {
    useToast().add({ title: 'Failed', description: errMsg(e), color: 'error' })
  } finally { whSaving.value = false }
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

// ---- Notification rules (PRD: advanced notification rules) ----
const nRules = ref<any[]>([])
const nEvents = ref<any[]>([])
const nChannels = ref<string[]>([])
const showNRule = ref(false)
const nForm = reactive({ name: '', event_type: 'NEW_WHATSAPP_ORDER', target_scope: 'ALL_STAFF', role_name: '', user_id: 0, channel: 'IN_APP' })
const checking = ref(false)

async function loadNotifications() {
  const r = await api('/notification-rules')
  nRules.value = r.rules; nEvents.value = r.events; nChannels.value = r.channels
}

const canManageNotify = computed(() => can('settings.manage'))

async function createNRule() {
  saving.value = true
  try {
    await api('/notification-rules', { method: 'POST', body: {
      name: nForm.name, event_type: nForm.event_type, target_scope: nForm.target_scope,
      role_name: nForm.target_scope === 'ROLE' ? nForm.role_name : '',
      user_id: nForm.target_scope === 'USER' ? nForm.user_id : null,
      channel: nForm.channel,
    } })
    useToast().add({ title: 'Notification rule created', color: 'success' })
    showNRule.value = false
    nForm.name = ''
    await loadNotifications()
  } catch (e) {
    useToast().add({ title: 'Failed', description: errMsg(e), color: 'error' })
  } finally { saving.value = false }
}

async function toggleNRule(r: any) {
  try {
    await api(`/notification-rules/${r.id}`, { method: 'PATCH', body: { enabled: !r.enabled } })
    await loadNotifications()
  } catch (e) {
    useToast().add({ title: 'Failed', description: errMsg(e), color: 'error' })
  }
}

async function deleteNRule(r: any) {
  try {
    await api(`/notification-rules/${r.id}`, { method: 'DELETE' })
    useToast().add({ title: 'Rule deleted', color: 'success' })
    await loadNotifications()
  } catch (e) {
    useToast().add({ title: 'Failed', description: errMsg(e), color: 'error' })
  }
}

const testingRule = ref<number | null>(null)
async function testNRule(r: any) {
  testingRule.value = r.id
  try {
    const res = await api(`/notification-rules/${r.id}/test`, { method: 'POST' })
    useToast().add({
      title: res.sent ? `Test sent to ${res.sent} target(s) via ${res.channel}` : 'No targets matched this rule',
      description: res.failed ? `${res.failed} delivery failed - check the phone number / channel config.` : '',
      color: res.sent && !res.failed ? 'success' : res.failed ? 'warning' : 'neutral',
    })
  } catch (e) {
    useToast().add({ title: 'Failed', description: errMsg(e), color: 'error' })
  } finally { testingRule.value = null }
}

async function runChecks() {
  checking.value = true
  try {
    const r = await api('/notifications/run-checks', { method: 'POST' })
    useToast().add({ title: r.total ? `${r.total} new alert(s)` : 'Everything looks good',
                     description: r.total ? Object.entries(r.created).filter(([, v]) => v).map(([k, v]) => `${k}: ${v}`).join(', ') : 'No low stock or unconfirmed orders detected.',
                     color: r.total ? 'warning' : 'success' })
    await loadNotifications()
  } catch (e) {
    useToast().add({ title: 'Failed', description: errMsg(e), color: 'error' })
  } finally { checking.value = false }
}

// ---- WhatsApp Cloud API (Phase 6A) ----
const waForm = reactive({ mode: 'SIMULATOR', phone_number_id: '', waba_id: '', access_token: '' })
const waSaving = ref(false)
const waTesting = ref(false)
const tokenSet = ref(false)
watch(account, (a) => {
  if (!a) return
  waForm.mode = a.mode || 'SIMULATOR'
  waForm.phone_number_id = a.phone_number_id || ''
  waForm.waba_id = a.waba_id || ''
  tokenSet.value = !!a.access_token_set
})
async function saveWa() {
  waSaving.value = true
  try {
    account.value = await api('/whatsapp/account', {
      method: 'PUT',
      body: {
        mode: waForm.mode,
        phone_number_id: waForm.phone_number_id,
        waba_id: waForm.waba_id,
        access_token: waForm.access_token || undefined,
      },
    })
    waForm.access_token = ''
    useToast().add({ title: 'WhatsApp channel updated', color: 'success' })
  } catch (e) {
    useToast().add({ title: 'Failed', description: errMsg(e), color: 'error' })
  } finally { waSaving.value = false }
}
async function testWa() {
  waTesting.value = true
  try {
    const r = await api('/whatsapp/account/test', { method: 'POST' })
    useToast().add({ title: r.ok ? 'Credentials valid' : 'Credential check failed',
                     description: r.detail, color: r.ok ? 'success' : 'error' })
    await load()
  } catch (e) {
    useToast().add({ title: 'Failed', description: errMsg(e), color: 'error' })
  } finally { waTesting.value = false }
}
const webhookUrl = computed(() => {
  if (!import.meta.client) return '/api/whatsapp/webhook'
  return `${window.location.origin}/api/whatsapp/webhook`
})
function copyWebhook() {
  if (import.meta.client) {
    navigator.clipboard?.writeText(webhookUrl.value)
    useToast().add({ title: 'Link copied', color: 'success' })
  }
}
</script>

<template>
  <div>
    <PageHeader title="Settings" subtitle="Staff and roles, features, appearance, printed documents, pricing and messaging." />
    <ScrollTabs :items="tabs" v-model="tab" class="mb-4" />

    <SettingsAppearance v-if="tab === 'appearance'" />
    <SettingsDocuments v-else-if="tab === 'documents'" />
    <SettingsInstall v-else-if="tab === 'install'" />
    <SettingsModules v-else-if="tab === 'modules'" />
    <SettingsRoles v-else-if="tab === 'roles'" @changed="load" />

    <!-- USERS -->
    <template v-else-if="tab === 'users'">
      <div class="mb-3">
        <UButton icon="i-lucide-user-plus" @click="showUser = true">Add staff</UButton>
      </div>
      <DataTable :columns="[
        { key: 'full_name', label: 'Name' },
        { key: 'email', label: 'Email' },
        { key: 'role_name', label: 'Role' },
        { key: 'home_wh', label: 'Home warehouse' },
        { key: 'vendor_scope', label: 'Data scope' },
        { key: 'active', label: 'Status' },
        { key: 'actions', label: '' },
      ]" :rows="users.map(u => ({
        ...u,
        home_wh: warehouses.find(w => w.id === u.warehouse_id)?.name || '',
        vendor_scope: u.is_vendor ? `Vendor #${u.vendor_id}` : 'All (staff)',
        active: u.is_active ? 'Active' : 'Suspended',
      }))" :loading="loading" empty-title="No users">
        <template #active="{ row }"><StatusBadge :status="row.is_active ? 'ACTIVE' : 'CANCELLED'" /></template>
        <template #home_wh="{ row }">
          <USelect v-if="!row.is_vendor && canManageInventory" :model-value="row.warehouse_id || 0" size="xs" class="w-44"
                   :items="[{ label: 'No home warehouse', value: 0 }, ...warehouses.filter(w => w.is_active).map(w => ({ label: w.name, value: w.id }))]"
                   @update:model-value="v => setUserWarehouse(row, v)" />
          <span v-else class="text-xs text-zinc-400">{{ warehouses.find(w => w.id === row.warehouse_id)?.name || '-' }}</span>
        </template>
        <template #actions="{ row }">
          <UButton size="xs" variant="soft" :color="row.is_active ? 'error' : 'success'" @click.stop="toggleUser(row)">
            {{ row.is_active ? 'Suspend' : 'Activate' }}
          </UButton>
        </template>
      </DataTable>
    </template>

    <!-- WAREHOUSES -->
    <template v-else-if="tab === 'warehouses'">
      <div class="mb-3 flex items-center gap-2">
        <UButton v-if="canManageInventory" icon="i-lucide-plus" @click="showWh = true">New warehouse</UButton>
        <p class="text-xs text-zinc-400">Stock balances, receipts and transfers are tracked per warehouse. The default warehouse fulfils orders when no branch is chosen.</p>
      </div>
      <DataTable :columns="[
        { key: 'code', label: 'Code' },
        { key: 'name', label: 'Warehouse' },
        { key: 'location', label: 'City / State' },
        { key: 'locations', label: 'Locations' },
        { key: 'default', label: 'Flags' },
        { key: 'actions', label: '' },
      ]" :rows="warehouses.map(w => ({
        ...w,
        location: [w.city, w.state].filter(Boolean).join(', ') || '-',
      }))" :loading="loading" empty-title="No warehouses">
        <template #code="{ row }"><span class="font-mono font-semibold text-primary-600">{{ row.code }}</span></template>
        <template #locations="{ row }">
          <div class="flex flex-wrap gap-1">
            <UBadge v-for="l in (row.locations || [])" :key="l.id" color="neutral" variant="subtle" size="xs">{{ l.code }}</UBadge>
            <span v-if="!(row.locations || []).length" class="text-xs text-zinc-400">-</span>
          </div>
        </template>
        <template #default="{ row }">
          <div class="flex gap-1">
            <UBadge v-if="row.is_default" color="primary" variant="subtle" size="xs">default</UBadge>
            <UBadge :color="row.is_active ? 'success' : 'error'" variant="subtle" size="xs">{{ row.is_active ? 'active' : 'inactive' }}</UBadge>
          </div>
        </template>
        <template #actions="{ row }">
          <div class="flex gap-1" v-if="canManageInventory">
            <UButton size="xs" variant="ghost" icon="i-lucide-pencil" @click.stop="openEditWh(row)" aria-label="Edit warehouse" />
            <UButton v-if="!row.is_default" size="xs" variant="soft" color="primary" @click.stop="makeDefault(row)">Make default</UButton>
            <UButton v-if="!row.is_default" size="xs" variant="soft" :color="row.is_active ? 'error' : 'success'" @click.stop="toggleWarehouse(row)">
              {{ row.is_active ? 'Deactivate' : 'Activate' }}
            </UButton>
          </div>
        </template>
      </DataTable>
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

    <!-- NOTIFICATIONS -->
    <template v-else-if="tab === 'notify'">
      <div class="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <div class="lg:col-span-2">
          <div class="flex items-center gap-2 mb-3 flex-wrap">
            <UButton v-if="canManageNotify" icon="i-lucide-plus" @click="showNRule = true">New rule</UButton>
            <UButton v-if="canManageNotify" :loading="checking" variant="soft" color="neutral" icon="i-lucide-refresh-ccw" @click="runChecks">
              Run checks now
            </UButton>
            <p class="text-xs text-zinc-400 ml-auto">Checks for low stock and orders waiting for confirmation. You will not get the same alert twice while the first is unread.</p>
          </div>
          <DataTable :columns="[
            { key: 'name', label: 'Rule' },
            { key: 'event_label', label: 'Event' },
            { key: 'target', label: 'Target' },
            { key: 'channel', label: 'Channel' },
            { key: 'enabled', label: 'Enabled' },
            { key: 'actions', label: '' },
          ]" :rows="nRules.map(r => ({
            ...r,
            event_label: (nEvents.find(e => e.event_type === r.event_type)?.label) || r.event_type,
            target: r.target_scope === 'ROLE' ? `Role: ${r.role_name}` : r.target_scope === 'USER' ? `User #${r.user_id}` : 'All staff',
          }))" :loading="loading" empty-title="No rules" empty-hint="With no rules, staff notifications go to everyone in-app.">
            <template #name="{ row }"><span class="font-medium text-zinc-800 dark:text-zinc-200">{{ row.name }}</span></template>
            <template #channel="{ row }">
              <UBadge :color="row.channel === 'IN_APP' ? 'neutral' : row.channel === 'WHATSAPP' ? 'success' : 'info'" variant="subtle" size="xs">{{ row.channel }}</UBadge>
            </template>
            <template #enabled="{ row }">
              <USwitch v-if="canManageNotify" :model-value="row.enabled" size="sm" @update:model-value="toggleNRule(row)" />
              <UBadge v-else :color="row.enabled ? 'success' : 'neutral'" variant="subtle" size="xs">{{ row.enabled ? 'on' : 'off' }}</UBadge>
            </template>
            <template #actions="{ row }">
              <UButton v-if="canManageNotify" size="xs" variant="ghost" icon="i-lucide-send" :loading="testingRule === row.id" @click.stop="testNRule(row)">Test</UButton>
              <UButton v-if="canManageNotify" size="xs" variant="ghost" color="error" icon="i-lucide-trash-2" @click.stop="deleteNRule(row)" aria-label="Delete rule" />
            </template>
          </DataTable>
        </div>
        <div class="bg-white dark:bg-zinc-900 rounded-xl border border-zinc-200 dark:border-zinc-800 p-5 self-start">
          <h3 class="font-semibold text-zinc-700 dark:text-zinc-200 mb-1 text-sm">Events that can trigger notifications</h3>
          <p class="text-xs text-zinc-400 mb-2">Raised by order intake, delivery, COD and settlement flows.</p>
          <div v-for="e in nEvents" :key="e.event_type" class="py-1.5 border-b last:border-0 border-zinc-100 dark:border-zinc-800/70">
            <p class="text-sm text-zinc-700 dark:text-zinc-300">{{ e.label }}</p>
            <p class="text-[11px] text-zinc-400"><code>{{ e.event_type }}</code> · typical audience: {{ e.audience }}</p>
          </div>
        </div>
      </div>
    </template>

    <!-- WHATSAPP -->
    <template v-else-if="tab === 'whatsapp' && on('whatsapp')">
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <div class="bg-white dark:bg-zinc-900 rounded-xl border border-zinc-200 dark:border-zinc-800 p-5" v-if="account">
          <div class="flex items-center justify-between mb-3">
            <h3 class="font-semibold text-zinc-700 dark:text-zinc-200">WhatsApp connection</h3>
            <UBadge :color="waForm.mode === 'SIMULATOR' ? 'warning' : (account.status === 'CONNECTED' ? 'success' : 'error')" variant="subtle" size="xs">
              {{ waForm.mode === 'SIMULATOR' ? 'Practice mode' : account.status }}
            </UBadge>
          </div>
          <div class="space-y-3 text-sm">
            <UFormField label="Mode" description="Practice mode lets you try the inbox with test messages. Live mode uses your real WhatsApp number.">
              <USelect v-model="waForm.mode" class="w-full"
                       :items="[{ label: 'Practice (no WhatsApp account needed)', value: 'SIMULATOR' }, { label: 'Live (real WhatsApp messages)', value: 'CLOUD_API' }]" />
            </UFormField>
            <UFormField label="Phone number ID" help="Found in your Meta WhatsApp setup page">
              <UInput v-model="waForm.phone_number_id" class="w-full" placeholder="e.g. 123456789012345" />
            </UFormField>
            <UFormField label="WhatsApp Business Account ID">
              <UInput v-model="waForm.waba_id" class="w-full" placeholder="e.g. 987654321098765" />
            </UFormField>
            <UFormField :label="tokenSet ? 'Access key (replace)' : 'Access key'"
                        :hint="tokenSet ? 'An access key is saved. Leave blank to keep it.' : 'The permanent access key from your Meta account'">
              <UInput v-model="waForm.access_token" type="password" class="w-full" :placeholder="tokenSet ? '•••••••• (stored)' : 'EAAG...'" />
            </UFormField>
            <div class="flex gap-2 pt-1">
              <UButton :loading="waSaving" @click="saveWa" icon="i-lucide-save">Save</UButton>
              <UButton :loading="waTesting" variant="soft" color="neutral" @click="testWa" icon="i-lucide-plug-zap">Test connection</UButton>
            </div>
          </div>
          <USeparator class="my-4" />
          <div>
            <p class="text-xs font-medium text-zinc-500 mb-1">Message link (paste this into your Meta app settings)</p>
            <div class="flex items-center gap-2">
              <code class="text-xs bg-zinc-100 dark:bg-zinc-800 rounded px-2 py-1.5 flex-1 truncate">{{ webhookUrl }}</code>
              <UButton size="xs" variant="ghost" icon="i-lucide-copy" @click="copyWebhook" />
            </div>
            <p class="text-xs text-zinc-400 mt-1.5">Your developer sets the matching verification codes on the server.</p>
          </div>
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
            <USelect placeholder="Choose..." @update:model-value="(v: any) => { form.role_id = v }" :model-value="form.role_id || undefined" class="w-full" :items="(roles?.roles || []).map(r => ({ label: r.name, value: r.id }))" />
          </UFormField>
          <UFormField label="Home warehouse" help="Preselects this branch when the user creates orders or filters inventory" class="sm:col-span-2">
            <USelect v-model="form.warehouse_id" class="w-full" :items="[{ label: 'No home warehouse', value: 0 }, ...warehouses.filter(w => w.is_active).map(w => ({ label: w.name, value: w.id }))]" />
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
            <USelect placeholder="Choose..." @update:model-value="(v: any) => { ruleForm.vendor_id = v }" :model-value="ruleForm.vendor_id || undefined" class="w-full" :items="(vendorsList || []).map(v => ({ label: v.name, value: v.id }))" />
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
    <!-- new notification rule modal -->
    <UModal v-model:open="showNRule" title="New notification rule">
      <template #body>
        <div class="grid sm:grid-cols-2 gap-3">
          <UFormField label="Rule name" class="sm:col-span-2"><UInput v-model="nForm.name" class="w-full" placeholder="e.g. Low stock -> warehouse manager" /></UFormField>
          <UFormField label="Event">
            <USelect v-model="nForm.event_type" class="w-full" :items="nEvents.map(e => ({ label: e.label, value: e.event_type }))" />
          </UFormField>
          <UFormField label="Channel">
            <USelect v-model="nForm.channel" class="w-full" :items="nChannels.map(c => ({ label: c === 'IN_APP' ? 'In-app' : c, value: c }))" />
          </UFormField>
          <UFormField label="Target">
            <USelect v-model="nForm.target_scope" class="w-full" :items="[
              { label: 'All staff', value: 'ALL_STAFF' },
              { label: 'A specific role', value: 'ROLE' },
              { label: 'One user', value: 'USER' },
            ]" />
          </UFormField>
          <UFormField v-if="nForm.target_scope === 'ROLE'" label="Role">
            <USelect v-model="nForm.role_name" class="w-full" :items="(roles?.roles || []).map(r => ({ label: r.name, value: r.name }))" />
          </UFormField>
          <UFormField v-if="nForm.target_scope === 'USER'" label="User">
            <USelect placeholder="Choose..." @update:model-value="(v: any) => { nForm.user_id = v }" :model-value="nForm.user_id || undefined" class="w-full" :items="users.filter(u => !u.is_vendor).map(u => ({ label: `${u.full_name} (${u.email})`, value: u.id }))" />
          </UFormField>
          <p v-if="nForm.channel !== 'IN_APP'" class="text-xs text-amber-600 sm:col-span-2">
            {{ nForm.channel }} delivery attempts the real channel (WhatsApp uses the Cloud API when configured). Undeliverable messages are marked FAILED and can be retried from the audit view.
          </p>
        </div>
      </template>
      <template #footer>
        <div class="flex justify-end gap-2 w-full">
          <UButton variant="ghost" color="neutral" @click="showNRule = false">Cancel</UButton>
          <UButton :loading="saving" :disabled="!nForm.name || (nForm.target_scope === 'ROLE' && !nForm.role_name) || (nForm.target_scope === 'USER' && !nForm.user_id)" @click="createNRule">Create</UButton>
        </div>
      </template>
    </UModal>

    <!-- new warehouse modal -->
    <UModal v-model:open="showWh" title="New warehouse">
      <template #body>
        <div class="grid sm:grid-cols-2 gap-3">
          <UFormField label="Code" help="Short unique code, e.g. WH-ABJ">
            <UInput v-model="whForm.code" class="w-full" placeholder="WH-ABJ" />
          </UFormField>
          <UFormField label="Name">
            <UInput v-model="whForm.name" class="w-full" placeholder="Abuja Central Warehouse" />
          </UFormField>
          <UFormField label="City"><UInput v-model="whForm.city" class="w-full" /></UFormField>
          <UFormField label="State"><UInput v-model="whForm.state" class="w-full" /></UFormField>
          <UFormField label="Address" class="sm:col-span-2"><UInput v-model="whForm.address" class="w-full" /></UFormField>
          <USwitch v-model="whForm.is_default" label="Make this the default warehouse" class="sm:col-span-2" />
        </div>
      </template>
      <template #footer>
        <div class="flex justify-end gap-2 w-full">
          <UButton variant="ghost" color="neutral" @click="showWh = false">Cancel</UButton>
          <UButton :loading="whSaving" :disabled="!whForm.code || !whForm.name" @click="createWarehouse">Create</UButton>
        </div>
      </template>
    </UModal>

    <!-- edit warehouse modal -->
    <UModal :open="!!editWh" @update:open="v => { if (!v) editWh = null }" :title="editWh ? `Edit ${editWh.code}` : 'Edit warehouse'">
      <template #body>
        <div class="grid sm:grid-cols-2 gap-3">
          <UFormField label="Code"><UInput :model-value="editWh?.code" disabled class="w-full" /></UFormField>
          <UFormField label="Name"><UInput v-model="editWhForm.name" class="w-full" /></UFormField>
          <UFormField label="City"><UInput v-model="editWhForm.city" class="w-full" /></UFormField>
          <UFormField label="State"><UInput v-model="editWhForm.state" class="w-full" /></UFormField>
          <UFormField label="Address" class="sm:col-span-2"><UInput v-model="editWhForm.address" class="w-full" /></UFormField>
          <USwitch v-model="editWhForm.is_default" label="Default warehouse" class="sm:col-span-2" />
          <USeparator class="sm:col-span-2" />
          <p class="text-xs font-semibold text-zinc-500 sm:col-span-2 -mb-1">Locations (bins, shelves, staging areas)</p>
          <div class="sm:col-span-2 flex flex-wrap gap-1">
            <UBadge v-for="l in (editWh?.locations || [])" :key="l.id" color="neutral" variant="subtle" size="xs">{{ l.code }} · {{ l.kind }}</UBadge>
            <span v-if="!(editWh?.locations || []).length" class="text-xs text-zinc-400">No locations yet</span>
          </div>
          <UFormField label="New location code"><UInput v-model="locForm.code" class="w-full" placeholder="e.g. C03-SHELF" @keydown.enter="addLocation" /></UFormField>
          <UFormField label="Kind">
            <USelect v-model="locForm.kind" class="w-full" :items="['SHELF', 'STAGING', 'DAMAGED', 'RETURNS'].map(k => ({ label: k, value: k }))" />
          </UFormField>
          <div class="sm:col-span-2">
            <UButton size="xs" variant="soft" icon="i-lucide-plus" :loading="whSaving" :disabled="!locForm.code" @click="addLocation">Add location</UButton>
          </div>
        </div>
      </template>
      <template #footer>
        <div class="flex justify-end gap-2 w-full">
          <UButton variant="ghost" color="neutral" @click="editWh = null">Cancel</UButton>
          <UButton :loading="whSaving" :disabled="!editWhForm.name" @click="saveWarehouse">Save changes</UButton>
        </div>
      </template>
    </UModal>
  </div>
</template>
