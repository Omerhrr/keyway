<script setup lang="ts">
import { DEFAULT_DOCS, TEMPLATE_INFO, buildTableDoc, buildRecordDoc, type DocSettings } from '~/utils/documents'
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

const previewKind = ref<'list' | 'order'>('list')
const html = computed(() => {
  const ctx = { settings: { ...form }, preparedBy: user.value?.full_name, fallbackName: brand.value.brand_name }
  if (previewKind.value === 'list') return buildTableDoc(sample, ctx, true)
  return buildRecordDoc({
    title: 'Order KW-1001', subtitle: 'Kano Fashion Hub',
    fields: [['Status', 'Delivered'], ['Customer', 'Amaka Obi'], ['Phone', '08012345678'], ['Delivery address', '12 Marina Road, Lagos'], ['Payment', 'Cash on delivery'], ['Cash to collect', '₦12,500']],
    tables: [{ heading: 'Items', columns: ['Item', 'Qty', 'Unit price', 'Total'], rows: [['Black Sneakers', 1, '₦9,500', '₦9,500'], ['Socks (pair)', 2, '₦1,500', '₦3,000']] }],
  }, ctx, true)
})

function pickTemplate(t: (typeof TEMPLATE_INFO)[number]) {
  Object.assign(form, t.preset, { template: t.value })
}

const box = ref<HTMLElement | null>(null)
const scale = ref(0.5)
const pageW = computed(() => (form.paper === 'Receipt' ? 302 : 794))
function fit() { if (box.value) scale.value = Math.min(1, box.value.clientWidth / pageW.value) }
onMounted(() => {
  fit()
  if (typeof ResizeObserver !== 'undefined' && box.value) new ResizeObserver(fit).observe(box.value)
})
watch(pageW, () => nextTick(fit))

const MAX_SIDE = 480
function onLogo(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  ;(e.target as HTMLInputElement).value = ''
  if (!file) return
  if (!/^image\/(png|jpe?g|webp)$/.test(file.type)) {
    useToast().add({ title: 'Use a PNG, JPG or WebP picture', color: 'error' })
    return
  }
  const img = new Image()
  const url = URL.createObjectURL(file)
  img.onload = () => {
    const k = Math.min(1, MAX_SIDE / Math.max(img.width, img.height))
    const c = document.createElement('canvas')
    c.width = Math.round(img.width * k)
    c.height = Math.round(img.height * k)
    c.getContext('2d')!.drawImage(img, 0, 0, c.width, c.height)
    URL.revokeObjectURL(url)
    const out = c.toDataURL('image/png')
    form.logo = out.length > 390_000 ? c.toDataURL('image/jpeg', 0.85) : out
    if (form.logo.length > 390_000) {
      form.logo = ''
      useToast().add({ title: 'That picture is too large', description: 'Try a smaller one.', color: 'error' })
    }
  }
  img.onerror = () => { URL.revokeObjectURL(url); useToast().add({ title: 'Could not read that picture', color: 'error' }) }
  img.src = url
}

const papers = [
  { label: 'A4', value: 'A4' }, { label: 'A5', value: 'A5' }, { label: 'A3', value: 'A3' }, { label: 'Letter', value: 'Letter' },
  { label: 'Legal', value: 'Legal' }, { label: 'Receipt slip (80 mm)', value: 'Receipt' },
]
const fonts = [{ label: 'Clean', value: 'sans' }, { label: 'Classic serif', value: 'serif' }, { label: 'Typewriter', value: 'mono' }, { label: 'Friendly', value: 'rounded' }]
const headers = [{ label: 'Name on the left', value: 'split' }, { label: 'Centered', value: 'centered' }, { label: 'Colour banner', value: 'banner' }, { label: 'Stacked', value: 'stacked' }]
const tableStyles = [{ label: 'Striped rows', value: 'striped' }, { label: 'Lines', value: 'lines' }, { label: 'Boxed grid', value: 'boxed' }, { label: 'Clean', value: 'clean' }]
const densities = [{ label: 'Roomy', value: 'comfortable' }, { label: 'Tight', value: 'compact' }]
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
  ['show_row_numbers', 'Number the rows'], ['show_totals', 'Add a total line for money columns'], ['show_signatures', 'Signature lines at the bottom'],
]
</script>

<template>
  <div class="grid xl:grid-cols-2 gap-6">
    <div class="space-y-5">
      <UCard>
        <template #header><p class="font-semibold">Template</p></template>
        <div class="grid sm:grid-cols-3 gap-2">
          <button
            v-for="t in TEMPLATE_INFO" :key="t.value" type="button"
            class="text-left p-3 rounded-lg border transition"
            :class="form.template === t.value ? 'border-primary-500 bg-primary-50 dark:bg-primary-950/40' : 'border-zinc-200 dark:border-zinc-800 hover:border-zinc-400'"
            @click="pickTemplate(t)"
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
        <template #header><p class="font-semibold">Look and feel</p></template>
        <div class="grid sm:grid-cols-2 gap-4">
          <UFormField label="Header"><USelect v-model="form.header_style" :items="headers" class="w-full" /></UFormField>
          <UFormField label="Table"><USelect v-model="form.table_style" :items="tableStyles" class="w-full" /></UFormField>
          <UFormField label="Lettering"><USelect v-model="form.font" :items="fonts" class="w-full" /></UFormField>
          <UFormField label="Spacing"><USelect v-model="form.density" :items="densities" class="w-full" /></UFormField>
        </div>
        <UFormField label="Faint word across the page" description="For example DRAFT or COPY. Leave empty for none." class="mt-4">
          <UInput v-model="form.watermark" class="w-full" maxlength="30" />
        </UFormField>
      </UCard>

      <UCard>
        <template #header><p class="font-semibold">Your logo</p></template>
        <div class="flex items-center gap-4">
          <div class="w-24 h-24 rounded-lg border border-dashed border-zinc-300 dark:border-zinc-700 flex items-center justify-center bg-white overflow-hidden">
            <img v-if="form.logo" :src="form.logo" alt="Your logo" class="max-w-full max-h-full object-contain">
            <span v-else class="text-xs text-zinc-400 text-center px-2">No logo yet</span>
          </div>
          <div class="space-y-2">
            <label class="inline-flex">
              <input type="file" accept="image/png,image/jpeg,image/webp" class="hidden" @change="onLogo">
              <span class="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-md bg-primary-600 text-white cursor-pointer hover:bg-primary-700">
                <UIcon name="i-lucide-upload" class="w-4 h-4" /> {{ form.logo ? 'Change logo' : 'Upload logo' }}
              </span>
            </label>
            <div><UButton v-if="form.logo" size="xs" color="neutral" variant="ghost" icon="i-lucide-trash-2" @click="form.logo = ''">Remove</UButton></div>
            <p class="text-xs text-zinc-500 dark:text-zinc-400">PNG, JPG or WebP. A square or wide picture on a clear background works best.</p>
          </div>
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
          <UFormField label="Paper size"><USelect v-model="form.paper" :items="papers" class="w-full" /></UFormField>
          <UFormField label="Direction"><USelect v-model="form.orientation" :items="orients" class="w-full" /></UFormField>
        </div>
        <div class="grid sm:grid-cols-2 gap-2 mt-4">
          <USwitch v-for="[k, label] in toggles" :key="k" v-model="(form as any)[k]" :label="label" />
        </div>
      </UCard>

      <UButton :loading="saving" icon="i-lucide-check" @click="save">Save print layout</UButton>
    </div>

    <div>
      <div class="flex items-center justify-between mb-2">
        <p class="text-xs font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400">Live preview</p>
        <div class="flex gap-1">
          <UButton size="xs" :variant="previewKind === 'list' ? 'solid' : 'soft'" color="neutral" @click="previewKind = 'list'">A list</UButton>
          <UButton size="xs" :variant="previewKind === 'order' ? 'solid' : 'soft'" color="neutral" @click="previewKind = 'order'">One order</UButton>
        </div>
      </div>
      <div class="border border-zinc-200 dark:border-zinc-800 rounded-xl overflow-hidden bg-zinc-100 dark:bg-zinc-800 p-3">
        <div ref="box" class="mx-auto w-full overflow-hidden" :style="{ height: `${1123 * scale}px` }">
          <div class="bg-white shadow origin-top-left" :style="{ width: `${pageW}px`, height: '1123px', transform: `scale(${scale})` }">
            <iframe :srcdoc="html" class="w-full h-full border-0 bg-white" title="Print preview" sandbox="" />
          </div>
        </div>
      </div>
      <p class="text-xs text-zinc-500 dark:text-zinc-400 mt-2">Use the Print PDF button on any list. In the print window choose "Save as PDF".</p>
    </div>
  </div>
</template>
