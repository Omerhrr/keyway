<template>
  <UApp>
    <NuxtLayout>
      <NuxtPage />
    </NuxtLayout>
    <GuardDialog />
  </UApp>
</template>

<script setup lang="ts">
const { bind, updateReady, applyUpdate } = usePwa()

// Per-page document titles: "Orders · Keyway" instead of one static title.
const route = useRoute()
const brand = useBranding()
const pageTitles: Record<string, string> = {
  '/dashboard': 'Dashboard',
  '/conversations': 'WhatsApp Inbox',
  '/drafts': 'Order Drafts',
  '/orders': 'Orders',
  '/confirmations': 'Confirmations',
  '/dispatch': 'Dispatch',
  '/vendors': 'Vendors',
  '/catalog': 'Catalog',
  '/inventory': 'Inventory & Warehouse',
  '/customers': 'Customers',
  '/cod': 'COD Collections',
  '/settlements': 'Settlements',
  '/finance': 'Finance',
  '/reports': 'Reports',
  '/settings': 'Settings',
  '/audit': 'Audit Trail',
  '/portal': 'Vendor Portal',
  '/portal/orders': 'My Orders',
  '/portal/inventory': 'My Stock',
  '/portal/statement': 'My Statement',
}
useHead({
  title: () => {
    if (route.path === '/login') return `Sign in · ${brand.value.brand_name}`
    const base = pageTitles[route.path]
      || (route.path.startsWith('/portal') ? 'Vendor Portal' : undefined)
      || (route.path.startsWith('/orders/') ? 'Order' : undefined)
    return base ? `${base} · ${brand.value.brand_name}` : brand.value.brand_name
  },
})

onMounted(() => {
  // Service worker only in production builds: in dev, Vite serves mutable
  // module URLs that must never be cached (stale assets break hydration).
  if (!import.meta.dev && 'serviceWorker' in navigator) {
    navigator.serviceWorker.register('/sw.js').catch(() => {})
  }
  bind()

  // surface a waiting service worker as a dismissible toast
  watch(updateReady, (ready) => {
    if (!ready) return
    useToast().add({
      title: 'Update available',
      description: 'A new version of Keyway is ready.',
      color: 'info',
      icon: 'i-lucide-refresh-cw',
      timeout: 0,
      actions: [{ label: 'Reload', onClick: () => applyUpdate() }],
    })
  }, { immediate: true })
})
</script>
