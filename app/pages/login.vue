<script setup lang="ts">
definePageMeta({ layout: false })
const { login, user } = useAuth()
const route = useRoute()
const brand = useBranding()
const colorMode = useColorMode()
const isDark = computed(() => colorMode.value === 'dark')

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
  <div class="min-h-screen flex flex-col lg:flex-row bg-white dark:bg-zinc-950">
    <!-- brand panel: follows the colour chosen in Settings -->
    <div class="lg:w-[45%] text-white p-8 lg:p-14 flex flex-col justify-between relative overflow-hidden"
         style="background-image: linear-gradient(135deg, var(--ui-color-primary-600), var(--ui-color-primary-800) 55%, var(--ui-color-primary-950))">
      <div class="flex items-center gap-3">
        <span class="rounded-xl bg-white/15 p-1"><BrandLogo :size="36" /></span>
        <div>
          <p class="text-2xl font-bold leading-none">{{ brand.brand_name }}</p>
          <p class="text-white/75 text-sm mt-1">{{ brand.tagline }}</p>
        </div>
      </div>
      <div class="my-10 lg:my-0">
        <h1 class="text-3xl lg:text-4xl font-bold leading-tight mb-4">{{ brand.login_headline }}</h1>
        <p class="text-white/85 max-w-md">{{ brand.login_text }}</p>
      </div>
      <p class="text-white/60 text-xs">© {{ new Date().getFullYear() }} {{ brand.brand_name }}</p>
    </div>

    <!-- form panel -->
    <div class="flex-1 flex items-center justify-center p-6 relative">
      <UButton
        class="absolute top-4 right-4" color="neutral" variant="ghost" size="sm"
        :icon="isDark ? 'i-lucide-sun' : 'i-lucide-moon'"
        :aria-label="isDark ? 'Switch to light mode' : 'Switch to dark mode'"
        @click="colorMode.preference = isDark ? 'light' : 'dark'"
      />
      <div class="w-full max-w-sm">
        <h2 class="text-2xl font-bold text-zinc-900 dark:text-white mb-1">Sign in</h2>
        <p class="text-sm text-zinc-500 dark:text-zinc-400 mb-6">Staff workspace or vendor portal.</p>

        <form class="space-y-4" @submit.prevent="submit">
          <UFormField label="Email">
            <UInput v-model="email" type="email" icon="i-lucide-mail" class="w-full" size="lg" placeholder="you@company.com" required />
          </UFormField>
          <UFormField label="Password">
            <UInput v-model="password" type="password" icon="i-lucide-key-round" class="w-full" size="lg" placeholder="Your password" required />
          </UFormField>
          <UAlert v-if="error" color="error" variant="subtle" icon="i-lucide-circle-alert" :title="error" />
          <UButton type="submit" size="lg" block :loading="loading" class="mt-2">
            Sign in
            <UIcon name="i-lucide-arrow-right" class="ml-1" />
          </UButton>
        </form>

        <UCard v-if="isDev" class="mt-8" :ui="{ body: 'p-3' }">
          <p class="text-[11px] font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400 mb-2">Demo accounts · password {{ 'Keyway@2026' }}</p>
          <div class="space-y-1">
            <button
              v-for="[em, desc] in demoAccounts" :key="em"
              class="w-full text-left px-2 py-1.5 rounded-lg hover:bg-zinc-100 dark:hover:bg-zinc-800 flex items-center justify-between gap-2"
              @click="email = em; password = 'Keyway@2026'"
            >
              <span class="text-xs font-mono text-zinc-700 dark:text-zinc-300">{{ em }}</span>
              <span class="text-[10px] text-zinc-500 dark:text-zinc-400 truncate">{{ desc }}</span>
            </button>
          </div>
        </UCard>
      </div>
    </div>
  </div>
</template>
