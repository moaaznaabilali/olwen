<script setup lang="ts">
/* Dev Studio — a project cockpit.
 * Freely movable/resizable terminal windows on a canvas, plus a live rail where
 * Olwen reads the project's git state + PRD phases and tells you where Claude Code
 * stopped and what to resume — and you discuss it with him. */
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import OlwenEntity from './OlwenEntity.vue'
import TerminalApp from './TerminalApp.vue'

const emit = defineEmits<{ close: [] }>()

const apiBase = useRuntimeConfig().public.apiBase as string
function h(): Record<string, string> {
  const t = import.meta.client ? localStorage.getItem('olwen_access') : null
  return t ? { Authorization: `Bearer ${t}`, 'Content-Type': 'application/json' } : { 'Content-Type': 'application/json' }
}

type StudioProject = { name: string; path: string; autoStart?: string | null }
const incoming = useState<StudioProject[]>('devstudio:incoming', () => [])
const projects = computed(() => incoming.value.slice(0, 2))
const activeIdx = ref(0)
const active = computed(() => projects.value[activeIdx.value] || projects.value[0])

const entered = ref(false)

// ── movable / resizable terminal windows ─────────────────────────────
interface Win { x: number; y: number; w: number; h: number; z: number }
const wins = reactive<Record<string, Win>>({})
let topZ = 10
function ensureWins() {
  projects.value.forEach((p, i) => {
    if (!wins[p.path]) {
      wins[p.path] = { x: 40 + i * 56, y: 30 + i * 48, w: 760, h: 480, z: ++topZ }
    }
  })
}
function focusWin(path: string) { const w = wins[path]; if (w) w.z = ++topZ }
function closeProject(path: string) {
  incoming.value = incoming.value.filter(p => p.path !== path)
  delete wins[path]
  if (!incoming.value.length) { close(); return }
  if (activeIdx.value >= projects.value.length) activeIdx.value = 0
}
ensureWins()  // position windows synchronously so the first paint is placed

let drag: { path: string; mode: 'move' | 'resize'; sx: number; sy: number; ox: number; oy: number; ow: number; oh: number } | null = null
function startDrag(e: PointerEvent, path: string, mode: 'move' | 'resize') {
  focusWin(path)
  const w = wins[path]
  if (!w) return
  drag = { path, mode, sx: e.clientX, sy: e.clientY, ox: w.x, oy: w.y, ow: w.w, oh: w.h }
  window.addEventListener('pointermove', onDrag)
  window.addEventListener('pointerup', endDrag)
  e.preventDefault()
}
function onDrag(e: PointerEvent) {
  if (!drag) return
  const w = wins[drag.path]
  if (!w) return
  const dx = e.clientX - drag.sx, dy = e.clientY - drag.sy
  if (drag.mode === 'move') { w.x = Math.max(0, drag.ox + dx); w.y = Math.max(0, drag.oy + dy) }
  else { w.w = Math.max(360, drag.ow + dx); w.h = Math.max(240, drag.oh + dy) }
}
function endDrag() {
  drag = null
  window.removeEventListener('pointermove', onDrag)
  window.removeEventListener('pointerup', endDrag)
}

// ── project intelligence: git state + PRD/phases ─────────────────────
interface Intel {
  ok: boolean; name?: string; branch?: string; ahead?: number; behind?: number
  stopped?: string; commits?: { hash: string; subject: string; when: string }[]
  dirty?: string[]; phases?: { title: string; items: { text: string; done: boolean }[]; done: number; total: number }[]
  prd_name?: string
}
const intel = ref<Intel | null>(null)
const intelLoading = ref(false)
async function loadIntel() {
  const p = active.value
  if (!p) return
  intelLoading.value = true
  try {
    intel.value = await $fetch<Intel>(`${apiBase}/api/devmode/intel?path=${encodeURIComponent(p.path)}`, { headers: h() })
  } catch { intel.value = { ok: false } }
  finally { intelLoading.value = false }
}

// ── unattended jobs: give Olwen a goal, walk away, get a PR ──────────
interface Job { id: string; goal: string; project: string; status: string; branch?: string; pr_url?: string; note: string; question?: string }
const jobs = ref<Job[]>([])
const jobGoal = ref('')
const jobReply = reactive<Record<string, string>>({})
async function replyJob(id: string) {
  const a = (jobReply[id] || '').trim(); if (!a) return
  jobReply[id] = ''
  try {
    await fetch(`${apiBase}/api/devmode/jobs/${id}/reply`, {
      method: 'POST', headers: h(), body: JSON.stringify({ answer: a }),
    })
    loadJobs()
  } catch { /* */ }
}
async function loadJobs() {
  try {
    const res = await fetch(`${apiBase}/api/devmode/jobs`, { headers: h() })
    if (res.ok) jobs.value = (await res.json()).jobs || []
  } catch { /* */ }
}
async function queueJob() {
  const g = jobGoal.value.trim(); const p = active.value
  if (!g || !p) return
  jobGoal.value = ''
  try {
    await fetch(`${apiBase}/api/devmode/jobs`, {
      method: 'POST', headers: h(),
      body: JSON.stringify({ goal: g, path: p.path, name: p.name, notify: true }),
    })
    loadJobs()
  } catch { /* */ }
}

// ── discussion with Olwen (project-aware) ────────────────────────────
interface Msg { role: 'you' | 'olwen' | 'claude'; text: string }
const discussion = ref<Msg[]>([])
const thinking = ref(false)
const input = ref('')
const feed = ref<HTMLElement | null>(null)

// auto = Olwen manages Claude Code to completion · claude = relay one prompt ·
// olwen = ask Olwen for advice.
const target = ref<'auto' | 'claude' | 'olwen'>('auto')
type TermExpose = { sendInput: (d: string, submit?: boolean) => boolean; getOutput: () => string; idleFor: () => number }
const termRefs = reactive<Record<string, TermExpose | null>>({})
function setTermRef(path: string, el: unknown) { termRefs[path] = (el as TermExpose) || null }
function activeTerm(): TermExpose | null { const p = active.value; return p ? termRefs[p.path] || null : null }

// ── Activity view: a friendly, live picture of what Claude Code is doing, in
// plain language (no jargon), parsed from the terminal — for non-developers.
type Step = { icon: string; text: string }
const winView = reactive<Record<string, 'terminal' | 'activity'>>({})
function viewOf(path: string): 'terminal' | 'activity' { return winView[path] || 'activity' }
function setView(path: string, v: 'terminal' | 'activity') { winView[path] = v }
const activity = reactive<Record<string, Step[]>>({})
const previewUrl = reactive<Record<string, string>>({})

function humanizeFile(p: string): string {
  let n = (p.split('/').pop() || p).replace(/\.[a-z0-9]+$/i, '')
  n = n.replace(/[-_]+/g, ' ').replace(/([a-z0-9])([A-Z])/g, '$1 $2').trim().toLowerCase()
  return n || 'a file'
}
function friendlyBash(cmd: string): string {
  const c = cmd.toLowerCase()
  if (/\b(build|compile|tsc|webpack)\b/.test(c)) return 'Building the project'
  if (/\b(test|jest|vitest|pytest)\b/.test(c)) return 'Running the tests'
  if (/\bgit (commit|add)\b/.test(c)) return 'Saving the changes'
  if (/\bgit (push|pull|fetch)\b/.test(c)) return 'Syncing with the repo'
  if (/\b(install|npm i|pnpm i|yarn|pip)\b/.test(c)) return 'Installing tools'
  if (/\b(dev|serve|preview|start)\b/.test(c)) return 'Starting the preview'
  return 'Exploring the project'
}
const TOOL_RE = /[●⏺•]?\s*(Read|Edit|Update|Write|Create|MultiEdit|Bash|Grep|Glob|Search|Task|WebFetch|WebSearch|TodoWrite|NotebookEdit)\(([^)\n]{0,120})/g

function stepFor(tool: string, raw: string): Step {
  const f = humanizeFile(raw)
  switch (tool) {
    case 'Read': return { icon: '📖', text: `Looking at the ${f}` }
    case 'Grep': case 'Glob': case 'Search': return { icon: '🔍', text: 'Finding the right files' }
    case 'Edit': case 'Update': case 'MultiEdit': case 'NotebookEdit': return { icon: '✏️', text: `Updating the ${f}` }
    case 'Write': case 'Create': return { icon: '✨', text: `Creating the ${f}` }
    case 'Bash': return { icon: '⚡', text: friendlyBash(raw) }
    case 'Task': return { icon: '🤖', text: 'Working through a sub-task' }
    case 'WebFetch': case 'WebSearch': return { icon: '🌐', text: 'Looking it up online' }
    case 'TodoWrite': return { icon: '🗒️', text: 'Planning the steps' }
    default: return { icon: '•', text: 'Working' }
  }
}

function parseActivity(out: string): Step[] {
  const steps: Step[] = []
  TOOL_RE.lastIndex = 0
  let m: RegExpExecArray | null
  while ((m = TOOL_RE.exec(out)) !== null) {
    const tool = m[1]; const raw = m[2]
    if (!tool || raw === undefined) continue
    const s = stepFor(tool, raw.trim())
    const prev = steps[steps.length - 1]
    if (!prev || prev.text !== s.text) steps.push(s)
  }
  return steps.slice(-16)
}

function detectPreviewUrl(out: string): string {
  const m = out.match(/https?:\/\/(?:localhost|127\.0\.0\.1):\d{2,5}\/?/i)
  return m ? m[0] : ''
}

// ── Live mode: a "remote control" look — a frame around the whole screen and a
// ghost mouse cursor that moves and JUMPS between the windows, like someone took
// control of the device. The cursor follows whichever terminal Claude Code is in.
const live = ref(false)
const animating = ref(false)

function tileWindows() {
  // Lay the two windows side by side so both are visible while Olwen works.
  if (projects.value.length < 2) return
  const railW = window.innerWidth > 1040 ? 360 : 320
  const W = window.innerWidth - railW
  const H = window.innerHeight - 58
  const w = (W - 60) / 2
  animating.value = true
  projects.value.forEach((p, i) => {
    const win = wins[p.path]; if (!win) return
    win.x = 20 + i * (w + 20); win.y = 24; win.w = w; win.h = H - 56
  })
  setTimeout(() => { animating.value = false }, 850)
}
function toggleLive() { live.value = !live.value; if (live.value) tileWindows() }

// Focus the terminal that is ACTUALLY producing output — a real signal, not a
// fake animation. With two projects this brings the busy one to the front.
function autoFollow() {
  if (!live.value || projects.value.length < 2) return
  let busy = -1, busiest = 2500
  projects.value.forEach((p, i) => {
    const tr = termRefs[p.path]; if (!tr) return
    const idle = tr.idleFor()
    if (idle < busiest) { busiest = idle; busy = i }
  })
  if (busy >= 0 && busy !== activeIdx.value) {
    activeIdx.value = busy
    const p = active.value; if (p) focusWin(p.path)
  }
}

function sendToClaude(text: string) {
  const term = activeTerm()
  if (!term || !term.sendInput(text, true)) {
    discussion.value.push({ role: 'olwen', text: "The terminal isn't ready yet — give Claude Code a second to boot." })
    scrollFeed(); return
  }
  discussion.value.push({ role: 'claude', text })
  scrollFeed()
}

// ── Olwen conducts Claude Code: drive it, read the terminal, reply, until done ──
const conducting = ref(false)
const conductStatus = ref('')
function stopConduct() { conducting.value = false; conductStatus.value = '' }

function oneLine(s: string): string { return s.replace(/\s*\n+\s*/g, ' ').replace(/\s{2,}/g, ' ').trim() }

async function callConduct(goal: string, out: string, transcript: { from: string; text: string }[]): Promise<{ action: string; message: string; note: string }> {
  try {
    const res = await fetch(`${apiBase}/api/devmode/conduct`, {
      method: 'POST', headers: h(),
      body: JSON.stringify({ goal, output: out, transcript }),
    })
    return await res.json()
  } catch (e) { return { action: 'blocked', message: '', note: `couldn't reach the conductor (${(e as Error).message})` } }
}

// Wait until Claude Code goes quiet (idle) — it finished a step and is waiting.
// ~4s of silence is enough to tell "done with this turn" from a thinking pause,
// without making small tasks crawl.
async function waitIdle(term: TermExpose, quietMs = 4000, maxMs = 240_000): Promise<void> {
  const start = Date.now()
  await new Promise(r => setTimeout(r, 1000))  // let it start reacting first
  while (conducting.value && Date.now() - start < maxMs) {
    if (term.idleFor() > quietMs) return
    await new Promise(r => setTimeout(r, 400))
  }
}

async function runWithOlwen(goal: string) {
  const term = activeTerm()
  if (!term) { discussion.value.push({ role: 'olwen', text: 'No terminal to drive yet.' }); return }
  conducting.value = true
  discussion.value.push({ role: 'you', text: goal })
  scrollFeed()
  const transcript: { from: string; text: string }[] = []
  let output = term.getOutput()
  let lastLen = output.length
  let noProgress = 0
  for (let i = 0; i < 16 && conducting.value; i++) {
    conductStatus.value = i === 0 ? 'Olwen is planning the task…' : 'Olwen is checking the session…'
    // Olwen INTERPRETS the goal into a clear instruction (turn 0), or reads the
    // terminal and decides the next move (later turns).
    const r = await callConduct(`${projectContext()}\n\nGOAL: ${goal}`, output, transcript)
    if (r.action === 'done') { discussion.value.push({ role: 'olwen', text: `✓ ${r.note || 'Task complete.'}` }); break }
    if (r.action === 'blocked') { discussion.value.push({ role: 'olwen', text: `⚠ ${r.note || 'I need you on this one.'}` }); break }
    if (r.message) {
      const line = oneLine(r.message)  // single line so Claude Code's input submits cleanly
      if (!term.sendInput(line, true)) {
        discussion.value.push({ role: 'olwen', text: "The terminal isn't connected — wait for it to (re)launch, then retry." }); break
      }
      if (r.note) discussion.value.push({ role: 'olwen', text: r.note })
      discussion.value.push({ role: 'claude', text: line })
      transcript.push({ from: 'olwen', text: line })
      conductStatus.value = 'Claude Code is working…'
    }
    scrollFeed()
    await waitIdle(term)
    output = term.getOutput()
    // If Claude Code didn't react at all, the input didn't take — don't pile on.
    if (output.length <= lastLen + 16) {
      if (++noProgress >= 2) {
        discussion.value.push({ role: 'olwen', text: "⚠ Claude Code isn't reacting to input — check the terminal, then try again." })
        break
      }
    } else { noProgress = 0 }
    lastLen = output.length
    transcript.push({ from: 'claude', text: output.slice(-1800) })
  }
  conducting.value = false
  conductStatus.value = ''
  scrollFeed()
}

function projectContext(): string {
  const p = active.value, it = intel.value
  if (!p) return ''
  let s = `[Dev Studio — you are pairing with me on a coding project; Claude Code runs in the terminal] Project "${p.name}" at ${p.path}.`
  if (it?.ok) {
    s += ` Git: branch ${it.branch}, ${it.ahead || 0} unpushed, ${it.behind || 0} behind. ${it.stopped || ''}`
    if (it.commits?.length) s += ` Recent commits: ${it.commits.slice(0, 4).map(c => c.subject).join(' | ')}.`
    if (it.dirty?.length) s += ` Uncommitted: ${it.dirty.slice(0, 10).join(', ')}.`
    if (it.phases?.length) s += ` Plan phases: ${it.phases.map(ph => `${ph.title} ${ph.done}/${ph.total}`).join('; ')}.`
  }
  return s
}

async function askOlwen(text: string) {
  if (!text.trim() || thinking.value) return
  discussion.value.push({ role: 'you', text })
  const reply = reactive<Msg>({ role: 'olwen', text: '' })
  discussion.value.push(reply)
  thinking.value = true
  scrollFeed()
  try {
    const res = await fetch(`${apiBase}/api/chat/stream`, {
      method: 'POST', headers: h(),
      body: JSON.stringify({ message: `${projectContext()}\n\nMoaz: ${text}` }),
    })
    if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`)
    const reader = res.body.getReader(); const dec = new TextDecoder(); let buf = ''
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buf += dec.decode(value, { stream: true })
      const parts = buf.split('\n\n'); buf = parts.pop() ?? ''
      for (const part of parts) {
        const line = part.trim()
        if (!line.startsWith('data:')) continue
        try {
          const ev = JSON.parse(line.slice(5).trim())
          if (ev.type === 'delta') { reply.text += ev.text; scrollFeed() }
          else if (ev.type === 'error') reply.text += `\n[error: ${ev.message}]`
        } catch { /* skip */ }
      }
    }
  } catch (e) {
    reply.text = reply.text || `Couldn't reach the backend (${(e as Error).message}).`
  } finally { thinking.value = false; scrollFeed() }
}
function whereDidWeStop() {
  askOlwen('Read the git state and the plan above. Tell me concretely: where did Claude Code stop, and exactly what should we start next? Name the files or the phase, and give me the first command or step.')
}
function send() {
  const t = input.value.trim(); if (!t || conducting.value) return; input.value = ''
  if (target.value === 'auto') runWithOlwen(t)
  else if (target.value === 'claude') sendToClaude(t)
  else askOlwen(t)
}
function scrollFeed() { requestAnimationFrame(() => feed.value?.scrollTo({ top: feed.value.scrollHeight, behavior: 'smooth' })) }

// ── chrome ───────────────────────────────────────────────────────────
const clock = ref('')
function tick() { clock.value = new Date().toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' }) }
function close() { entered.value = false; setTimeout(() => emit('close'), 340) }
function onKey(e: KeyboardEvent) {
  const inField = (document.activeElement as HTMLElement)?.closest?.('.ds-term, .ds-input')
  if (e.key === 'Escape' && !inField) close()
}

let timers: ReturnType<typeof setInterval>[] = []
onMounted(() => {
  ensureWins()
  requestAnimationFrame(() => { entered.value = true })
  document.addEventListener('keydown', onKey)
  tick(); loadIntel(); loadJobs()
  timers.push(setInterval(tick, 1000))
  timers.push(setInterval(loadJobs, 5000))
  timers.push(setInterval(loadIntel, 30_000))
  // Parse each terminal into a friendly activity timeline, live.
  timers.push(setInterval(() => {
    for (const p of projects.value) {
      const tr = termRefs[p.path]
      if (!tr) continue
      const out = tr.getOutput()
      activity[p.path] = parseActivity(out)
      const url = detectPreviewUrl(out)
      if (url) previewUrl[p.path] = url
    }
  }, 1500))
  timers.push(setInterval(autoFollow, 1500))   // ghost cursor wander + jump between windows
})
watch(activeIdx, () => { loadIntel(); if (live.value) { const p = active.value; if (p) focusWin(p.path) } })
watch(projects, ensureWins, { deep: true })
watch(conducting, (c) => { if (c && projects.value.length) { live.value = true; tileWindows() } })
onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKey)
  timers.forEach(clearInterval); endDrag()
})
</script>

<template>
  <div class="ds" :class="{ entered }">
    <div class="ds-fx" aria-hidden="true"><div class="ds-grid" /></div>

    <!-- live session indicator — reflects REAL state only (no fake cursor) -->
    <div v-if="live" class="ds-controlframe" aria-hidden="true" />
    <div v-if="live" class="ds-controlbadge"><span class="ds-cb-dot" /> Live · Olwen is running Claude Code</div>

    <header class="ds-bar">
      <div class="ds-brand"><span class="ds-dot" />OLWEN <span class="ds-sep">/</span> <span class="ds-mode">DEV STUDIO</span></div>
      <div class="ds-chips">
        <button v-for="(p, i) in projects" :key="p.path" class="ds-chip" :class="{ on: i === activeIdx }" @click="activeIdx = i">{{ p.name }}</button>
      </div>
      <button class="ds-livebtn" :class="{ on: live }" @click="toggleLive" title="Cinematic mode — watch Olwen work across the screen">🎬 Live</button>
      <button class="ds-exit" @click="close">exit <span class="ds-exit-k">esc</span></button>
    </header>

    <div class="ds-body">
      <!-- canvas with movable terminal windows -->
      <section class="ds-canvas">
        <div v-for="p in projects" :key="p.path" class="ds-win" :class="{ anim: animating }"
             :style="{ left: wins[p.path]?.x + 'px', top: wins[p.path]?.y + 'px', width: wins[p.path]?.w + 'px', height: wins[p.path]?.h + 'px', zIndex: wins[p.path]?.z }"
             @pointerdown="focusWin(p.path)">
          <div class="ds-win-head" @pointerdown="startDrag($event, p.path, 'move')">
            <span class="ds-win-glyph">▌</span><span class="ds-win-name">{{ p.name }}</span>
            <span class="ds-win-path">{{ p.path }}</span>
            <div class="ds-view" @pointerdown.stop>
              <button :class="{ on: viewOf(p.path) === 'activity' }" @click="setView(p.path, 'activity')">◉ Activity</button>
              <button :class="{ on: viewOf(p.path) === 'terminal' }" @click="setView(p.path, 'terminal')">›_ Terminal</button>
            </div>
            <button class="ds-win-x" title="Close" @pointerdown.stop @click="closeProject(p.path)">✕</button>
          </div>
          <div class="ds-term">
            <!-- terminal stays mounted (capturing) even in Activity view -->
            <div v-show="viewOf(p.path) === 'terminal'" class="ds-term-host">
              <TerminalApp embedded :ref="el => setTermRef(p.path, el)" :cwd="p.path" :title="p.name"
                           :auto-start="p.autoStart === undefined ? 'claude --dangerously-skip-permissions' : p.autoStart" />
            </div>
            <div v-if="viewOf(p.path) === 'activity'" class="ds-activity">
              <div class="ds-act-head">
                <span class="ds-act-dot" :class="{ live: conducting }" />
                {{ conducting ? (conductStatus || 'Olwen and Claude Code are building this for you…') : 'What Olwen is building' }}
              </div>

              <!-- live preview (a free, live "screenshot" — no AI, no tokens) -->
              <div v-if="previewUrl[p.path]" class="ds-preview">
                <div class="ds-preview-bar">
                  <span class="ds-preview-live">● live preview</span>
                  <span class="ds-preview-url">{{ previewUrl[p.path] }}</span>
                  <a class="ds-preview-open" :href="previewUrl[p.path]" target="_blank" rel="noopener">open ↗</a>
                </div>
                <iframe class="ds-preview-frame" :src="previewUrl[p.path]" />
              </div>

              <ul class="ds-acts">
                <li v-for="(s, i) in (activity[p.path] || [])" :key="i" class="ds-act"
                    :class="{ cur: conducting && i === (activity[p.path] || []).length - 1 }">
                  <span class="ds-act-ic">{{ s.icon }}</span>
                  <span class="ds-act-text">{{ s.text }}</span>
                </li>
                <li v-if="!(activity[p.path] || []).length" class="ds-act-empty">
                  Give Olwen a goal below — you'll watch the work appear here in plain language, step by step.
                </li>
              </ul>
            </div>
          </div>
          <div class="ds-win-resize" @pointerdown="startDrag($event, p.path, 'resize')" />
        </div>
        <div class="ds-hint">drag the title bar to move · drag the corner to resize</div>
      </section>

      <!-- cockpit rail -->
      <aside class="ds-rail">
        <div class="ds-creature"><OlwenEntity :state="thinking ? 'thinking' : 'working'" /></div>
        <div class="ds-clock">{{ clock }}</div>

        <!-- project intel -->
        <div class="ds-card">
          <h3 class="ds-h">Project <span class="ds-branch" v-if="intel?.ok">⎇ {{ intel.branch }}</span></h3>
          <div class="ds-proj-name">{{ active?.name }}</div>
          <div class="ds-gitline" v-if="intel?.ok">
            <span class="ds-pill" v-if="intel.ahead">↑ {{ intel.ahead }} unpushed</span>
            <span class="ds-pill" v-if="intel.behind">↓ {{ intel.behind }} behind</span>
            <span class="ds-pill ds-pill--dirty" v-if="intel.dirty?.length">● {{ intel.dirty.length }} changed</span>
            <span class="ds-pill ds-pill--clean" v-else>✓ clean</span>
          </div>
          <div class="ds-stopped" v-if="intel?.ok">
            <span class="ds-stopped-h">Where you stopped</span>
            {{ intel.stopped }}
          </div>
        </div>

        <!-- recent commits -->
        <div class="ds-card" v-if="intel?.commits?.length">
          <h3 class="ds-h">Recent</h3>
          <ul class="ds-commits">
            <li v-for="c in intel.commits.slice(0, 4)" :key="c.hash">
              <span class="ds-hash">{{ c.hash }}</span>
              <span class="ds-subj">{{ c.subject }}</span>
              <span class="ds-when">{{ c.when }}</span>
            </li>
          </ul>
        </div>

        <!-- phases from PRD -->
        <div class="ds-card" v-if="intel?.phases?.length">
          <h3 class="ds-h">Phases <span class="ds-prd" v-if="intel.prd_name">{{ intel.prd_name }}</span></h3>
          <div v-for="ph in intel.phases" :key="ph.title" class="ds-phase">
            <div class="ds-phase-top"><span>{{ ph.title }}</span><span class="ds-phase-n">{{ ph.done }}/{{ ph.total }}</span></div>
            <div class="ds-bar2"><div class="ds-bar2-fill" :style="{ width: (ph.total ? Math.round(ph.done / ph.total * 100) : 0) + '%' }" /></div>
          </div>
        </div>
        <div class="ds-card ds-muted-card" v-else-if="intel && intel.ok">
          <h3 class="ds-h">Phases</h3>
          <p class="ds-muted">No PRD/roadmap found. Add a <code>PRD.md</code> with <code>## Phase 1</code> + checkboxes and Olwen will track progress here.</p>
        </div>

        <!-- unattended jobs: run while away -->
        <div class="ds-card">
          <h3 class="ds-h">Run while away</h3>
          <div class="ds-composer">
            <input v-model="jobGoal" class="ds-input" placeholder="a goal Olwen runs unattended…" @keyup.enter="queueJob">
            <button class="ds-send" title="Run unattended — commits to a branch + opens a PR + pings you" @click="queueJob">▶</button>
          </div>
          <ul class="ds-jobs">
            <li v-for="j in jobs" :key="j.id" class="ds-job" :class="j.status">
              <span class="ds-job-dot" />
              <div class="ds-job-body">
                <div class="ds-job-goal">{{ j.goal }}</div>
                <div class="ds-job-meta">
                  <span class="ds-job-status">{{ j.status === 'needs_you' ? 'needs you' : j.status }}</span>
                  <a v-if="j.pr_url" :href="j.pr_url" target="_blank" rel="noopener" class="ds-job-pr">PR ↗</a>
                  <span v-else-if="j.note && j.status !== 'running' && j.status !== 'needs_you'" class="ds-job-note">{{ j.note }}</span>
                </div>
                <div v-if="j.status === 'needs_you'" class="ds-job-ask">
                  <p class="ds-job-q">{{ j.question || 'Olwen needs a decision.' }}</p>
                  <div class="ds-composer">
                    <input v-model="jobReply[j.id]" class="ds-input" placeholder="your answer — resumes the job…" @keyup.enter="replyJob(j.id)">
                    <button class="ds-send" @click="replyJob(j.id)">↵</button>
                  </div>
                </div>
              </div>
            </li>
          </ul>
          <p v-if="!jobs.length" class="ds-muted">Queue a goal — Olwen runs Claude Code, opens a PR, and WhatsApps you when it's done. Close the tab; it keeps running.</p>
        </div>

        <!-- discuss with olwen -->
        <div class="ds-card ds-discuss">
          <h3 class="ds-h">Discuss with Olwen</h3>
          <button class="ds-ask-btn" :disabled="thinking" @click="whereDidWeStop">✦ Where did we stop? What's next?</button>
          <div class="ds-feed" ref="feed">
            <div v-for="(m, i) in discussion" :key="i" class="ds-msg" :class="m.role">
              <span class="ds-msg-who">{{ m.role === 'you' ? 'you' : m.role === 'claude' ? '→ claude code' : 'olwen' }}</span>
              <p class="ds-msg-text">{{ m.text }}<span v-if="thinking && m.role === 'olwen' && i === discussion.length - 1" class="ds-cursor">▍</span></p>
            </div>
            <p v-if="!discussion.length" class="ds-muted">Give Olwen a goal — he'll drive Claude Code in the terminal (your subscription), reading its output and replying until it's done. Switch to relay-once or advice below.</p>
          </div>
          <div v-if="conducting" class="ds-conducting">
            <span class="ds-spin" /> {{ conductStatus || 'Olwen is running Claude Code…' }}
            <button class="ds-stop" @click="stopConduct">STOP</button>
          </div>
          <div class="ds-target">
            <button :class="{ on: target === 'auto' }" @click="target = 'auto'" title="Olwen drives Claude Code to completion">⚙ Auto</button>
            <button :class="{ on: target === 'claude' }" @click="target = 'claude'" title="Send one prompt into Claude Code">→ Relay</button>
            <button :class="{ on: target === 'olwen' }" @click="target = 'olwen'" title="Ask Olwen for advice">Olwen</button>
          </div>
          <div class="ds-composer">
            <input v-model="input" class="ds-input"
                   :placeholder="target === 'auto' ? 'give Olwen a goal — he runs Claude Code…' : target === 'claude' ? 'one prompt for Claude Code…' : 'ask Olwen about this project…'"
                   @keyup.enter="send" :disabled="thinking || conducting">
            <button class="ds-send" @click="send" :disabled="thinking || conducting">↵</button>
          </div>
        </div>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.ds { position: fixed; inset: 0; z-index: 60; background: var(--bg); color: var(--text);
  font-family: 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace;
  display: flex; flex-direction: column; opacity: 0; transition: opacity .34s ease; }
.ds.entered { opacity: 1; }
.ds-fx { position: absolute; inset: 0; pointer-events: none; }
.ds-grid { position: absolute; inset: 0;
  background-image: linear-gradient(rgba(94,234,212,.04) 1px, transparent 1px), linear-gradient(90deg, rgba(94,234,212,.04) 1px, transparent 1px);
  background-size: 46px 46px; mask-image: radial-gradient(ellipse 80% 60% at 60% 0%, #000 35%, transparent 85%); }

.ds-bar { display: flex; align-items: center; gap: 1rem; padding: .8rem 1.2rem; border-bottom: 1px solid var(--border-strong); position: relative; z-index: 5; }
.ds-brand { display: flex; align-items: center; gap: .5rem; letter-spacing: .3em; font-size: .78rem; color: var(--accent); }
.ds-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--accent); box-shadow: 0 0 12px #5EEAD4; animation: dsp 2.4s ease-in-out infinite; }
@keyframes dsp { 50% { opacity: .35; } }
.ds-sep { color: var(--border-strong); }
.ds-mode { color: var(--accent-2); }
.ds-chips { display: flex; gap: .4rem; margin-left: auto; }
.ds-chip { font: inherit; font-size: .72rem; color: var(--text-muted); border: 1px solid var(--border-strong); background: var(--surface-solid); border-radius: 999px; padding: .25rem .8rem; cursor: pointer; }
.ds-chip.on { color: var(--bg); background: var(--accent); border-color: var(--accent); }
.ds-exit { margin-left: .6rem; background: none; border: 1px solid var(--border-strong); border-radius: 8px; color: var(--text-muted); font: inherit; font-size: .72rem; letter-spacing: .12em; text-transform: uppercase; padding: .35rem .7rem; cursor: pointer; }
.ds-exit:hover { color: var(--accent); border-color: var(--accent); }
.ds-exit-k { color: var(--text-muted); }

.ds-body { flex: 1; display: flex; min-height: 0; position: relative; z-index: 1; }
.ds-canvas { flex: 1; position: relative; overflow: hidden; }
.ds-hint { position: absolute; bottom: .7rem; left: 50%; transform: translateX(-50%); font-size: .68rem; color: var(--text-muted); letter-spacing: .06em; }

.ds-win { position: absolute; display: flex; flex-direction: column; background: var(--surface-solid); border: 1px solid var(--border-strong); border-radius: 12px; overflow: hidden; box-shadow: 0 24px 60px rgba(0,0,0,.55); }
.ds-win.anim { transition: left .85s cubic-bezier(.22,1,.36,1), top .85s cubic-bezier(.22,1,.36,1), width .85s cubic-bezier(.22,1,.36,1), height .85s cubic-bezier(.22,1,.36,1); }
.ds-livebtn { background: none; border: 1px solid var(--border-strong); border-radius: 8px; color: var(--text-muted); font: inherit; font-size: .72rem; letter-spacing: .08em; padding: .35rem .7rem; cursor: pointer; }
.ds-livebtn.on { color: var(--bg); background: var(--accent); border-color: var(--accent); }

/* remote-control frame around the whole screen */
.ds-controlframe { position: fixed; inset: 0; z-index: 90; pointer-events: none; border: 2px solid rgba(94,234,212,.6); box-shadow: inset 0 0 0 1px rgba(94,234,212,.25), inset 0 0 60px rgba(94,234,212,.12); border-radius: 4px; animation: ds-frame 2.6s ease-in-out infinite; }
@keyframes ds-frame { 50% { border-color: rgba(94,234,212,.95); box-shadow: inset 0 0 0 1px rgba(94,234,212,.4), inset 0 0 80px rgba(94,234,212,.2); } }
.ds-controlbadge { position: fixed; top: 10px; left: 50%; transform: translateX(-50%); z-index: 95; pointer-events: none; display: flex; align-items: center; gap: .5rem; font-size: .68rem; letter-spacing: .12em; text-transform: uppercase; color: var(--accent); background: color-mix(in srgb, var(--bg) 85%, transparent); border: 1px solid var(--border-strong); border-radius: 999px; padding: .3rem .8rem; }
.ds-cb-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--accent); box-shadow: 0 0 10px #5EEAD4; animation: dsp 1.4s ease-in-out infinite; }
.ds-win-head { display: flex; align-items: center; gap: .5rem; padding: .5rem .8rem; background: var(--surface-solid); border-bottom: 1px solid var(--border-strong); cursor: grab; user-select: none; }
.ds-win-head:active { cursor: grabbing; }
.ds-win-glyph { color: var(--accent); }
.ds-win-name { color: var(--accent); font-size: .76rem; }
.ds-win-path { color: var(--text-muted); font-size: .64rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; }
.ds-win-grip { color: var(--text-muted); font-size: .64rem; letter-spacing: .1em; }
.ds-win-x { background: none; border: none; color: var(--text-muted); font: inherit; font-size: .8rem; cursor: pointer; padding: 0 .2rem; line-height: 1; }
.ds-win-x:hover { color: #FCA5A5; }
.ds-view { display: flex; gap: .2rem; margin-left: auto; margin-right: .5rem; }
.ds-view button { font: inherit; font-size: .6rem; letter-spacing: .04em; color: var(--text-muted); background: var(--surface-solid); border: 1px solid var(--border-strong); border-radius: 6px; padding: .18rem .45rem; cursor: pointer; }
.ds-view button.on { color: var(--bg); background: var(--accent); border-color: var(--accent); }
.ds-term-host { height: 100%; }

/* friendly activity timeline */
.ds-activity { height: 100%; overflow-y: auto; padding: .9rem 1rem; background: var(--surface-solid); }
.ds-act-head { display: flex; align-items: center; gap: .5rem; font-size: .78rem; color: var(--accent-2); letter-spacing: .04em; margin-bottom: .9rem; }
.ds-act-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--text-muted); }
.ds-act-dot.live { background: var(--accent); box-shadow: 0 0 10px #5EEAD4; animation: dsp 1.6s ease-in-out infinite; }
.ds-acts { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: .1rem; }
.ds-act { display: flex; align-items: center; gap: .6rem; padding: .42rem .5rem; border-radius: 8px; border-left: 2px solid transparent; }
.ds-act + .ds-act { position: relative; }
.ds-act-ic { width: 1.4rem; text-align: center; font-size: 1rem; }
.ds-act-text { color: var(--text); font-size: .9rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ds-act.cur { background: var(--surface-2); border-left-color: var(--accent); }
.ds-act.cur .ds-act-text { color: var(--text-strong); }
.ds-act-empty { color: var(--text-muted); font-size: .85rem; line-height: 1.7; padding: 1.5rem .5rem; }

/* live preview — a free, live picture of the actual result */
.ds-preview { border: 1px solid var(--border-strong); border-radius: 10px; overflow: hidden; margin-bottom: 1rem; background: #fff; }
.ds-preview-bar { display: flex; align-items: center; gap: .6rem; padding: .4rem .6rem; background: var(--surface-solid); border-bottom: 1px solid var(--border-strong); }
.ds-preview-live { font-size: .64rem; letter-spacing: .12em; text-transform: uppercase; color: var(--accent); }
.ds-preview-url { font-size: .68rem; color: var(--text-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; }
.ds-preview-open { font-size: .66rem; color: #67E8F9; }
.ds-preview-frame { width: 100%; height: 320px; border: 0; background: #fff; display: block; }
.ds-term { flex: 1; min-height: 0; overflow: hidden; }
.ds-win-resize { position: absolute; right: 0; bottom: 0; width: 18px; height: 18px; cursor: nwse-resize; background: linear-gradient(135deg, transparent 50%, var(--border-strong) 50%, var(--border-strong) 60%, transparent 60%, transparent 72%, var(--border-strong) 72%, var(--border-strong) 82%, transparent 82%); }

.ds-rail { width: 360px; flex-shrink: 0; border-left: 1px solid var(--border-strong); background: var(--surface-solid); display: flex; flex-direction: column; padding: 1rem; gap: .8rem; overflow-y: auto; }
.ds-creature { height: 116px; position: relative; }
.ds-clock { text-align: center; font-size: .74rem; letter-spacing: .2em; color: var(--accent); margin-top: -.4rem; }
.ds-card { border: 1px solid var(--border-strong); border-radius: 12px; background: var(--surface-solid); padding: .8rem .9rem; }
.ds-h { margin: 0 0 .6rem; font-size: .66rem; letter-spacing: .22em; text-transform: uppercase; color: var(--accent); display: flex; align-items: center; gap: .5rem; }
.ds-branch { margin-left: auto; color: var(--accent-2); font-size: .68rem; letter-spacing: .04em; text-transform: none; }
.ds-prd { margin-left: auto; color: var(--text-muted); font-size: .64rem; text-transform: none; letter-spacing: 0; }
.ds-proj-name { font-size: 1rem; color: var(--text-strong); margin-bottom: .5rem; }
.ds-gitline { display: flex; flex-wrap: wrap; gap: .35rem; margin-bottom: .6rem; }
.ds-pill { font-size: .66rem; color: var(--text); border: 1px solid var(--border-strong); border-radius: 6px; padding: .12rem .45rem; }
.ds-pill--dirty { color: #FCD34D; border-color: #78350F; }
.ds-pill--clean { color: var(--accent); border-color: var(--border-strong); }
.ds-stopped { font-size: .8rem; color: var(--text); line-height: 1.5; background: var(--surface-solid); border-left: 2px solid var(--accent); padding: .5rem .7rem; border-radius: 0 8px 8px 0; }
.ds-stopped-h { display: block; font-size: .6rem; letter-spacing: .2em; text-transform: uppercase; color: var(--accent); margin-bottom: .25rem; }
.ds-commits { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: .4rem; }
.ds-commits li { display: flex; align-items: baseline; gap: .5rem; font-size: .76rem; }
.ds-hash { color: var(--accent); flex-shrink: 0; }
.ds-subj { color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; }
.ds-when { color: var(--text-muted); font-size: .64rem; flex-shrink: 0; }
.ds-phase { margin-bottom: .55rem; }
.ds-phase-top { display: flex; justify-content: space-between; font-size: .76rem; color: var(--text); margin-bottom: .25rem; }
.ds-phase-n { color: var(--accent); }
.ds-bar2 { height: 5px; border-radius: 3px; background: var(--border-strong); overflow: hidden; }
.ds-bar2-fill { height: 100%; background: linear-gradient(90deg, #5EEAD4, #67E8F9); border-radius: 3px; transition: width .4s ease; }
.ds-muted { color: var(--text-muted); font-size: .76rem; line-height: 1.5; }
.ds-muted code { color: var(--text-muted); }
.ds-jobs { list-style: none; margin: .6rem 0 0; padding: 0; display: flex; flex-direction: column; gap: .5rem; }
.ds-job { display: flex; gap: .55rem; align-items: flex-start; }
.ds-job-dot { width: 8px; height: 8px; border-radius: 50%; margin-top: .35rem; flex-shrink: 0; background: var(--text-muted); }
.ds-job.queued .ds-job-dot { background: #94A3B8; }
.ds-job.running .ds-job-dot { background: #5EEAD4; box-shadow: 0 0 8px #5EEAD4; animation: dsp 1.4s ease-in-out infinite; }
.ds-job.done .ds-job-dot { background: #34D399; }
.ds-job.needs_you .ds-job-dot { background: #FBBF24; }
.ds-job.failed .ds-job-dot { background: #FCA5A5; }
.ds-job-body { flex: 1; min-width: 0; }
.ds-job-goal { font-size: .82rem; color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ds-job-meta { display: flex; gap: .5rem; align-items: baseline; font-size: .68rem; margin-top: .1rem; }
.ds-job-status { color: var(--text-muted); text-transform: uppercase; letter-spacing: .08em; }
.ds-job.done .ds-job-status { color: #34D399; }
.ds-job.needs_you .ds-job-status { color: #FBBF24; }
.ds-job.running .ds-job-status { color: var(--accent); }
.ds-job-pr { color: #67E8F9; }
.ds-job-note { color: var(--text-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ds-job-ask { margin-top: .4rem; border-left: 2px solid #FBBF24; padding-left: .55rem; }
.ds-job-q { margin: 0 0 .4rem; font-size: .78rem; color: #FDE68A; line-height: 1.4; }
.ds-job-ask .ds-composer { margin-top: 0; }

.ds-discuss { flex: 1; min-height: 200px; display: flex; flex-direction: column; }
.ds-ask-btn { font: inherit; font-size: .74rem; color: var(--bg); background: linear-gradient(135deg, var(--accent-2), var(--accent)); border: none; border-radius: 8px; padding: .5rem .7rem; cursor: pointer; margin-bottom: .6rem; font-weight: 500; }
.ds-ask-btn:disabled { opacity: .5; cursor: default; }
.ds-feed { flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: .7rem; min-height: 80px; }
.ds-msg { display: flex; flex-direction: column; gap: .15rem; }
.ds-msg-who { font-size: .58rem; letter-spacing: .18em; text-transform: uppercase; color: var(--text-muted); }
.ds-msg.you .ds-msg-who { color: #67E8F9; }
.ds-msg.olwen .ds-msg-who { color: var(--accent); }
.ds-msg.claude .ds-msg-who { color: #FB923C; }
.ds-msg.claude .ds-msg-text { color: #FDBA74; border-left: 2px solid #7C2D12; padding-left: .6rem; }
.ds-target { display: flex; gap: .3rem; margin-top: .6rem; }
.ds-target button { flex: 1; font: inherit; font-size: .68rem; letter-spacing: .04em; color: var(--text-muted); background: var(--surface-solid); border: 1px solid var(--border-strong); border-radius: 7px; padding: .35rem; cursor: pointer; }
.ds-target button.on { color: var(--bg); background: var(--accent); border-color: var(--accent); font-weight: 500; }
.ds-target button:nth-child(2).on { background: #FB923C; border-color: #FB923C; }
.ds-conducting { display: flex; align-items: center; gap: .5rem; margin-top: .6rem; font-size: .74rem; color: var(--accent-2); background: var(--surface-solid); border: 1px solid var(--border-strong); border-radius: 8px; padding: .45rem .6rem; }
.ds-spin { width: 9px; height: 9px; border-radius: 50%; border: 1.5px solid var(--accent); border-top-color: transparent; animation: ds-spin 0.8s linear infinite; }
@keyframes ds-spin { to { transform: rotate(360deg); } }
.ds-stop { margin-left: auto; font: inherit; font-size: .66rem; letter-spacing: .12em; color: #FCA5A5; background: none; border: 1px solid #7F1D1D; border-radius: 6px; padding: .2rem .5rem; cursor: pointer; }
.ds-stop:hover { background: #7F1D1D; color: #FECACA; }
.ds-msg-text { margin: 0; font-size: .82rem; line-height: 1.55; color: var(--text); white-space: pre-wrap; }
.ds-cursor { color: var(--accent); }
.ds-composer { display: flex; gap: .4rem; margin-top: .6rem; }
.ds-input { flex: 1; background: var(--surface-solid); border: 1px solid var(--border-strong); border-radius: 8px; color: var(--text); font: inherit; font-size: .78rem; padding: .45rem .6rem; outline: none; }
.ds-input:focus { border-color: var(--accent); }
.ds-send { background: var(--surface-solid); border: 1px solid var(--border-strong); border-radius: 8px; color: var(--accent); font: inherit; padding: 0 .7rem; cursor: pointer; }
.ds-send:disabled { opacity: .4; }

@media (max-width: 1040px) { .ds-rail { width: 320px; } }
</style>
