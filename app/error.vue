<script setup lang="ts">
import type { NuxtError } from '#app'

const props = defineProps<{ error: NuxtError }>()

const is404 = computed(() => props.error?.statusCode === 404)
const title = computed(() => (is404.value
  ? 'Page not found'
  : `Something went wrong (${props.error?.statusCode || 'error'})`))
const detail = computed(() => {
  const d: any = props.error
  return d?.message && !d.message.includes('403') && !d.message.includes('Fetch')
    ? String(d.message) : ''
})

function goHome() {
  clearError({ redirect: '/' })
}
</script>

<template>
  <div class="min-h-screen flex items-center justify-center bg-zinc-50 dark:bg-zinc-950 p-6">
    <div class="max-w-md w-full text-center">
      <div class="w-14 h-14 rounded-2xl bg-primary-50 dark:bg-primary-950/50 flex items-center justify-center mx-auto mb-5">
        <UIcon :name="is404 ? 'i-lucide-map-pin-off' : 'i-lucide-circle-alert'" class="w-7 h-7 text-primary-600 dark:text-primary-400" />
      </div>
      <p class="text-[11px] font-semibold uppercase tracking-wider text-zinc-400 mb-1">Keyway</p>
      <h1 class="text-xl font-bold text-zinc-900 dark:text-white mb-2">{{ title }}</h1>
      <p class="text-sm text-zinc-500 mb-1">
        {{ is404
          ? 'The page you are looking for does not exist or has moved.'
          : 'An unexpected error interrupted this page. Your data is safe - the ledger records every step.' }}
      </p>
      <p v-if="detail" class="text-xs text-zinc-400 mb-5 break-words">{{ detail }}</p>
      <div class="flex items-center justify-center gap-2 mt-5">
        <UButton icon="i-lucide-layout-dashboard" @click="goHome">Back to workspace</UButton>
        <UButton color="neutral" variant="outline" icon="i-lucide-rotate-ccw" @click="clearError()">Try again</UButton>
      </div>
    </div>
  </div>
</template>
