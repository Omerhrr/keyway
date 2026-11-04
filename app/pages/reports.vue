<script setup lang="ts">
const byStatus = ref<any[]>([])
const revenue = ref<any[]>([])
const delivery = ref<any>(null)
const wa = ref<any>(null)
const loading = ref(true)

onMounted(async () => {
  try {
    const [s, r, d, w] = await Promise.all([
      api('/reports/orders-by-status'), api('/reports/revenue-14d'),
      api('/reports/delivery-performance'), api('/reports/whatsapp-stats'),
    ])
    byStatus.value = s; revenue.value = r; delivery.value = d; wa.value = w
  } finally { loading.value = false }
})

const maxRev = computed(() => Math.max(1, ...revenue.value.map(r => r.amount)))
const intentRows = computed(() => Object.entries(wa.value?.intents || {}).map(([k, v]) => ({ intent: k, count: v })))
const maxIntent = computed(() => Math.max(1, ...intentRows.value.map(r => r.count)))
</script>

<template>
  <div>
    <PageHeader title="Reports & Analytics" subtitle="Operational, financial and WhatsApp-intelligence reporting." />

    <div v-if="loading" class="py-20 text-center text-zinc-400"><UIcon name="i-lucide-loader-circle" class="animate-spin w-6 h-6" /></div>

    <template v-else>
      <div class="grid lg:grid-cols-3 gap-5">
        <!-- revenue -->
        <div class="lg:col-span-2 bg-white dark:bg-zinc-900 rounded-xl border border-zinc-200 dark:border-zinc-800 p-5">
          <h3 class="font-semibold text-zinc-700 dark:text-zinc-200 mb-4">Collections - last 14 days</h3>
          <div class="flex items-end gap-1.5 h-44">
            <div v-for="r in revenue" :key="r.day" class="flex-1 flex flex-col items-center gap-1 group">
              <span class="text-[9px] text-zinc-400 opacity-0 group-hover:opacity-100 transition-opacity">₦{{ r.amount.toLocaleString() }}</span>
              <div class="w-full bg-primary-500/80 hover:bg-primary-500 rounded-t-md transition-all" :style="{ height: `${Math.max(3, (r.amount / maxRev) * 100)}%` }" />
              <span class="text-[9px] text-zinc-400">{{ r.day }}</span>
            </div>
          </div>
        </div>

        <!-- delivery perf -->
        <div class="bg-white dark:bg-zinc-900 rounded-xl border border-zinc-200 dark:border-zinc-800 p-5" v-if="delivery">
          <h3 class="font-semibold text-zinc-700 dark:text-zinc-200 mb-3">Delivery performance</h3>
          <div class="grid grid-cols-3 gap-2 mb-4">
            <StatCard label="Success" :value="`${delivery.success_rate}%`" tone="success" />
            <StatCard label="Delivered" :value="delivery.delivered" />
            <StatCard label="Failed" :value="delivery.failed" tone="error" />
          </div>
          <p class="text-[11px] uppercase text-zinc-400 font-semibold mb-2">By rider</p>
          <div v-for="r in delivery.riders" :key="r.name" class="flex items-center gap-2 text-sm py-1">
            <span class="flex-1 truncate text-zinc-600 dark:text-zinc-300">{{ r.name }}</span>
            <span class="text-zinc-400 text-xs">{{ r.delivered }}/{{ r.total }}</span>
            <div class="w-20 h-1.5 bg-zinc-100 dark:bg-zinc-800 rounded-full overflow-hidden">
              <div class="h-full bg-primary-500" :style="{ width: `${r.total ? (r.delivered / r.total) * 100 : 0}%` }" />
            </div>
          </div>
        </div>

        <!-- whatsapp -->
        <div class="lg:col-span-2 bg-white dark:bg-zinc-900 rounded-xl border border-zinc-200 dark:border-zinc-800 p-5" v-if="wa">
          <h3 class="font-semibold text-zinc-700 dark:text-zinc-200 mb-1">WhatsApp intelligence</h3>
          <p class="text-xs text-zinc-400 mb-4">{{ wa.inbound_messages }} inbound messages · {{ wa.drafts_created }} drafts · {{ wa.conversion_rate }}% draft→order conversion · {{ wa.unassigned_senders }} unidentified senders</p>
          <div class="space-y-2">
            <div v-for="row in intentRows" :key="row.intent" class="flex items-center gap-3">
              <div class="w-56 shrink-0"><UBadge color="neutral" variant="subtle" size="xs">{{ titleize(row.intent) }}</UBadge></div>
              <div class="flex-1 h-2 bg-zinc-100 dark:bg-zinc-800 rounded-full overflow-hidden">
                <div class="h-full bg-emerald-500 rounded-full" :style="{ width: `${(row.count / maxIntent) * 100}%` }" />
              </div>
              <span class="text-sm font-semibold text-zinc-500 w-8 text-right">{{ row.count }}</span>
            </div>
          </div>
        </div>

        <!-- orders by status -->
        <div class="bg-white dark:bg-zinc-900 rounded-xl border border-zinc-200 dark:border-zinc-800 p-5">
          <h3 class="font-semibold text-zinc-700 dark:text-zinc-200 mb-3">Orders by status</h3>
          <div class="space-y-1.5">
            <div v-for="s in byStatus" :key="s.status" class="flex justify-between text-sm">
              <StatusBadge :status="s.status" />
              <span class="font-semibold text-zinc-600 dark:text-zinc-300">{{ s.count }}</span>
            </div>
          </div>
        </div>
      </div>

      <UAlert class="mt-6" color="neutral" variant="subtle" icon="i-lucide-file-down"
              title="Exports" description="CSV / Excel / PDF export endpoints are part of phase 6 - this scaffold ships the live aggregates." />
    </template>
  </div>
</template>
