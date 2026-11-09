<script setup lang="ts">
defineProps<{ title: string; subtitle?: string }>()
</script>

<template>
  <div class="flex flex-wrap items-start gap-3 mb-5">
    <div class="flex-1 min-w-[200px]">
      <h1 class="text-xl sm:text-2xl font-bold text-zinc-900 dark:text-white">{{ title }}</h1>
      <p v-if="subtitle" class="text-sm text-zinc-500 mt-0.5">{{ subtitle }}</p>
    </div>
    <div class="flex flex-wrap items-center gap-2">
      <slot name="actions" />
    </div>
  </div>
</template>
