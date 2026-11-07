<script setup lang="ts">
const { user, logout, can } = useAuth()
const route = useRoute()
const isVendorPortal = computed(() => user.value?.is_vendor)
const { unread, items, markAllRead, markRead, startPolling, targetFor } = useNotifications()
const { canInstall, isIOS, standalone, installable, install } = usePwa()
const { online } = useOnline()
const { canOpen } = useModules()

watch(() => user.value?.id, (id) => { if (id) startPolling() }, { immediate: true })

const bellOpen = ref(false)
const bellOpenMobile = ref(false)
const showInstallHelp = ref(false)
const fmtWhen = (s: string) => s ? new Date(s).toLocaleString('en-NG', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : ''

interface NavItem { label: string; to: string; icon: string; perm?: string }
interface NavGroup { title: string; items: NavItem[] }

const groups = computed<NavGroup[]>(() => [
  {
    title: 'Operations',
    items: [
      { label: 'Dashboard', to: '/dashboard', icon: 'i-lucide-layout-dashboard', perm: 'dashboard.view' },
      { label: 'WhatsApp Inbox', to: '/conversations', icon: 'i-lucide-message-circle', perm: 'conversations.view' },
      { label: 'Order Drafts', to: '/drafts', icon: 'i-lucide-file-input', perm: 'orders.view' },
      { label: 'Orders', to: '/orders', icon: 'i-lucide-package', perm: 'orders.view' },
      { label: 'Confirmations', to: '/confirmations', icon: 'i-lucide-phone-call' },
      { label: 'Dispatch', to: '/dispatch', icon: 'i-lucide-truck', perm: 'dispatch.view' },
    ],
  },
  {
    title: 'Commerce',
    items: [
      { label: 'Vendors', to: '/vendors', icon: 'i-lucide-store', perm: 'vendors.view' },
      { label: 'Catalog', to: '/catalog', icon: 'i-lucide-boxes', perm: 'catalog.view' },
      { label: 'Inventory', to: '/inventory', icon: 'i-lucide-warehouse', perm: 'inventory.view' },
      { label: 'Customers', to: '/customers', icon: 'i-lucide-users' },
    ],
  },
  {
    title: 'Money',
    items: [
      { label: 'COD', to: '/cod', icon: 'i-lucide-banknote', perm: 'cod.manage' },
      { label: 'Settlements', to: '/settlements', icon: 'i-lucide-receipt-text', perm: 'settlements.manage' },
      { label: 'Finance', to: '/finance', icon: 'i-lucide-landmark', perm: 'finance.manage' },
    ],
  },
  {
    title: 'Insights & Admin',
    items: [
      { label: 'Reports', to: '/reports', icon: 'i-lucide-bar-chart-3', perm: 'reports.view' },
      { label: 'Settings', to: '/settings', icon: 'i-lucide-settings', perm: 'settings.manage' },
      { label: 'Audit Trail', to: '/audit', icon: 'i-lucide-shield-check', perm: 'audit.view' },
    ],
  },
])

const visibleGroups = computed(() =>
  groups.value
    .map((g) => ({ ...g, items: g.items.filter((i) => canOpen(i.to)) }))
    .filter((g) => g.items.length),
)

const mobileOpen = ref(false)
const mobileNav = computed(() => visibleGroups.value.flatMap((g) => g.items))
const primaryMobile = computed(() => mobileNav.value.slice(0, 4))
const brand = useBranding()
const colorMode = useColorMode()
const isDark = computed(() => colorMode.value === 'dark')
function toggleTheme() {
  colorMode.preference = isDark.value ? 'light' : 'dark'
}

async function doLogout() {
  logout()
  await navigateTo('/login')
}

async function installApp() {
  // Chrome/Edge/Android fire beforeinstallprompt; iOS Safari needs manual steps
  if (!canInstall && isIOS) { showInstallHelp.value = true; return }
  const ok = await install()
  if (ok) useToast().add({ title: 'App installed', description: 'Launch it from your home screen.', color: 'success' })
}
</script>

<template>
  <div class="min-h-screen flex flex-col bg-zinc-50 dark:bg-zinc-950">
    <!-- Desktop sidebar -->
    <aside class="hidden lg:flex flex-col fixed inset-y-0 left-0 w-60 border-r border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 z-30">
      <div class="flex items-center gap-2.5 px-5 h-16 border-b border-zinc-200 dark:border-zinc-800">
        <BrandLogo :size="32" />
        <div>
          <p class="font-bold text-lg leading-none text-zinc-900 dark:text-white">{{ brand.brand_name }}</p>
          <p class="text-[11px] text-zinc-500 truncate max-w-[150px]">{{ brand.tagline }}</p>
        </div>
      </div>
      <nav class="flex-1 overflow-y-auto thin-scroll px-3 py-4 space-y-5">
        <div v-for="g in visibleGroups" :key="g.title">
          <p class="px-2.5 mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-zinc-400">{{ g.title }}</p>
          <NuxtLink
            v-for="item in g.items" :key="item.to" :to="item.to"
            class="flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-sm transition-colors"
            :class="route.path.startsWith(item.to)
              ? 'bg-primary-50 dark:bg-primary-950/40 text-primary-600 dark:text-primary-400 font-semibold'
              : 'text-zinc-600 dark:text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800'"
          >
            <UIcon :name="item.icon" class="w-[18px] h-[18px] shrink-0" />
            {{ item.label }}
          </NuxtLink>
        </div>
      </nav>
      <div class="p-3 border-t border-zinc-200 dark:border-zinc-800">
        <div class="flex items-center gap-2.5 px-2 py-1.5">
          <UAvatar :text="(user?.full_name || 'K').slice(0, 1)" size="sm" />
          <div class="min-w-0 flex-1">
            <p class="text-sm font-medium truncate text-zinc-800 dark:text-zinc-200">{{ user?.full_name }}</p>
            <p class="text-[11px] text-zinc-500 truncate">{{ user?.role_name }}</p>
          </div>
          <UButton icon="i-lucide-log-out" variant="ghost" color="neutral" size="xs" @click="doLogout" aria-label="Log out" />
        </div>
      </div>
    </aside>

    <!-- Mobile topbar -->
    <header class="lg:hidden sticky top-0 z-30 bg-white dark:bg-zinc-900 border-b border-zinc-200 dark:border-zinc-800 h-14 flex items-center px-4 gap-3">
      <BrandLogo :size="28" />
      <p class="font-bold text-zinc-900 dark:text-white flex-1">{{ brand.brand_name }}</p>
      <UPopover v-model:open="bellOpenMobile" :popper="{ placement: 'bottom-end' }">
        <UButton icon="i-lucide-bell" variant="ghost" color="neutral" aria-label="Notifications" class="relative">
          <span v-if="unread" class="absolute -top-0.5 -right-0.5 min-w-[18px] h-[18px] px-1 rounded-full bg-red-500 text-white text-[10px] font-bold flex items-center justify-center">{{ unread > 99 ? '99+' : unread }}</span>
        </UButton>
        <template #content>
          <div class="w-[330px] max-w-[86vw]">
            <div class="flex items-center justify-between px-3 py-2 border-b border-zinc-200 dark:border-zinc-800">
              <p class="text-sm font-semibold">Notifications</p>
              <UButton size="xs" variant="ghost" color="neutral" icon="i-lucide-check-check" :disabled="!unread" @click="markAllRead">Mark all read</UButton>
            </div>
            <div class="max-h-[380px] overflow-y-auto thin-scroll">
              <div v-if="!items.length" class="px-4 py-8 text-center text-sm text-zinc-400">No notifications yet</div>
              <button v-for="n in items" :key="n.id" class="w-full text-left px-3 py-2.5 border-b border-zinc-100 dark:border-zinc-800/60 hover:bg-zinc-50 dark:hover:bg-zinc-800/50 flex gap-2.5"
                      :class="n.status === 'UNREAD' ? 'bg-primary-50/40 dark:bg-primary-950/20' : ''"
                      @click="markRead(n); targetFor(n) && navigateTo(targetFor(n)); bellOpen = false">
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
      <UButton icon="i-lucide-menu" variant="ghost" color="neutral" aria-label="Open menu" @click="mobileOpen = true" />
    </header>

    <!-- Mobile nav slideover -->
    <USlideover v-model:open="mobileOpen" side="left" :ui="{ content: 'max-w-[280px]' }">
      <template #content>
        <div class="flex flex-col h-full bg-white dark:bg-zinc-900">
          <div class="flex items-center gap-2 px-4 h-14 border-b border-zinc-200 dark:border-zinc-800">
            <BrandLogo :size="28" />
            <p class="font-bold">{{ brand.brand_name }}</p>
            <UButton class="ml-auto" icon="i-lucide-x" variant="ghost" color="neutral" size="sm" aria-label="Close menu" @click="mobileOpen = false" />
          </div>
          <nav class="flex-1 overflow-y-auto p-3 space-y-4">
            <div v-for="g in visibleGroups" :key="g.title">
              <p class="px-2 mb-1 text-[10px] font-semibold uppercase tracking-wider text-zinc-400">{{ g.title }}</p>
              <NuxtLink
                v-for="item in g.items" :key="item.to" :to="item.to" @click="mobileOpen = false"
                class="flex items-center gap-2.5 px-2.5 py-2.5 rounded-lg text-sm"
                :class="route.path.startsWith(item.to) ? 'bg-primary-50 text-primary-600 font-semibold' : 'text-zinc-600 dark:text-zinc-400'"
              >
                <UIcon :name="item.icon" class="w-[18px] h-[18px]" />
                {{ item.label }}
              </NuxtLink>
            </div>
          </nav>
          <div class="p-3 border-t border-zinc-200 dark:border-zinc-800 flex items-center gap-2">
            <UAvatar :text="(user?.full_name || 'K').slice(0, 1)" size="sm" />
            <div class="flex-1 min-w-0">
              <p class="text-sm truncate">{{ user?.full_name }}</p>
              <p class="text-[11px] text-zinc-500 truncate">{{ user?.email }}</p>
            </div>
            <UButton :icon="isDark ? 'i-lucide-sun' : 'i-lucide-moon'" variant="ghost" color="neutral" size="xs"
                     :aria-label="isDark ? 'Switch to light mode' : 'Switch to dark mode'" @click="toggleTheme" />
            <UButton icon="i-lucide-log-out" variant="ghost" color="neutral" size="xs" @click="doLogout" aria-label="Log out" />
          </div>
        </div>
      </template>
    </USlideover>

    <!-- Main -->
    <main class="flex-1 lg:pl-60 flex flex-col">
      <!-- Offline banner -->
      <div v-if="!online" class="bg-amber-500 text-white text-sm font-medium text-center py-1.5 px-4">
        <UIcon name="i-lucide-wifi-off" class="w-4 h-4 inline-block align-[-2px] mr-1" />
        You are offline - showing cached data. Changes will fail until the connection returns.
      </div>
      <!-- Desktop topbar: theme, notifications + install -->
      <div class="hidden lg:flex h-12 items-center justify-end gap-2 px-6 border-b border-zinc-200 dark:border-zinc-800 bg-white/70 dark:bg-zinc-900/70 backdrop-blur sticky top-0 z-20">
        <UButton :icon="isDark ? 'i-lucide-sun' : 'i-lucide-moon'" size="xs" variant="ghost" color="neutral"
                 :aria-label="isDark ? 'Switch to light mode' : 'Switch to dark mode'" @click="toggleTheme" />
        <UButton v-if="installable" icon="i-lucide-download" size="xs" variant="soft" color="primary" @click="installApp">
          {{ canInstall ? 'Install app' : 'Install on iPhone' }}
        </UButton>
        <UPopover v-model:open="bellOpen" :popper="{ placement: 'bottom-end' }">
          <UButton icon="i-lucide-bell" variant="ghost" color="neutral" aria-label="Notifications" class="relative">
            <span v-if="unread" class="absolute -top-0.5 -right-0.5 min-w-[18px] h-[18px] px-1 rounded-full bg-red-500 text-white text-[10px] font-bold flex items-center justify-center">{{ unread > 99 ? '99+' : unread }}</span>
          </UButton>
          <template #content>
            <div class="w-[360px] max-w-[90vw]">
              <div class="flex items-center justify-between px-3 py-2 border-b border-zinc-200 dark:border-zinc-800">
                <p class="text-sm font-semibold">Notifications</p>
                <UButton size="xs" variant="ghost" color="neutral" icon="i-lucide-check-check" :disabled="!unread" @click="markAllRead">Mark all read</UButton>
              </div>
              <div class="max-h-[380px] overflow-y-auto thin-scroll">
                <div v-if="!items.length" class="px-4 py-8 text-center text-sm text-zinc-400">No notifications yet</div>
                <button v-for="n in items" :key="n.id" class="w-full text-left px-3 py-2.5 border-b border-zinc-100 dark:border-zinc-800/60 hover:bg-zinc-50 dark:hover:bg-zinc-800/50 flex gap-2.5"
                        :class="n.status === 'UNREAD' ? 'bg-primary-50/40 dark:bg-primary-950/20' : ''"
                        @click="markRead(n); targetFor(n) && navigateTo(targetFor(n)); bellOpen = false">
                  <span class="mt-0.5 w-2 h-2 rounded-full shrink-0" :class="n.status === 'UNREAD' ? 'bg-primary-500' : 'bg-zinc-300 dark:bg-zinc-700'" />
                  <span class="min-w-0 flex-1">
                    <span class="block text-sm font-medium truncate" :class="n.status === 'FAILED' ? 'text-red-500' : ''">{{ n.title }}</span>
                    <span v-if="n.body" class="block text-xs text-zinc-500 line-clamp-2">{{ n.body }}</span>
                    <span class="block text-[10px] text-zinc-400 mt-0.5">{{ fmtWhen(n.created_at) }} · {{ n.channel === 'IN_APP' ? (n.status === 'FAILED' ? 'failed' : 'in-app') : n.channel.toLowerCase() }}</span>
                  </span>
                </button>
              </div>
            </div>
          </template>
        </UPopover>
      </div>
      <div class="flex-1 p-4 sm:p-6 pb-24 lg:pb-6">
        <slot />
      </div>
      <footer class="hidden lg:block mt-auto py-3 px-6 text-[11px] text-zinc-400 border-t border-zinc-200 dark:border-zinc-800">
        {{ brand.brand_name }} · Amounts in Naira
      </footer>
    </main>

    <!-- Mobile bottom nav -->
    <nav class="lg:hidden fixed bottom-0 inset-x-0 z-30 bg-white dark:bg-zinc-900 border-t border-zinc-200 dark:border-zinc-800 safe-bottom">
      <div class="grid grid-cols-5 h-16">
        <NuxtLink
          v-for="item in mobileNav.slice(0, 4)" :key="item.to"
          :to="item.to"
          class="flex flex-col items-center justify-center gap-0.5 text-[10px]"
          :class="route.path.startsWith(item.to) ? 'text-primary-600 font-semibold' : 'text-zinc-500'"
        >
          <UIcon :name="item.icon" class="w-5 h-5" />
          {{ item.label.split(' ')[0] }}
        </NuxtLink>
        <button
          class="flex flex-col items-center justify-center gap-0.5 text-[10px] text-zinc-500"
          @click="mobileOpen = true"
        >
          <UIcon name="i-lucide-menu" class="w-5 h-5" />
          More
        </button>
      </div>
    </nav>

    <!-- iOS install help (Safari has no programmatic install prompt) -->
    <UModal v-model:open="showInstallHelp" :title="`Add ${brand.brand_name} to your iPhone or iPad`">
      <template #body>
        <ol class="list-decimal list-inside space-y-2.5 text-sm text-zinc-700 dark:text-zinc-300">
          <li>Open this website in <strong>Safari</strong> (this only works in Safari).</li>
          <li>Tap the <strong>Share</strong> button <UIcon name="i-lucide-share" class="w-4 h-4 inline-block align-[-3px]" /> in the toolbar.</li>
          <li>Scroll and tap <strong>Add to Home Screen</strong>.</li>
          <li>Tap <strong>Add</strong> - it opens full-screen like any other app.</li>
        </ol>
        <p class="text-xs text-zinc-400 mt-4">Already added? This button hides itself once the app is on your home screen.</p>
      </template>
      <template #footer>
        <div class="flex justify-end w-full">
          <UButton color="primary" @click="showInstallHelp = false">Got it</UButton>
        </div>
      </template>
    </UModal>
  </div>
</template>
