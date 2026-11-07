<script setup lang="ts">
// Same mark as /logo.svg but painted with the business colour, so it follows the theme.
defineProps<{ size?: number | string }>()
</script>

<template>
  <svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg" :width="size || 32" :height="size || 32" aria-hidden="true">
    <rect x="2" y="2" width="60" height="60" rx="14" fill="var(--ui-color-primary-600)" />
    <circle cx="26" cy="26" r="10" fill="none" stroke="#ffffff" stroke-width="5" />
    <line x1="33" y1="33" x2="48" y2="48" stroke="#ffffff" stroke-width="6" stroke-linecap="round" />
    <line x1="41" y1="41" x2="46" y2="36" stroke="#ffffff" stroke-width="4.5" stroke-linecap="round" />
    <line x1="46" y1="46" x2="51" y2="41" stroke="#ffffff" stroke-width="4.5" stroke-linecap="round" />
  </svg>
</template>
