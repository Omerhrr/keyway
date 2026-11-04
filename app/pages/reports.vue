<script setup lang="ts">
const byStatus = ref<any[]>([])
const revenue = ref<any[]>([])
const delivery = ref<any>(null)
const wa = ref<any>(null)
const vendors = ref<any[]>([])
const staff = ref<any[]>([])
const ops = ref<any>(null)
const fin = ref<any>(null)
const loading = ref(true)

async function load() {
  loading.value = true
  try {
    const [s, r, d, w, v, st, o, f] = await Promise.all([
      api('/reports/orders-by-status'), api('/reports/revenue-14d'),
      api('/reports/delivery-performance'), api('/reports/whatsapp-stats'),
      api('/reports/vendor-performance'), api('/reports/staff-performance'),
      api('/reports/operational'), api('/reports/financial'),
    ])
    byStatus.value = s; revenue.value = r; delivery.value = d; wa.value = w
    vendors.value = v; staff.value = st; ops.value = o; fin.value = f
  } finally { loading.value = false }
}
onMounted(load)

const maxRev = computed(() => Math.max(1, ...revenue.value.map(r => r.amount)))
const intentRows = computed(() => Object.entries(wa.value?.intents || {}).map(([k, v]) => ({ intent: k, count: v })))
const maxIntent = computed(() => Math.max(1, ...intentRows.value.map(r => r.count)))
const maxOpsDay = computed(() => Math.max(1, ...(ops.value?.daily || []).map((d: any) => Math.max(d.created, d.delivered))))
const maxTrend = computed(() => Math.max(1, ...(fin.value?.trend_30d || []).map((d: any) => Math.max(d.revenue, d.expense))))

const datasets = [
  { label: 'Orders', key: 'orders', icon: 'i-lucide-package' },
  { label: 'Ledger', key: 'ledger', icon: 'i-lucide-book-open' },
  { label: 'Settlements', key: 'settlements', icon: 'i-lucide-hand-coins' },
  { label: 'COD', key: 'cod', icon: 'i-lucide-banknote' },
  { label: 'Vendors', key: 'vendors', icon: 'i-lucide-store' },
]
const exporting = ref('')
async function exportCsv(key: string) {
  exporting.value = key
  try {
    const { access, logout } = useAuth()
    const res = await $fetch.raw(`/api/reports/export/${key}`, {
      headers: access.value ? { Authorization: `Bearer ${access.value}` } : {},
      responseType: 'blob',
      onResponseError({ response }) { if (response.status === 401) logout() },
    })
    const blob = res._data as Blob
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `keyway-${key}.csv`
    a.click()
    URL.revokeObjectURL(url)
    useToast().add({ title: `${key} exported`, description: 'CSV downloaded.', color: 'success' })
  } catch (e) {
    useToast().add({ title: 'Export failed', description: errMsg(e), color: 'error' })
  } finally { exporting.value = '' }
}
</script>

<template>
  <div>
    <PageHeader title="Reports & Analytics" subtitle="Operational, financial and WhatsApp-intelligence reporting.">
      <template #actions>
        <UDropdownMenu :items="[datasets.map(d => ({ label: d.label, icon: d.icon, onSelect: () => exportCsv(d.key) }))]">
          <UButton variant="soft" color="neutral" icon="i-lucide-download" :loading="!!exporting">Export CSV</UButton>
        </UDropdownMenu>
      </template>
    </PageHeader>

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

        <!-- OPERATIONAL TREND -->
        <div class="lg:col-span-2 bg-white dark:bg-zinc-900 rounded-xl border border-zinc-200 dark:border-zinc-800 p-5" v-if="ops">
          <div class="flex items-center justify-between mb-4 flex-wrap gap-2">
            <div>
              <h3 class="font-semibold text-zinc-700 dark:text-zinc-200">Operational flow - 14 days</h3>
              <p class="text-xs text-zinc-400 mt-0.5">
                {{ ops.total_orders }} orders · {{ ops.delivery_rate }}% delivered
                <template v-if="ops.avg_cycle_hours"> · avg {{ ops.avg_cycle_hours }}h door-to-door</template>
                · WhatsApp→draft {{ ops.wa_to_draft_rate }}%
              </p>
            </div>
            <div class="flex items-center gap-3 text-[10px] text-zinc-400">
              <span class="flex items-center gap-1"><span class="w-2 h-2 rounded-sm bg-primary-500 inline-block" /> created</span>
              <span class="flex items-center gap-1"><span class="w-2 h-2 rounded-sm bg-emerald-500 inline-block" /> delivered</span>
            </div>
          </div>
          <div class="flex items-end gap-1 h-32">
            <div v-for="d in ops.daily" :key="d.day" class="flex-1 flex items-end gap-0.5 group">
              <div class="flex-1 bg-primary-500/80 rounded-t-sm" :style="{ height: `${Math.max(2, (d.created / maxOpsDay) * 100)}%` }" :title="`${d.created} created`" />
              <div class="flex-1 bg-emerald-500/80 rounded-t-sm" :style="{ height: `${Math.max(2, (d.delivered / maxOpsDay) * 100)}%` }" :title="`${d.delivered} delivered`" />
            </div>
          </div>
          <div class="flex gap-1 mt-1">
            <span v-for="d in ops.daily" :key="d.day" class="flex-1 text-[8px] text-zinc-400 text-center">{{ d.day.slice(5) }}</span>
          </div>
          <div v-if="ops.top_cities?.length" class="mt-4 flex flex-wrap gap-1.5">
            <UBadge v-for="c in ops.top_cities" :key="c.city" color="neutral" variant="subtle" size="xs">{{ c.city }} · {{ c.orders }}</UBadge>
          </div>
        </div>

        <!-- FINANCIAL SUMMARY -->
        <div class="bg-white dark:bg-zinc-900 rounded-xl border border-zinc-200 dark:border-zinc-800 p-5" v-if="fin">
          <h3 class="font-semibold text-zinc-700 dark:text-zinc-200 mb-3">COD funnel</h3>
          <div class="grid grid-cols-2 gap-2 mb-3">
            <StatCard label="Expected" :value="fmtNaira(fin.cod.expected_kobo)" />
            <StatCard label="Collected" :value="fmtNaira(fin.cod.collected_kobo)" tone="primary" />
            <StatCard label="Verified" :value="fmtNaira(fin.cod.verified_kobo)" tone="success" />
            <StatCard label="Leakage" :value="`${fin.cod.leakage_rate}%`" :tone="fin.cod.leakage_rate > 2 ? 'error' : 'success'" />
          </div>
          <div class="text-xs space-y-1.5 border-t border-zinc-100 dark:border-zinc-800 pt-3">
            <div class="flex justify-between"><span class="text-zinc-500">Pending verification</span><span class="font-medium">{{ fmtNaira(fin.cod.pending_verification_kobo) }}</span></div>
            <div class="flex justify-between"><span class="text-zinc-500">Vendor payables</span><span class="font-medium">{{ fmtNaira(fin.vendor_payables_kobo) }}</span></div>
            <div class="flex justify-between"><span class="text-zinc-500">Revenue (ledger)</span><span class="font-medium text-emerald-600">{{ fmtNaira(fin.revenue_total_kobo) }}</span></div>
            <div class="flex justify-between"><span class="text-zinc-500">Expenses</span><span class="font-medium text-red-500">{{ fmtNaira(fin.expense_total_kobo) }}</span></div>
            <div class="flex justify-between"><span class="text-zinc-500">Cash balance</span><span class="font-medium">{{ fmtNaira(fin.cash_balance_kobo) }}</span></div>
          </div>
          <div v-if="Object.keys(fin.charges_by_type_kobo || {}).length" class="mt-3 border-t border-zinc-100 dark:border-zinc-800 pt-3">
            <p class="text-[11px] uppercase text-zinc-400 font-semibold mb-1.5">Charges by type</p>
            <div v-for="(amt, t) in fin.charges_by_type_kobo" :key="t" class="flex justify-between text-xs py-0.5">
              <span class="text-zinc-500">{{ titleize(String(t)) }}</span>
              <span class="font-medium text-zinc-600 dark:text-zinc-300">{{ fmtNaira(Number(amt)) }}</span>
            </div>
          </div>
        </div>

        <!-- 30D REVENUE VS EXPENSE -->
        <div class="lg:col-span-2 bg-white dark:bg-zinc-900 rounded-xl border border-zinc-200 dark:border-zinc-800 p-5" v-if="fin">
          <h3 class="font-semibold text-zinc-700 dark:text-zinc-200 mb-4">Revenue vs expenses - 30 days <span class="text-xs font-normal text-zinc-400">(ledger-derived)</span></h3>
          <div class="relative h-40">
            <div class="absolute inset-0 flex items-end gap-px">
              <div v-for="d in fin.trend_30d" :key="d.day" class="flex-1 flex items-end gap-px group">
                <div class="flex-1 bg-primary-500/80 rounded-t-[2px]" :style="{ height: `${Math.max(1, (d.revenue / maxTrend) * 100)}%` }" :title="`Revenue ₦${d.revenue.toLocaleString()}`" />
                <div class="flex-1 bg-red-400/70 rounded-t-[2px]" :style="{ height: `${Math.max(1, (d.expense / maxTrend) * 100)}%` }" :title="`Expense ₦${d.expense.toLocaleString()}`" />
              </div>
            </div>
          </div>
          <div class="flex justify-between text-[9px] text-zinc-400 mt-1">
            <span>{{ fin.trend_30d[0]?.day.slice(5) }}</span>
            <span class="flex items-center gap-3">
              <span class="flex items-center gap-1"><span class="w-2 h-2 rounded-sm bg-primary-500 inline-block" /> revenue</span>
              <span class="flex items-center gap-1"><span class="w-2 h-2 rounded-sm bg-red-400 inline-block" /> expense</span>
            </span>
            <span>{{ fin.trend_30d[fin.trend_30d.length - 1]?.day.slice(5) }}</span>
          </div>
        </div>

        <!-- STAFF PERFORMANCE -->
        <div class="bg-white dark:bg-zinc-900 rounded-xl border border-zinc-200 dark:border-zinc-800 p-5">
          <h3 class="font-semibold text-zinc-700 dark:text-zinc-200 mb-3">Staff performance</h3>
          <div v-if="staff.length" class="space-y-3">
            <div v-for="s in staff" :key="s.user_id" class="text-sm border-b last:border-0 border-zinc-100 dark:border-zinc-800 pb-2 last:pb-0">
              <div class="flex items-center justify-between">
                <p class="font-medium text-zinc-700 dark:text-zinc-200">{{ s.name }}</p>
                <UBadge v-if="s.role" color="neutral" variant="subtle" size="xs">{{ titleize(s.role) }}</UBadge>
              </div>
              <p class="text-[11px] text-zinc-400 mt-0.5">
                {{ s.orders_created }} orders · {{ s.cod_verifications }} COD checks ({{ fmtNaira(s.cod_verified_kobo) }})
                · {{ s.settlements_approved }} settlements · {{ s.journal_entries_posted }} journal entries
              </p>
            </div>
          </div>
          <p v-else class="text-sm text-zinc-400">No staff activity recorded yet.</p>
        </div>

        <!-- VENDOR PERFORMANCE -->
        <div class="lg:col-span-3 bg-white dark:bg-zinc-900 rounded-xl border border-zinc-200 dark:border-zinc-800 p-5">
          <h3 class="font-semibold text-zinc-700 dark:text-zinc-200 mb-3">Vendor performance scorecard</h3>
          <DataTable :columns="[
            { key: 'vendor', label: 'Vendor' },
            { key: 'orders', label: 'Orders', align: 'right' },
            { key: 'delivered', label: 'Delivered', align: 'right' },
            { key: 'rate', label: 'Delivery rate', align: 'right' },
            { key: 'cycle', label: 'Avg cycle', align: 'right' },
            { key: 'cod', label: 'COD verified', align: 'right' },
            { key: 'charges', label: 'Charges', align: 'right' },
            { key: 'outstanding', label: 'Outstanding payable', align: 'right' },
          ]" :rows="vendors.map(v => ({
            ...v,
            rate: `${v.delivery_rate}%`,
            cycle: v.avg_cycle_hours != null ? `${v.avg_cycle_hours}h` : '—',
            cod: fmtNaira(v.cod_verified_kobo),
            charges: fmtNaira(v.charges_kobo),
            outstanding: fmtNaira(v.outstanding_payable_kobo),
          }))" empty-title="No vendors yet">
            <template #vendor="{ row }">
              <div class="flex items-center gap-2">
                <span class="font-medium">{{ row.vendor }}</span>
                <UBadge v-if="row.status !== 'ACTIVE'" color="warning" variant="subtle" size="xs">{{ row.status }}</UBadge>
              </div>
            </template>
            <template #rate="{ row }">
              <span :class="row.delivery_rate >= 90 ? 'text-emerald-600 font-semibold' : row.delivery_rate >= 70 ? 'text-amber-600' : 'text-red-500'">{{ row.rate }}</span>
            </template>
          </DataTable>
        </div>
      </div>
    </template>
  </div>
</template>
