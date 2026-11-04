<template>
  <UApp>
    <NuxtLayout>
      <NuxtPage />
    </NuxtLayout>
  </UApp>
</template>

<script setup lang="ts">
const { bind, updateReady, applyUpdate } = usePwa()

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
