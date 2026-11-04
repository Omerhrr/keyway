<script setup lang="ts">
export interface Column {
  key: string
  label: string
  align?: 'left' | 'right' | 'center'
  class?: string
}

withDefaults(defineProps<{
  columns: Column[]
  rows: any[]
  loading?: boolean
  clickable?: boolean
  emptyTitle?: string
  emptyHint?: string
}>(), { emptyTitle: 'Nothing here yet', emptyHint: '' })

const emit = defineEmits<{ (e: 'row-click', row: any): void }>()
</script>

<template>
  <div class="bg-white dark:bg-zinc-900 rounded-xl border border-zinc-200 dark:border-zinc-800 overflow-hidden">
    <div class="overflow-x-auto thin-scroll">
      <table class="w-full text-sm min-w-[640px]">
        <thead>
          <tr class="border-b border-zinc-200 dark:border-zinc-800 bg-zinc-50/60 dark:bg-zinc-800/40">
            <th
              v-for="c in columns" :key="c.key"
              class="px-4 py-2.5 text-left font-semibold text-zinc-500 dark:text-zinc-400 text-[11px] uppercase tracking-wide whitespace-nowrap"
              :class="[c.align === 'right' ? 'text-right' : '', c.class]"
            >
              {{ c.label }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="loading">
            <td :colspan="columns.length" class="px-4 py-10 text-center text-zinc-400">
              <UIcon name="i-lucide-loader-circle" class="w-5 h-5 animate-spin inline-block" />
              <span class="ml-2">Loading…</span>
            </td>
          </tr>
          <tr v-else-if="!rows.length">
            <td :colspan="columns.length" class="px-4 py-10 text-center">
              <p class="text-zinc-500 font-medium">{{ emptyTitle }}</p>
              <p v-if="emptyHint" class="text-zinc-400 text-xs mt-1">{{ emptyHint }}</p>
            </td>
          </tr>
          <tr
            v-else
            v-for="(row, idx) in rows" :key="row.id ?? idx"
            class="border-b border-zinc-100 dark:border-zinc-800/60 last:border-0 hover:bg-zinc-50 dark:hover:bg-zinc-800/40 transition-colors"
            :class="clickable ? 'cursor-pointer' : ''"
            @click="clickable ? emit('row-click', row) : undefined"
          >
            <td
              v-for="c in columns" :key="c.key"
              class="px-4 py-2.5 align-middle"
              :class="[c.align === 'right' ? 'text-right' : '', c.class]"
            >
              <slot :name="c.key" :row="row" :value="row[c.key]">
                <span class="text-zinc-700 dark:text-zinc-300">{{ row[c.key] ?? '—' }}</span>
              </slot>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
