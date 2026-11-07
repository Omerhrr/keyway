<script setup lang="ts">
const { canInstall, isIOS, standalone, install, bind } = usePwa()
const isAndroid = ref(false)
const msg = ref('')
onMounted(() => {
  bind()
  isAndroid.value = /android/i.test(navigator.userAgent)
})
async function go() {
  msg.value = ''
  const ok = await install()
  msg.value = ok ? 'Installed. Look for Keyway on your home screen.' : 'Install was cancelled. You can try again any time.'
}
const link = computed(() => (import.meta.client ? window.location.origin : ''))
function copyLink() {
  navigator.clipboard?.writeText(link.value)
  useToast().add({ title: 'Link copied', color: 'success' })
}
</script>

<template>
  <div class="max-w-2xl space-y-4">
    <UCard>
      <div class="flex items-start gap-3">
        <BrandLogo class="w-12 h-12 shrink-0" />
        <div class="min-w-0">
          <h3 class="font-semibold">Keyway on your phone or computer</h3>
          <p class="text-sm text-zinc-500 mt-1">Install it like an app. It opens full screen, gets its own icon and starts faster.</p>
        </div>
      </div>

      <UAlert v-if="standalone" class="mt-4" color="success" variant="subtle" icon="i-lucide-check-circle"
              title="You are already using the installed app" />

      <template v-else>
        <div v-if="canInstall" class="mt-4">
          <UButton icon="i-lucide-download" size="lg" @click="go">Install Keyway</UButton>
          <p v-if="msg" class="text-sm text-zinc-500 mt-2">{{ msg }}</p>
        </div>

        <div v-else-if="isIOS" class="mt-4 space-y-2 text-sm">
          <p class="font-medium">iPhone and iPad need three taps:</p>
          <ol class="list-decimal pl-5 space-y-1 text-zinc-600 dark:text-zinc-300">
            <li>Open this page in <b>Safari</b> (other browsers on iPhone cannot install apps).</li>
            <li>Tap the <b>Share</b> button <UIcon name="i-lucide-share" class="inline w-4 h-4 align-text-bottom" /> at the bottom of the screen.</li>
            <li>Scroll down, tap <b>Add to Home Screen</b>, then <b>Add</b>.</li>
          </ol>
          <UButton icon="i-lucide-copy" color="neutral" variant="outline" size="sm" class="mt-2" @click="copyLink">Copy page link to open in Safari</UButton>
        </div>

        <div v-else class="mt-4 space-y-2 text-sm text-zinc-600 dark:text-zinc-300">
          <template v-if="isAndroid">
            <p class="font-medium text-zinc-900 dark:text-zinc-100">The install button is not ready yet.</p>
            <p>Open this page in Chrome, then tap the <b>⋮</b> menu and choose <b>Install app</b> (or <b>Add to Home screen</b>).</p>
          </template>
          <template v-else>
            <p class="font-medium text-zinc-900 dark:text-zinc-100">The install button is not ready yet.</p>
            <p>In Chrome or Edge on a computer, click the install icon at the right end of the address bar, or open the browser menu and choose <b>Install Keyway</b>. Firefox and Safari on desktop do not support this.</p>
          </template>
        </div>
      </template>
    </UCard>
  </div>
</template>
