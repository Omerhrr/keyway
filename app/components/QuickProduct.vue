<script setup lang="ts">
const props = defineProps<{ open: boolean; vendorId?: number; vendors: any[] }>()
const emit = defineEmits<{ (e: 'update:open', v: boolean): void; (e: 'created', p: any): void }>()
const { needs } = useGuard()
const saving = ref(false)
const form = reactive({ vendor_id: 0, name: '', price_naira: '', category: '', reorder_level: 5 })

watch(() => props.open, (o) => {
  if (!o) return
  Object.assign(form, { vendor_id: props.vendorId || 0, name: '', price_naira: '', category: '', reorder_level: 5 })
})

async function save() {
  if (!needs([['Vendor', form.vendor_id], ['Product name', form.name]])) return
  saving.value = true
  try {
    const p = await api('/catalog/products', {
      method: 'POST',
      body: { vendor_id: form.vendor_id, name: form.name.trim(), category: form.category,
              default_sell_price_kobo: form.price_naira ? toKobo(form.price_naira) : 0,
              reorder_level: Number(form.reorder_level) || 0 },
    })
    useToast().add({ title: `${p.name} added`, description: `Product code ${p.sku} was created for you.`, color: 'success' })
    emit('created', p)
    emit('update:open', false)
  } catch (e) {
    useToast().add({ title: 'Could not add the product', description: errMsg(e), color: 'error' })
  } finally { saving.value = false }
}
</script>

<template>
  <UModal :open="open" title="Add a product" @update:open="(v: boolean) => emit('update:open', v)">
    <template #body>
      <div class="grid sm:grid-cols-2 gap-3">
        <UFormField label="Vendor" class="sm:col-span-2">
          <USelect placeholder="Choose..." :model-value="form.vendor_id || undefined" class="w-full" :disabled="!!vendorId"
                   :items="vendors.map(v => ({ label: v.name, value: v.id }))" @update:model-value="(v: any) => form.vendor_id = v" />
        </UFormField>
        <UFormField label="Product name" class="sm:col-span-2"><UInput v-model="form.name" class="w-full" @keydown.enter="save" /></UFormField>
        <UFormField label="Selling price (₦)"><UInput v-model="form.price_naira" inputmode="decimal" class="w-full" /></UFormField>
        <UFormField label="Category (optional)"><UInput v-model="form.category" class="w-full" /></UFormField>
        <UFormField label="Reorder level" help="Warn me when stock falls to this number"><UInput v-model="form.reorder_level" type="number" min="0" class="w-full" /></UFormField>
        <UFormField label="Product code"><UInput model-value="" placeholder="Made for you automatically" disabled class="w-full" /></UFormField>
      </div>
    </template>
    <template #footer>
      <div class="flex justify-end gap-2 w-full">
        <UButton variant="ghost" color="neutral" @click="emit('update:open', false)">Cancel</UButton>
        <UButton :loading="saving" @click="save">Add product</UButton>
      </div>
    </template>
  </UModal>
</template>
