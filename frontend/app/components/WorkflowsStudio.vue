<script setup lang="ts">
/* Workflows Studio — an n8n-style, workflow-first builder for Olwen.
 *
 * Everything here is a *workflow*: a trigger (when) + ordered steps that run top
 * to bottom. Producer steps set the working "content"; sink steps consume it.
 *
 * This component is EMBEDDABLE: its root is a plain flex container that fills its
 * parent (it lives inside a Settings pane AND inside an overlay). It has no
 * fixed-position chrome, no header bar, and no close button of its own — the
 * surrounding surface owns that. It manages its own state and loads on mount. */
import { computed, onMounted, reactive, ref } from 'vue'
import {
  useSchedules,
  type OlwenSchedule,
  type ScheduleAction,
  type SchedulePayload,
} from '../composables/useSchedules'

const { schedules, error, loading, load, create, update, toggle, runNow, remove } = useSchedules()

const vFocus = { mounted: (el: HTMLElement) => el.focus() }

// ── step contract (frozen) ───────────────────────────────────────────────────
// A single step. `op` picks what it does; the rest are op-specific params. The
// running content flows step→step: producers set it, sinks use it.
type StepOp =
  | 'message'
  | 'morning_brief'
  | 'read_news'
  | 'ask_olwen'
  | 'save_file'
  | 'send_email'
  | 'send_telegram'

type WorkflowStep = {
  op: StepOp
  text?: string      // message
  prompt?: string    // ask_olwen
  filename?: string  // save_file
  subject?: string   // send_email
  to?: string        // send_email (comma-separated, optional)
}

const PALETTE: { op: StepOp; label: string }[] = [
  { op: 'message', label: 'Write a message' },
  { op: 'morning_brief', label: 'Get my morning brief' },
  { op: 'read_news', label: 'Get the news' },
  { op: 'ask_olwen', label: 'Ask Olwen' },
  { op: 'save_file', label: 'Save to a file' },
  { op: 'send_email', label: 'Send email' },
  { op: 'send_telegram', label: 'Send Telegram message' },
]

// Short label for the compact card chain summary.
const CHAIN_LABELS: Record<StepOp, string> = {
  message: 'Message',
  morning_brief: 'Brief',
  read_news: 'Get news',
  ask_olwen: 'Ask Olwen',
  save_file: 'Save file',
  send_email: 'Email',
  send_telegram: 'Telegram',
}

// `workflow` isn't part of the ScheduleAction union (the backend contract lives
// elsewhere) — cast at the boundary, both writing and reading.
type WorkflowAction = { type: 'workflow'; steps: WorkflowStep[] }

const defaultTz = (() => {
  try { return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC' } catch { return 'UTC' }
})()

// ── views ────────────────────────────────────────────────────────────────────
type View = 'list' | 'builder'
const view = ref<View>('list')
const editingId = ref<string | null>(null)

// only workflows belong in this studio
const workflows = computed(() =>
  schedules.value.filter(s => (s.action as { type?: string } | null)?.type === 'workflow'),
)

// ── builder form ─────────────────────────────────────────────────────────────
const form = reactive({
  name: '',
  steps: [] as WorkflowStep[],
  advanced: false,
  dailyTime: '08:00',
  cronExpr: '0 8 * * *',
  tz: defaultTz,
})
const submitting = ref(false)
const formError = ref('')

function blankStep(): WorkflowStep { return { op: 'message' } }

function resetForm() {
  form.name = ''
  form.steps = [blankStep()]
  form.advanced = false
  form.dailyTime = '08:00'
  form.cronExpr = '0 8 * * *'
  form.tz = defaultTz
  formError.value = ''
}

function openCreate() {
  editingId.value = null
  resetForm()
  view.value = 'builder'
}

function openEdit(s: OlwenSchedule) {
  editingId.value = s.id
  formError.value = ''
  form.name = s.name
  const action = s.action as unknown as WorkflowAction
  const steps = Array.isArray(action?.steps) ? action.steps : []
  // clone so edits don't mutate the shared store object
  form.steps = steps.length
    ? steps.map(st => ({ ...st }))
    : [blankStep()]
  form.advanced = s.schedule_kind === 'cron'
  form.dailyTime = s.daily_time || '08:00'
  form.cronExpr = s.cron_expr || '0 8 * * *'
  form.tz = s.tz || defaultTz
  view.value = 'builder'
}

function cancelBuilder() {
  view.value = 'list'
  editingId.value = null
}

// ── step editor ──────────────────────────────────────────────────────────────
function addStep() { form.steps.push(blankStep()) }
function removeStep(i: number) { form.steps.splice(i, 1) }
function moveStep(i: number, dir: -1 | 1) {
  const j = i + dir
  if (j < 0 || j >= form.steps.length) return
  const s = form.steps[i]!
  form.steps.splice(i, 1)
  form.steps.splice(j, 0, s)
}

// Build the steps array, validating required params and stripping empties.
function buildSteps(): WorkflowStep[] | null {
  if (!form.steps.length) { formError.value = 'Add at least one step.'; return null }
  const out: WorkflowStep[] = []
  for (let i = 0; i < form.steps.length; i++) {
    const s = form.steps[i]!
    const step: WorkflowStep = { op: s.op }
    if (s.op === 'message') {
      const text = (s.text || '').trim()
      if (!text) { formError.value = `Step ${i + 1}: write the message text.`; return null }
      step.text = text
    } else if (s.op === 'ask_olwen') {
      const prompt = (s.prompt || '').trim()
      if (!prompt) { formError.value = `Step ${i + 1}: tell Olwen what to do.`; return null }
      step.prompt = prompt
    } else if (s.op === 'save_file') {
      const filename = (s.filename || '').trim()
      if (!filename) { formError.value = `Step ${i + 1}: name the file to save.`; return null }
      step.filename = filename
    } else if (s.op === 'send_email') {
      const subject = (s.subject || '').trim()
      if (!subject) { formError.value = `Step ${i + 1}: the email needs a subject.`; return null }
      step.subject = subject
      const to = (s.to || '').trim()
      if (to) step.to = to
    }
    // morning_brief, read_news, send_telegram: no params
    out.push(step)
  }
  return out
}

async function save() {
  formError.value = ''
  const name = form.name.trim()
  if (!name) { formError.value = 'Give your workflow a name.'; return }
  const steps = buildSteps()
  if (!steps) return

  const payload: SchedulePayload = {
    name,
    action: { type: 'workflow', steps } as unknown as ScheduleAction,
    schedule_kind: form.advanced ? 'cron' : 'daily',
    tz: form.tz.trim() || defaultTz,
    // workflows do their own sending (save_file / send_email / send_telegram) —
    // the schedule itself never picks a delivery channel.
    notify_channel: 'inapp',
  }
  if (form.advanced) payload.cron_expr = form.cronExpr.trim()
  else payload.daily_time = form.dailyTime

  submitting.value = true
  // On create, default to enabled. On update, leave `enabled` alone so editing a
  // paused workflow doesn't silently turn it back on (the list has a toggle).
  const result = editingId.value
    ? await update(editingId.value, payload)
    : await create({ ...payload, enabled: true })
  submitting.value = false

  if (result) {
    view.value = 'list'
    editingId.value = null
    resetForm()
  } else {
    formError.value = error.value || 'Could not save workflow.'
  }
}

// ── card helpers ─────────────────────────────────────────────────────────────
function trunc(s: string, n: number): string {
  return s.length > n ? `${s.slice(0, n - 1)}…` : s
}

function stepChain(s: OlwenSchedule): string[] {
  const action = s.action as unknown as WorkflowAction
  const steps = Array.isArray(action?.steps) ? action.steps : []
  if (!steps.length) return ['(empty)']
  return steps.map(st => CHAIN_LABELS[st.op] || st.op)
}

function scheduleSummary(s: OlwenSchedule): string {
  if (s.schedule_kind === 'cron') return `cron: ${s.cron_expr}`
  const t = s.daily_time || '—'
  return `Daily at ${t} · ${s.tz}`
}

function fmtAbs(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}

// Friendly relative time, e.g. "in 3h", "in 2d", "12m ago".
function fmtRel(iso: string | null): string {
  if (!iso) return 'not scheduled'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const diff = d.getTime() - Date.now()
  const past = diff < 0
  const abs = Math.abs(diff)
  const mins = Math.round(abs / 60000)
  let label: string
  if (mins < 1) label = 'now'
  else if (mins < 60) label = `${mins}m`
  else if (mins < 1440) label = `${Math.round(mins / 60)}h`
  else label = `${Math.round(mins / 1440)}d`
  if (label === 'now') return past ? 'just now' : 'now'
  return past ? `${label} ago` : `in ${label}`
}

const STATUS_COLORS: Record<string, string> = {
  ok: '#34D399',
  error: '#F87171',
  skipped: '#FBBF24',
}
function statusColor(s: OlwenSchedule): string {
  if (s.last_status === 'running') return 'var(--accent)'
  return STATUS_COLORS[s.last_status || ''] || 'var(--text-muted)'
}
function statusTitle(s: OlwenSchedule): string {
  const parts: string[] = [`status: ${s.last_status || 'never run'}`]
  if (s.last_run) parts.push(`last run: ${fmtAbs(s.last_run)}`)
  if (s.last_error) parts.push(`error: ${s.last_error}`)
  return parts.join('\n')
}

// ── per-card actions ─────────────────────────────────────────────────────────
const runningId = ref<string | null>(null)
async function onRunNow(s: OlwenSchedule) {
  runningId.value = s.id
  await runNow(s.id)
  runningId.value = null
}
function onToggle(s: OlwenSchedule) { toggle(s.id) }
function onDelete(s: OlwenSchedule) {
  // eslint-disable-next-line no-alert
  if (window.confirm(`Delete the "${s.name}" workflow?`)) remove(s.id)
}

// which cards have their output expanded
const expanded = reactive<Record<string, boolean>>({})
function toggleOutput(id: string) { expanded[id] = !expanded[id] }

onMounted(() => { load() })
</script>

<template>
  <div class="ws">
    <p v-if="error" class="ws-error">{{ error }}</p>

    <!-- ── LIST VIEW ─────────────────────────────────────────────────────── -->
    <template v-if="view === 'list'">
      <div class="ws-list-head">
        <span class="ws-count">
          {{ workflows.length }} {{ workflows.length === 1 ? 'workflow' : 'workflows' }}
          <template v-if="workflows.length">· {{ workflows.filter(w => w.enabled).length }} active</template>
        </span>
        <button class="ws-new" @click="openCreate">＋ New workflow</button>
      </div>

      <div v-if="loading && !workflows.length" class="ws-empty">Loading…</div>
      <div v-else-if="!workflows.length" class="ws-empty">
        No workflows yet. Build one to have Olwen run a sequence of steps on a schedule.
      </div>

      <div v-else class="ws-cards">
        <article
          v-for="s in workflows"
          :key="s.id"
          class="ws-card"
          :class="{ 'ws-card--off': !s.enabled }"
        >
          <div class="ws-card-main">
            <div class="ws-card-top">
              <span
                class="ws-status"
                :style="{ background: statusColor(s) }"
                :class="{ 'ws-status--run': s.last_status === 'running' }"
                :title="statusTitle(s)"
              />
              <span class="ws-name">{{ s.name }}</span>
              <label class="ws-switch" :title="s.enabled ? 'Enabled' : 'Disabled'">
                <input type="checkbox" :checked="s.enabled" @change="onToggle(s)">
                <span class="ws-slider" />
              </label>
            </div>

            <!-- compact step chain -->
            <div class="ws-chain">
              <template v-for="(node, i) in stepChain(s)" :key="i">
                <span class="ws-chain-node">{{ node }}</span>
                <span v-if="i < stepChain(s).length - 1" class="ws-chain-arrow">→</span>
              </template>
            </div>

            <div class="ws-line">
              <span class="ws-sched">{{ scheduleSummary(s) }}</span>
            </div>

            <div class="ws-line ws-sub">
              <span :title="s.next_run ? fmtAbs(s.next_run) : ''">
                next: {{ s.enabled ? fmtRel(s.next_run) : 'paused' }}
              </span>
              <span v-if="s.last_run" class="ws-sep">·</span>
              <span v-if="s.last_run" :title="fmtAbs(s.last_run)">last: {{ fmtRel(s.last_run) }}</span>
              <span v-if="s.last_error" class="ws-err-tag" :title="s.last_error">error</span>
            </div>

            <!-- last output -->
            <div v-if="s.last_output" class="ws-output">
              <button class="ws-output-toggle" type="button" @click="toggleOutput(s.id)">
                {{ expanded[s.id] ? '▾' : '▸' }} output
              </button>
              <pre v-if="expanded[s.id]" class="ws-output-full">{{ s.last_output }}</pre>
              <span v-else class="ws-output-peek">{{ trunc(s.last_output, 90) }}</span>
            </div>
          </div>

          <div class="ws-card-actions">
            <button class="ws-run" :disabled="runningId === s.id" @click="onRunNow(s)">
              {{ runningId === s.id ? 'Running…' : 'Run now' }}
            </button>
            <button class="ws-edit" @click="openEdit(s)">Edit</button>
            <button class="ws-del" title="Delete" @click="onDelete(s)">✕</button>
          </div>
        </article>
      </div>
    </template>

    <!-- ── BUILDER VIEW ──────────────────────────────────────────────────── -->
    <form v-else class="ws-builder" @submit.prevent="save">
      <div class="ws-builder-head">
        <span class="ws-builder-title">{{ editingId ? 'Edit workflow' : 'New workflow' }}</span>
      </div>

      <label class="ws-field">
        <span class="ws-flabel">Name</span>
        <input v-model="form.name" class="ws-input" placeholder="e.g. Morning news digest" v-focus>
      </label>

      <!-- WHEN trigger node -->
      <div class="ws-node ws-node--trigger">
        <div class="ws-node-tag">When</div>
        <div class="ws-node-body">
          <div class="ws-trigger-row">
            <span class="ws-flabel">
              Run
              <button type="button" class="ws-adv" @click="form.advanced = !form.advanced">
                {{ form.advanced ? '← simple' : 'Advanced (cron)' }}
              </button>
            </span>
          </div>
          <div v-if="!form.advanced" class="ws-row">
            <input v-model="form.dailyTime" type="time" class="ws-input ws-time">
            <input v-model="form.tz" class="ws-input" placeholder="Timezone">
          </div>
          <div v-else class="ws-row">
            <input v-model="form.cronExpr" class="ws-input ws-mono" placeholder="0 8 * * *">
            <input v-model="form.tz" class="ws-input" placeholder="Timezone">
          </div>
        </div>
      </div>

      <div class="ws-connector">↓</div>

      <!-- steps pipeline -->
      <template v-for="(step, i) in form.steps" :key="i">
        <div class="ws-node">
          <div class="ws-node-num">{{ i + 1 }}</div>
          <div class="ws-node-body">
            <div class="ws-node-row">
              <select v-model="step.op" class="ws-input ws-op">
                <option v-for="o in PALETTE" :key="o.op" :value="o.op">{{ o.label }}</option>
              </select>
              <div class="ws-node-ctrls">
                <button type="button" class="ws-mv" title="Move up" :disabled="i === 0" @click="moveStep(i, -1)">↑</button>
                <button type="button" class="ws-mv" title="Move down" :disabled="i === form.steps.length - 1" @click="moveStep(i, 1)">↓</button>
                <button type="button" class="ws-rm" title="Remove step" @click="removeStep(i)">✕</button>
              </div>
            </div>

            <!-- per-op params -->
            <template v-if="step.op === 'message'">
              <textarea v-model="step.text" class="ws-input ws-area" rows="3" placeholder="Type the text this workflow works with…" />
              <span class="ws-help">This literal text becomes the working content for the steps below.</span>
            </template>

            <template v-else-if="step.op === 'ask_olwen'">
              <textarea v-model="step.prompt" class="ws-input ws-area" rows="2" placeholder="e.g. Summarize this in 3 bullet points: {content}" />
              <span class="ws-help">Write <code>{content}</code> to insert the text from the previous step.</span>
            </template>

            <template v-else-if="step.op === 'save_file'">
              <input v-model="step.filename" class="ws-input" placeholder="news-{date}.txt">
              <span class="ws-help">Saved under <code>~/Olwen</code>. <code>{date}</code> becomes today's date.</span>
            </template>

            <template v-else-if="step.op === 'send_email'">
              <input v-model="step.subject" class="ws-input" placeholder="Subject line">
              <input v-model="step.to" class="ws-input" placeholder="To (optional, comma-separated — defaults to you)">
            </template>

            <template v-else-if="step.op === 'send_telegram'">
              <span class="ws-help">Sends the current content to Telegram. Put this after a step that produces text.</span>
            </template>

            <template v-else-if="step.op === 'morning_brief' || step.op === 'read_news'">
              <span class="ws-help">No setup needed — this produces content for the steps below.</span>
            </template>
          </div>
        </div>
        <div class="ws-connector">↓</div>
      </template>

      <button type="button" class="ws-add" @click="addStep">＋ Add step</button>

      <p v-if="formError" class="ws-form-error">{{ formError }}</p>

      <div class="ws-builder-actions">
        <button type="button" class="ws-btn-ghost" @click="cancelBuilder">Cancel</button>
        <button type="submit" class="ws-btn-primary" :disabled="submitting">
          {{ submitting ? 'Saving…' : (editingId ? 'Save changes' : 'Create workflow') }}
        </button>
      </div>
    </form>
  </div>
</template>

<style scoped>
.ws {
  display: flex;
  flex-direction: column;
  width: 100%;
  color: var(--text);
  font-family: system-ui, -apple-system, 'Segoe UI', sans-serif;
}

.ws-error { color: #F87171; font-size: .82rem; margin: 0 0 1rem; }

/* ── list head ──────────────────────────────────────────────────────────── */
.ws-list-head { display: flex; align-items: center; gap: 1rem; margin-bottom: 1.1rem; }
.ws-count { font-family: 'JetBrains Mono', monospace; font-size: .72rem; letter-spacing: .06em; color: var(--text-muted); }
.ws-new {
  margin-left: auto; background: var(--accent); border: 1px solid var(--accent); color: var(--bg);
  font: inherit; font-weight: 600; font-size: .82rem; padding: .5rem .95rem; border-radius: 9px; cursor: pointer;
}
.ws-new:hover { background: var(--accent-2); border-color: var(--accent-2); }

.ws-empty { color: var(--text-muted); font-size: .88rem; padding: 1.4rem .2rem; text-align: center; line-height: 1.5; }

/* ── cards ──────────────────────────────────────────────────────────────── */
.ws-cards { display: flex; flex-direction: column; gap: .8rem; }
.ws-card { display: flex; gap: 1rem; background: var(--surface-solid); border: 1px solid var(--border-strong); border-radius: 14px; padding: 1rem 1.1rem; }
.ws-card--off { opacity: .62; }
.ws-card-main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: .45rem; }

.ws-card-top { display: flex; align-items: center; gap: .55rem; }
.ws-status { width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0; }
.ws-status--run { animation: ws-pulse 1.1s ease-in-out infinite; }
@keyframes ws-pulse { 0%,100% { opacity: 1; } 50% { opacity: .35; } }
.ws-name { font-size: .98rem; color: var(--text-strong); font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.ws-switch { margin-left: auto; position: relative; display: inline-block; width: 38px; height: 21px; flex-shrink: 0; }
.ws-switch input { opacity: 0; width: 0; height: 0; }
.ws-slider { position: absolute; inset: 0; background: var(--surface-2); border: 1px solid var(--border-strong); border-radius: 999px; cursor: pointer; transition: background .15s ease, border-color .15s ease; }
.ws-slider::before { content: ''; position: absolute; height: 15px; width: 15px; left: 2px; top: 2px; background: var(--text-muted); border-radius: 50%; transition: transform .15s ease, background .15s ease; }
.ws-switch input:checked + .ws-slider { background: color-mix(in srgb, var(--accent) 35%, transparent); border-color: var(--accent); }
.ws-switch input:checked + .ws-slider::before { transform: translateX(17px); background: var(--accent); }

/* step chain */
.ws-chain { display: flex; flex-wrap: wrap; align-items: center; gap: .35rem; }
.ws-chain-node {
  font-family: 'JetBrains Mono', monospace; font-size: .7rem; letter-spacing: .02em;
  color: var(--text); background: var(--surface-2); border: 1px solid var(--border);
  border-radius: 6px; padding: .12rem .4rem;
}
.ws-chain-arrow { color: var(--accent-2); font-size: .72rem; }

.ws-line { font-family: 'JetBrains Mono', monospace; font-size: .72rem; color: var(--text-muted); display: flex; align-items: center; gap: .5rem; flex-wrap: wrap; }
.ws-sched { color: var(--accent-2); letter-spacing: .04em; }
.ws-sub { color: var(--text-muted); }
.ws-sep { opacity: .5; }
.ws-err-tag { color: #F87171; border: 1px solid color-mix(in srgb, #F87171 45%, transparent); border-radius: 999px; padding: 0 .4rem; cursor: help; }

.ws-output { margin-top: .25rem; border-top: 1px solid var(--border); padding-top: .4rem; }
.ws-output-toggle { background: none; border: none; color: var(--text-muted); font: inherit; font-size: .72rem; cursor: pointer; padding: 0; font-family: 'JetBrains Mono', monospace; }
.ws-output-toggle:hover { color: var(--accent); }
.ws-output-peek { display: block; font-size: .78rem; color: var(--text-muted); margin-top: .2rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ws-output-full { margin: .35rem 0 0; font-size: .78rem; color: var(--text); background: var(--bg); border: 1px solid var(--border); border-radius: 8px; padding: .55rem .65rem; max-height: 200px; overflow: auto; white-space: pre-wrap; word-break: break-word; font-family: 'JetBrains Mono', monospace; }

.ws-card-actions { display: flex; flex-direction: column; align-items: flex-end; gap: .45rem; flex-shrink: 0; }
.ws-run, .ws-edit { background: none; border: 1px solid var(--border-strong); color: var(--accent); font: inherit; font-size: .78rem; padding: .35rem .7rem; border-radius: 8px; cursor: pointer; white-space: nowrap; }
.ws-run:hover, .ws-edit:hover { border-color: var(--accent); color: var(--accent-2); }
.ws-run:disabled { opacity: .6; cursor: default; }
.ws-edit { color: var(--text-muted); }
.ws-del { background: none; border: none; color: var(--text-muted); cursor: pointer; font-size: .8rem; padding: .2rem; }
.ws-del:hover { color: #F87171; }

/* ── builder ────────────────────────────────────────────────────────────── */
.ws-builder { display: flex; flex-direction: column; }
.ws-builder-head { margin-bottom: 1rem; }
.ws-builder-title { font-family: 'JetBrains Mono', monospace; font-size: .74rem; letter-spacing: .18em; text-transform: uppercase; color: var(--accent-2); }

.ws-field { display: flex; flex-direction: column; gap: .35rem; margin-bottom: 1rem; }
.ws-flabel { display: flex; align-items: center; gap: .5rem; font-family: 'JetBrains Mono', monospace; font-size: .66rem; letter-spacing: .12em; text-transform: uppercase; color: var(--text-muted); }
.ws-input { background: var(--bg); border: 1px solid var(--border-strong); border-radius: 8px; color: var(--text); font: inherit; font-size: .88rem; padding: .5rem .6rem; outline: none; width: 100%; }
.ws-input:focus { border-color: var(--accent); }
select.ws-input { cursor: pointer; }
.ws-area { resize: vertical; min-height: 60px; }
.ws-mono { font-family: 'JetBrains Mono', monospace; letter-spacing: .04em; }
.ws-time { max-width: 140px; }
.ws-row { display: flex; gap: .6rem; }
.ws-row .ws-input { flex: 1; }

/* flow nodes */
.ws-node {
  display: flex; gap: .7rem;
  background: var(--surface-solid); border: 1px solid var(--border-strong);
  border-radius: 12px; padding: .8rem .85rem;
}
.ws-node--trigger { border-color: var(--accent); box-shadow: var(--glow); }
.ws-node-tag {
  flex-shrink: 0; align-self: flex-start;
  font-family: 'JetBrains Mono', monospace; font-size: .62rem; letter-spacing: .14em; text-transform: uppercase;
  color: var(--accent-2); background: color-mix(in srgb, var(--accent) 18%, transparent);
  border: 1px solid var(--accent); border-radius: 6px; padding: .2rem .45rem;
}
.ws-node-num {
  flex-shrink: 0; width: 24px; height: 24px; border-radius: 50%; display: grid; place-items: center;
  background: color-mix(in srgb, var(--accent) 22%, transparent); border: 1px solid var(--accent);
  color: var(--accent-2); font-family: 'JetBrains Mono', monospace; font-size: .74rem; font-weight: 600;
}
.ws-node-body { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: .45rem; }
.ws-node-row { display: flex; align-items: center; gap: .5rem; }
.ws-op { flex: 1; }
.ws-node-ctrls { display: flex; gap: .2rem; flex-shrink: 0; }
.ws-mv, .ws-rm { background: none; border: 1px solid var(--border-strong); color: var(--text-muted); border-radius: 6px; width: 26px; height: 26px; cursor: pointer; font-size: .8rem; line-height: 1; }
.ws-mv:hover:not(:disabled), .ws-rm:hover { color: var(--accent); border-color: var(--accent); }
.ws-rm:hover { color: #F87171; border-color: color-mix(in srgb, #F87171 50%, transparent); }
.ws-mv:disabled { opacity: .35; cursor: default; }

.ws-trigger-row { display: flex; align-items: center; }
.ws-adv { margin-left: auto; background: none; border: none; color: var(--accent); font: inherit; font-size: .66rem; cursor: pointer; text-transform: none; letter-spacing: normal; }
.ws-adv:hover { color: var(--accent-2); }

.ws-help { font-size: .7rem; color: var(--text-muted); line-height: 1.4; }
.ws-help code { font-family: 'JetBrains Mono', monospace; font-size: .68rem; color: var(--accent-2); background: var(--bg); border: 1px solid var(--border); border-radius: 4px; padding: 0 .25rem; }

.ws-connector { align-self: center; color: var(--text-muted); font-size: 1rem; line-height: 1; padding: .3rem 0; }

.ws-add {
  align-self: flex-start; background: none; border: 1px dashed var(--border-strong); border-radius: 9px;
  color: var(--accent); font: inherit; font-size: .82rem; padding: .45rem .85rem; cursor: pointer; margin-top: .2rem;
}
.ws-add:hover { border-color: var(--accent); color: var(--accent-2); }

.ws-form-error { color: #F87171; font-size: .8rem; margin: .9rem 0 0; }

.ws-builder-actions { display: flex; justify-content: flex-end; gap: .6rem; margin-top: 1.2rem; }
.ws-btn-ghost { background: none; border: 1px solid var(--border-strong); color: var(--text-muted); font: inherit; font-size: .84rem; padding: .45rem .9rem; border-radius: 8px; cursor: pointer; }
.ws-btn-ghost:hover { color: var(--text); border-color: var(--text-muted); }
.ws-btn-primary { background: var(--accent); border: 1px solid var(--accent); color: var(--bg); font: inherit; font-weight: 600; font-size: .84rem; padding: .45rem 1.1rem; border-radius: 8px; cursor: pointer; }
.ws-btn-primary:hover { background: var(--accent-2); border-color: var(--accent-2); }
.ws-btn-primary:disabled { opacity: .6; cursor: default; }
</style>
