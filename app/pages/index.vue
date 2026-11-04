<script setup lang="ts">
const { user, fetchMe } = useAuth()
onMounted(async () => {
  if (!user.value) await fetchMe()
  await navigateTo(user.value?.is_vendor ? '/portal' : '/dashboard', { replace: true })
})
</script>

<template>
  <div class="min-h-screen flex items-center justify-center text-zinc-400 gap-2">
    <UIcon name="i-lucide-loader-circle" class="animate-spin" />
    Opening your workspace…
  </div>
</template>
