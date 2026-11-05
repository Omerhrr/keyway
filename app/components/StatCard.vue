<script setup lang="ts">
import { NuxtLink } from '#components'

defineProps<{
  label: string
  value: string | number
  icon?: string
  tone?: 'primary' | 'success' | 'warning' | 'error' | 'neutral'
  sub?: string
  to?: string
}>()

const tones: Record<string, string> = {
  primary: 'bg-primary-50 text-primary-600 dark:bg-primary-950/50 dark:text-primary-400',
  success: 'bg-emerald-50 text-emerald-600 dark:bg-emerald-950/50 dark:text-emerald-400',
  warning: 'bg-amber-50 text-amber-600 dark:bg-amber-950/50 dark:text-amber-400',
  error: 'bg-red-50 text-red-600 dark:bg-red-950/50 dark:text-red-400',
  neutral: 'bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300',
}
</script>

<template>
  <component
    :is="to ? NuxtLink : 'div'"
    :to="to"
    class="bg-white dark:bg-zinc-900 rounded-xl border border-zinc-200 dark:border-zinc-800 p-4 flex gap-3 items-start hover:shadow-sm transition-shadow"
  >
    <div v-if="icon" class="w-9 h-9 rounded-lg flex items-center justify-center shrink-0" :class="tones[tone || 'neutral']">
      <UIcon :name="icon" class="w-5 h-5" />
    </div>
    <div class="min-w-0">
      <p class="text-[11px] uppercase tracking-wide text-zinc-500 font-medium line-clamp-2 leading-snug break-words">{{ label }}</p>
      <p class="text-xl font-bold text-zinc-900 dark:text-white leading-tight truncate">{{ value }}</p>
      <p v-if="sub" class="text-[11px] text-zinc-400 line-clamp-2 leading-snug">{{ sub }}</p>
    </div>
  </component>
</template>
