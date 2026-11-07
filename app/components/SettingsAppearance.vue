<script setup lang="ts">
import { COLOR_PRESETS, colorScale, DEFAULT_BRANDING } from '~/utils/theme'

const brand = useBranding()
const colorMode = useColorMode()
const form = reactive({ ...brand.value })
const saving = ref(false)
const hexOk = computed(() => /^#[0-9a-fA-F]{6}$/.test(form.primary))

const previewVars = computed(() => {
  const sc = hexOk.value ? colorScale(form.primary) : colorScale(DEFAULT_BRANDING.primary)
  const out: Record<string, string> = {}
  for (const [k, v] of Object.entries(sc)) out[`--p-${k}`] = v as string
  out['--r'] = `${form.radius}rem`
  return out
})

const modes = [
  { label: 'Match the device', value: 'system' },
  { label: 'Light', value: 'light' },
  { label: 'Dark', value: 'dark' },
]

async function save() {
  if (!hexOk.value) {
    useToast().add({ title: 'Pick a valid colour', description: 'Use a colour like #059669.', color: 'error' })
    return
  }
  saving.value = true
  try {
    const res: any = await api('/settings/theme', { method: 'PUT', body: { ...form, primary: form.primary.toLowerCase() } })
    Object.assign(brand.value, res?.brand_name ? res : form)
    // Show the chosen mode right away on this device
    colorMode.preference = form.default_mode
    useToast().add({ title: 'Appearance saved', color: 'success' })
  } catch (e: any) {
    useToast().add({ title: 'Could not save', description: errMsg(e), color: 'error' })
  } finally {
    saving.value = false
  }
}

function reset() {
  Object.assign(form, DEFAULT_BRANDING)
}
</script>

<template>
  <div class="grid lg:grid-cols-2 gap-6">
    <div class="space-y-5">
      <UCard>
        <template #header><p class="font-semibold">Colour</p></template>
        <div class="flex flex-wrap gap-2 mb-3">
          <button
            v-for="c in COLOR_PRESETS" :key="c.hex" type="button" :title="c.name"
            class="w-8 h-8 rounded-full ring-offset-2 ring-offset-white dark:ring-offset-zinc-900 transition"
            :class="form.primary.toLowerCase() === c.hex ? 'ring-2 ring-zinc-900 dark:ring-white' : 'hover:scale-110'"
            :style="{ background: c.hex }"
            @click="form.primary = c.hex"
          />
        </div>
        <UFormField label="Custom colour" :error="hexOk ? undefined : 'Use a colour like #059669'">
          <div class="flex items-center gap-2">
            <input v-model="form.primary" type="color" class="h-9 w-12 rounded cursor-pointer bg-transparent" :disabled="false">
            <UInput v-model="form.primary" class="w-36 font-mono" maxlength="7" />
          </div>
        </UFormField>
        <UFormField label="Corner roundness" class="mt-4">
          <div class="flex items-center gap-3">
            <input v-model.number="form.radius" type="range" min="0" max="1.25" step="0.05" class="flex-1">
            <span class="text-xs text-zinc-500 w-10">{{ form.radius }}</span>
          </div>
        </UFormField>
        <UFormField label="Light or dark" class="mt-4" description="Used for people who have not picked their own.">
          <URadioGroup v-model="form.default_mode" :items="modes" orientation="horizontal" />
        </UFormField>
      </UCard>

      <UCard>
        <template #header><p class="font-semibold">Words</p></template>
        <div class="space-y-3">
          <UFormField label="Business name"><UInput v-model="form.brand_name" class="w-full" maxlength="40" /></UFormField>
          <UFormField label="Short tagline"><UInput v-model="form.tagline" class="w-full" maxlength="80" /></UFormField>
          <UFormField label="Sign in page headline"><UInput v-model="form.login_headline" class="w-full" maxlength="120" /></UFormField>
          <UFormField label="Sign in page text"><UTextarea v-model="form.login_text" class="w-full" :rows="3" maxlength="400" /></UFormField>
        </div>
      </UCard>

      <div class="flex gap-2">
        <UButton :loading="saving" icon="i-lucide-check" @click="save">Save appearance</UButton>
        <UButton color="neutral" variant="outline" @click="reset">Back to defaults</UButton>
      </div>
    </div>

    <!-- live preview -->
    <div>
      <p class="text-xs font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400 mb-2">Live preview</p>
      <div class="border border-zinc-200 dark:border-zinc-800 overflow-hidden flex flex-col sm:flex-row" :style="{ ...previewVars, borderRadius: 'calc(var(--r) * 2)' }">
        <div class="sm:w-1/2 p-5 text-white" style="background-image: linear-gradient(135deg, var(--p-600), var(--p-800) 55%, var(--p-950))">
          <div class="flex items-center gap-2 mb-6">
            <span class="w-8 h-8 bg-white/20 flex items-center justify-center font-bold" :style="{ borderRadius: 'var(--r)' }">{{ (form.brand_name || 'K').slice(0, 1) }}</span>
            <div>
              <p class="font-bold leading-none">{{ form.brand_name }}</p>
              <p class="text-[11px] text-white/75 mt-1">{{ form.tagline }}</p>
            </div>
          </div>
          <p class="text-lg font-bold leading-snug mb-2">{{ form.login_headline }}</p>
          <p class="text-xs text-white/85">{{ form.login_text }}</p>
        </div>
        <div class="sm:w-1/2 p-5 bg-white dark:bg-zinc-950">
          <p class="font-bold text-zinc-900 dark:text-white mb-3">Sign in</p>
          <div class="h-8 border border-zinc-300 dark:border-zinc-700 mb-2" :style="{ borderRadius: 'var(--r)' }" />
          <div class="h-8 border border-zinc-300 dark:border-zinc-700 mb-3" :style="{ borderRadius: 'var(--r)' }" />
          <div class="h-9 text-white text-sm font-medium flex items-center justify-center" :style="{ background: 'var(--p-600)', borderRadius: 'var(--r)' }">Sign in</div>
          <div class="flex gap-2 mt-4">
            <span class="text-[11px] px-2 py-0.5" :style="{ background: 'var(--p-100)', color: 'var(--p-800)', borderRadius: 'var(--r)' }">Delivered</span>
            <span class="text-[11px] px-2 py-0.5" :style="{ background: 'var(--p-600)', color: '#fff', borderRadius: 'var(--r)' }">New order</span>
          </div>
        </div>
      </div>
      <p class="text-xs text-zinc-500 dark:text-zinc-400 mt-2">The same colour and wording are used on the sign in page and across the app.</p>
    </div>
  </div>
</template>
