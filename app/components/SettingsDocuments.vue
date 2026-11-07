<script setup lang="ts">
import { DEFAULT_DOCS, TEMPLATE_INFO, buildTableDoc, type DocSettings } from '~/utils/documents'
import { COLOR_PRESETS } from '~/utils/theme'

const docs = useDocs()
const brand = useBranding()
const { user } = useAuth()
const form = reactive<DocSettings>({ ...DEFAULT_DOCS })
const saving = ref(false)

onMounted(async () => {
  Object.assign(form, await docs.load(true))
  if (!form.company_name) form.company_name = brand.value.brand_name
})

const sample = {
  title: 'Orders',
  subtitle: 'Sample preview',
  columns: ['Reference', 'Customer', 'Status', 'Amount'],
  rows: [
    ['KW-1001', 'Amaka Obi', 'Delivered', '₦12,500'],
    ['KW-1002', 'Tunde Bello', 'Out For Delivery', '₦8,000'],
    ['KW-1003', 'Zainab Musa', 'Confirmed', '₦21,750'],
    ['KW-1004', 'Chidi Eze', 'New', '₦5,400'],
  ] as (string | number)[][],
  rightAlign: [false, false, false, true],
}

const html = computed(() => buildTableDoc(sample, {
  settings: { ...form }, preparedBy: user.value?.full_name, fallbackName: brand.value.brand_name,
}))

const papers = ['A4', 'A5', 'Letter'].map((v) => ({ label: v, value: v }))
const orients = [{ label: 'Automatic', value: 'auto' }, { label: 'Portrait', value: 'portrait' }, { label: 'Landscape', value: 'landscape' }]
const hexOk = computed(() => /^#[0-9a-fA-F]{6}$/.test(form.accent))

async function save() {
  if (!hexOk.value) {
    useToast().add({ title: 'Pick a valid colour', color: 'error' })
    return
  }
  saving.value = true
  try {
    const res = await api<DocSettings>('/settings/documents', { method: 'PUT', body: { ...form } })
    Object.assign(docs.settings.value, res)
    useToast().add({ title: 'Print layout saved', color: 'success' })
  } catch (e: any) {
    useToast().add({ title: 'Could not save', description: errMsg(e), color: 'error' })
  } finally {
    saving.value = false
  }
}
const toggles: [keyof DocSettings, string][] = [
  ['show_logo', 'Show logo'], ['show_date', 'Show date'], ['show_prepared_by', 'Show who printed it'],
  ['show_row_numbers', 'Number the rows'], ['show_signatures', 'Signature lines at the bottom'],
]
</script>

<template>
  <div class="grid xl:grid-cols-2 gap-6">
    <div class="space-y-5">
      <UCard>
        <template #header><p class="font-semibold">Template</p></template>
        <div class="grid sm:grid-cols-2 gap-2">
          <button
            v-for="t in TEMPLATE_INFO" :key="t.value" type="button"
            class="text-left p-3 rounded-lg border transition"
            :class="form.template === t.value ? 'border-primary-500 bg-primary-50 dark:bg-primary-950/40' : 'border-zinc-200 dark:border-zinc-800 hover:border-zinc-400'"
            @click="form.template = t.value as any"
          >
            <p class="font-medium text-zinc-900 dark:text-white">{{ t.label }}</p>
            <p class="text-xs text-zinc-500 dark:text-zinc-400">{{ t.hint }}</p>
          </button>
        </div>
        <div class="flex flex-wrap gap-2 mt-4 items-center">
          <span class="text-sm text-zinc-600 dark:text-zinc-300 mr-1">Accent colour</span>
          <button v-for="c in COLOR_PRESETS" :key="c.hex" type="button" :title="c.name" class="w-6 h-6 rounded-full"
                  :class="form.accent.toLowerCase() === c.hex ? 'ring-2 ring-offset-2 ring-zinc-900 dark:ring-white dark:ring-offset-zinc-900' : ''"
                  :style="{ background: c.hex }" @click="form.accent = c.hex" />
          <UInput v-model="form.accent" class="w-28 font-mono" size="sm" maxlength="7" />
        </div>
      </UCard>

      <UCard>
        <template #header><p class="font-semibold">Business details on the page</p></template>
        <div class="grid sm:grid-cols-2 gap-3">
          <UFormField label="Business name"><UInput v-model="form.company_name" class="w-full" maxlength="80" /></UFormField>
          <UFormField label="Phone"><UInput v-model="form.phone" class="w-full" maxlength="40" /></UFormField>
          <UFormField label="Email"><UInput v-model="form.email" class="w-full" maxlength="80" /></UFormField>
          <UFormField label="Address"><UInput v-model="form.address" class="w-full" maxlength="200" /></UFormField>
        </div>
        <UFormField label="Note at the bottom" class="mt-3"><UInput v-model="form.footer_text" class="w-full" maxlength="200" /></UFormField>
      </UCard>

      <UCard>
        <template #header><p class="font-semibold">Page</p></template>
        <div class="grid sm:grid-cols-2 gap-4">
          <UFormField label="Paper size"><URadioGroup v-model="form.paper" :items="papers" orientation="horizontal" /></UFormField>
          <UFormField label="Direction"><URadioGroup v-model="form.orientation" :items="orients" orientation="horizontal" /></UFormField>
        </div>
        <div class="grid sm:grid-cols-2 gap-2 mt-4">
          <USwitch v-for="[k, label] in toggles" :key="k" v-model="(form as any)[k]" :label="label" />
        </div>
      </UCard>

      <UButton :loading="saving" icon="i-lucide-check" @click="save">Save print layout</UButton>
    </div>

    <div>
      <p class="text-xs font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400 mb-2">Live preview</p>
      <div class="border border-zinc-200 dark:border-zinc-800 rounded-xl overflow-hidden bg-zinc-100 dark:bg-zinc-800 p-3">
        <div class="bg-white shadow mx-auto overflow-hidden" style="width:100%;aspect-ratio:1/1.1">
          <iframe :srcdoc="html" class="w-full h-full border-0 bg-white" title="Print preview" sandbox="" />
        </div>
      </div>
      <p class="text-xs text-zinc-500 dark:text-zinc-400 mt-2">Use the Print PDF button on any list. In the print window choose "Save as PDF".</p>
    </div>
  </div>
</template>
