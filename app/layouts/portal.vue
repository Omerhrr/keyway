<script setup lang="ts">
const { user, logout } = useAuth()
const route = useRoute()
const { unread, items: notifItems, markAllRead, markRead, startPolling, targetFor } = useNotifications()
const { canInstall, isIOS, installable, install } = usePwa()
const { online } = useOnline()

watch(() => user.value?.id, (id) => { if (id) startPolling() }, { immediate: true })

const navItems = [
  { label: 'Home', to: '/portal', icon: 'i-lucide-home' },
  { label: 'Orders', to: '/portal/orders', icon: 'i-lucide-package' },
  { label: 'Inventory', to: '/portal/inventory', icon: 'i-lucide-warehouse' },
  { label: 'Statement', to: '/portal/statement', icon: 'i-lucide-file-text' },
]

const bellOpen = ref(false)
const showInstallHelp = ref(false)
const fmtWhen = (s: string) => s ? new Date(s).toLocaleString('en-NG', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : ''

/** Portal users live under /portal/* - map notification targets to vendor-safe routes. */
function portalTarget(n: any): string {
  const et = n.entity_type
  if (['order', 'draft'].includes(et)) return '/portal/orders'
  if (['inventory_balance', 'stock_transfer'].includes(et)) return '/portal/inventory'
  if (et === 'settlement') return '/portal/statement'
  return ''
}

async function doLogout() {
  logout()
  await navigateTo('/login')
}

async function installApp() {
  if (!canInstall && isIOS) { showInstallHelp.value = true; return }
  const ok = await install()
  if (ok) useToast().add({ title: 'Keyway installed', description: 'Launch it from your home screen.', color: 'success' })
}
</script>

<template>
  <div class="min-h-screen flex flex-col bg-zinc-50 dark:bg-zinc-950">
    <header class="sticky top-0 z-30 bg-white dark:bg-zinc-900 border-b border-zinc-200 dark:border-zinc-800">
      <div class="max-w-3xl mx-auto flex items-center gap-2.5 px-4 h-14">
        <img src="/logo.svg" alt="Keyway" class="w-7 h-7">
        <p class="font-bold text-zinc-900 dark:text-white">Keyway <span class="text-zinc-400 font-normal text-sm">Vendor Portal</span></p>
        <div class="ml-auto flex items-center gap-1.5">
          <UButton v-if="installable" icon="i-lucide-download" size="xs" variant="soft" color="primary" @click="installApp">
            {{ canInstall ? 'Install' : 'Add to Home Screen' }}
          </UButton>
          <UPopover v-model:open="bellOpen" :popper="{ placement: 'bottom-end' }">
            <UButton icon="i-lucide-bell" variant="ghost" color="neutral" size="xs" aria-label="Notifications" class="relative">
              <span v-if="unread" class="absolute -top-0.5 -right-0.5 min-w-[18px] h-[18px] px-1 rounded-full bg-red-500 text-white text-[10px] font-bold flex items-center justify-center">{{ unread > 99 ? '99+' : unread }}</span>
            </UButton>
            <template #content>
              <div class="w-[330px] max-w-[86vw]">
                <div class="flex items-center justify-between px-3 py-2 border-b border-zinc-200 dark:border-zinc-800">
                  <p class="text-sm font-semibold">Notifications</p>
                  <UButton size="xs" variant="ghost" color="neutral" icon="i-lucide-check-check" :disabled="!unread" @click="markAllRead">Mark all read</UButton>
                </div>
                <div class="max-h-[380px] overflow-y-auto thin-scroll">
                  <div v-if="!notifItems.length" class="px-4 py-8 text-center text-sm text-zinc-400">No notifications yet</div>
                  <button v-for="n in notifItems" :key="n.id" class="w-full text-left px-3 py-2.5 border-b border-zinc-100 dark:border-zinc-800/60 hover:bg-zinc-50 dark:hover:bg-zinc-800/50 flex gap-2.5"
                          :class="n.status === 'UNREAD' ? 'bg-primary-50/40 dark:bg-primary-950/20' : ''"
                          @click="markRead(n); portalTarget(n) && navigateTo(portalTarget(n)); bellOpen = false">
                    <span class="mt-0.5 w-2 h-2 rounded-full shrink-0" :class="n.status === 'UNREAD' ? 'bg-primary-500' : 'bg-zinc-300 dark:bg-zinc-700'" />
                    <span class="min-w-0 flex-1">
                      <span class="block text-sm font-medium truncate">{{ n.title }}</span>
                      <span v-if="n.body" class="block text-xs text-zinc-500 line-clamp-2">{{ n.body }}</span>
                      <span class="block text-[10px] text-zinc-400 mt-0.5">{{ fmtWhen(n.created_at) }}</span>
                    </span>
                  </button>
                </div>
              </div>
            </template>
          </UPopover>
          <UAvatar :text="(user?.full_name || 'V').slice(0, 1)" size="xs" />
          <UButton icon="i-lucide-log-out" variant="ghost" color="neutral" size="xs" aria-label="Log out" @click="doLogout" />
        </div>
      </div>
      <nav class="max-w-3xl mx-auto px-2 flex overflow-x-auto thin-scroll">
        <NuxtLink
          v-for="i in navItems" :key="i.to" :to="i.to"
          class="flex items-center gap-1.5 px-3 py-2.5 text-sm whitespace-nowrap border-b-2"
          :class="route.path === i.to ? 'border-primary-500 text-primary-600 font-semibold' : 'border-transparent text-zinc-500'"
        >
          <UIcon :name="i.icon" class="w-4 h-4" />
          {{ i.label }}
        </NuxtLink>
      </nav>
    </header>
    <div v-if="!online" class="bg-amber-500 text-white text-sm font-medium text-center py-1.5 px-4">
      <UIcon name="i-lucide-wifi-off" class="w-4 h-4 inline-block align-[-2px] mr-1" />
      You are offline - showing cached data.
    </div>
    <main class="flex-1 max-w-3xl w-full mx-auto p-4 pb-16">
      <slot />
    </main>
    <footer class="mt-auto py-3 text-center text-[11px] text-zinc-400">
      Keyway Vendor Portal · installable as an app (PWA)
    </footer>

    <!-- iOS install help (Safari has no programmatic install prompt) -->
    <UModal v-model:open="showInstallHelp" title="Install Keyway on your iPhone / iPad">
      <template #body>
        <ol class="list-decimal list-inside space-y-2.5 text-sm text-zinc-700 dark:text-zinc-300">
          <li>Open <strong>keyway</strong> in <strong>Safari</strong> (installing requires Safari).</li>
          <li>Tap the <strong>Share</strong> button <UIcon name="i-lucide-share" class="w-4 h-4 inline-block align-[-3px]" /> in the toolbar.</li>
          <li>Scroll and tap <strong>Add to Home Screen</strong>.</li>
          <li>Tap <strong>Add</strong> - Keyway launches full-screen like a native app.</li>
        </ol>
      </template>
      <template #footer>
        <div class="flex justify-end w-full">
          <UButton color="primary" @click="showInstallHelp = false">Got it</UButton>
        </div>
      </template>
    </UModal>
  </div>
</template>
