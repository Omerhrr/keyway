<script setup lang="ts">
definePageMeta({ layout: false })
const { login, user } = useAuth()
const route = useRoute()

// Demo credentials are only prefilled in local development builds, never in production.
const isDev = import.meta.dev
const email = ref(isDev ? 'owner@keyway.ng' : '')
const password = ref(isDev ? 'Keyway@2026' : '')
const loading = ref(false)
const error = ref('')

async function submit() {
  loading.value = true
  error.value = ''
  try {
    const u = await login(email.value.trim(), password.value)
    const raw = (route.query.next as string) || ''
    // only same-site relative paths (blocks open redirects like //evil.com or https://evil.com)
    const next = raw.startsWith('/') && !raw.startsWith('//') && !raw.startsWith('/\\') ? raw : ''
    if (next) await navigateTo(next)
    else await navigateTo(u?.is_vendor ? '/portal' : '/dashboard')
  } catch (e: any) {
    error.value = errMsg(e)
  } finally {
    loading.value = false
  }
}

const demoAccounts = [
  ['owner@keyway.ng', 'Business Owner - everything'],
  ['ops@keyway.ng', 'Operations Manager'],
  ['orders@keyway.ng', 'Order Processing'],
  ['finance@keyway.ng', 'Finance Manager'],
  ['portal@kanofashion.ng', 'Vendor Portal (Kano Fashion Hub)'],
]
</script>

<template>
  <div class="min-h-screen flex flex-col lg:flex-row">
    <!-- brand panel -->
    <div class="lg:w-[45%] bg-gradient-to-br from-emerald-600 via-emerald-700 to-emerald-900 text-white p-8 lg:p-14 flex flex-col justify-between relative overflow-hidden">
      <div class="flex items-center gap-3">
        <img src="/logo.svg" alt="Keyway" class="w-10 h-10">
        <div>
          <p class="text-2xl font-bold leading-none">Keyway</p>
          <p class="text-emerald-200 text-sm">Logistics, delivered simply</p>
        </div>
      </div>
      <div class="my-10 lg:my-0">
        <h1 class="text-3xl lg:text-4xl font-bold leading-tight mb-4">Your whole logistics operation, one workspace.</h1>
        <p class="text-emerald-100/90 max-w-md">
          WhatsApp-first order intake, vendor-owned inventory, customer confirmation, dispatch,
          COD reconciliation, settlements and a double-entry ledger - built for Nigerian logistics operators.
        </p>
        <div class="flex flex-wrap gap-2 mt-6">
          <UBadge v-for="t in ['WhatsApp Orders', 'Vendor Isolation', 'COD Tracking', 'Double-Entry Ledger', 'PWA Ready']" :key="t"
                  color="neutral" variant="outline" class="text-emerald-100 border-emerald-400/40">
            {{ t }}
          </UBadge>
        </div>
      </div>
      <p class="text-emerald-200/70 text-xs">© 2026 Keyway · Modular monolith · Nuxt + FastAPI + SQLAlchemy</p>
    </div>

    <!-- form panel -->
    <div class="flex-1 flex items-center justify-center p-6 bg-white dark:bg-zinc-950">
      <div class="w-full max-w-sm">
        <h2 class="text-2xl font-bold text-zinc-900 dark:text-white mb-1">Sign in</h2>
        <p class="text-sm text-zinc-500 mb-6">Staff workspace or vendor portal.</p>

        <form class="space-y-4" @submit.prevent="submit">
          <UFormField label="Email">
            <UInput v-model="email" type="email" icon="i-lucide-mail" class="w-full" size="lg" placeholder="you@company.ng" required />
          </UFormField>
          <UFormField label="Password">
            <UInput v-model="password" type="password" icon="i-lucide-key-round" class="w-full" size="lg" placeholder="••••••••" required />
          </UFormField>
          <UAlert v-if="error" color="error" variant="subtle" icon="i-lucide-circle-alert" :title="error" />
          <UButton type="submit" size="lg" block :loading="loading" class="mt-2">
            Sign in
            <UIcon name="i-lucide-arrow-right" class="ml-1" />
          </UButton>
        </form>

        <UCard v-if="isDev" class="mt-8" :ui="{ body: 'p-3' }">
          <p class="text-[11px] font-semibold uppercase tracking-wide text-zinc-400 mb-2">Demo accounts · password {{ 'Keyway@2026' }}</p>
          <div class="space-y-1">
            <button
              v-for="[em, desc] in demoAccounts" :key="em"
              class="w-full text-left px-2 py-1.5 rounded-lg hover:bg-zinc-100 dark:hover:bg-zinc-800 flex items-center justify-between gap-2"
              @click="email = em; password = 'Keyway@2026'"
            >
              <span class="text-xs font-mono text-zinc-700 dark:text-zinc-300">{{ em }}</span>
              <span class="text-[10px] text-zinc-400 truncate">{{ desc }}</span>
            </button>
          </div>
        </UCard>
      </div>
    </div>
  </div>
</template>
