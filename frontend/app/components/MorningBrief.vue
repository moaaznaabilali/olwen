<script setup lang="ts">
/* Cinematic morning brief — Olwen narrates the day ahead, with the underlying
   data cards floating in around him. Modeled on the tasks WorkMode visual
   language: cosmic stage, entity right, content left, dismiss = absorb pulse. */
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import OlwenEntity from './OlwenEntity.vue'
import OlwenDismissFX from './OlwenDismissFX.vue'
import type { Brief, BriefEvent, BriefInboxItem, BriefNewsItem, BriefTask } from '../composables/useBrief'

const props = defineProps<{ brief: Brief }>()
const emit = defineEmits<{ close: [] }>()

const voice = useVoice()
const voiceOn = useState<boolean>('voice:on', () => true)

const entered = ref(false)
const reading = ref(false)
const typed = ref('')
const preparing = ref(true)
const dismissing = ref(false)
const dismissCenter = ref({ x: 0, y: 0 })

const entityRef = ref<HTMLElement>()

const entityState = computed(() => (dismissing.value ? 'idle' : reading.value ? 'speaking' : preparing.value ? 'thinking' : 'idle'))

// Caption rolling tail (so long narratives don't bury the entity)
const captionTail = computed(() => {
  const t = typed.value
  if (t.length <= 280) return { text: t, truncated: false }
  return { text: t.slice(t.length - 280), truncated: true }
})

/* ---- speak the narrative (server TTS → audio + word-paced reveal) ---- */
let fallbackTimer: ReturnType<typeof setInterval> | undefined

function speakNarrative(text: string) {
  if (!text) { preparing.value = false; return }
  reading.value = true
  typed.value = ''
  preparing.value = true
  const words = text.split(/\s+/).filter(Boolean)
  let wordIdx = 0
  const release = (i: number) => {
    if (i < 0 || i >= words.length) return
    typed.value = words.slice(0, i + 1).join(' ')
    preparing.value = false
    wordIdx = i + 1
  }
  if (voiceOn.value) {
    voice.speakAudio(text, {
      onStart: (durMs) => {
        const wordMs = Math.max(140, Math.min(520, Math.round(durMs / words.length)))
        fallbackTimer = setInterval(() => {
          if (wordIdx >= words.length) { if (fallbackTimer) clearInterval(fallbackTimer); return }
          release(wordIdx)
        }, wordMs)
      },
      onEnd: () => {
        for (let k = wordIdx; k < words.length; k++) release(k)
        if (fallbackTimer) clearInterval(fallbackTimer)
        reading.value = false
      },
    })
  } else {
    fallbackTimer = setInterval(() => {
      if (wordIdx >= words.length) { if (fallbackTimer) clearInterval(fallbackTimer); reading.value = false; return }
      release(wordIdx)
    }, 230)
  }
}

function stopSpeech() {
  voice.cancelAudio()
  if (fallbackTimer) clearInterval(fallbackTimer)
  reading.value = false
  preparing.value = false
}

/* ---- card helpers ---- */
function fmtTime(iso: string): string {
  if (!iso || iso.length === 10) return 'All day'
  const d = new Date(iso); return isFinite(d.getTime()) ? d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' }) : ''
}
function shortFrom(s: string): string {
  const m = s?.match(/^\s*"?([^"<]+?)"?\s*<.*>/)
  return (m ? m[1] : s)?.trim() || s || ''
}
function ago(iso: string): string {
  if (!iso) return ''
  const t = new Date(iso).getTime(); if (!isFinite(t)) return ''
  const s = Math.max(0, (Date.now() - t) / 1000)
  if (s < 3600) return `${Math.floor(s / 60)}m`
  if (s < 86400) return `${Math.floor(s / 3600)}h`
  return `${Math.floor(s / 86400)}d`
}
function weatherDesc(code: number): string {
  if (code === 0) return 'Clear'
  if (code <= 3) return 'Partly cloudy'
  if (code <= 48) return 'Fog'
  if (code <= 67) return 'Rain'
  if (code <= 77) return 'Snow'
  if (code <= 82) return 'Showers'
  return 'Storm'
}

/* ---- dismiss ---- */
function close() {
  if (dismissing.value) return
  stopSpeech()
  voice.cancelAudio()
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
  await nextTick()
  // small breath so the entity entrance animation lands first
  setTimeout(() => speakNarrative(props.brief.narrative), 750)
})
onBeforeUnmount(() => { stopSpeech() })

const hasAny = computed(() => Boolean(
  props.brief.weather || props.brief.calendar.length || props.brief.tasks.length || props.brief.inbox.length || props.brief.news.length
))
</script>

<template>
  <div class="brief" :class="{ entered }">
    <div class="brief__bg" aria-hidden="true" />

    <!-- LEFT: floating data cards arranged in a vertical stream -->
    <div class="stream">
      <Transition name="card" appear>
        <div v-if="brief.weather" class="card card--weather" :style="{ '--d': '0ms' }">
          <span class="card__tag">Weather</span>
          <div class="card__row">
            <span class="card__big">{{ brief.weather.now_c }}°</span>
            <div class="card__sub">
              <span>{{ weatherDesc(brief.weather.code) }}</span>
              <span class="card__hi">↑ {{ brief.weather.high_c }}°  ↓ {{ brief.weather.low_c }}°</span>
            </div>
          </div>
        </div>
      </Transition>

      <Transition name="card" appear>
        <div v-if="brief.calendar.length" class="card card--cal" :style="{ '--d': '120ms' }">
          <span class="card__tag">Today's calendar</span>
          <ul class="lst">
            <li v-for="e in brief.calendar.slice(0, 3)" :key="e.id">
              <span class="lst__at">{{ fmtTime(e.start) }}</span>
              <span class="lst__lbl">{{ e.title }}</span>
            </li>
          </ul>
        </div>
      </Transition>

      <Transition name="card" appear>
        <div v-if="brief.tasks.length" class="card card--tasks" :style="{ '--d': '240ms' }">
          <span class="card__tag">Open tasks</span>
          <ul class="lst">
            <li v-for="(t, i) in brief.tasks.slice(0, 4)" :key="i" :class="`p-${t.priority}`">
              <span class="lst__dot" />
              <span class="lst__lbl">{{ t.text }}</span>
            </li>
          </ul>
        </div>
      </Transition>

      <Transition name="card" appear>
        <div v-if="brief.inbox.length" class="card card--inbox" :style="{ '--d': '360ms' }">
          <span class="card__tag">Inbox · {{ brief.inbox.length }} unread</span>
          <ul class="lst">
            <li v-for="m in brief.inbox.slice(0, 3)" :key="m.uid">
              <span class="lst__lbl">
                <strong>{{ shortFrom(m.sender) }}</strong> · {{ m.subject }}
              </span>
            </li>
          </ul>
        </div>
      </Transition>

      <Transition name="card" appear>
        <div v-if="brief.news.length" class="card card--news" :style="{ '--d': '480ms' }">
          <span class="card__tag">News</span>
          <ul class="lst">
            <li v-for="(n, i) in brief.news.slice(0, 3)" :key="i">
              <span class="lst__tag">{{ n.tag }}</span>
              <a class="lst__lbl" :href="n.url" target="_blank" rel="noopener">{{ n.title }}</a>
              <span class="lst__ago">{{ ago(n.published) }}</span>
            </li>
          </ul>
        </div>
      </Transition>

      <p v-if="!hasAny" class="empty">Quiet day. Nothing urgent across calendar, tasks, or inbox.</p>
    </div>

    <!-- RIGHT: Olwen + spoken narrative (rolling tail) -->
    <div
      ref="entityRef"
      class="brief__entity"
      :class="{ dismissing }"
      data-olwen
      role="button"
      aria-label="Tap Olwen to dismiss the brief"
      tabindex="0"
      @click="close" @keyup.enter="close"
    >
      <span class="halo" aria-hidden="true" />
      <span class="entityhint">↩ tap to return home</span>
      <OlwenEntity :state="entityState" />
      <div class="caption">
        <div v-if="preparing && !typed" class="prep"><span /><span /><span /></div>
        <template v-else>
          <span class="caption__label">Olwen's brief</span>
          <p class="caption__text">
            <span v-if="captionTail.truncated" class="caption__ellipsis">… </span>{{ captionTail.text }}<span v-if="reading" class="cursor">▍</span>
          </p>
        </template>
      </div>
    </div>

    <div class="controls">
      <span class="controls__time">{{ new Date().toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' }) }}</span>
      <button v-if="reading" class="ctl" @click="stopSpeech">⏸ Stop</button>
      <button class="ctl ctl--exit" @click="close">Done</button>
    </div>

    <OlwenDismissFX v-if="dismissing" :center="dismissCenter" />
  </div>
</template>

<style scoped>
.brief { position: fixed; inset: 0; z-index: 62; display: grid; grid-template-columns: 1fr 1fr; align-items: center; opacity: 0; transition: opacity .5s ease; overflow: hidden; }
.brief.entered { opacity: 1; }
.brief__bg { position: absolute; inset: 0; z-index: -1; background: radial-gradient(ellipse at 70% 45%, #0A1419 0%, #02060A 70%); }

.stream { grid-column: 1; justify-self: center; width: min(460px, 86%); display: flex; flex-direction: column; gap: 11px; max-height: 78vh; overflow-y: auto; padding: 6px 4px; }
.stream::-webkit-scrollbar { width: 4px; }
.stream::-webkit-scrollbar-thumb { background: rgba(94,234,212,0.2); border-radius: 3px; }

.card {
  padding: 12px 14px; border-radius: 14px;
  border: 0.5px solid rgba(94,234,212,0.18);
  background: rgba(8, 30, 38, 0.55); backdrop-filter: blur(12px);
  display: flex; flex-direction: column; gap: 6px;
}
.card__tag { font-family: 'JetBrains Mono', monospace; font-size: 9px; letter-spacing: 1.6px; text-transform: uppercase; color: rgba(167,243,208,0.55); }
.card__row { display: flex; align-items: center; gap: 14px; }
.card__big { font-size: 30px; color: #ECFEFF; font-weight: 200; letter-spacing: 0.3px; }
.card__sub { display: flex; flex-direction: column; gap: 2px; font-size: 12px; color: rgba(220,252,245,0.7); }
.card__hi { font-family: 'JetBrains Mono', monospace; font-size: 10.5px; color: rgba(167,243,208,0.55); }

.card--cal { border-left: 3px solid #5EEAD4; }
.card--tasks { border-left: 3px solid #F87171; }
.card--inbox { border-left: 3px solid #67E8F9; }
.card--news { border-left: 3px solid #22D3EE; }
.card--weather { border-left: 3px solid #FBBF24; }

.lst { list-style: none; margin: 2px 0 0; padding: 0; display: flex; flex-direction: column; gap: 5px; }
.lst li { display: flex; align-items: center; gap: 8px; font-size: 12.5px; color: #DCFCF5; line-height: 1.35; }
.lst li strong { color: #ECFEFF; font-weight: 500; }
.lst__at { font-family: 'JetBrains Mono', monospace; font-size: 10.5px; color: #5EEAD4; width: 50px; flex-shrink: 0; }
.lst__dot { width: 5px; height: 5px; border-radius: 50%; background: rgba(167,243,208,0.4); flex-shrink: 0; }
.lst li.p-high .lst__dot { background: #F87171; box-shadow: 0 0 8px #F87171; }
.lst li.p-med  .lst__dot { background: #FBBF24; }
.lst__lbl { flex: 1; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-decoration: none; color: inherit; }
a.lst__lbl:hover { color: #ECFEFF; text-decoration: underline; }
.lst__tag { font-family: 'JetBrains Mono', monospace; font-size: 8.5px; letter-spacing: 1px; text-transform: uppercase; color: #22D3EE; border: 0.5px solid rgba(34,211,238,0.4); border-radius: 999px; padding: 1px 6px; }
.lst__ago { font-family: 'JetBrains Mono', monospace; font-size: 10px; color: rgba(167,243,208,0.4); }

.empty { font-size: 13px; color: rgba(167,243,208,0.55); margin: 20px 2px 0; }

/* card entrance — staggered fade-up using --d delay set inline */
.card-enter-active { transition: all .6s cubic-bezier(.22,.61,.36,1); transition-delay: var(--d, 0ms); }
.card-enter-from { opacity: 0; transform: translateX(-30px) translateY(8px); }

/* RIGHT entity */
.brief__entity { position: relative; grid-column: 2; justify-self: center; width: 360px; height: 360px; display: grid; place-items: center; cursor: pointer; transform: translateX(-50px) scale(0.9); opacity: 0; transition: transform .8s cubic-bezier(.22,.61,.36,1), opacity .8s ease, filter .35s ease; }
.brief.entered .brief__entity { transform: translateX(0) scale(1); opacity: 1; }
.brief__entity:hover { transform: translateX(0) scale(1.03); filter: drop-shadow(0 0 38px rgba(94,234,212,0.45)); }
.halo { position: absolute; inset: -8%; border-radius: 50%; pointer-events: none; background: radial-gradient(circle, rgba(94,234,212,0.18) 0%, rgba(94,234,212,0.06) 40%, transparent 65%); opacity: 0.35; transition: opacity .35s ease, transform .35s ease; }
.brief__entity:hover .halo { opacity: 1; transform: scale(1.08); }
.entityhint { position: absolute; top: -36px; left: 50%; transform: translate(-50%, 8px); font-family: 'JetBrains Mono', monospace; font-size: 9.5px; letter-spacing: 2px; text-transform: uppercase; color: #ECFEFF; padding: 5px 14px; border-radius: 999px; background: linear-gradient(180deg, rgba(8,51,68,0.85), rgba(2,6,10,0.85)); border: 0.5px solid rgba(94,234,212,0.5); opacity: 0; pointer-events: none; transition: opacity .3s ease, transform .3s ease; white-space: nowrap; }
.brief__entity:hover .entityhint { opacity: 1; transform: translate(-50%, 0); }

.caption { position: absolute; bottom: -48px; width: 95%; max-width: 480px; text-align: center; }
.caption__label { display: block; font-family: 'JetBrains Mono', monospace; font-size: 9px; letter-spacing: 2px; text-transform: uppercase; color: #5EEAD4; margin-bottom: 6px; }
.caption__text { margin: 0; font-size: 14px; line-height: 1.55; color: #ECFEFF; font-weight: 300; min-height: 1.5em; max-height: 5.5em; overflow: hidden; -webkit-mask-image: linear-gradient(to bottom, transparent 0%, #000 25%, #000 100%); }
.caption__ellipsis { color: rgba(167,243,208,0.5); }
.cursor { color: #5EEAD4; animation: blink 1s step-start infinite; margin-left: 2px; }
@keyframes blink { 50% { opacity: 0; } }

.prep { display: flex; gap: 7px; justify-content: center; }
.prep span { width: 8px; height: 8px; border-radius: 50%; background: #5EEAD4; box-shadow: 0 0 12px #5EEAD4; animation: bob 1.2s ease-in-out infinite; }
.prep span:nth-child(2) { animation-delay: .18s; }
.prep span:nth-child(3) { animation-delay: .36s; }
@keyframes bob { 0%,100% { transform: translateY(0) scale(0.85); opacity: 0.45; } 50% { transform: translateY(-8px) scale(1.15); opacity: 1; } }

/* dismiss absorb */
.brief__entity.dismissing { animation: absorb 0.95s cubic-bezier(.55,.05,.68,.19) forwards; }
@keyframes absorb {
  0%   { transform: translateX(0) scale(1) rotate(0deg); opacity: 1; filter: brightness(1); }
  30%  { transform: translateX(0) scale(1.22) rotate(8deg); opacity: 1; filter: brightness(1.7) drop-shadow(0 0 38px #5EEAD4); }
  70%  { transform: translateX(0) scale(0.55) rotate(-30deg); opacity: 0.8; filter: brightness(2.4) drop-shadow(0 0 60px #67E8F9); }
  100% { transform: translateX(0) scale(0.05) rotate(-90deg); opacity: 0; filter: brightness(3); }
}

.controls { position: absolute; bottom: 26px; left: 0; right: 0; display: flex; align-items: center; justify-content: center; gap: 16px; z-index: 4; }
.controls__time { font-family: 'JetBrains Mono', monospace; font-size: 10px; letter-spacing: 1.4px; color: rgba(167,243,208,0.45); }
.ctl { padding: 7px 16px; border-radius: 999px; cursor: pointer; border: 0.5px solid rgba(94,234,212,0.25); background: rgba(8,51,68,0.3); color: #A7F3D0; font-family: 'JetBrains Mono', monospace; font-size: 10px; letter-spacing: 1.5px; text-transform: uppercase; transition: all .2s ease; }
.ctl:hover { border-color: #5EEAD4; color: #ECFEFF; }
.ctl--exit { color: rgba(167,243,208,0.6); }

@media (max-width: 900px) { .brief { grid-template-columns: 1fr; } .brief__entity { width: 220px; height: 220px; } }
</style>
