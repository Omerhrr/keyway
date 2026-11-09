<script setup lang="ts">
const { missing, open } = useGuard()
</script>

<template>
  <UModal v-model:open="open" title="Something is missing" :ui="{ overlay: 'z-[200]', content: 'max-w-sm z-[201]' }">
    <template #body>
      <div class="flex gap-3">
        <UIcon name="i-lucide-triangle-alert" class="w-6 h-6 text-amber-500 shrink-0" />
        <div class="min-w-0">
          <p class="text-sm text-zinc-600 dark:text-zinc-300 mb-2">Please fill in:</p>
          <ul class="space-y-1">
            <li v-for="m in missing" :key="m" class="text-sm font-semibold flex items-center gap-2">
              <span class="w-1.5 h-1.5 rounded-full bg-amber-500" /> {{ m }}
            </li>
          </ul>
        </div>
      </div>
    </template>
    <template #footer>
      <div class="flex justify-end w-full"><UButton @click="open = false">Okay, go back</UButton></div>
    </template>
  </UModal>
</template>
