<script setup lang="ts">
/* News brief — Olwen reads the day's curated stories with his commentary.
   Same cinematic language as MorningBrief but news-only and cyan-keyed. */
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import OlwenEntity from './OlwenEntity.vue'
import OlwenDismissFX from './OlwenDismissFX.vue'
import type { NewsItem } from '../composables/useNews'

type Item = NewsItem & { why: string }

const props = defineProps<{ narrative: string; items: Item[]; topics: string[] }>()
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

const entityState = computed(() => (reading.value ? 'speaking' : preparing.value ? 'thinking' : 'idle'))

const captionTail = computed(() => {
  const t = typed.value
  if (t.length <= 280) return { text: t, truncated: false }
  return { text: t.slice(t.length - 280), truncated: true }
})

const title = computed(() => {
  if (!props.topics.length) return 'News'
  return props.topics.slice(0, 3).map(t => t === 'ai' ? 'AI' : t[0].toUpperCase() + t.slice(1)).join(' · ')
})

let fallbackTimer: ReturnType<typeof setInterval> | undefined
function speakNarrative(text: string) {
  if (!text) { preparing.value = false; return }
  reading.value = true; typed.value = ''; preparing.value = true
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
  reading.value = false; preparing.value = false
}

function close() {
  if (dismissing.value) return
  stopSpeech()
  const el = entityRef.value
  if (el) {
    const r = el.getBoundingClientRect()
    dismissCenter.value = { x: r.left + r.width / 2, y: r.top + r.height / 2 }
  }
  dismissing.value = true
  setTimeout(() => { entered.value = false }, 380)
  setTimeout(() => emit('close'), 1000)
}

function ago(iso: string): string {
  if (!iso) return ''
  const t = new Date(iso).getTime(); if (!isFinite(t)) return ''
  const s = Math.max(0, (Date.now() - t) / 1000)
  if (s < 3600) return `${Math.floor(s / 60)}m`
  if (s < 86400) return `${Math.floor(s / 3600)}h`
  return `${Math.floor(s / 86400)}d`
}

onMounted(async () => {
  requestAnimationFrame(() => { entered.value = true })
  await nextTick()
  setTimeout(() => speakNarrative(props.narrative), 750)
})
onBeforeUnmount(() => { stopSpeech() })
</script>

<template>
  <div class="brief" :class="{ entered }">
    <div class="brief__bg" aria-hidden="true" />

    <!-- LEFT: curated story cards with Olwen's "why this matters" line -->
    <div class="stream">
      <span class="streamhead">{{ title }}</span>
      <Transition v-for="(n, i) in items" :key="i" name="card" appear>
        <a
          class="card"
          :style="{ '--d': `${i * 120}ms` }"
          :href="n.url" target="_blank" rel="noopener"
        >
          <div class="card__top">
            <span class="card__tag">{{ n.tag }}</span>
            <span class="card__ago">{{ ago(n.published) }}</span>
          </div>
          <div class="card__title">{{ n.title }}</div>
          <div class="card__src">{{ n.source }}</div>
          <div v-if="n.why" class="card__why">✦ {{ n.why }}</div>
        </a>
      </Transition>
      <p v-if="!items.length" class="empty">No fresh stories on your topics.</p>
    </div>

    <!-- RIGHT: Olwen + spoken narrative -->
    <div
      ref="entityRef"
      class="brief__entity"
      :class="{ dismissing }"
      data-olwen role="button"
      aria-label="Tap Olwen to dismiss"
      tabindex="0"
      @click="close" @keyup.enter="close"
    >
      <span class="halo" aria-hidden="true" />
      <span class="entityhint">↩ tap to return home</span>
      <OlwenEntity :state="entityState" />
      <div class="caption">
        <div v-if="preparing && !typed" class="prep"><span /><span /><span /></div>
        <template v-else>
          <span class="caption__label">Olwen reads the news</span>
          <p class="caption__text">
            <span v-if="captionTail.truncated" class="caption__ellipsis">… </span>{{ captionTail.text }}<span v-if="reading" class="cursor">▍</span>
          </p>
        </template>
      </div>
    </div>

    <div class="controls">
      <button v-if="reading" class="ctl" @click="stopSpeech">⏸ Stop</button>
      <button class="ctl ctl--exit" @click="close">Done</button>
    </div>

    <OlwenDismissFX v-if="dismissing" :center="dismissCenter" />
  </div>
</template>

<style scoped>
.brief { position: fixed; inset: 0; z-index: 62; display: grid; grid-template-columns: 1fr 1fr; align-items: center; opacity: 0; transition: opacity .5s ease; overflow: hidden; }
.brief.entered { opacity: 1; }
.brief__bg { position: absolute; inset: 0; z-index: -1; background: radial-gradient(ellipse at 70% 45%, var(--bg) 0%, var(--bg) 70%); }

.stream { grid-column: 1; justify-self: center; width: min(480px, 86%); display: flex; flex-direction: column; gap: 12px; max-height: 78vh; overflow-y: auto; padding: 6px 4px; }
.stream::-webkit-scrollbar { width: 4px; }
.stream::-webkit-scrollbar-thumb { background: rgba(34,211,238,0.25); border-radius: 3px; }
.streamhead { font-family: 'JetBrains Mono', monospace; font-size: 10px; letter-spacing: 1.8px; text-transform: uppercase; color: #22D3EE; padding: 4px 2px; }

.card {
  padding: 14px 16px; border-radius: 14px;
  border: 0.5px solid rgba(34,211,238,0.2); border-left: 3px solid #22D3EE;
  background: var(--surface-2); backdrop-filter: blur(12px);
  text-decoration: none; color: inherit;
  display: flex; flex-direction: column; gap: 6px;
  transition: all .2s ease;
}
.card:hover { border-color: var(--accent); background: rgba(8,30,38,0.7); transform: translateX(2px); box-shadow: 0 8px 28px rgba(0,0,0,0.4), 0 0 22px rgba(34,211,238,0.12); }
.card__top { display: flex; align-items: center; justify-content: space-between; }
.card__tag { font-family: 'JetBrains Mono', monospace; font-size: 8.5px; letter-spacing: 1.2px; text-transform: uppercase; color: #22D3EE; border: 0.5px solid rgba(34,211,238,0.45); border-radius: 999px; padding: 2px 7px; }
.card__ago { font-family: 'JetBrains Mono', monospace; font-size: 10px; color: var(--text-muted); }
.card__title { font-size: 14px; color: var(--text-strong); line-height: 1.35; font-weight: 400; }
.card__src { font-family: 'JetBrains Mono', monospace; font-size: 10px; color: var(--text-muted); }
.card__why { margin-top: 4px; padding-top: 8px; border-top: 0.5px solid var(--border); font-size: 12px; line-height: 1.5; color: var(--accent-2); }

.card-enter-active { transition: all .55s cubic-bezier(.22,.61,.36,1); transition-delay: var(--d, 0ms); }
.card-enter-from { opacity: 0; transform: translateX(-30px) translateY(8px); }

.empty { font-size: 13px; color: var(--text-muted); margin: 18px 2px 0; }

/* entity */
.brief__entity { position: relative; grid-column: 2; justify-self: center; width: 360px; height: 360px; display: grid; place-items: center; cursor: pointer; transform: translateX(-50px) scale(0.9); opacity: 0; transition: transform .8s cubic-bezier(.22,.61,.36,1), opacity .8s ease, filter .35s ease; }
.brief.entered .brief__entity { transform: translateX(0) scale(1); opacity: 1; }
.brief__entity:hover { transform: translateX(0) scale(1.03); filter: drop-shadow(0 0 38px rgba(34,211,238,0.45)); }
.halo { position: absolute; inset: -8%; border-radius: 50%; pointer-events: none; background: radial-gradient(circle, rgba(34,211,238,0.18) 0%, rgba(34,211,238,0.06) 40%, transparent 65%); opacity: 0.35; transition: opacity .35s ease, transform .35s ease; }
.brief__entity:hover .halo { opacity: 1; transform: scale(1.08); }
.entityhint { position: absolute; top: -36px; left: 50%; transform: translate(-50%, 8px); font-family: 'JetBrains Mono', monospace; font-size: 9.5px; letter-spacing: 2px; text-transform: uppercase; color: var(--text-strong); padding: 5px 14px; border-radius: 999px; background: linear-gradient(180deg, var(--surface-2), color-mix(in srgb, var(--bg) 85%, transparent)); border: 0.5px solid rgba(34,211,238,0.5); opacity: 0; pointer-events: none; transition: opacity .3s ease, transform .3s ease; white-space: nowrap; }
.brief__entity:hover .entityhint { opacity: 1; transform: translate(-50%, 0); }

.caption { position: absolute; bottom: -48px; width: 95%; max-width: 480px; text-align: center; }
.caption__label { display: block; font-family: 'JetBrains Mono', monospace; font-size: 9px; letter-spacing: 2px; text-transform: uppercase; color: #22D3EE; margin-bottom: 6px; }
.caption__text { margin: 0; font-size: 14px; line-height: 1.55; color: var(--text); font-weight: 300; min-height: 1.5em; max-height: 5.5em; overflow: hidden; -webkit-mask-image: linear-gradient(to bottom, transparent 0%, #000 25%, #000 100%); }
.caption__ellipsis { color: var(--text-muted); }
.cursor { color: #22D3EE; animation: blink 1s step-start infinite; margin-left: 2px; }
@keyframes blink { 50% { opacity: 0; } }

.prep { display: flex; gap: 7px; justify-content: center; }
.prep span { width: 8px; height: 8px; border-radius: 50%; background: #22D3EE; box-shadow: 0 0 12px #22D3EE; animation: bob 1.2s ease-in-out infinite; }
.prep span:nth-child(2) { animation-delay: .18s; }
.prep span:nth-child(3) { animation-delay: .36s; }
@keyframes bob { 0%,100% { transform: translateY(0) scale(0.85); opacity: 0.45; } 50% { transform: translateY(-8px) scale(1.15); opacity: 1; } }

.brief__entity.dismissing { animation: absorb 0.95s cubic-bezier(.55,.05,.68,.19) forwards; }
@keyframes absorb {
  0%   { transform: translateX(0) scale(1) rotate(0deg); opacity: 1; }
  30%  { transform: translateX(0) scale(1.22) rotate(8deg); filter: brightness(1.7) drop-shadow(0 0 38px #22D3EE); }
  100% { transform: translateX(0) scale(0.05) rotate(-90deg); opacity: 0; filter: brightness(3); }
}

.controls { position: absolute; bottom: 26px; left: 0; right: 0; display: flex; justify-content: center; gap: 16px; z-index: 4; }
.ctl { padding: 7px 16px; border-radius: 999px; cursor: pointer; border: 0.5px solid rgba(34,211,238,0.3); background: var(--surface-2); color: var(--accent-2); font-family: 'JetBrains Mono', monospace; font-size: 10px; letter-spacing: 1.5px; text-transform: uppercase; }
.ctl:hover { border-color: #22D3EE; color: var(--text-strong); }

@media (max-width: 900px) { .brief { grid-template-columns: 1fr; } .brief__entity { width: 220px; height: 220px; } }
</style>
