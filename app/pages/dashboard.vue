<script setup lang="ts">
const loading = ref(true)
const d = ref<any>(null)
const loadError = ref('')
const user = useAuth().user

async function load() {
  loading.value = true
  loadError.value = ''
  try { d.value = await api('/dashboard') } catch (e) { loadError.value = errMsg(e) } finally { loading.value = false }
}
onMounted(load)

const maxStatus = computed(() => Math.max(1, ...Object.values(d.value?.orders_by_status || {}) as number[]))
const statusRows = computed(() => Object.entries(d.value?.orders_by_status || {}).map(([s, c]) => ({ status: s, count: c })))
</script>

<template>
  <div>
    <PageHeader title="Dashboard" :subtitle="`Good day, ${user?.full_name?.split(' ')[0] || 'there'} - here is your operation at a glance.`">
      <template #actions>
        <UButton to="/conversations" icon="i-lucide-message-circle" color="neutral" variant="outline">Open Inbox</UButton>
        <UButton to="/orders" icon="i-lucide-plus">New Order</UButton>
      </template>
    </PageHeader>

    <div v-if="loading" class="flex items-center gap-2 text-zinc-400 py-20 justify-center">
      <UIcon name="i-lucide-loader-circle" class="animate-spin" /> Loading dashboard…
    </div>

    <div v-else-if="loadError" class="py-20 text-center">
      <UIcon name="i-lucide-wifi-off" class="w-8 h-8 text-zinc-300 mx-auto mb-3" />
      <p class="text-sm text-zinc-500 mb-4">Could not load your dashboard. {{ loadError }}</p>
      <UButton variant="outline" color="neutral" icon="i-lucide-refresh-cw" @click="load">Try again</UButton>
    </div>

    <template v-else-if="d">
      <!-- Today -->
      <p class="text-[11px] font-semibold uppercase tracking-wider text-zinc-400 mb-2">Today</p>
      <div class="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3 mb-6">
        <StatCard label="Orders received" :value="d.orders_today" icon="i-lucide-inbox" tone="primary" />
        <StatCard label="Delivered" :value="d.delivered_today" icon="i-lucide-package-check" tone="success" />
        <StatCard v-if="d.cash_collected_today_kobo != null" label="Cash collected" :value="fmtNaira(d.cash_collected_today_kobo)" icon="i-lucide-banknote" tone="success" />
        <StatCard label="Failed deliveries" :value="d.failed_deliveries" icon="i-lucide-package-x" tone="error" />
        <StatCard label="Drafts to review" :value="d.drafts_pending_review" icon="i-lucide-file-input" tone="warning" to="/drafts" />
        <StatCard label="Unknown senders" :value="d.unassigned_senders" icon="i-lucide-user-question" tone="warning" to="/conversations" />
      </div>

      <!-- Pipelines -->
      <p class="text-[11px] font-semibold uppercase tracking-wider text-zinc-400 mb-2">Pipelines & queues</p>
      <div class="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3 mb-6">
        <StatCard label="Awaiting processing" :value="d.awaiting_processing" icon="i-lucide-clock" tone="warning" to="/orders" />
        <StatCard label="Awaiting customer" :value="d.awaiting_customer_confirmation" icon="i-lucide-phone-call" to="/confirmations" />
        <StatCard label="Ready for dispatch" :value="d.ready_for_dispatch" icon="i-lucide-package-open" to="/dispatch" />
        <StatCard label="In transit" :value="d.in_transit" icon="i-lucide-truck" tone="primary" to="/dispatch" />
        <StatCard label="Pending COD" :value="d.pending_cod_collections" icon="i-lucide-hand-coins" tone="warning" to="/cod" />
        <StatCard label="Settlements pending" :value="d.settlements_pending" icon="i-lucide-receipt-text" to="/settlements" />
      </div>

      <!-- Money + stock -->
      <p class="text-[11px] font-semibold uppercase tracking-wider text-zinc-400 mb-2">Money & stock</p>
      <div class="grid grid-cols-2 md:grid-cols-4 gap-3 mb-8">
        <StatCard v-if="d.vendor_payables_kobo != null" label="Vendor payables" :value="fmtNaira(d.vendor_payables_kobo)" icon="i-lucide-wallet" tone="primary" sub="Verified collections - charges - settled" />
        <StatCard v-if="d.logistics_revenue_kobo != null" label="Logistics revenue" :value="fmtNaira(d.logistics_revenue_kobo)" icon="i-lucide-trending-up" tone="success" sub="Charges recognized" />
        <StatCard v-if="d.inventory_value_kobo != null" label="Inventory value" :value="fmtNaira(d.inventory_value_kobo)" icon="i-lucide-warehouse" sub="At sell price" />
        <StatCard label="Low stock alerts" :value="d.low_stock_alerts" icon="i-lucide-triangle-alert" :tone="d.low_stock_alerts ? 'warning' : 'neutral'" to="/inventory" />
      </div>

      <div class="grid lg:grid-cols-2 gap-6">
        <!-- Orders by status -->
        <div class="bg-white dark:bg-zinc-900 rounded-xl border border-zinc-200 dark:border-zinc-800 p-5">
          <h3 class="font-semibold text-zinc-800 dark:text-zinc-200 mb-4">Orders by status</h3>
          <div class="space-y-2.5">
            <div v-for="row in statusRows" :key="row.status" class="flex items-center gap-3">
              <div class="w-44 shrink-0"><StatusBadge :status="row.status" /></div>
              <div class="flex-1 h-2.5 bg-zinc-100 dark:bg-zinc-800 rounded-full overflow-hidden">
                <div class="h-full bg-primary-500 rounded-full" :style="{ width: `${(row.count / maxStatus) * 100}%` }" />
              </div>
              <span class="text-sm font-semibold text-zinc-600 dark:text-zinc-300 w-8 text-right">{{ row.count }}</span>
            </div>
          </div>
        </div>

        <!-- Quick links -->
        <div class="bg-white dark:bg-zinc-900 rounded-xl border border-zinc-200 dark:border-zinc-800 p-5">
          <h3 class="font-semibold text-zinc-800 dark:text-zinc-200 mb-4">Next actions</h3>
          <div class="grid sm:grid-cols-2 gap-3">
            <NuxtLink v-for="q in [
              { label: 'Review WhatsApp drafts', hint: `${d.drafts_pending_review} waiting`, to: '/drafts', icon: 'i-lucide-file-input' },
              { label: 'Confirm customers', hint: `${d.awaiting_customer_confirmation} in queue`, to: '/confirmations', icon: 'i-lucide-phone-call' },
              { label: 'Dispatch ready orders', hint: `${d.ready_for_dispatch} ready`, to: '/dispatch', icon: 'i-lucide-truck' },
              { label: 'Reconcile COD', hint: `${d.pending_cod_collections} pending`, to: '/cod', icon: 'i-lucide-hand-coins' },
            ]" :key="q.to" :to="q.to"
              class="flex items-start gap-3 p-3 rounded-lg border border-zinc-200 dark:border-zinc-800 hover:border-primary-400 hover:bg-primary-50/40 dark:hover:bg-primary-950/20 transition-colors"
            >
              <UIcon :name="q.icon" class="w-5 h-5 text-primary-600 mt-0.5" />
              <div>
                <p class="text-sm font-medium text-zinc-800 dark:text-zinc-200">{{ q.label }}</p>
                <p class="text-xs text-zinc-400">{{ q.hint }}</p>
              </div>
            </NuxtLink>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>
