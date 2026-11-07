<script setup lang="ts">
const mods = useModules()
const items = ref<{ key: string; name: string; description: string; enabled: boolean }[]>([])
const saving = ref(false)
const loading = ref(true)

onMounted(async () => {
  try { items.value = (await api<any>('/settings/modules')).modules } finally { loading.value = false }
})

async function save() {
  saving.value = true
  try {
    const enabled = Object.fromEntries(items.value.map((m) => [m.key, m.enabled]))
    const res = await api<any>('/settings/modules', { method: 'PUT', body: { enabled } })
    items.value = res.modules
    await mods.load(true)
    useToast().add({ title: 'Features saved', description: 'Switched-off features are now hidden for everyone.', color: 'success' })
  } catch (e: any) {
    useToast().add({ title: 'Could not save', description: errMsg(e), color: 'error' })
  } finally { saving.value = false }
}
</script>

<template>
  <div class="max-w-2xl">
    <p class="text-sm text-zinc-500 dark:text-zinc-400 mb-4">
      Turn off anything your business does not use. A switched-off feature disappears completely: its pages, buttons,
      reports and settings are hidden for everyone until you turn it back on. Your information is kept safe meanwhile.
      Orders, products, stock, vendors, customers and settings are always on.
    </p>
    <div v-if="loading" class="py-10 text-center text-zinc-400"><UIcon name="i-lucide-loader-circle" class="animate-spin" /></div>
    <div v-else class="bg-white dark:bg-zinc-900 rounded-xl border border-zinc-200 dark:border-zinc-800 divide-y divide-zinc-100 dark:divide-zinc-800">
      <div v-for="m in items" :key="m.key" class="flex items-center justify-between gap-4 p-4">
        <div>
          <p class="font-medium text-zinc-800 dark:text-zinc-200">{{ m.name }}</p>
          <p class="text-xs text-zinc-500 dark:text-zinc-400">{{ m.description }}</p>
        </div>
        <USwitch v-model="m.enabled" />
      </div>
    </div>
    <UButton class="mt-4" :loading="saving" icon="i-lucide-check" @click="save">Save features</UButton>
  </div>
</template>
