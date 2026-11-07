<script setup lang="ts">
// Tabs that keep their full names and scroll sideways when they do not fit (phones, small windows).
const props = defineProps<{ items: any[]; size?: 'xs' | 'sm' | 'md' | 'lg' | 'xl' }>()
const model = defineModel<any>()
</script>

<template>
  <div class="overflow-x-auto thin-scroll pb-1 -mx-1 px-1">
    <UTabs v-model="model" :items="props.items" :size="props.size" :content="false" class="min-w-max"
           :ui="{ list: 'w-max', trigger: 'shrink-0 whitespace-nowrap' }" />
  </div>
</template>
