<script setup lang="ts">
const { user, logout } = useAuth()
const route = useRoute()

const items = [
  { label: 'Home', to: '/portal', icon: 'i-lucide-home' },
  { label: 'Orders', to: '/portal/orders', icon: 'i-lucide-package' },
  { label: 'Inventory', to: '/portal/inventory', icon: 'i-lucide-warehouse' },
  { label: 'Statement', to: '/portal/statement', icon: 'i-lucide-file-text' },
]

async function doLogout() {
  logout()
  await navigateTo('/login')
}
</script>

<template>
  <div class="min-h-screen flex flex-col bg-zinc-50 dark:bg-zinc-950">
    <header class="sticky top-0 z-30 bg-white dark:bg-zinc-900 border-b border-zinc-200 dark:border-zinc-800">
      <div class="max-w-3xl mx-auto flex items-center gap-2.5 px-4 h-14">
        <img src="/logo.svg" alt="Keyway" class="w-7 h-7">
        <p class="font-bold text-zinc-900 dark:text-white">Keyway <span class="text-zinc-400 font-normal text-sm">Vendor Portal</span></p>
        <div class="ml-auto flex items-center gap-2">
          <UAvatar :text="(user?.full_name || 'V').slice(0, 1)" size="xs" />
          <UButton icon="i-lucide-log-out" variant="ghost" color="neutral" size="xs" aria-label="Log out" @click="doLogout" />
        </div>
      </div>
      <nav class="max-w-3xl mx-auto px-2 flex overflow-x-auto thin-scroll">
        <NuxtLink
          v-for="i in items" :key="i.to" :to="i.to"
          class="flex items-center gap-1.5 px-3 py-2.5 text-sm whitespace-nowrap border-b-2"
          :class="route.path === i.to ? 'border-primary-500 text-primary-600 font-semibold' : 'border-transparent text-zinc-500'"
        >
          <UIcon :name="i.icon" class="w-4 h-4" />
          {{ i.label }}
        </NuxtLink>
      </nav>
    </header>
    <main class="flex-1 max-w-3xl w-full mx-auto p-4 pb-16">
      <slot />
    </main>
    <footer class="mt-auto py-3 text-center text-[11px] text-zinc-400">
      Keyway Vendor Portal · installable as an app (PWA)
    </footer>
  </div>
</template>
