<script setup lang="ts">
const tab = ref('overview')
const tabs = [
  { label: 'Overview', value: 'overview', icon: 'i-lucide-scale' },
  { label: 'Journals', value: 'journals', icon: 'i-lucide-book-open' },
  { label: 'Expenses', value: 'expenses', icon: 'i-lucide-receipt' },
  { label: 'Bank', value: 'bank', icon: 'i-lucide-building-2' },
]

const trial = ref<any>(null)
const pnl = ref<any>(null)
const bs = ref<any>(null)
const journals = ref<any[]>([])
const expenses = ref<any[]>([])
const bank = ref<any[]>([])
const accounts = ref<any[]>([])
const loading = ref(true)

async function load() {
  loading.value = true
  try {
    const [t, p, b, j, e, bk, a] = await Promise.all([
      api('/ledger/trial-balance'), api('/ledger/pnl'), api('/ledger/balance-sheet'),
      api('/ledger/journals'), api('/ledger/expenses'), api('/ledger/bank-transactions'), api('/ledger/accounts'),
    ])
    trial.value = t; pnl.value = p; bs.value = b; journals.value = j; expenses.value = e; bank.value = bk; accounts.value = a
  } finally { loading.value = false }
}
onMounted(load)

// manual journal
const showJournal = ref(false)
const jMemo = ref('')
const jLines = ref([{ account_id: 0, debit_naira: '', credit_naira: '' }, { account_id: 0, debit_naira: '', credit_naira: '' }])
const jSaving = ref(false)
const accountOptions = computed(() => accounts.value.map(a => ({ label: `${a.code} · ${a.name}`, value: a.id })))

async function postJournal() {
  jSaving.value = true
  try {
    const lines = jLines.value
      .filter(l => l.account_id && (toKobo(l.debit_naira) || toKobo(l.credit_naira)))
      .map(l => ({ account_id: l.account_id, debit_kobo: toKobo(l.debit_naira), credit_kobo: toKobo(l.credit_naira) }))
    await api('/ledger/journals', { method: 'POST', body: { memo: jMemo.value, lines } })
    useToast().add({ title: 'Journal posted', color: 'success', icon: 'i-lucide-book-check' })
    showJournal.value = false
    jMemo.value = ''
    await load()
  } catch (e) {
    useToast().add({ title: 'Not posted', description: errMsg(e), color: 'error' })
  } finally { jSaving.value = false }
}

const revEntry = ref<any>(null)
const revReason = ref('')
async function reverseEntry(e: any) {
  revEntry.value = e
}
async function confirmReverse() {
  try {
    await api(`/ledger/journals/${revEntry.value.id}/reverse`, { method: 'POST', body: { reason: revReason.value } })
    useToast().add({ title: 'Reversal posted', color: 'success' })
    revEntry.value = null
    await load()
  } catch (e) { useToast().add({ title: 'Failed', description: errMsg(e), color: 'error' }) }
}

// expenses
const showExpense = ref(false)
const eForm = reactive({ category: 'Fuel', description: '', amount_naira: '', payee: '', method: 'CASH' })
const eSaving = ref(false)
async function createExpense() {
  eSaving.value = true
  try {
    await api('/ledger/expenses', {
      method: 'POST',
      body: { category: eForm.category, description: eForm.description, amount_kobo: toKobo(eForm.amount_naira), payment_method: eForm.method, payee: eForm.payee },
    })
    useToast().add({ title: 'Expense submitted for approval' })
    showExpense.value = false
    await load()
  } finally { eSaving.value = false }
}
async function approveExpense(e: any, ok: boolean) {
  try {
    await api(`/ledger/expenses/${e.id}/${ok ? 'approve' : 'reject'}`, { method: 'POST' })
    useToast().add({ title: ok ? 'Expense approved & posted' : 'Expense rejected', color: ok ? 'success' : 'neutral' })
    await load()
  } catch (err) { useToast().add({ title: 'Failed', description: errMsg(err), color: 'error' }) }
}
</script>

<template>
  <div>
    <PageHeader title="Finance" subtitle="Your books. Posted entries cannot be edited. To fix a mistake, reverse the entry and post a new one." />

    <ScrollTabs :items="tabs" v-model="tab" class="mb-4" />

    <!-- OVERVIEW -->
    <template v-if="tab === 'overview'">
      <div v-if="pnl" class="grid grid-cols-1 lg:grid-cols-3 gap-5 mb-6">
        <div class="bg-white dark:bg-zinc-900 rounded-xl border border-zinc-200 dark:border-zinc-800 p-5">
          <h3 class="font-semibold mb-3 text-zinc-700 dark:text-zinc-200">Income statement</h3>
          <div class="space-y-1.5 text-sm">
            <p class="text-[11px] uppercase text-zinc-400 font-semibold">Revenue</p>
            <div v-for="r in pnl.revenue" :key="r.id" class="flex justify-between">
              <span class="text-zinc-500">{{ r.name }}</span><span class="font-medium text-emerald-600">{{ fmtNaira(r.net_kobo) }}</span>
            </div>
            <p class="text-[11px] uppercase text-zinc-400 font-semibold pt-2">Expenses</p>
            <div v-for="e in pnl.expenses" :key="e.id" class="flex justify-between">
              <span class="text-zinc-500">{{ e.name }}</span><span class="font-medium text-red-500">({{ fmtNaira(e.net_kobo) }})</span>
            </div>
            <USeparator class="my-2" />
            <div class="flex justify-between font-bold">
              <span>Net profit</span>
              <span :class="pnl.net_profit_kobo >= 0 ? 'text-emerald-600' : 'text-red-500'">{{ fmtNaira(pnl.net_profit_kobo) }}</span>
            </div>
          </div>
        </div>

        <div class="bg-white dark:bg-zinc-900 rounded-xl border border-zinc-200 dark:border-zinc-800 p-5">
          <h3 class="font-semibold mb-3 text-zinc-700 dark:text-zinc-200">Balance sheet</h3>
          <div class="space-y-1.5 text-sm">
            <p class="text-[11px] uppercase text-zinc-400 font-semibold">Assets</p>
            <div v-for="a in bs?.assets" :key="a.id" class="flex justify-between">
              <span class="text-zinc-500">{{ a.name }}</span><span class="font-medium">{{ fmtNaira(a.net_kobo) }}</span>
            </div>
            <p class="text-[11px] uppercase text-zinc-400 font-semibold pt-2">Liabilities</p>
            <div v-for="l in bs?.liabilities" :key="l.id" class="flex justify-between">
              <span class="text-zinc-500">{{ l.name }}</span><span class="font-medium text-amber-600">{{ fmtNaira(l.net_kobo) }}</span>
            </div>
            <p class="text-[11px] uppercase text-zinc-400 font-semibold pt-2">Equity & income</p>
            <div v-for="q in bs?.equity" :key="q.id" class="flex justify-between">
              <span class="text-zinc-500">{{ q.name }}</span><span class="font-medium">{{ fmtNaira(q.net_kobo) }}</span>
            </div>
            <div class="flex justify-between text-zinc-500">
              <span>Retained income</span><span :class="bs?.retained_income_kobo >= 0 ? 'text-emerald-600' : 'text-red-500'">{{ fmtNaira(bs?.retained_income_kobo) }}</span>
            </div>
          </div>
        </div>

        <div class="bg-white dark:bg-zinc-900 rounded-xl border border-zinc-200 dark:border-zinc-800 p-5" v-if="trial">
          <div class="flex items-center justify-between mb-3">
            <h3 class="font-semibold text-zinc-700 dark:text-zinc-200">Trial balance</h3>
            <UBadge :color="trial.balanced ? 'success' : 'error'" variant="subtle" size="xs">
              {{ trial.balanced ? 'Balanced' : 'OUT OF BALANCE' }}
            </UBadge>
          </div>
          <div class="space-y-1 text-xs max-h-80 overflow-y-auto thin-scroll">
            <div v-for="l in trial.lines" :key="l.id" class="flex justify-between py-1 border-b border-zinc-100 dark:border-zinc-800 last:border-0">
              <span class="text-zinc-500 font-mono">{{ l.code }} {{ l.name }}</span>
              <span class="font-medium">{{ fmtNaira(l.balance_kobo) }}</span>
            </div>
          </div>
          <p class="text-[11px] text-zinc-400 mt-2">Dr {{ fmtNaira(trial.total_debits_kobo) }} = Cr {{ fmtNaira(trial.total_credits_kobo) }}</p>
        </div>
      </div>
    </template>

    <!-- JOURNALS -->
    <template v-else-if="tab === 'journals'">
      <div class="mb-3">
        <UButton icon="i-lucide-plus" @click="showJournal = true">New manual journal</UButton>
      </div>
      <div class="space-y-3">
        <div v-for="j in journals" :key="j.id" class="bg-white dark:bg-zinc-900 rounded-xl border border-zinc-200 dark:border-zinc-800 p-4">
          <div class="flex items-center gap-2 flex-wrap mb-2">
            <span class="font-mono font-bold text-primary-600">{{ j.entry_no }}</span>
            <StatusBadge :status="j.status" />
            <UBadge color="neutral" variant="subtle" size="xs">{{ titleize(j.source_type) }}</UBadge>
            <span class="text-sm text-zinc-600 dark:text-zinc-300">{{ j.memo }}</span>
            <span class="text-[11px] text-zinc-400 ml-auto">{{ fmtDateTime(j.entry_date) }}</span>
            <UButton v-if="j.status === 'POSTED'" size="xs" variant="ghost" color="error" icon="i-lucide-undo-2" @click="reverseEntry(j)">Reverse</UButton>
          </div>
          <table class="w-full text-xs">
            <tbody>
              <tr v-for="(l, i) in j.lines" :key="i" class="border-t border-zinc-100 dark:border-zinc-800">
                <td class="py-1.5 font-mono text-zinc-400 w-16">{{ l.account_code }}</td>
                <td class="py-1.5 text-zinc-600 dark:text-zinc-300">{{ l.account_name }}</td>
                <td class="py-1.5 text-right text-emerald-600 w-28">{{ l.debit_kobo ? fmtNaira(l.debit_kobo) : '' }}</td>
                <td class="py-1.5 text-right text-amber-600 w-28 pr-1">{{ l.credit_kobo ? fmtNaira(l.credit_kobo) : '' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>

    <!-- EXPENSES -->
    <template v-else-if="tab === 'expenses'">
      <div class="mb-3">
        <UButton icon="i-lucide-plus" @click="showExpense = true">Register expense</UButton>
      </div>
      <DataTable export-title="Expenses" :columns="[
        { key: 'category', label: 'Category' },
        { key: 'description', label: 'Description' },
        { key: 'payee', label: 'Payee' },
        { key: 'amount', label: 'Amount', align: 'right' },
        { key: 'status', label: 'Status' },
        { key: 'actions', label: '' },
      ]" :rows="expenses.map(e => ({ ...e, amount: fmtNaira(e.amount_kobo) }))" :loading="loading" empty-title="No expenses">
        <template #amount="{ value }"><span class="font-semibold">{{ value }}</span></template>
        <template #status="{ row }"><StatusBadge :status="row.status" /></template>
        <template #actions="{ row }">
          <div v-if="row.status === 'PENDING_APPROVAL'" class="flex gap-1" @click.stop>
            <UButton size="xs" color="success" variant="soft" @click="approveExpense(row, true)">Approve</UButton>
            <UButton size="xs" color="error" variant="soft" @click="approveExpense(row, false)">Reject</UButton>
          </div>
        </template>
      </DataTable>
    </template>

    <!-- BANK -->
    <template v-else>
      <DataTable export-title="Accounts" :columns="[
        { key: 'txn_date', label: 'Date' },
        { key: 'account_name', label: 'Account' },
        { key: 'narration', label: 'Narration' },
        { key: 'bank_ref', label: 'Reference' },
        { key: 'direction', label: 'Dr/Cr' },
        { key: 'amount', label: 'Amount', align: 'right' },
      ]" :rows="bank.map(t => ({ ...t, amount: fmtNaira(t.amount_kobo), txn_date: fmtDate(t.txn_date) }))" :loading="loading" empty-title="No bank transactions">
        <template #direction="{ value }">
          <UBadge :color="value === 'CREDIT' ? 'success' : 'warning'" variant="subtle" size="xs">{{ value }}</UBadge>
        </template>
      </DataTable>
    </template>

    <!-- journal modal -->
    <UModal v-model:open="showJournal" :ui="{ content: 'max-w-xl' }" title="New manual journal">
      <template #body>
        <div class="space-y-3">
          <UFormField label="Memo"><UInput v-model="jMemo" class="w-full" placeholder="e.g. Owner draw, correction..." /></UFormField>
          <div v-for="(l, i) in jLines" :key="i" class="grid grid-cols-[1fr_100px_100px] gap-2 items-end">
            <UFormField :label="i === 0 ? 'Account' : ''"><USelect placeholder="Choose..." @update:model-value="(v: any) => { l.account_id = v }" :model-value="l.account_id || undefined" class="w-full" :items="accountOptions" /></UFormField>
            <UFormField :label="i === 0 ? 'Debit ₦' : ''"><UInput v-model="l.debit_naira" class="w-full" /></UFormField>
            <UFormField :label="i === 0 ? 'Credit ₦' : ''"><UInput v-model="l.credit_naira" class="w-full" /></UFormField>
          </div>
          <UButton size="xs" variant="soft" icon="i-lucide-plus" @click="jLines.push({ account_id: 0, debit_naira: '', credit_naira: '' })">Add line</UButton>
          <UAlert color="info" variant="subtle" icon="i-lucide-scale" title="Total debits must equal total credits. Entries that do not balance are rejected." />
        </div>
      </template>
      <template #footer>
        <div class="flex justify-end gap-2 w-full">
          <UButton variant="ghost" color="neutral" @click="showJournal = false">Cancel</UButton>
          <UButton :loading="jSaving" @click="postJournal">Post journal</UButton>
        </div>
      </template>
    </UModal>

    <!-- reversal modal -->
    <UModal :open="!!revEntry" @update:open="(v: boolean) => { if (!v) revEntry = null }" :title="`Reverse ${revEntry?.entry_no || ''}`">
      <template #body>
        <div class="space-y-3">
          <UAlert color="warning" variant="subtle" icon="i-lucide-undo-2" title="Posted entries are immutable." description="A reversal entry with mirrored lines will be created and linked to the original." />
          <UFormField label="Reason (optional)"><UInput v-model="revReason" class="w-full" /></UFormField>
        </div>
      </template>
      <template #footer>
        <div class="flex justify-end gap-2 w-full">
          <UButton variant="ghost" color="neutral" @click="revEntry = null">Cancel</UButton>
          <UButton color="error" @click="confirmReverse">Post reversal</UButton>
        </div>
      </template>
    </UModal>

    <!-- expense modal -->
    <UModal v-model:open="showExpense" title="Register expense">
      <template #body>
        <div class="grid sm:grid-cols-2 gap-3">
          <UFormField label="Category">
            <USelect v-model="eForm.category" class="w-full" :items="['Fuel', 'Staff Salaries', 'Warehouse Rent', 'Utilities', 'Vehicle Maintenance', 'Packaging', 'Transport', 'Communications', 'Administrative', 'Other']" />
          </UFormField>
          <UFormField label="Payee"><UInput v-model="eForm.payee" class="w-full" /></UFormField>
          <UFormField label="Amount (₦)"><UInput v-model="eForm.amount_naira" class="w-full" /></UFormField>
          <UFormField label="Payment method">
            <USelect v-model="eForm.method" class="w-full" :items="[{ label: 'Cash', value: 'CASH' }, { label: 'Bank transfer', value: 'BANK_TRANSFER' }]" />
          </UFormField>
          <UFormField label="Description" class="sm:col-span-2"><UTextarea v-model="eForm.description" :rows="2" class="w-full" /></UFormField>
        </div>
      </template>
      <template #footer>
        <div class="flex justify-end gap-2 w-full">
          <UButton variant="ghost" color="neutral" @click="showExpense = false">Cancel</UButton>
          <UButton :loading="eSaving" @click="createExpense">Submit</UButton>
        </div>
      </template>
    </UModal>
  </div>
</template>
