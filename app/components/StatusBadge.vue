<script setup lang="ts">
const props = defineProps<{ status: string }>()
const color = computed(() => statusColor(props.status))
const label = computed(() => titleize(props.status))
</script>

<template>
  <UBadge :color="color as any" variant="subtle" size="sm" class="whitespace-nowrap">{{ label }}</UBadge>
</template>
