<script setup lang="ts">
/**
 * Computer-Use surface — Olwen drives the user's mouse + keyboard via the
 * olwen-bridge daemon (127.0.0.1:8765). Streams Claude's thoughts + the
 * action it took + a fresh screenshot after each step. Always-visible STOP.
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

type Status =
  | { ok: true; bridge: { ok: boolean; version: string }; screen: { width: number; height: number; scale: number } }
  | { ok: false; reason: string }

type Event =
  | { kind: 'thought'; text: string; ts: number }
  | { kind: 'action'; action: { action: string; coordinate?: [number, number]; text?: string }; ts: number }
  | { kind: 'screenshot'; image_b64: string; ts: number }
  | { kind: 'done'; text?: string; ts: number }
  | { kind: 'error'; text: string; ts: number }

const emit = defineEmits<{
  (e: 'close'): void
  // Fired when the run ends — hands a plain-language summary back to Olwen so
  // the chat reports what happened instead of leaving the user in this overlay.
  (e: 'finished', payload: { ok: boolean; text: string }): void
}>()

const apiBase = useRuntimeConfig().public.apiBase as string
function h() {
  const t = import.meta.client ? localStorage.getItem('olwen_access') : null
  return t ? { Authorization: `Bearer ${t}` } : {}
}

const status = ref<Status | null>(null)
const checking = ref(true)
const instruction = ref('')
const running = ref(false)
const screenshot = ref<string | null>(null)   // data URL
const events = ref<Event[]>([])
const scroller = ref<HTMLElement | null>(null)

let controller: AbortController | null = null

const summary = computed(() => {
  const a = events.value.filter(e => e.kind === 'action').length
  const t = events.value.filter(e => e.kind === 'thought').length
  return { actions: a, thoughts: t }
})

async function check() {
  checking.value = true
  try {
    status.value = await $fetch<Status>(`${apiBase}/api/computer/status`, { headers: h() })
  } catch (e) {
    status.value = { ok: false, reason: (e as Error).message }
  } finally {
    checking.value = false
  }
}

async function refreshShot() {
  try {
    const blob = await $fetch<Blob>(`${apiBase}/api/computer/screenshot`, { headers: h(), responseType: 'blob' })
    screenshot.value = URL.createObjectURL(blob)
  } catch {
    // bridge offline — leave as-is
  }
}

async function start() {
  if (!instruction.value.trim() || running.value) return
  events.value = []
  running.value = true
  controller = new AbortController()

  try {
    const res = await fetch(`${apiBase}/api/computer/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...h() },
      body: JSON.stringify({ instruction: instruction.value.trim() }),
      signal: controller.signal,
    })
    if (!res.ok || !res.body) {
      events.value.push({ kind: 'error', text: `HTTP ${res.status}`, ts: Date.now() / 1000 })
      running.value = false
      emit('finished', { ok: false, text: `I couldn't start that on screen (HTTP ${res.status}).` })
      emit('close')
      return
    }
    const reader = res.body.getReader()
    const dec = new TextDecoder()
    let buf = ''
    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      buf += dec.decode(value, { stream: true })
      let idx: number
      while ((idx = buf.indexOf('\n\n')) >= 0) {
        const chunk = buf.slice(0, idx)
        buf = buf.slice(idx + 2)
        const line = chunk.split('\n').find(l => l.startsWith('data: '))
        if (!line) continue
        try {
          const ev: Event = JSON.parse(line.slice(6))
          if (ev.kind === 'screenshot') {
            screenshot.value = `data:image/png;base64,${ev.image_b64}`
          } else {
            events.value.push(ev)
            queueMicrotask(() => scroller.value?.scrollTo({ top: scroller.value!.scrollHeight, behavior: 'smooth' }))
          }
          if (ev.kind === 'done' || ev.kind === 'error') {
            running.value = false
            // Return control to Olwen and let the chat narrate the outcome.
            emit('finished', {
              ok: ev.kind === 'done',
              text: ev.kind === 'done'
                ? (ev.text || 'Done.')
                : `I couldn't finish that on screen: ${ev.text}`,
            })
            emit('close')
          }
        } catch { /* malformed chunk — skip */ }
      }
    }
  } catch (e) {
    if ((e as Error).name !== 'AbortError') {
      events.value.push({ kind: 'error', text: (e as Error).message, ts: Date.now() / 1000 })
    }
  } finally {
    running.value = false
    controller = null
  }
}

async function stop() {
  try { await $fetch(`${apiBase}/api/computer/stop`, { method: 'POST', headers: h() }) } catch {}
  controller?.abort()
  running.value = false
}

function fmtAction(a: { action: string; coordinate?: [number, number]; text?: string }) {
  switch (a.action) {
    case 'left_click':       return `click at (${a.coordinate?.[0]}, ${a.coordinate?.[1]})`
    case 'right_click':      return `right-click at (${a.coordinate?.[0]}, ${a.coordinate?.[1]})`
    case 'double_click':     return `double-click at (${a.coordinate?.[0]}, ${a.coordinate?.[1]})`
    case 'mouse_move':       return `move to (${a.coordinate?.[0]}, ${a.coordinate?.[1]})`
    case 'left_click_drag':  return `drag to (${a.coordinate?.[0]}, ${a.coordinate?.[1]})`
    case 'type':             return `type "${a.text}"`
    case 'key':              return `press ${a.text}`
    case 'screenshot':       return 'look at screen'
    case 'scroll':           return 'scroll'
    default:                 return a.action
  }
}

onMounted(async () => {
  await check()
  await refreshShot()
  // If the chat agent pre-filled a goal via give_olwen_the_wheel, auto-run it
  const incoming = useState<{ goal: string; auto: boolean } | null>('cu:incoming', () => null)
  if (incoming.value?.goal) {
    instruction.value = incoming.value.goal
    const shouldStart = incoming.value.auto && status.value?.ok
    incoming.value = null
    if (shouldStart) start()
  }
})
onBeforeUnmount(() => {
  controller?.abort()
  if (screenshot.value?.startsWith('blob:')) URL.revokeObjectURL(screenshot.value)
})
</script>

<template>
  <div class="cu">
    <!-- always-visible STOP rail -->
    <transition name="stop">
      <button v-if="running" class="cu__stop" @click="stop">
        <span class="cu__stop-pulse" />
        <span class="cu__stop-label">⏹ STOP — Olwen has the wheel</span>
      </button>
    </transition>

    <header class="cu__head">
      <div class="cu__title">
        <span class="cu__dot" />
        <h2>Computer use</h2>
        <span class="cu__beta">beta</span>
      </div>
      <button class="cu__close" @click="emit('close')" aria-label="Close">×</button>
    </header>

    <!-- bridge status banner -->
    <div v-if="checking" class="cu__banner cu__banner--mute">
      Checking the bridge…
    </div>
    <div v-else-if="!status?.ok" class="cu__banner cu__banner--warn">
      <strong>Bridge offline.</strong>
      <span>{{ (status as { reason: string }).reason }}</span>
      <code>cd bridge && ./install_bridge.sh</code>
    </div>
    <div v-else class="cu__banner cu__banner--ok">
      <strong>Bridge live</strong>
      <span>v{{ (status as { bridge: { version: string } }).bridge.version }}</span>
      <span>·</span>
      <span>{{ (status as { screen: { width: number; height: number } }).screen.width }} × {{ (status as { screen: { width: number; height: number } }).screen.height }} px</span>
    </div>

    <!-- live screen preview -->
    <div class="cu__stage">
      <div class="cu__shot" :class="{ 'cu__shot--live': running }">
        <img v-if="screenshot" :src="screenshot" alt="Live preview of your screen" />
        <div v-else class="cu__shot-empty">No screen yet — install the bridge above</div>
      </div>
      <div class="cu__legend">
        <span>{{ summary.thoughts }} thoughts</span>
        <span>·</span>
        <span>{{ summary.actions }} actions</span>
      </div>
    </div>

    <!-- prompt -->
    <form class="cu__form" @submit.prevent="start">
      <textarea
        v-model="instruction"
        :disabled="running || !status?.ok"
        rows="2"
        class="cu__input"
        placeholder='Tell Olwen what to do — e.g., "Open Safari and search for the Olwen GitHub repo"'
      />
      <button
        class="cu__go"
        type="submit"
        :disabled="!instruction.trim() || running || !status?.ok"
      >
        {{ running ? 'Running…' : 'Give Olwen the wheel' }}
      </button>
    </form>

    <!-- action log -->
    <div class="cu__log" ref="scroller">
      <div v-if="!events.length" class="cu__log-empty">
        <p>Every step shows up here in real time — Olwen's thought, the action it took, then the new screen.</p>
        <p class="cu__log-empty-hint">You can hit STOP at any moment.</p>
      </div>
      <div v-for="(ev, i) in events" :key="i" class="cu__log-row" :class="`cu__log-row--${ev.kind}`">
        <span class="cu__log-tag">{{ ev.kind }}</span>
        <span v-if="ev.kind === 'thought'" class="cu__log-text">{{ ev.text }}</span>
        <span v-else-if="ev.kind === 'action'" class="cu__log-action">{{ fmtAction(ev.action) }}</span>
        <span v-else-if="ev.kind === 'done'" class="cu__log-done">✓ {{ ev.text || 'done' }}</span>
        <span v-else-if="ev.kind === 'error'" class="cu__log-error">{{ ev.text }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.cu {
  position: relative;
  display: flex; flex-direction: column;
  height: 100%; min-height: 0;
  color: #F8FAFC;
  background:
    radial-gradient(ellipse 800px 500px at 80% -10%, rgba(94,234,212,0.06), transparent 60%),
    #02060A;
  font-family: system-ui, -apple-system, 'Segoe UI', sans-serif;
}

/* ── STOP rail ─────────────────────────────────────────────── */
.cu__stop {
  position: absolute; top: 16px; left: 50%; transform: translateX(-50%);
  z-index: 20;
  display: inline-flex; align-items: center; gap: 12px;
  padding: 12px 22px;
  background: linear-gradient(180deg, #DC2626, #B91C1C);
  border: 1px solid rgba(254,202,202,0.5);
  border-radius: 999px;
  color: #FFF1F2;
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 12px; letter-spacing: 2.5px; text-transform: uppercase; font-weight: 500;
  box-shadow: 0 8px 24px -8px rgba(220,38,38,0.6), 0 0 0 4px rgba(220,38,38,0.15);
  cursor: pointer;
  transition: transform .12s ease, filter .12s ease;
}
.cu__stop:hover { transform: translateX(-50%) translateY(-1px); filter: brightness(1.08); }
.cu__stop-pulse {
  width: 8px; height: 8px; border-radius: 50%;
  background: #FCA5A5;
  box-shadow: 0 0 12px #FCA5A5, 0 0 24px rgba(252,165,165,0.5);
  animation: cuPulse 1s ease-in-out infinite;
}
@keyframes cuPulse { 0%,100% { opacity: 0.4; } 50% { opacity: 1; } }
.stop-enter-from, .stop-leave-to { opacity: 0; transform: translateX(-50%) translateY(-12px); }
.stop-enter-active, .stop-leave-active { transition: opacity .2s ease, transform .2s ease; }

/* ── header ────────────────────────────────────────────────── */
.cu__head {
  display: flex; justify-content: space-between; align-items: center;
  padding: 22px 26px 14px;
}
.cu__title { display: flex; align-items: center; gap: 12px; }
.cu__title h2 {
  margin: 0; font-family: 'Instrument Serif', Georgia, serif;
  font-weight: 400; font-size: 1.6rem;
}
.cu__dot {
  width: 8px; height: 8px; border-radius: 50%;
  background: #5EEAD4;
  box-shadow: 0 0 12px #5EEAD4;
  animation: cuPulse 2.5s ease-in-out infinite;
}
.cu__beta {
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 9.5px; letter-spacing: 2px; text-transform: uppercase;
  padding: 3px 8px; border-radius: 4px;
  color: #A7F3D0;
  background: rgba(167,243,208,0.08);
  border: 0.5px solid rgba(167,243,208,0.3);
}
.cu__close {
  background: transparent; border: none;
  color: #94A3B8; font-size: 28px; line-height: 1;
  cursor: pointer; padding: 0 4px;
  transition: color .15s ease;
}
.cu__close:hover { color: #F8FAFC; }

/* ── status banner ────────────────────────────────────────── */
.cu__banner {
  display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
  margin: 0 26px 14px;
  padding: 12px 16px;
  border-radius: 10px;
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 11.5px; letter-spacing: 0.5px;
}
.cu__banner--mute { color: #94A3B8; background: rgba(148,163,184,0.06); }
.cu__banner--warn {
  color: #FBBF24;
  background: rgba(251,191,36,0.08);
  border: 0.5px solid rgba(251,191,36,0.3);
}
.cu__banner--warn code {
  background: rgba(0,0,0,0.35); padding: 3px 8px; border-radius: 4px;
  color: #A7F3D0;
}
.cu__banner--ok {
  color: #A7F3D0;
  background: rgba(94,234,212,0.06);
  border: 0.5px solid rgba(94,234,212,0.18);
}

/* ── live screen preview ──────────────────────────────────── */
.cu__stage {
  position: relative;
  margin: 0 26px 16px;
}
.cu__shot {
  position: relative;
  border-radius: 14px; overflow: hidden;
  border: 0.5px solid rgba(94,234,212,0.18);
  background: #04101A;
  aspect-ratio: 16/10;
  display: flex; align-items: center; justify-content: center;
  transition: border-color .25s ease, box-shadow .25s ease;
}
.cu__shot--live {
  border-color: rgba(94,234,212,0.55);
  box-shadow: 0 0 0 1px rgba(94,234,212,0.2), 0 20px 60px -30px rgba(94,234,212,0.4);
}
.cu__shot img { width: 100%; height: 100%; object-fit: contain; display: block; }
.cu__shot-empty {
  color: #64748B;
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 11px; letter-spacing: 1.5px;
}
.cu__legend {
  display: flex; gap: 8px; justify-content: flex-end;
  margin-top: 8px;
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 10.5px; color: #64748B; letter-spacing: 1.5px;
}

/* ── prompt form ──────────────────────────────────────────── */
.cu__form {
  display: flex; gap: 10px; align-items: flex-end;
  padding: 0 26px 16px;
}
.cu__input {
  flex: 1; resize: none;
  padding: 12px 14px;
  background: rgba(2,6,10,0.6);
  border: 0.5px solid rgba(94,234,212,0.2);
  border-radius: 10px;
  color: #F8FAFC;
  font-family: 'Instrument Serif', Georgia, serif;
  font-size: 15px; line-height: 1.5;
  outline: none;
  transition: border-color .15s ease;
}
.cu__input:focus { border-color: rgba(94,234,212,0.55); }
.cu__input::placeholder { color: rgba(148,163,184,0.55); font-style: italic; }
.cu__input:disabled { opacity: 0.5; }

.cu__go {
  white-space: nowrap;
  padding: 12px 18px;
  background: linear-gradient(135deg, #A7F3D0, #5EEAD4);
  border: none;
  border-radius: 10px;
  color: #02060A;
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 11px; letter-spacing: 1.5px; text-transform: uppercase; font-weight: 600;
  cursor: pointer;
  transition: filter .15s ease, transform .12s ease;
}
.cu__go:hover:not(:disabled) { filter: brightness(1.08); transform: translateY(-1px); }
.cu__go:disabled { opacity: 0.35; cursor: not-allowed; }

/* ── action log ───────────────────────────────────────────── */
.cu__log {
  flex: 1; min-height: 0; overflow-y: auto;
  padding: 4px 26px 26px;
  display: flex; flex-direction: column; gap: 8px;
}
.cu__log-empty {
  color: #64748B;
  font-family: 'Instrument Serif', Georgia, serif;
  font-style: italic;
  font-size: 14px; line-height: 1.55;
  padding: 28px 0;
}
.cu__log-empty-hint {
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 10.5px; letter-spacing: 1.5px;
  color: #5EEAD4; opacity: 0.6;
  margin-top: 8px; font-style: normal;
}
.cu__log-row {
  display: flex; gap: 10px; align-items: baseline;
  padding: 6px 10px;
  border-radius: 6px;
  font-size: 13px; line-height: 1.5;
  animation: cuRowIn .25s ease;
}
@keyframes cuRowIn { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: none; } }
.cu__log-tag {
  flex-shrink: 0;
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 9.5px; letter-spacing: 1.8px; text-transform: uppercase;
  padding: 2px 7px; border-radius: 3px;
  color: #64748B;
  background: rgba(148,163,184,0.08);
}
.cu__log-row--thought    .cu__log-tag { color: #A7F3D0; background: rgba(167,243,208,0.08); }
.cu__log-row--action     .cu__log-tag { color: #67E8F9; background: rgba(103,232,249,0.1); }
.cu__log-row--done       .cu__log-tag { color: #5EEAD4; background: rgba(94,234,212,0.12); }
.cu__log-row--error      .cu__log-tag { color: #FCA5A5; background: rgba(252,165,165,0.1); }

.cu__log-text   { color: #CBD5E1; font-family: 'Instrument Serif', Georgia, serif; font-style: italic; }
.cu__log-action { color: #F8FAFC; font-family: 'JetBrains Mono', ui-monospace, monospace; font-size: 12px; }
.cu__log-done   { color: #A7F3D0; font-weight: 500; }
.cu__log-error  { color: #FCA5A5; }
</style>
