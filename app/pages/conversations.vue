<script setup lang="ts">
const conversations = ref<any[]>([])
const selected = ref<any>(null)
const loading = ref(true)
const q = ref('')
const showUnassigned = ref(false)
const statusFilter = ref('ALL')
const mobileDetail = computed(() => !!selected.value)

const statuses = ['NEW', 'OPEN', 'PROCESSING', 'WAITING_FOR_VENDOR', 'WAITING_FOR_STAFF', 'RESOLVED', 'ARCHIVED']

async function load() {
  loading.value = true
  try {
    const params = new URLSearchParams()
    if (q.value) params.set('q', q.value)
    if (showUnassigned.value) params.set('unassigned', 'true')
    if (statusFilter.value && statusFilter.value !== 'ALL') params.set('status', statusFilter.value)
    conversations.value = await api(`/conversations?${params}`)
    if (selected.value && !conversations.value.find((c: any) => c.id === selected.value.id)) selected.value = null
  } catch (e) {
    useToast().add({ title: 'Could not load conversations', description: errMsg(e), color: 'error', icon: 'i-lucide-circle-alert' })
  } finally { loading.value = false }
}

async function open(conv: any) {
  selected.value = { ...conv, messages: [], loading: true }
  try {
    selected.value = await api(`/conversations/${conv.id}`)
  } catch (e) {
    selected.value = conv
  }
}

const vendorLabel = (c: any) => c.vendor_name || 'Unidentified sender'
const canSend = ref(true)

// Simulator: send a message AS THE VENDOR (enters real ingestion pipeline)
const simText = ref('')
const simSending = ref(false)
// Phase 6C: simulated voice notes / photos run through ASR + vision extraction
const simType = ref<'text' | 'voice' | 'image'>('text')
const simFile = ref<File | null>(null)
const simFileB64 = ref('')
async function onSimFile(e: Event) {
  const f = (e.target as HTMLInputElement)?.files?.[0]
  if (!f) { simFile.value = null; simFileB64.value = ''; return }
  if (f.size > 5 * 1024 * 1024) {
    useToast().add({ title: 'File too large', description: 'Keep simulated media under 5MB.', color: 'error' })
    return
  }
  simFile.value = f
  simFileB64.value = await new Promise<string>((resolve) => {
    const r = new FileReader()
    r.onload = () => resolve(String(r.result || ''))
    r.readAsDataURL(f)
  })
}
async function simulateInbound() {
  if (!selected.value) return
  const hasMedia = simType.value !== 'text' && !!simFileB64.value
  if (!simText.value.trim() && !hasMedia) return
  simSending.value = true
  try {
    const res: any = await api('/whatsapp/simulator/send', {
      method: 'POST',
      body: {
        from_phone: selected.value.contact_phone,
        text: simText.value.trim(),
        msg_type: simType.value,
        media_b64: hasMedia ? simFileB64.value : '',
      },
    })
    simText.value = ''; simFile.value = null; simFileB64.value = ''
    const engine = res?.media_engine && res.media_engine !== 'none' ? ` · ${res.media_engine.toUpperCase()}` : ''
    useToast().add({ title: `Message received${engine}`, description: 'The vendor, what they want and the order details were read automatically.', icon: 'i-lucide-bot' })
    await load()
    await open(selected.value)
  } catch (e) {
    useToast().add({ title: 'Failed', description: errMsg(e), color: 'error' })
  } finally { simSending.value = false }
}

// Staff outbound reply (simulated WhatsApp send)
const replyText = ref('')
const replySending = ref(false)
async function sendReply() {
  if (!replyText.value.trim() || !selected.value) return
  replySending.value = true
  try {
    await api(`/conversations/${selected.value.id}/send`, { method: 'POST', body: { text: replyText.value.trim() } })
    replyText.value = ''
    await open(selected.value)
  } catch (e) {
    useToast().add({ title: 'Failed', description: errMsg(e), color: 'error' })
  } finally { replySending.value = false }
}

const users = ref<any[]>([])
onMounted(async () => { try { users.value = await api('/users') } catch {} })

async function assignTo(userId: number) {
  await api(`/conversations/${selected.value.id}/assign`, { method: 'POST', body: { user_id: userId } })
  await open(selected.value)
}

async function setStatus(status: string) {
  await api(`/conversations/${selected.value.id}/status`, { method: 'POST', body: { status } })
  await open(selected.value)
}

const vendors = ref<any[]>([])
const showAttach = ref(false)
const attachVendorId = ref<number | null>(null)
onMounted(async () => { try { vendors.value = await api('/vendors') } catch {} })

async function attachVendor() {
  if (!attachVendorId.value) return
  await api(`/conversations/${selected.value.id}/attach-vendor`, { method: 'POST', body: { vendor_id: attachVendorId.value } })
  showAttach.value = false
  useToast().add({ title: 'Sender identified', description: 'Future messages from this number will auto-match.', icon: 'i-lucide-user-check' })
  await load()
  await open(selected.value)
}

onMounted(load)
</script>

<template>
  <div>
    <PageHeader title="WhatsApp Inbox" subtitle="One inbox for every vendor conversation - orders, questions and updates." />

    <div class="grid lg:grid-cols-[340px_1fr] gap-4">
      <!-- List -->
      <div :class="mobileDetail ? 'hidden lg:block' : ''">
        <div class="space-y-2 mb-3">
          <UInput v-model="q" icon="i-lucide-search" placeholder="Search conversations…" class="w-full" @keydown.enter="load" />
          <div class="flex gap-2 flex-wrap items-center">
            <USelect v-model="statusFilter" :items="[{ label: 'All statuses', value: 'ALL' }, ...statuses.map(s => ({ label: titleize(s), value: s }))]" size="xs" class="w-40" @change="load" />
            <UCheckbox v-model="showUnassigned" label="Unidentified only" size="sm" @update:model-value="load" />
          </div>
        </div>
        <div class="space-y-2 max-h-[70vh] overflow-y-auto thin-scroll pr-1">
          <div v-if="loading" class="text-center text-zinc-400 py-10"><UIcon name="i-lucide-loader-circle" class="animate-spin" /></div>
          <button
            v-else v-for="c in conversations" :key="c.id"
            class="w-full text-left bg-white dark:bg-zinc-900 border rounded-xl p-3 transition-colors flex gap-3"
            :class="selected?.id === c.id ? 'border-primary-400 ring-1 ring-primary-300' : 'border-zinc-200 dark:border-zinc-800 hover:border-zinc-300'"
            @click="open(c)"
          >
            <UAvatar :text="(c.contact_name || c.vendor_name || 'S').slice(0, 1)" size="md"
                     :class="c.vendor_id ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-300' : 'bg-amber-100 text-amber-700 dark:bg-amber-900 dark:text-amber-300'" />
            <div class="min-w-0 flex-1">
              <div class="flex items-center gap-2">
                <p class="text-sm font-semibold truncate text-zinc-800 dark:text-zinc-200">{{ vendorLabel(c) }}</p>
                <span v-if="c.unread_count" class="ml-auto bg-primary-500 text-white text-[10px] rounded-full px-1.5 py-0.5">{{ c.unread_count }}</span>
              </div>
              <p class="text-[11px] text-zinc-400 font-mono">{{ c.contact_phone }}</p>
              <p class="text-xs text-zinc-500 truncate mt-0.5">{{ c.last_message_preview || 'No messages yet' }}</p>
              <div class="flex items-center gap-1.5 mt-1">
                <UBadge :color="c.vendor_id ? 'success' : 'warning'" variant="subtle" size="xs">{{ c.vendor_id ? titleize(c.status) : 'Unidentified' }}</UBadge>
              </div>
            </div>
          </button>
          <div v-if="!loading && !conversations.length" class="text-center text-zinc-400 text-sm py-10">No conversations match.</div>
        </div>
      </div>

      <!-- Thread -->
      <div v-if="selected" :class="mobileDetail ? '' : 'hidden lg:block'" class="bg-white dark:bg-zinc-900 rounded-xl border border-zinc-200 dark:border-zinc-800 flex flex-col h-[76vh]">
        <!-- header -->
        <div class="flex items-center gap-3 p-3 border-b border-zinc-200 dark:border-zinc-800">
          <UButton icon="i-lucide-arrow-left" variant="ghost" color="neutral" size="xs" class="lg:hidden" @click="selected = null" aria-label="Back" />
          <UAvatar :text="vendorLabel(selected).slice(0, 1)" size="sm" />
          <div class="flex-1 min-w-0">
            <p class="font-semibold text-sm text-zinc-800 dark:text-zinc-200 truncate">{{ vendorLabel(selected) }}</p>
            <p class="text-[11px] text-zinc-400 font-mono">{{ selected.contact_phone }}</p>
          </div>
          <USelect
            :model-value="selected.status" :items="statuses.map(s => ({ label: titleize(s), value: s }))"
            size="xs" class="w-40" @update:model-value="setStatus"
          />
        </div>

        <!-- vendor context strip -->
        <div class="px-3 py-2 bg-zinc-50 dark:bg-zinc-800/50 border-b border-zinc-200 dark:border-zinc-800 flex flex-wrap items-center gap-2 text-xs">
          <template v-if="selected.vendor">
            <UBadge color="success" variant="subtle" size="xs">Vendor: {{ selected.vendor.name }}</UBadge>
            <UBadge color="neutral" variant="subtle" size="xs">{{ selected.vendor.code }}</UBadge>
            <UButton to="/vendors" variant="link" size="xs" trailing-icon="i-lucide-arrow-up-right">Vendor profile</UButton>
          </template>
          <template v-else>
            <UBadge color="warning" variant="subtle" size="xs">Unidentified sender</UBadge>
            <UButton size="xs" color="warning" variant="soft" icon="i-lucide-user-plus" @click="showAttach = true">Attach to vendor</UButton>
          </template>
          <UDropdownMenu v-if="users.length" :items="[users.map(u => ({ label: `${u.full_name}`, onSelect: () => assignTo(u.id) }))]" size="xs">
            <UButton size="xs" variant="outline" color="neutral" icon="i-lucide-user-cog">
              {{ selected.assigned_user_id ? `Assigned #${selected.assigned_user_id}` : 'Assign to staff' }}
            </UButton>
          </UDropdownMenu>
        </div>

        <!-- messages -->
        <div class="flex-1 overflow-y-auto thin-scroll p-4 space-y-2 bg-[repeating-linear-gradient(0deg,transparent,transparent_24px,rgba(0,0,0,0.015)_25px)]">
          <div v-for="m in selected.messages" :key="m.id"
               class="flex" :class="m.direction === 'IN' ? 'justify-start' : 'justify-end'">
            <div class="max-w-[75%] rounded-2xl px-3.5 py-2 shadow-sm"
                 :class="m.direction === 'IN'
                   ? 'bg-white dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 rounded-tl-sm'
                   : 'bg-primary-600 text-white rounded-tr-sm'">
              <div v-if="m.msg_type === 'voice'" class="flex items-center gap-1.5 mb-1 text-[11px] opacity-75">
                <UIcon name="i-lucide-audio-lines" class="w-3.5 h-3.5" /> Voice note · transcribed
              </div>
              <div v-else-if="m.msg_type === 'image'" class="flex items-center gap-1.5 mb-1 text-[11px] opacity-75">
                <UIcon name="i-lucide-image" class="w-3.5 h-3.5" /> Photo · vision-extracted
              </div>
              <div v-else-if="m.msg_type === 'document'" class="flex items-center gap-1.5 mb-1 text-[11px] opacity-75">
                <UIcon name="i-lucide-file-text" class="w-3.5 h-3.5" /> Document
              </div>
              <p class="text-sm whitespace-pre-wrap break-words" :class="m.direction === 'IN' ? 'text-zinc-800 dark:text-zinc-200' : ''">{{ m.body_text }}</p>
              <p class="text-[10px] mt-1 flex items-center gap-1" :class="m.direction === 'IN' ? 'text-zinc-400' : 'text-primary-100'">
                {{ fmtDateTime(m.created_at) }}
                <UIcon v-if="m.direction === 'OUT'" :name="m.status === 'READ' ? 'i-lucide-check-check' : 'i-lucide-check'" class="w-3 h-3" />
                <UBadge v-if="m.direction === 'IN' && m.intent" color="neutral" variant="outline" size="xs" class="ml-1">{{ titleize(m.intent) }}</UBadge>
              </p>
            </div>
          </div>
          <div v-if="!selected.messages?.length" class="text-center text-zinc-400 text-sm py-10">No messages.</div>
        </div>

        <!-- drafts attached -->
        <div v-if="selected.drafts?.length" class="px-3 py-2 border-t border-zinc-200 dark:border-zinc-800 flex flex-wrap gap-2 items-center">
          <span class="text-[11px] text-zinc-400">Drafts:</span>
          <UBadge v-for="dr in selected.drafts" :key="dr.id" :color="dr.status === 'CONVERTED' ? 'success' : 'warning'" variant="subtle" size="xs">
            {{ dr.draft_ref }} · {{ titleize(dr.status) }}
          </UBadge>
          <UButton to="/drafts" size="xs" variant="link" trailing-icon="i-lucide-arrow-up-right">Review queue</UButton>
        </div>

        <!-- reply -->
        <div class="p-3 border-t border-zinc-200 dark:border-zinc-800 space-y-2">
          <div class="flex gap-2">
            <UInput v-model="replyText" placeholder="Type a reply (test mode)..." class="flex-1" size="sm"
                    @keydown.enter="sendReply" />
            <UButton icon="i-lucide-send" :loading="replySending" @click="sendReply" aria-label="Send reply" />
          </div>
          <USeparator label="Practice as a vendor" :ui="{ border: 'border-dashed' }" />
          <div class="flex gap-2">
            <USelect v-model="simType" :items="[
              { label: 'Text', value: 'text' },
              { label: 'Voice note', value: 'voice' },
              { label: 'Photo', value: 'image' },
            ]" size="sm" class="w-32" />
            <input v-if="simType !== 'text'" type="file" :accept="simType === 'voice' ? 'audio/*' : 'image/*'"
                   class="text-xs text-zinc-500 file:mr-2 file:rounded-md file:border-0 file:bg-zinc-100 dark:file:bg-zinc-800 file:px-2 file:py-1 file:text-xs"
                   @change="onSimFile" aria-label="Attach simulated media" />
            <UInput v-model="simText" :placeholder="simType === 'text' ? 'Type as the vendor to test how orders are picked up...' : simType === 'voice' ? 'Caption (optional) - voice note is turned into text' : 'Caption (optional) - photo is read automatically'" class="flex-1" size="sm"
                    @keydown.enter="simulateInbound" />
            <UButton icon="i-lucide-bot" color="warning" variant="soft" :loading="simSending"
                     :disabled="simType !== 'text' && !simFileB64" @click="simulateInbound" aria-label="Simulate vendor message" />
          </div>
        </div>
      </div>

      <div v-else class="hidden lg:flex items-center justify-center bg-white dark:bg-zinc-900 rounded-xl border border-zinc-200 dark:border-zinc-800 h-[76vh] text-zinc-400 flex-col gap-2">
        <UIcon name="i-lucide-message-circle" class="w-10 h-10 opacity-30" />
        <p>Select a conversation</p>
        <p class="text-xs">Use the practice box below any chat to send test vendor messages.</p>
      </div>
    </div>

    <!-- Attach vendor modal -->
    <UModal v-model:open="showAttach" title="Attach sender to vendor">
      <template #body>
        <div class="space-y-3">
          <p class="text-sm text-zinc-500">Staff-assisted identification for <span class="font-mono">{{ selected?.contact_phone }}</span>. This is recorded as an identity match with method STAFF_ASSISTED.</p>
          <USelect v-model="attachVendorId" placeholder="Choose vendor" class="w-full"
                   :items="vendors.map(v => ({ label: `${v.name} (${v.code})`, value: v.id }))" />
        </div>
      </template>
      <template #footer>
        <div class="flex justify-end gap-2 w-full">
          <UButton variant="ghost" color="neutral" @click="showAttach = false">Cancel</UButton>
          <UButton color="primary" @click="attachVendor">Confirm identity</UButton>
        </div>
      </template>
    </UModal>
  </div>
</template>
