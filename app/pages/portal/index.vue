<script setup lang="ts">
definePageMeta({ layout: 'portal' })
const s = ref<any>(null)
const loading = ref(true)
const notes = ref<any[]>([])

onMounted(async () => {
  try {
    const [sum, n] = await Promise.all([api('/portal/summary'), api('/notifications?limit=8')])
    s.value = sum; notes.value = n
  } finally { loading.value = false }
})

const fmtWhen = (t: string) => t ? new Date(t).toLocaleString('en-NG', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : ''
</script>

<template>
  <div>
    <h1 class="text-2xl font-bold text-zinc-900 dark:text-white mb-1">{{ s?.name || 'Your store' }}</h1>
    <p class="text-sm text-zinc-500 mb-6">Welcome to your self-service portal - inventory, orders, COD collections and money owed to you.</p>

    <div v-if="loading" class="py-16 text-center text-zinc-400"><UIcon name="i-lucide-loader-circle" class="animate-spin w-6 h-6" /></div>
    <template v-else-if="s">
      <div class="grid grid-cols-2 lg:grid-cols-3 gap-3 mb-6">
        <StatCard label="Active orders" :value="s.orders_active" icon="i-lucide-package" tone="primary" to="/portal/orders" />
        <StatCard label="Verified collections" :value="fmtNaira(s.verified_collections_kobo)" icon="i-lucide-banknote" tone="success" />
        <StatCard label="Outstanding payable" :value="fmtNaira(s.outstanding_payable_kobo)" icon="i-lucide-wallet" sub="Money owed to you" />
        <StatCard label="Logistics charges" :value="fmtNaira(s.charges_kobo)" icon="i-lucide-scissors" />
        <StatCard label="Settled to date" :value="fmtNaira(s.settled_kobo)" icon="i-lucide-check" tone="success" />
        <StatCard label="Stock value" :value="fmtNaira(s.inventory_value_kobo)" icon="i-lucide-warehouse" to="/portal/inventory" />
      </div>

      <div v-if="notes.length" class="bg-white dark:bg-zinc-900 rounded-xl border border-zinc-200 dark:border-zinc-800 p-5 mb-6">
        <h3 class="font-semibold text-zinc-700 dark:text-zinc-200 mb-1">Updates</h3>
        <p class="text-xs text-zinc-400 mb-2">Delivery progress, settlements and account notifications.</p>
        <div v-for="n in notes" :key="n.id" class="flex gap-2.5 py-2 border-b last:border-0 border-zinc-100 dark:border-zinc-800/70">
          <span class="mt-1.5 w-2 h-2 rounded-full shrink-0" :class="n.status === 'UNREAD' ? 'bg-primary-500' : 'bg-zinc-300 dark:bg-zinc-700'" />
          <div class="min-w-0">
            <p class="text-sm font-medium text-zinc-700 dark:text-zinc-300">{{ n.title }}</p>
            <p v-if="n.body" class="text-xs text-zinc-500">{{ n.body }}</p>
            <p class="text-[10px] text-zinc-400 mt-0.5">{{ fmtWhen(n.created_at) }}</p>
          </div>
        </div>
      </div>

      <div class="bg-white dark:bg-zinc-900 rounded-xl border border-zinc-200 dark:border-zinc-800 p-5">
        <h3 class="font-semibold text-zinc-700 dark:text-zinc-200 mb-2">How your account works</h3>
        <ol class="text-sm text-zinc-500 space-y-1.5 list-decimal ml-4">
          <li>Send orders on WhatsApp - we recognise your number automatically.</li>
          <li>We confirm the draft with you before it becomes an order.</li>
          <li>We deliver and collect COD from your customers.</li>
          <li>Verified collections minus agreed charges become your payable balance.</li>
          <li>Settlement batches are paid out and reflected in your statement.</li>
        </ol>
      </div>
    </template>
  </div>
</template>
