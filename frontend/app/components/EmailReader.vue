<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import OlwenEntity from './OlwenEntity.vue'
import OlwenDismissFX from './OlwenDismissFX.vue'
import type { EmailAction, EmailMessage, FullEmail, TriagedEmail } from '../composables/useEmail'

const props = defineProps<{ initial: EmailMessage | TriagedEmail }>()
const emit = defineEmits<{ close: []; markedRead: [string] }>()

const { message, summarize, markRead, reply: sendReply, draftReply } = useEmail()
const { fetchSettings } = useSettings()
const { lists: taskLists, add: addTaskFn, load: loadTasks } = useTasks()
const autoMarkRead = useState<boolean>('email:autoMarkRead', () => false)
const voice = useVoice()
const voiceOn = useState<boolean>('voice:on', () => true)
const voiceLang = useState<string>('voice:lang', () => 'en-US')

const entered = ref(false)
const loading = ref(true)
const summarizing = ref(false)
const error = ref('')
const full = ref<FullEmail | null>(null)
const summary = ref('')
const actions = ref<EmailAction[]>([])
const actionedKeys = ref<Set<string>>(new Set())          // labels already handled
const markReadStatus = ref<'idle' | 'done' | 'failed'>('idle')

// Reply composer state
const replyOpen = ref(false)
const replyBody = ref('')
const replyDrafting = ref(false)
const replySending = ref(false)
const replySent = ref(false)
const replyError = ref('')

async function openReply(prefill = '') {
  replyOpen.value = true
  replySent.value = false
  replyError.value = ''
  if (prefill) replyBody.value = prefill
  // Auto-draft if there's nothing in the box
  if (!replyBody.value.trim()) await draftWithOlwen()
}
async function draftWithOlwen() {
  replyDrafting.value = true; replyError.value = ''
  try {
    const r = await draftReply(props.initial.uid)
    replyBody.value = r.draft
  } catch (e: unknown) {
    replyError.value = (e as { data?: { detail?: string } })?.data?.detail || 'Could not draft a reply.'
  } finally { replyDrafting.value = false }
}
async function submitReply() {
  if (!replyBody.value.trim() || replySending.value) return
  replySending.value = true; replyError.value = ''
  try {
    await sendReply(props.initial.uid, replyBody.value.trim())
    replySent.value = true
    setTimeout(() => { replyOpen.value = false; replySent.value = false }, 2200)
  } catch (e: unknown) {
    replyError.value = (e as { data?: { detail?: string } })?.data?.detail || 'Send failed.'
  } finally { replySending.value = false }
}
const typed = ref('')
const reading = ref(false)
const preparing = ref(false)        // true between "open email" and "first word spoken"
const mode = ref<'summary' | 'full'>('summary')

const containerRef = ref<HTMLElement>()
const cardRef = ref<HTMLElement>()
const entityRef = ref<HTMLElement>()

interface Particle { id: number; text: string; left: number; top: number; dx: number; dy: number; rot: number; size: number }
const particles = ref<Particle[]>([])
let particleId = 0

const initialDate = computed(() => {
  const d = props.initial.date ? new Date(props.initial.date) : null
  return d && !isNaN(d.getTime())
    ? d.toLocaleString(undefined, { weekday: 'short', hour: '2-digit', minute: '2-digit', month: 'short', day: 'numeric' })
    : props.initial.date
})

function shortFrom(s: string): string {
  const m = s.match(/^\s*"?([^"<]+?)"?\s*<.*>/)
  return (m ? m[1] : s).trim() || s
}
function addrFrom(s: string): string {
  const m = s.match(/<([^>]+)>/)
  return m ? m[1] : ''
}

/* drive Olwen's own tendril to the email card */
const reachTarget = ref<{ x: number; y: number } | null>(null)
let rafM = 0
function measureLoop() {
  const el = cardRef.value
  if (el) {
    const r = el.getBoundingClientRect()
    reachTarget.value = { x: r.right + 8, y: r.top + 90 }
  }
  rafM = requestAnimationFrame(measureLoop)
}

/* ----- creative word flight: each spoken word is released as a glowing firefly ----- */
function spawnWord(text: string) {
  const t = text.replace(/^[^\p{L}\p{N}]+|[^\p{L}\p{N}]+$/gu, '').trim()
  if (!t || t.length < 2) return
  const ent = entityRef.value
  if (!ent) return
  const r = ent.getBoundingClientRect()
  const ox = r.left + r.width * 0.3
  const oy = r.top + r.height * 0.45 + (Math.random() * 30 - 15)
  // drift toward the card on the left, with a little upward float
  const dx = -(150 + Math.random() * 260)
  const dy = -(60 + Math.random() * 110)
  const rot = -10 + Math.random() * 20
  const size = 11 + Math.random() * 4
  const id = ++particleId
  particles.value.push({ id, text: t, left: ox, top: oy, dx, dy, rot, size })
  // remove after the CSS animation
  setTimeout(() => {
    const i = particles.value.findIndex(p => p.id === id)
    if (i >= 0) particles.value.splice(i, 1)
  }, 2200)
}

/* ----- speak + sync typing + per-word fireflies ----- */
let fallbackTimer: ReturnType<typeof setInterval> | undefined
let boundaryWatchdog: ReturnType<typeof setTimeout> | undefined

function stopSpeech() {
  voice.cancelSpeak()
  voice.cancelAudio()
  if (fallbackTimer) clearInterval(fallbackTimer)
  if (boundaryWatchdog) clearTimeout(boundaryWatchdog)
  reading.value = false
  preparing.value = false
}

function speak(text: string) {
  // Don't slap cancelSpeak() in the same tick as speak() — Chrome aborts the new
  // utterance with error="canceled". `useVoice.speak` now manages that internally.
  if (fallbackTimer) clearInterval(fallbackTimer)
  if (boundaryWatchdog) clearTimeout(boundaryWatchdog)
  if (!text) return
  reading.value = true
  preparing.value = true             // hold the loader until the first word fires
  typed.value = ''
  const words = text.split(/\s+/).filter(Boolean)
  let wordIdx = 0

  const releaseWord = (i: number) => {
    if (i < 0 || i >= words.length) return
    typed.value = words.slice(0, i + 1).join(' ')
    spawnWord(words[i])
    wordIdx = i + 1
    preparing.value = false          // first audible/visible word — drop the loader
  }

  if (voiceOn.value) {
    // Server-side TTS (Edge neural MP3 → <audio>). The MP3 doesn't expose word
    // boundaries, so we start the per-word reveal the moment the audio actually
    // plays, paced by the real audio duration so words and voice stay in sync.
    voice.speakAudio(text, {
      onStart: (durationMs) => {
        preparing.value = false
        const wordMs = Math.max(140, Math.min(520, Math.round(durationMs / words.length)))
        fallbackTimer = setInterval(() => {
          if (wordIdx >= words.length) { if (fallbackTimer) clearInterval(fallbackTimer); return }
          releaseWord(wordIdx)
        }, wordMs)
      },
      onEnd: () => {
        for (let k = wordIdx; k < words.length; k++) releaseWord(k)
        if (fallbackTimer) clearInterval(fallbackTimer)
        reading.value = false
      },
    })
  } else {
    fallbackTimer = setInterval(() => {
      if (wordIdx >= words.length) {
        if (fallbackTimer) clearInterval(fallbackTimer)
        reading.value = false
        return
      }
      releaseWord(wordIdx)
    }, 220)
  }
}

async function loadFull() {
  loading.value = true; error.value = ''
  try {
    full.value = await message(props.initial.uid)
  } catch (e: unknown) {
    // Soft fail — we can still summarize from the snippet we already have.
    const detail = (e as { data?: { detail?: string }; status?: number })?.data?.detail
    error.value = detail === 'Message not found' ? '' : (detail || '')
  } finally { loading.value = false }
}

async function loadSummary() {
  summarizing.value = true
  try {
    const r = await summarize(props.initial.uid, {
      sender: props.initial.sender,
      subject: props.initial.subject,
      snippet: full.value?.body || props.initial.snippet,
    })
    summary.value = r.summary
    actions.value = r.actions || []
    mode.value = 'summary'
    await nextTick()
    speak(summary.value)
    // Auto mark-as-read if the user has the setting on.
    if (autoMarkRead.value && markReadStatus.value === 'idle') {
      try {
        const res = await markRead(props.initial.uid)
        markReadStatus.value = res.ok ? 'done' : 'failed'
        if (res.ok) emit('markedRead', props.initial.uid)
      } catch { markReadStatus.value = 'failed' }
    }
  } catch (e: unknown) {
    error.value = (e as { data?: { detail?: string } })?.data?.detail || 'Olwen could not summarize this one.'
  } finally { summarizing.value = false }
}

/* ---- handling Olwen's suggested actions ---- */
async function doActionNow(a: EmailAction) {
  actionedKeys.value.add(a.label)
  if (a.kind === 'open_url' && a.payload) {
    window.open(a.payload, '_blank', 'noopener')
    return
  }
  if (a.kind === 'reply') {
    // Open the inline composer, prefilled with Olwen's suggestion + AI-drafted body
    await openReply(a.description ? `${a.description}\n\n` : '')
    return
  }
  // reminder / task / unknown — keep the safety net of queuing a task
  await actionLater(a)
}

async function actionLater(a: EmailAction) {
  actionedKeys.value.add(a.label)
  // Pick the default/first list; if none, load and try again.
  if (!taskLists.value.length) await loadTasks()
  const list = taskLists.value[0]
  if (!list) return
  const fromName = shortFrom(props.initial.sender)
  const text = `${a.label} — ${fromName}: ${props.initial.subject}`.slice(0, 200)
  await addTaskFn(list.id, text, 'high')
}

const readableBody = computed(() => full.value?.body || props.initial.snippet || '')

// Caption shows a rolling tail — only the last ~240 chars of what Olwen has
// spoken so far, so the long-form "read full email" doesn't bury the entity.
const captionTail = computed(() => {
  const t = typed.value || summary.value || ''
  if (t.length <= 240) return { text: t, truncated: false }
  return { text: t.slice(t.length - 240), truncated: true }
})
function readFully() {
  if (!readableBody.value) return
  mode.value = 'full'
  // cap to keep TTS reasonable; first 2000 chars catches most actionable content
  speak(readableBody.value.slice(0, 2000))
}
function replaySummary() {
  if (!summary.value) return
  mode.value = 'summary'
  speak(summary.value)
}
const dismissing = ref(false)
const dismissCenter = ref({ x: 0, y: 0 })
function close() {
  if (dismissing.value) return
  // Hard-stop voice immediately and again as the overlay tears down (Chrome quirk).
  stopSpeech()
  voice.cancelSpeak()
  setTimeout(() => voice.cancelSpeak(), 120)
  // Anchor the FX layer at Olwen's actual screen position.
  const el = entityRef.value
  if (el) {
    const r = el.getBoundingClientRect()
    dismissCenter.value = { x: r.left + r.width / 2, y: r.top + r.height / 2 }
  }
  dismissing.value = true
  setTimeout(() => { entered.value = false }, 380)
  setTimeout(() => emit('close'), 1000)
}

onMounted(async () => {
  requestAnimationFrame(() => { entered.value = true })
  rafM = requestAnimationFrame(measureLoop)

  // refresh the auto-mark-read preference; non-blocking
  fetchSettings().then(s => { autoMarkRead.value = !!s.auto_mark_read }).catch(() => {})

  // Speak a one-line intro IMMEDIATELY (no LLM, instant TTS) so there's no dead
  // silence while the AI thinks.
  if (voiceOn.value) {
    const introLine = `Email from ${shortFrom(props.initial.sender)}. Subject: ${props.initial.subject}.`
    voice.speakAudio(introLine)
  }
  await Promise.all([loadFull(), loadSummary()])
})
onBeforeUnmount(() => { stopSpeech(); cancelAnimationFrame(rafM) })

const entityState = computed(() => (reading.value ? 'speaking' : (summarizing.value || loading.value ? 'thinking' : 'working')))
</script>

<template>
  <div ref="containerRef" class="reader" :class="{ entered }">
    <div class="reader__bg" aria-hidden="true" />

    <!-- LEFT: the actual email opened -->
    <article ref="cardRef" class="card">
      <header class="card__head">
        <div class="card__from">
          <span class="card__avatar">{{ shortFrom(initial.sender).charAt(0).toUpperCase() }}</span>
          <div>
            <div class="card__name">{{ shortFrom(initial.sender) }}</div>
            <div class="card__addr">{{ addrFrom(initial.sender) }}</div>
          </div>
          <span v-if="initial.unread" class="card__unread">UNREAD</span>
        </div>
        <h1 class="card__subj">{{ initial.subject }}</h1>
        <div class="card__meta">
          <span>{{ initialDate }}</span>
          <span v-if="(initial as TriagedEmail).priority" class="card__prio" :class="`p-${(initial as TriagedEmail).priority}`">
            {{ (initial as TriagedEmail).priority?.toUpperCase() }}
          </span>
        </div>
      </header>

      <div class="card__body">
        <div v-if="loading" class="card__loading">
          <span class="dot" /><span class="dot" /><span class="dot" />
        </div>
        <template v-else>
          <p v-if="!full?.body && initial.snippet" class="card__hint">
            Showing preview — Olwen couldn't fetch the full message body.
          </p>
          <p v-else-if="!full?.body && !initial.snippet" class="card__hint card__hint--err">
            {{ error || 'No content available for this message.' }}
          </p>
          <pre class="card__text">{{ full?.body || initial.snippet || '' }}</pre>
        </template>
      </div>

      <!-- Olwen's suggested actions — Now sends to its native handler; Later adds a task -->
      <div v-if="actions.length" class="suggestions">
        <span class="suggestions__label">✦ Olwen sees actions</span>
        <ul class="suggestions__list">
          <li v-for="a in actions" :key="a.label" class="sugg" :class="{ done: actionedKeys.has(a.label) }">
            <div class="sugg__main">
              <span class="sugg__label">{{ a.label }}</span>
              <span v-if="a.description" class="sugg__desc">{{ a.description }}</span>
            </div>
            <div class="sugg__btns">
              <button class="sugg__btn sugg__btn--now" :disabled="actionedKeys.has(a.label)" @click="doActionNow(a)">
                {{ a.kind === 'open_url' ? '↗ Open' : '⚡ Do now' }}
              </button>
              <button class="sugg__btn" :disabled="actionedKeys.has(a.label)" @click="actionLater(a)">↻ Later</button>
            </div>
          </li>
        </ul>
      </div>

      <p v-if="markReadStatus === 'failed'" class="markhint">
        Couldn't mark as read — for Gmail, disconnect and reconnect to grant write permission.
      </p>

      <footer class="card__actions">
        <button class="act" :disabled="!summary" @click="replaySummary">
          <span class="act__glyph">✦</span> {{ reading && mode === 'summary' ? 'Reading summary…' : 'Read summary again' }}
        </button>
        <button class="act act--primary" :disabled="!readableBody" @click="readFully">
          <span class="act__glyph">▶</span> {{ reading && mode === 'full' ? 'Reading aloud…' : 'Read the whole email' }}
        </button>
        <button v-if="reading" class="act" @click="stopSpeech">⏸ Stop</button>
        <button class="act" :disabled="replyOpen" @click="openReply('')">✎ Reply</button>
        <button class="act act--ghost" type="button" @click="close">✕ Close</button>
      </footer>

      <!-- Inline reply composer -->
      <Transition name="reply">
        <div v-if="replyOpen" class="reply">
          <div class="reply__head">
            <span class="reply__label">REPLY TO {{ shortFrom(initial.sender).toUpperCase() }}</span>
            <button class="reply__x" @click="replyOpen = false">✕</button>
          </div>
          <textarea
            v-model="replyBody"
            class="reply__body"
            :placeholder="replyDrafting ? 'Olwen is drafting…' : 'Type your reply, or let Olwen draft it.'"
            rows="7"
            :disabled="replyDrafting || replySending"
          />
          <p v-if="replyError" class="reply__err">{{ replyError }}</p>
          <p v-if="replySent" class="reply__ok">✓ Sent to {{ shortFrom(initial.sender) }}</p>
          <div class="reply__actions">
            <button class="act" :disabled="replyDrafting || replySending" @click="draftWithOlwen">
              {{ replyDrafting ? '✦ Drafting…' : '✦ Draft with Olwen' }}
            </button>
            <button class="act act--primary" :disabled="!replyBody.trim() || replySending || replyDrafting" @click="submitReply">
              {{ replySending ? 'Sending…' : '✈ Send' }}
            </button>
          </div>
        </div>
      </Transition>
    </article>

    <!-- RIGHT: Olwen + spoken caption — tap him to return home -->
    <div
      ref="entityRef"
      class="reader__entity"
      :class="{ dismissing }"
      data-olwen
      role="button"
      aria-label="Tap Olwen to return home"
      tabindex="0"
      @click="close"
      @keyup.enter="close"
    >
      <!-- one soft halo that simply brightens on hover -->
      <span class="halo" aria-hidden="true" />
      <span class="reader__entityhint">↩ tap to return home</span>
      <OlwenEntity :state="entityState" :reach-target="reachTarget" />
      <div class="caption">
        <!-- one unified loader: visible from "opened email" until first spoken word -->
        <div v-if="loading || summarizing || (preparing && !typed)" class="prep">
          <div class="prep__dots"><span /><span /><span /></div>
          <span class="prep__label">
            {{ loading ? 'Opening email…' : (summarizing ? 'Olwen is reading the email…' : 'Olwen is preparing to speak…') }}
          </span>
        </div>
        <template v-else>
          <span class="caption__label">{{ mode === 'summary' ? 'Olwen summarizes' : 'Olwen reads' }}</span>
          <p v-if="summary || typed" class="caption__text">
            <span v-if="captionTail.truncated" class="caption__ellipsis">… </span>{{ captionTail.text }}<span v-if="reading" class="cursor">▍</span>
          </p>
          <p v-else-if="error" class="caption__err">
            {{ error }}
            <button class="caption__retry" @click="loadSummary">↻ Retry</button>
          </p>
          <p v-else class="caption__hint">Tap “Read summary again” to hear it.</p>
        </template>
      </div>
    </div>

    <!-- cinematic dismissal — full-screen, escapes any clipping -->
    <OlwenDismissFX v-if="dismissing" :center="dismissCenter" />

    <!-- creative animation: each spoken word becomes a glowing firefly drifting off the tendril -->
    <div class="firefly-layer" aria-hidden="true">
      <span
        v-for="p in particles"
        :key="p.id"
        class="firefly"
        :style="{
          left: p.left + 'px',
          top: p.top + 'px',
          fontSize: p.size + 'px',
          '--dx': p.dx + 'px',
          '--dy': p.dy + 'px',
          '--rot': p.rot + 'deg',
        }"
      >{{ p.text }}</span>
    </div>
  </div>
</template>

<style scoped>
.reader { position: fixed; inset: 0; z-index: 65; display: grid; grid-template-columns: minmax(0, 1.05fr) minmax(0, 0.95fr); align-items: center; opacity: 0; transition: opacity .45s ease; overflow: hidden; }
.reader.entered { opacity: 1; }
.reader__bg { position: absolute; inset: 0; z-index: -1; background:
  radial-gradient(ellipse at 30% 40%, rgba(6,182,212,0.10) 0%, transparent 60%),
  radial-gradient(ellipse at 75% 60%, rgba(94,234,212,0.08) 0%, transparent 65%),
  var(--bg);
}

/* ---- the actual email card ---- */
.card {
  justify-self: center; width: min(620px, 92%); max-height: 80vh;
  display: flex; flex-direction: column;
  border-radius: 18px; border: 0.5px solid var(--border-strong);
  background: linear-gradient(180deg, var(--surface-2) 0%, color-mix(in srgb, var(--bg) 65%, transparent) 100%);
  box-shadow: 0 30px 80px rgba(0,0,0,0.5), 0 0 0 1px rgba(94,234,212,0.05), 0 0 60px rgba(94,234,212,0.06);
  backdrop-filter: blur(18px);
  transform: translateX(-30px) scale(0.96); opacity: 0;
  transition: transform .7s cubic-bezier(.22,.61,.36,1), opacity .7s ease;
  overflow: hidden;
}
.reader.entered .card { transform: translateX(0) scale(1); opacity: 1; }

.card__head { padding: 22px 26px 16px; border-bottom: 0.5px solid var(--border); }
.card__from { display: flex; align-items: center; gap: 12px; }
.card__avatar {
  width: 38px; height: 38px; border-radius: 50%; display: grid; place-items: center;
  background: linear-gradient(135deg, #5EEAD4, #06B6D4); color: var(--bg);
  font-family: 'JetBrains Mono', monospace; font-weight: 600; font-size: 15px;
  box-shadow: 0 0 18px rgba(94,234,212,0.4);
}
.card__name { font-size: 14.5px; color: var(--text-strong); font-weight: 500; }
.card__addr { font-family: 'JetBrains Mono', monospace; font-size: 10.5px; color: var(--text-muted); }
.card__unread { margin-left: auto; font-family: 'JetBrains Mono', monospace; font-size: 8.5px; letter-spacing: 1.5px; color: var(--bg); background: var(--accent); padding: 3px 8px; border-radius: 999px; }
.card__subj { margin: 14px 0 0; font-size: 22px; font-weight: 300; color: var(--text-strong); line-height: 1.25; letter-spacing: 0.2px; }
.card__meta { margin-top: 10px; display: flex; align-items: center; gap: 10px; font-family: 'JetBrains Mono', monospace; font-size: 10px; letter-spacing: 1.2px; color: var(--text-muted); text-transform: uppercase; }
.card__prio { padding: 2px 8px; border-radius: 999px; border: 0.5px solid currentColor; font-size: 9px; }
.card__prio.p-high { color: #F87171; }
.card__prio.p-med  { color: #FBBF24; }
.card__prio.p-low  { color: var(--accent); }

.card__body { flex: 1; min-height: 0; overflow-y: auto; padding: 18px 26px 8px; }
.card__body::-webkit-scrollbar { width: 5px; }
.card__body::-webkit-scrollbar-thumb { background: rgba(94,234,212,0.2); border-radius: 3px; }
.card__text { margin: 0; font-family: inherit; font-size: 13.5px; line-height: 1.65; color: var(--text); white-space: pre-wrap; word-wrap: break-word; }
.card__loading { display: flex; gap: 6px; padding: 6px 0; }
.card__loading .dot { width: 6px; height: 6px; border-radius: 50%; background: var(--accent); opacity: 0.4; animation: dotpulse 1.2s ease-in-out infinite; }
.card__loading .dot:nth-child(2) { animation-delay: .2s; }
.card__loading .dot:nth-child(3) { animation-delay: .4s; }
@keyframes dotpulse { 0%,100% { opacity: 0.25; transform: scale(0.8); } 50% { opacity: 1; transform: scale(1.1); } }
.card__error { font-size: 12.5px; color: #FCA5A5; border-left: 2px solid #F87171; padding-left: 9px; }
.card__hint { margin: 0 0 10px; font-size: 11px; color: var(--text-muted); font-family: 'JetBrains Mono', monospace; letter-spacing: 0.4px; border-left: 2px solid var(--border-strong); padding-left: 9px; }
.card__hint--err { color: #FCA5A5; border-left-color: #F87171; }

.card__actions { display: flex; gap: 10px; padding: 14px 22px 18px; border-top: 0.5px solid var(--border); flex-wrap: wrap; }
.act { display: inline-flex; align-items: center; gap: 7px; padding: 9px 16px; border-radius: 999px; cursor: pointer; border: 0.5px solid var(--border-strong); background: var(--surface-2); color: var(--accent-2); font-family: 'JetBrains Mono', monospace; font-size: 10.5px; letter-spacing: 1.3px; text-transform: uppercase; transition: all .2s ease; }
.act:hover:not(:disabled) { border-color: var(--accent); color: var(--text-strong); background: rgba(94,234,212,0.12); }
.act:disabled { opacity: 0.45; cursor: not-allowed; }
.act--primary { color: var(--bg); background: var(--accent); border-color: var(--accent); box-shadow: 0 0 18px rgba(94,234,212,0.3); }
.act--primary:hover:not(:disabled) { background: #67E8F9; color: var(--bg); }
.act--ghost { margin-left: auto; color: var(--text-muted); }

/* ---- Olwen's suggested actions ---- */
.suggestions { padding: 12px 22px 4px; border-top: 0.5px solid var(--border); }
.suggestions__label { display: block; font-family: 'JetBrains Mono', monospace; font-size: 9px; letter-spacing: 1.8px; text-transform: uppercase; color: var(--accent); margin-bottom: 8px; }
.suggestions__list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.sugg { display: flex; align-items: center; gap: 10px; padding: 9px 12px; border-radius: 10px; background: var(--surface-2); border: 0.5px solid var(--border-strong); transition: opacity .25s ease; }
.sugg.done { opacity: 0.45; }
.sugg__main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 1px; }
.sugg__label { font-size: 12.5px; color: var(--text-strong); font-weight: 500; }
.sugg__desc { font-size: 11px; color: var(--text-muted); }
.sugg__btns { display: flex; gap: 6px; flex-shrink: 0; }
.sugg__btn { padding: 5px 10px; border-radius: 999px; cursor: pointer; border: 0.5px solid var(--border-strong); background: transparent; color: var(--accent-2); font-family: 'JetBrains Mono', monospace; font-size: 9.5px; letter-spacing: 1.2px; text-transform: uppercase; transition: all .15s ease; }
.sugg__btn:hover:not(:disabled) { border-color: var(--accent); color: var(--text-strong); background: rgba(94,234,212,0.10); }
.sugg__btn:disabled { opacity: 0.4; cursor: not-allowed; }
.sugg__btn--now { background: rgba(94,234,212,0.14); border-color: var(--border-strong); color: var(--accent); }
.sugg__btn--now:hover:not(:disabled) { background: rgba(94,234,212,0.25); color: var(--text-strong); }

.markhint { margin: 0 22px 6px; font-size: 11px; color: rgba(251,191,36,0.75); border-left: 2px solid #FBBF24; padding-left: 9px; }

/* ---- inline reply composer ---- */
.reply { margin: 0 22px 18px; padding: 14px 16px; border-radius: 12px; border: 0.5px solid var(--border-strong); background: var(--surface-2); display: flex; flex-direction: column; gap: 10px; }
.reply__head { display: flex; align-items: center; justify-content: space-between; }
.reply__label { font-family: 'JetBrains Mono', monospace; font-size: 9px; letter-spacing: 1.6px; color: var(--accent); }
.reply__x { background: transparent; border: none; color: var(--text-muted); cursor: pointer; font-size: 14px; }
.reply__x:hover { color: #F87171; }
.reply__body { width: 100%; min-height: 130px; padding: 12px 14px; border-radius: 10px; border: 0.5px solid var(--border-strong); background: color-mix(in srgb, var(--bg) 50%, transparent); color: var(--text-strong); font-family: inherit; font-size: 13.5px; line-height: 1.6; resize: vertical; outline: none; }
.reply__body:focus { border-color: var(--accent); box-shadow: 0 0 18px rgba(94,234,212,0.15); }
.reply__body:disabled { opacity: 0.55; cursor: progress; }
.reply__err { margin: 0; font-size: 12px; color: #FCA5A5; border-left: 2px solid #F87171; padding-left: 9px; }
.reply__ok { margin: 0; font-size: 12px; color: var(--accent); font-family: 'JetBrains Mono', monospace; letter-spacing: 0.6px; }
.reply__actions { display: flex; gap: 10px; justify-content: flex-end; }

.reply-enter-active, .reply-leave-active { transition: opacity .3s ease, transform .35s cubic-bezier(.22,.7,.36,1), max-height .35s ease; overflow: hidden; }
.reply-enter-from, .reply-leave-to { opacity: 0; transform: translateY(-8px); max-height: 0; }
.reply-enter-to, .reply-leave-from { opacity: 1; transform: translateY(0); max-height: 500px; }
.act__glyph { font-size: 11px; }

/* ---- right column: entity + caption ---- */
.reader__entity { position: relative; justify-self: center; width: 360px; height: 360px; display: grid; place-items: center; transform: translateX(40px) scale(0.92); opacity: 0; transition: transform .8s cubic-bezier(.22,.61,.36,1), opacity .8s ease; }
.reader.entered .reader__entity { transform: translateX(0) scale(1); opacity: 1; }
/* ---- simple, soft hover ---- */
.reader__entity { position: relative; transition: transform .35s cubic-bezier(.22,.61,.36,1), filter .35s ease; }
.reader__entity:hover { transform: translateX(0) scale(1.03); filter: drop-shadow(0 0 38px rgba(94,234,212,0.45)); }
.reader__entity:focus-visible { outline: none; filter: drop-shadow(0 0 42px rgba(167,243,208,0.55)); }
.reader__entity:active { transform: translateX(0) scale(0.97); transition-duration: .12s; }

/* a single soft halo — gently brightens on hover */
.halo {
  position: absolute; inset: -8%; border-radius: 50%; pointer-events: none;
  background: radial-gradient(circle, rgba(94,234,212,0.18) 0%, rgba(94,234,212,0.06) 40%, transparent 65%);
  opacity: 0.35; transition: opacity .35s ease, transform .35s ease;
}
.reader__entity:hover .halo,
.reader__entity:focus-visible .halo { opacity: 1; transform: scale(1.08); }

/* hint pill — breathes when shown */
.reader__entity:hover .reader__entityhint,
.reader__entity:focus-visible .reader__entityhint { opacity: 1; transform: translate(-50%, 0); }
.reader__entityhint {
  position: absolute; top: -36px; left: 50%; transform: translate(-50%, 8px);
  font-family: 'JetBrains Mono', monospace; font-size: 9.5px; letter-spacing: 2px; text-transform: uppercase;
  color: var(--text-strong); padding: 5px 14px; border-radius: 999px;
  background: linear-gradient(180deg, var(--surface-2), color-mix(in srgb, var(--bg) 85%, transparent));
  border: 0.5px solid var(--border-strong);
  box-shadow: 0 0 22px rgba(94,234,212,0.25), inset 0 0 18px rgba(94,234,212,0.08);
  opacity: 0; pointer-events: none;
  transition: opacity .3s ease, transform .3s ease;
  white-space: nowrap; z-index: 5;
  animation: hintbreath 2.4s ease-in-out infinite;
}
@keyframes hintbreath { 0%,100% { box-shadow: 0 0 18px rgba(94,234,212,0.2); } 50% { box-shadow: 0 0 28px rgba(94,234,212,0.45); } }

/* shockwave + starlight burst — invisible until dismissed */
.shock, .burst { position: absolute; left: 50%; top: 50%; pointer-events: none; opacity: 0; }
.shock {
  width: 70%; height: 70%; transform: translate(-50%, -50%);
  border-radius: 50%; border: 1.5px solid #5EEAD4;
  box-shadow: 0 0 30px #5EEAD4;
}
.burst {
  width: 6px; height: 6px; border-radius: 50%;
  background: #A7F3D0; box-shadow: 0 0 10px #5EEAD4, 0 0 24px rgba(94,234,212,0.7);
  transform: translate(-50%, -50%);
}
.reader__entity.dismissing .shock        { animation: shock 0.95s cubic-bezier(.18,.6,.32,1) forwards; }
.reader__entity.dismissing .shock--delay { animation: shock 0.95s cubic-bezier(.18,.6,.32,1) .14s forwards; opacity: 0; }
.reader__entity.dismissing .burst        { animation: burst 0.9s cubic-bezier(.18,.6,.32,1) forwards; }
.reader__entity.dismissing { animation: absorb 0.95s cubic-bezier(.55,.05,.68,.19) forwards; }

@keyframes shock {
  0%   { width: 30%; height: 30%; opacity: 0.95; border-width: 2px; }
  100% { width: 240%; height: 240%; opacity: 0; border-width: 0.4px; }
}
@keyframes burst {
  0%   { transform: translate(-50%, -50%) rotate(var(--a)) translateX(0) scale(1); opacity: 0; }
  15%  { opacity: 1; }
  100% { transform: translate(-50%, -50%) rotate(var(--a)) translateX(220px) scale(0.2); opacity: 0; }
}
@keyframes absorb {
  0%   { transform: translateX(0) scale(1)    rotate(0deg);   opacity: 1; filter: brightness(1); }
  30%  { transform: translateX(0) scale(1.22) rotate(8deg);   opacity: 1; filter: brightness(1.7) drop-shadow(0 0 38px #5EEAD4); }
  70%  { transform: translateX(0) scale(0.55) rotate(-30deg); opacity: 0.8; filter: brightness(2.4) drop-shadow(0 0 60px #67E8F9); }
  100% { transform: translateX(0) scale(0.05) rotate(-90deg); opacity: 0; filter: brightness(3); }
}
@media (prefers-reduced-motion: reduce) {
  .reader__entity, .aura, .shock, .burst { animation: none !important; transition: none !important; }
  .reader__entity.dismissing { opacity: 0; transition: opacity .3s ease !important; }
}
.caption { position: absolute; bottom: -40px; width: 92%; max-width: 460px; text-align: center; }
.caption__label { display: block; font-family: 'JetBrains Mono', monospace; font-size: 9px; letter-spacing: 2px; text-transform: uppercase; color: var(--accent); margin-bottom: 6px; }
.caption__loading { font-family: 'JetBrains Mono', monospace; font-size: 10px; letter-spacing: 2px; text-transform: uppercase; color: var(--accent-2); }
.caption__loading::after { content: '…'; color: var(--accent); }
.caption__text {
  margin: 0; font-size: 14px; line-height: 1.5; color: var(--text-strong); font-weight: 300;
  min-height: 1.5em; max-height: 4.6em; overflow: hidden;
  /* fade the top so the rolling tail looks like a subtitle */
  -webkit-mask-image: linear-gradient(to bottom, transparent 0%, #000 25%, #000 100%);
          mask-image: linear-gradient(to bottom, transparent 0%, #000 25%, #000 100%);
}
.caption__ellipsis { color: var(--text-muted); }
.caption__err { margin: 0; font-size: 12.5px; color: #FCA5A5; display: flex; flex-direction: column; align-items: center; gap: 8px; }
.caption__retry { margin-top: 4px; padding: 6px 14px; border-radius: 999px; border: 0.5px solid rgba(252,165,165,0.45); background: transparent; color: #FCA5A5; font-family: 'JetBrains Mono', monospace; font-size: 10px; letter-spacing: 1.3px; text-transform: uppercase; cursor: pointer; }
.caption__retry:hover { background: rgba(252,165,165,0.1); border-color: #FCA5A5; }
.caption__hint { margin: 0; font-size: 12px; color: var(--text-muted); font-style: italic; }

/* preparing-to-read loader */
.prep { display: flex; flex-direction: column; align-items: center; gap: 10px; }
.prep__dots { display: flex; gap: 7px; }
.prep__dots span {
  width: 8px; height: 8px; border-radius: 50%;
  background: var(--accent); box-shadow: 0 0 12px #5EEAD4, 0 0 24px rgba(94,234,212,0.6);
  animation: prepbob 1.2s ease-in-out infinite;
}
.prep__dots span:nth-child(2) { animation-delay: .18s; }
.prep__dots span:nth-child(3) { animation-delay: .36s; }
@keyframes prepbob {
  0%, 100% { transform: translateY(0) scale(0.85); opacity: 0.45; }
  50%      { transform: translateY(-8px) scale(1.15); opacity: 1; }
}
.prep__label {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px; letter-spacing: 2px; text-transform: uppercase;
  color: var(--accent-2); opacity: 0.85;
}
@media (prefers-reduced-motion: reduce) {
  .prep__dots span { animation: none; opacity: 0.7; }
}
.cursor { color: var(--accent); animation: blink 1s step-start infinite; margin-left: 2px; }
@keyframes blink { 50% { opacity: 0; } }

/* ---- the firefly layer: spoken words drifting off the tendril ---- */
.firefly-layer { position: fixed; inset: 0; pointer-events: none; z-index: 70; overflow: hidden; }
.firefly {
  position: absolute; transform-origin: center; pointer-events: none;
  color: var(--text-strong);
  font-family: 'JetBrains Mono', monospace;
  letter-spacing: 0.3px;
  white-space: nowrap;
  text-shadow: 0 0 8px rgba(94,234,212,0.85), 0 0 18px rgba(94,234,212,0.55), 0 0 30px rgba(6,182,212,0.35);
  animation: wordfly 2.2s cubic-bezier(.18,.6,.32,1) forwards;
  will-change: transform, opacity;
}
@keyframes wordfly {
  0% { transform: translate(0, 0) rotate(0deg) scale(0.6); opacity: 0; filter: blur(2px); }
  12% { opacity: 1; transform: translate(calc(var(--dx) * 0.05), calc(var(--dy) * 0.05)) rotate(calc(var(--rot) * 0.2)) scale(1); filter: blur(0); }
  70% { opacity: 1; }
  100% { transform: translate(var(--dx), var(--dy)) rotate(var(--rot)) scale(1.05); opacity: 0; filter: blur(1px); }
}
@media (prefers-reduced-motion: reduce) {
  .firefly { animation: wordfly-soft 1.4s ease-out forwards; }
  @keyframes wordfly-soft { 0% { opacity: 0; } 30% { opacity: 1; } 100% { opacity: 0; } }
}

@media (max-width: 900px) {
  .reader { grid-template-columns: 1fr; grid-template-rows: 1fr auto; }
  .reader__entity { width: 180px; height: 180px; }
  .card { max-height: 60vh; }
}
</style>
