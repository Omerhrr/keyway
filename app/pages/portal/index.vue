<script setup lang="ts">
definePageMeta({ layout: 'portal' })
const s = ref<any>(null)
const loading = ref(true)
onMounted(async () => {
  try { s.value = await api('/portal/summary') } finally { loading.value = false }
})
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
