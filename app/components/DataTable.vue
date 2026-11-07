<script setup lang="ts">
export interface Column {
  key: string
  label: string
  align?: 'left' | 'right' | 'center'
  class?: string
}

const props = withDefaults(defineProps<{
  columns: Column[]
  rows: any[]
  loading?: boolean
  clickable?: boolean
  emptyTitle?: string
  emptyHint?: string
  /** Show Print PDF and Export Excel buttons. The title is used as the document heading and file name. */
  exportTitle?: string
}>(), { emptyTitle: 'Nothing here yet', emptyHint: '' })

const emit = defineEmits<{ (e: 'row-click', row: any): void }>()

const tableEl = ref<HTMLTableElement | null>(null)
const { printTable, exportExcel } = useDocs()
const busy = ref(false)

/** Read exactly what is on screen (so amounts, dates and labels match), skipping button columns. */
function snapshot() {
  const t = tableEl.value
  if (!t) return { head: [] as string[], rows: [] as string[][], right: [] as boolean[] }
  const ths = Array.from(t.querySelectorAll('thead th'))
  const keep = ths.map((th, i) => ((th.textContent || '').trim() !== '' && props.columns[i]?.key !== 'actions') ? i : -1).filter((i) => i >= 0)
  const clean = (el: Element | undefined) => (el?.textContent || '').replace(/\s+/g, ' ').trim()
  const rows = Array.from(t.querySelectorAll('tbody tr'))
    .filter((tr) => tr.children.length === ths.length)
    .map((tr) => keep.map((i) => clean(tr.children[i])))
  return { head: keep.map((i) => clean(ths[i])), rows, right: keep.map((i) => props.columns[i]?.align === 'right') }
}

async function doPrint() {
  const { head, rows, right } = snapshot()
  busy.value = true
  try { await printTable({ title: props.exportTitle || 'Records', columns: head, rows, rightAlign: right }) } finally { busy.value = false }
}
async function doExcel() {
  const { head, rows } = snapshot()
  busy.value = true
  try { await exportExcel(props.exportTitle || 'Records', head, rows) }
  catch (e: any) { useToast().add({ title: 'Could not export', description: errMsg(e), color: 'error' }) }
  finally { busy.value = false }
}
</script>

<template>
  <div>
  <div v-if="exportTitle && rows.length && !loading" class="flex justify-end gap-2 mb-2 print:hidden">
    <UButton size="xs" color="neutral" variant="outline" icon="i-lucide-printer" :disabled="busy" @click="doPrint">Print PDF</UButton>
    <UButton size="xs" color="neutral" variant="outline" icon="i-lucide-file-spreadsheet" :disabled="busy" @click="doExcel">Export Excel</UButton>
  </div>
  <div class="bg-white dark:bg-zinc-900 rounded-xl border border-zinc-200 dark:border-zinc-800 overflow-hidden">
    <div class="overflow-x-auto thin-scroll">
      <table ref="tableEl" class="w-full text-sm min-w-[640px]">
        <thead>
          <tr class="border-b border-zinc-200 dark:border-zinc-800 bg-zinc-50/60 dark:bg-zinc-800/40">
            <th
              v-for="c in columns" :key="c.key"
              class="px-4 py-2.5 text-left font-semibold text-zinc-500 dark:text-zinc-400 text-[11px] uppercase tracking-wide whitespace-nowrap"
              :class="[c.align === 'right' ? 'text-right' : '', /(date|when|added|created|expected|time)$/i.test(c.key) ? 'whitespace-nowrap' : '', c.class]"
            >
              {{ c.label }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="loading">
            <td :colspan="columns.length" class="px-4 py-10 text-center text-zinc-400">
              <UIcon name="i-lucide-loader-circle" class="w-5 h-5 animate-spin inline-block" />
              <span class="ml-2">Loading...</span>
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
              :class="[c.align === 'right' ? 'text-right' : '', /(date|when|added|created|expected|time)$/i.test(c.key) ? 'whitespace-nowrap' : '', c.class]"
            >
              <slot :name="c.key" :row="row" :value="row[c.key]">
                <span class="text-zinc-700 dark:text-zinc-300">{{ row[c.key] ?? '-' }}</span>
              </slot>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
  </div>
</template>
