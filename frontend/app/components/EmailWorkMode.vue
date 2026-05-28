<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import OlwenEntity from './OlwenEntity.vue'
import OlwenDismissFX from './OlwenDismissFX.vue'
import type { TriagedEmail } from '../composables/useEmail'

const props = defineProps<{ items: TriagedEmail[] }>()
const emit = defineEmits<{ close: [] }>()

const voice = useVoice()
const voiceOn = useState<boolean>('voice:on', () => true)
const voiceLang = useState<string>('voice:lang', () => 'en-US')

const entered = ref(false)
const index = ref(0)
const typed = ref('')
const phase = ref<'reaching' | 'reading' | 'summary'>('reaching')

const containerRef = ref<HTMLElement>()
const listRef = ref<HTMLElement>()

const visible = computed(() => props.items.slice(0, index.value + 1))
const entityState = computed(() => (phase.value === 'reaching' ? 'working' : 'speaking'))
const priorityColor: Record<string, string> = { high: '#F87171', med: '#FBBF24', low: '#5EEAD4' }

const PRIO = { high: 0, med: 1, low: 2 } as const
const startIndex = computed(() => {
  let best = 0, bestScore = 99
  props.items.forEach((e, i) => {
    const s = PRIO[(e.priority as 'high'|'med'|'low')] ?? 2
    if (s < bestScore) { bestScore = s; best = i }
  })
  return best
})
const startEmail = computed(() => props.items[startIndex.value] ?? props.items[0])

function shortFrom(s: string): string {
  const m = s.match(/^\s*"?([^"<]+?)"?\s*<.*>/)
  return (m ? m[1] : s).trim() || s
}
function shown(i: number): string {
  return i === index.value && phase.value !== 'summary'
    ? typed.value
    : props.items[i]?.suggestion ?? ''
}

/* ---------- drive Olwen's own tendril toward the active card ---------- */
const reachTarget = ref<{ x: number, y: number } | null>(null)
let rafM = 0
function measureLoop() {
  const list = listRef.value
  if (list) {
    const sel = phase.value === 'summary' ? '.card.start' : '.card.active'
    const el = list.querySelector(sel) as HTMLElement | null
    if (el) {
      const r = el.getBoundingClientRect()
      reachTarget.value = { x: r.right + 8, y: r.top + r.height / 2 }
    }
  }
  rafM = requestAnimationFrame(measureLoop)
}

/* ---------- choreography ---------- */
let typeTimer: ReturnType<typeof setInterval> | undefined
let reachTimer: ReturnType<typeof setTimeout> | undefined
let holdTimer: ReturnType<typeof setTimeout> | undefined
function clearTimers() {
  if (typeTimer) clearInterval(typeTimer)
  if (reachTimer) clearTimeout(reachTimer)
  if (holdTimer) clearTimeout(holdTimer)
}

function playCard(i: number) {
  clearTimers()
  index.value = i
  typed.value = ''
  phase.value = 'reaching'
  reachTimer = setTimeout(async () => {
    await nextTick()
    const active = listRef.value?.querySelector('.card.active') as HTMLElement | null
    active?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
    phase.value = 'reading'
    const text = props.items[i]?.suggestion ?? ''
    let n = 0
    if (voiceOn.value) {
      const spoken = `Email from ${shortFrom(props.items[i]?.sender || '')}. ${props.items[i]?.subject || ''}. ${text}`
      typeTimer = setInterval(() => {
        if (n < text.length) { n += 1; typed.value = text.slice(0, n) }
        else if (typeTimer) clearInterval(typeTimer)
      }, 42)
      voice.speak(spoken, voiceLang.value, {
        onEnd: () => {
          if (typeTimer) clearInterval(typeTimer)
          n = text.length; typed.value = text
          holdTimer = setTimeout(next, 1300)
        },
      })
    } else {
      typeTimer = setInterval(() => {
        n += 1
        typed.value = text.slice(0, n)
        if (n >= text.length) {
          if (typeTimer) clearInterval(typeTimer)
          holdTimer = setTimeout(next, 1800)
        }
      }, 48)
    }
  }, 750)
}

function next() {
  if (index.value < props.items.length - 1) playCard(index.value + 1)
  else showSummary()
}

async function showSummary() {
  clearTimers()
  phase.value = 'summary'
  index.value = props.items.length - 1
  await nextTick()
  const start = listRef.value?.querySelectorAll('.card')[startIndex.value] as HTMLElement | undefined
  start?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  if (voiceOn.value && startEmail.value) {
    voice.speak(
      `Start with this one — ${startEmail.value.subject}. ${startEmail.value.suggestion}`,
      voiceLang.value,
    )
  }
}

function skip() { voice.cancelSpeak(); next() }
const dismissing = ref(false)
const dismissCenter = ref({ x: 0, y: 0 })
function finish(ev?: Event) {
  if (dismissing.value) return
  clearTimers()
  voice.cancelSpeak()
  setTimeout(() => voice.cancelSpeak(), 120)
  const el = (ev?.currentTarget as HTMLElement) || (containerRef.value?.querySelector('.work__entity') as HTMLElement | null)
  if (el) {
    const r = el.getBoundingClientRect()
    dismissCenter.value = { x: r.left + r.width / 2, y: r.top + r.height / 2 }
  }
  dismissing.value = true
  setTimeout(() => { entered.value = false }, 380)
  setTimeout(() => emit('close'), 1000)
}

onMounted(() => {
  requestAnimationFrame(() => { entered.value = true })
  rafM = requestAnimationFrame(measureLoop)
  setTimeout(() => playCard(0), 900)
})
onBeforeUnmount(() => { clearTimers(); voice.cancelSpeak(); cancelAnimationFrame(rafM) })
</script>

<template>
  <div ref="containerRef" class="work" :class="{ entered }">
    <div class="work__bg" aria-hidden="true" />

    <!-- emails stack on the LEFT -->
    <div class="stage">
      <div ref="listRef" class="list">
        <TransitionGroup name="card">
          <div
            v-for="(e, i) in visible"
            :key="e.uid"
            class="card"
            :class="[`p-${e.priority}`, { active: i === index && phase !== 'summary', read: i < index, start: i === startIndex }]"
            :style="{ '--p': priorityColor[e.priority] || '#5EEAD4' }"
          >
            <div class="card__top">
              <span class="card__from">{{ shortFrom(e.sender) }}</span>
              <span v-if="i === startIndex" class="card__start">★ Start here</span>
              <span v-else class="card__prio" :style="{ color: priorityColor[e.priority] }">{{ e.priority.toUpperCase() }}</span>
            </div>
            <p class="card__subj">{{ e.subject }}</p>
            <p v-if="e.snippet" class="card__snip">{{ e.snippet.slice(0, 180) }}</p>
            <p class="card__sug">
              ✦ <span>{{ shown(i) }}</span><span v-if="i === index && phase === 'reading' && typed.length < (e.suggestion?.length || 0)" class="cursor">▍</span>
            </p>
          </div>
        </TransitionGroup>
      </div>
    </div>

    <!-- Olwen on the RIGHT — tap to return home -->
    <div
      class="work__entity"
      :class="{ dismissing }"
      data-olwen
      role="button"
      aria-label="Tap Olwen to return home"
      tabindex="0"
      @click="finish"
      @keyup.enter="finish"
    >
      <span class="halo" aria-hidden="true" />
      <span class="work__entityhint">↩ tap to return home</span>
      <OlwenEntity :state="entityState" :reach-target="reachTarget" />
      <div class="work__status">
        <span class="work__statusdot" />
        <template v-if="phase === 'summary'">Reply to “{{ startEmail?.subject }}”</template>
        <template v-else>Reading your inbox · {{ index + 1 }}/{{ items.length }}</template>
      </div>
    </div>

    <Transition name="banner">
      <div v-if="phase === 'summary' && startEmail" class="summary">
        <span class="summary__label">✦ Olwen says start with</span>
        <span class="summary__task">{{ startEmail.subject }}</span>
        <span class="summary__why">{{ startEmail.suggestion }}</span>
      </div>
    </Transition>

    <div class="controls">
      <div class="dots">
        <span v-for="(e, i) in items" :key="e.uid" class="dot" :class="{ on: i === index && phase !== 'summary', past: i < index }" />
      </div>
      <div class="btns">
        <button v-if="phase !== 'summary'" class="ctl" @click="skip">Skip ›</button>
        <button class="ctl ctl--exit" @click="finish">{{ phase === 'summary' ? 'Done' : 'Exit' }}</button>
      </div>
    </div>

    <OlwenDismissFX v-if="dismissing" :center="dismissCenter" />
  </div>
</template>

<style scoped>
.work { position: fixed; inset: 0; z-index: 60; display: grid; grid-template-columns: 1fr 1fr; align-items: center; opacity: 0; transition: opacity .5s ease; overflow: hidden; }
.work.entered { opacity: 1; }
.work__bg { position: absolute; inset: 0; z-index: -1; background: radial-gradient(ellipse at 70% 45%, #0A1419 0%, #02060A 70%); }

.work__entity {
  position: relative; grid-column: 2; justify-self: center;
  width: 340px; height: 340px; display: grid; place-items: center;
  transform: translateX(-50px) scale(0.9); opacity: 0;
  transition: transform .8s cubic-bezier(.22,.61,.36,1), opacity .8s ease;
}
.work.entered .work__entity { transform: translateX(0) scale(1); opacity: 1; }
.work__entity { position: relative; transition: transform .35s cubic-bezier(.22,.61,.36,1), filter .35s ease; }
.work__entity:hover { transform: translateX(0) scale(1.04); filter: drop-shadow(0 0 36px rgba(94,234,212,0.35)); }
.work__entity:focus-visible { outline: none; filter: drop-shadow(0 0 42px rgba(167,243,208,0.55)); }
.work__entity:active { transform: translateX(0) scale(0.97); transition-duration: .12s; }

.halo {
  position: absolute; inset: -8%; border-radius: 50%; pointer-events: none;
  background: radial-gradient(circle, rgba(94,234,212,0.18) 0%, rgba(94,234,212,0.06) 40%, transparent 65%);
  opacity: 0.35; transition: opacity .35s ease, transform .35s ease;
}
.work__entity:hover .halo,
.work__entity:focus-visible .halo { opacity: 1; transform: scale(1.08); }

.work__entity:hover .work__entityhint,
.work__entity:focus-visible .work__entityhint { opacity: 1; transform: translate(-50%, 0); }
.work__entityhint {
  position: absolute; top: -36px; left: 50%; transform: translate(-50%, 8px);
  font-family: 'JetBrains Mono', monospace; font-size: 9.5px; letter-spacing: 2px; text-transform: uppercase;
  color: #ECFEFF; padding: 5px 14px; border-radius: 999px;
  background: linear-gradient(180deg, rgba(8,51,68,0.85), rgba(2,6,10,0.85));
  border: 0.5px solid rgba(94,234,212,0.5);
  box-shadow: 0 0 22px rgba(94,234,212,0.25), inset 0 0 18px rgba(94,234,212,0.08);
  opacity: 0; pointer-events: none;
  transition: opacity .3s ease, transform .3s ease;
  white-space: nowrap; z-index: 5;
  animation: hintbreath 2.4s ease-in-out infinite;
}
@keyframes hintbreath { 0%,100% { box-shadow: 0 0 18px rgba(94,234,212,0.2); } 50% { box-shadow: 0 0 28px rgba(94,234,212,0.45); } }

.shock, .burst { position: absolute; left: 50%; top: 50%; pointer-events: none; opacity: 0; }
.shock { width: 70%; height: 70%; transform: translate(-50%, -50%); border-radius: 50%; border: 1.5px solid #5EEAD4; box-shadow: 0 0 30px #5EEAD4; }
.burst { width: 6px; height: 6px; border-radius: 50%; background: #A7F3D0; box-shadow: 0 0 10px #5EEAD4, 0 0 24px rgba(94,234,212,0.7); transform: translate(-50%, -50%); }
.work__entity.dismissing .shock        { animation: shock 0.95s cubic-bezier(.18,.6,.32,1) forwards; }
.work__entity.dismissing .shock--delay { animation: shock 0.95s cubic-bezier(.18,.6,.32,1) .14s forwards; opacity: 0; }
.work__entity.dismissing .burst        { animation: burst 0.9s cubic-bezier(.18,.6,.32,1) forwards; }
.work__entity.dismissing { animation: absorb 0.95s cubic-bezier(.55,.05,.68,.19) forwards; }

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
  .work__entity, .aura, .shock, .burst { animation: none !important; transition: none !important; }
  .work__entity.dismissing { opacity: 0; transition: opacity .3s ease !important; }
}
.work__status { position: absolute; bottom: 0%; display: inline-flex; align-items: center; gap: 8px; max-width: 90%; font-family: 'JetBrains Mono', monospace; font-size: 10px; letter-spacing: 1.4px; text-transform: uppercase; color: #A7F3D0; white-space: nowrap; }
.work__statusdot { width: 6px; height: 6px; border-radius: 50%; background: #5EEAD4; box-shadow: 0 0 8px #5EEAD4; flex-shrink: 0; }

.stage { grid-column: 1; justify-self: center; width: min(460px, 86%); z-index: 3; }
.list { display: flex; flex-direction: column; gap: 10px; max-height: 76vh; overflow-y: auto; padding: 4px; }
.list::-webkit-scrollbar { width: 4px; }
.list::-webkit-scrollbar-thumb { background: rgba(94,234,212,0.2); border-radius: 3px; }

.card { border-radius: 14px; padding: 14px 16px; border: 0.5px solid rgba(94,234,212,0.14); border-left: 3px solid var(--p); background: rgba(8, 30, 38, 0.5); backdrop-filter: blur(12px); transition: opacity .4s ease, box-shadow .4s ease, border-color .4s ease; }
.card.active { border-color: rgba(94,234,212,0.35); background: rgba(8, 30, 38, 0.7); box-shadow: 0 14px 44px rgba(0,0,0,0.4), 0 0 30px rgba(94,234,212,0.12); }
.card.read { opacity: 0.5; }
.work .card.start { box-shadow: 0 0 0 0.5px rgba(94,234,212,0.4), 0 0 24px rgba(94,234,212,0.15); }
.card__top { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.card__from { font-size: 13px; color: #ECFEFF; font-weight: 500; }
.card__prio { font-family: 'JetBrains Mono', monospace; font-size: 8px; letter-spacing: 1.2px; }
.card__start { font-family: 'JetBrains Mono', monospace; font-size: 8px; letter-spacing: 1px; text-transform: uppercase; color: #02060A; background: #5EEAD4; border-radius: 999px; padding: 2px 8px; }
.card__subj { margin: 5px 0 0; font-size: 14.5px; font-weight: 300; color: #ECFEFF; line-height: 1.3; }
.card__snip { margin: 5px 0 0; font-size: 11.5px; color: rgba(167,243,208,0.45); line-height: 1.4; }
.card__sug { margin: 8px 0 0; font-size: 12.5px; line-height: 1.5; color: #A7F3D0; display: flex; gap: 6px; }
.cursor { color: #5EEAD4; animation: blink 1s step-start infinite; }
@keyframes blink { 50% { opacity: 0; } }
.card-enter-active { transition: all .55s cubic-bezier(.22,.61,.36,1); }
.card-enter-from { opacity: 0; transform: translateX(80px) scale(0.94); }

.summary { position: absolute; bottom: 92px; left: 0; right: 0; z-index: 4; display: flex; flex-direction: column; align-items: center; gap: 5px; text-align: center; padding: 0 24px; }
.summary__label { font-family: 'JetBrains Mono', monospace; font-size: 9px; letter-spacing: 1.8px; text-transform: uppercase; color: #5EEAD4; }
.summary__task { font-size: 17px; font-weight: 300; color: #ECFEFF; max-width: 560px; }
.summary__why { font-size: 12.5px; color: rgba(167,243,208,0.6); max-width: 520px; }
.banner-enter-active { transition: all .5s ease; }
.banner-enter-from { opacity: 0; transform: translateY(12px); }

.controls { position: absolute; bottom: 26px; left: 0; right: 0; z-index: 4; display: flex; flex-direction: column; align-items: center; gap: 14px; }
.dots { display: flex; gap: 7px; }
.dot { width: 6px; height: 6px; border-radius: 50%; background: rgba(167,243,208,0.25); transition: all .3s ease; }
.dot.past { background: rgba(94,234,212,0.5); }
.dot.on { background: #5EEAD4; box-shadow: 0 0 8px #5EEAD4; width: 20px; border-radius: 3px; }
.btns { display: flex; gap: 10px; }
.ctl { padding: 7px 16px; border-radius: 999px; cursor: pointer; border: 0.5px solid rgba(94,234,212,0.25); background: rgba(8,51,68,0.3); color: #A7F3D0; font-family: 'JetBrains Mono', monospace; font-size: 10px; letter-spacing: 1.5px; text-transform: uppercase; transition: all .2s ease; }
.ctl:hover { border-color: #5EEAD4; color: #ECFEFF; }
.ctl--exit { color: rgba(167,243,208,0.5); }

@media (max-width: 900px) { .work { grid-template-columns: 1fr; } .work__entity { width: 200px; height: 200px; } }
</style>
