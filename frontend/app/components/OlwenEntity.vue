<!--
  OLWEN ENTITY - FINAL COMPONENT

  States: 'idle' | 'listening' | 'thinking' | 'speaking' | 'working'

  DO NOT modify the SVG structure or animations.
  This is the final design - replace any existing entity with this.
-->

<template>
  <div
    class="olwen-entity-wrapper"
    :class="{ receiving }"
    :style="{ '--recv': recvColor }"
  >
    <svg
      ref="svgRef"
      width="100%"
      viewBox="0 0 400 460"
      xmlns="http://www.w3.org/2000/svg"
      class="olwen-entity"
      :class="[`state-${state}`, { receiving }]"
      role="img"
      aria-label="Olwen entity"
    >
      <defs>
        <!-- Body gradient: bioluminescent translucent core -->
        <radialGradient id="olwen-core-body" cx="50%" cy="45%" r="55%">
          <stop offset="0%" stop-color="#A7F3D0" stop-opacity="1"/>
          <stop offset="15%" stop-color="#5EEAD4" stop-opacity="0.95"/>
          <stop offset="40%" stop-color="#06B6D4" stop-opacity="0.8"/>
          <stop offset="70%" stop-color="#0E7490" stop-opacity="0.5"/>
          <stop offset="100%" stop-color="#083344" stop-opacity="0"/>
        </radialGradient>

        <!-- Inner translucent glow -->
        <radialGradient id="olwen-core-inner" cx="40%" cy="35%" r="50%">
          <stop offset="0%" stop-color="#FFFFFF" stop-opacity="0.9"/>
          <stop offset="25%" stop-color="#67E8F9" stop-opacity="0.6"/>
          <stop offset="60%" stop-color="#0891B2" stop-opacity="0.3"/>
          <stop offset="100%" stop-color="#164E63" stop-opacity="0"/>
        </radialGradient>

        <!-- Halo atmosphere -->
        <radialGradient id="olwen-halo" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stop-color="#5EEAD4" stop-opacity="0.35"/>
          <stop offset="50%" stop-color="#22D3EE" stop-opacity="0.1"/>
          <stop offset="100%" stop-color="#06B6D4" stop-opacity="0"/>
        </radialGradient>

        <!-- Mist clouds -->
        <radialGradient id="olwen-mist" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stop-color="#5EEAD4" stop-opacity="0.25"/>
          <stop offset="100%" stop-color="#5EEAD4" stop-opacity="0"/>
        </radialGradient>

        <!-- Tendril gradient: bright at base, transparent at tip -->
        <linearGradient id="olwen-tendril" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#67E8F9" stop-opacity="0.9"/>
          <stop offset="60%" stop-color="#22D3EE" stop-opacity="0.5"/>
          <stop offset="100%" stop-color="#0E7490" stop-opacity="0"/>
        </linearGradient>

        <!-- Bright tendril highlight -->
        <linearGradient id="olwen-tendril-glow" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#A7F3D0" stop-opacity="1"/>
          <stop offset="100%" stop-color="#5EEAD4" stop-opacity="0"/>
        </linearGradient>

        <!-- Organic blur for body softness -->
        <filter id="olwen-organic-blur">
          <feGaussianBlur stdDeviation="0.8"/>
        </filter>

        <!-- Soft glow filter for tendrils -->
        <filter id="olwen-soft-glow" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="4"/>
          <feComposite in="SourceGraphic" operator="over"/>
        </filter>
      </defs>

      <!-- ATMOSPHERIC MIST CLOUDS -->
      <g class="mist-group">
        <ellipse class="mist-cloud mist-1" cx="130" cy="350" rx="100" ry="40" fill="url(#olwen-mist)"/>
        <ellipse class="mist-cloud mist-2" cx="290" cy="320" rx="90" ry="35" fill="url(#olwen-mist)"/>
        <ellipse class="mist-cloud mist-3" cx="200" cy="410" rx="140" ry="30" fill="url(#olwen-mist)"/>
      </g>

      <!-- BACKGROUND STARS -->
      <g class="stars">
        <circle cx="80" cy="100" r="0.6" fill="#A7F3D0" opacity="0.7"/>
        <circle cx="320" cy="80" r="0.8" fill="#67E8F9" opacity="0.6"/>
        <circle cx="50" cy="180" r="0.5" fill="#fff" opacity="0.5"/>
        <circle cx="360" cy="160" r="0.7" fill="#A7F3D0" opacity="0.65"/>
        <circle cx="30" cy="280" r="0.6" fill="#67E8F9" opacity="0.6"/>
        <circle cx="375" cy="290" r="0.5" fill="#fff" opacity="0.5"/>
        <circle cx="100" cy="60" r="0.4" fill="#A7F3D0" opacity="0.5"/>
        <circle cx="280" cy="50" r="0.5" fill="#67E8F9" opacity="0.55"/>
        <circle cx="370" cy="350" r="0.6" fill="#A7F3D0" opacity="0.6"/>
        <circle cx="20" cy="380" r="0.5" fill="#fff" opacity="0.5"/>
      </g>

      <!-- 7 TENDRILS IN DIFFERENT DIRECTIONS -->
      <g class="tendrils" style="filter: url(#olwen-soft-glow);">
        <!-- Down-left -->
        <path
          class="tendril tendril-1"
          d="M 200 200 Q 180 240 165 290 Q 155 340 170 380"
          fill="none"
          stroke="url(#olwen-tendril)"
          stroke-width="6"
          stroke-linecap="round"
          opacity="0.85"
        />
        <!-- Down-right -->
        <path
          class="tendril tendril-2"
          d="M 200 200 Q 230 230 250 280 Q 265 330 245 380"
          fill="none"
          stroke="url(#olwen-tendril)"
          stroke-width="5"
          stroke-linecap="round"
          opacity="0.8"
        />
        <!-- Far left, going sideways -->
        <path
          class="tendril tendril-3"
          d="M 200 200 Q 160 220 130 250 Q 100 285 90 330"
          fill="none"
          stroke="url(#olwen-tendril)"
          stroke-width="4"
          stroke-linecap="round"
          opacity="0.7"
        />
        <!-- Far right, going sideways -->
        <path
          class="tendril tendril-4"
          d="M 200 200 Q 245 215 280 240 Q 320 270 335 310"
          fill="none"
          stroke="url(#olwen-tendril)"
          stroke-width="4"
          stroke-linecap="round"
          opacity="0.7"
        />
        <!-- Center down, thickest -->
        <path
          class="tendril tendril-5"
          d="M 200 200 Q 200 250 195 300 Q 200 350 210 395"
          fill="none"
          stroke="url(#olwen-tendril)"
          stroke-width="7"
          stroke-linecap="round"
          opacity="0.9"
        />
        <!-- HORIZONTAL LEFT (important - tendrils in all directions) -->
        <path
          class="tendril tendril-6"
          d="M 200 200 Q 150 195 105 200 Q 60 210 35 235"
          fill="none"
          stroke="url(#olwen-tendril)"
          stroke-width="3.5"
          stroke-linecap="round"
          opacity="0.6"
        />
        <!-- HORIZONTAL RIGHT -->
        <path
          class="tendril tendril-7"
          d="M 200 200 Q 255 198 305 205 Q 350 215 380 235"
          fill="none"
          stroke="url(#olwen-tendril)"
          stroke-width="3.5"
          stroke-linecap="round"
          opacity="0.6"
        />
      </g>

      <!-- TENDRIL HIGHLIGHTS (bright streaks for depth) -->
      <g class="tendril-highlights" style="mix-blend-mode: screen;">
        <path
          class="tendril-h tendril-h-1"
          d="M 200 200 Q 180 240 165 290 Q 155 340 170 380"
          fill="none"
          stroke="url(#olwen-tendril-glow)"
          stroke-width="1.5"
          stroke-linecap="round"
        />
        <path
          class="tendril-h tendril-h-5"
          d="M 200 200 Q 200 250 195 300 Q 200 350 210 395"
          fill="none"
          stroke="url(#olwen-tendril-glow)"
          stroke-width="1.5"
          stroke-linecap="round"
        />
      </g>

      <!-- HALO -->
      <circle
        class="halo"
        cx="200"
        cy="195"
        r="120"
        fill="url(#olwen-halo)"
      />

      <!-- BODY CORE (ASYMMETRIC ORGANIC SHAPE - NOT A CIRCLE!) -->
      <g class="body-core">
        <!-- Outer body with organic blur -->
        <g filter="url(#olwen-organic-blur)">
          <path
            d="M 200 110
               C 240 108, 270 130, 280 165
               C 295 200, 285 235, 255 255
               C 230 275, 195 280, 165 270
               C 130 255, 115 220, 120 185
               C 125 145, 160 112, 200 110 Z"
            fill="url(#olwen-core-body)"
            opacity="0.92"
          />
        </g>

        <!-- Inner translucent layer -->
        <path
          d="M 200 130
             C 230 128, 252 145, 258 175
             C 265 200, 255 225, 230 240
             C 210 252, 185 252, 165 240
             C 145 225, 138 200, 145 175
             C 152 150, 175 132, 200 130 Z"
          fill="url(#olwen-core-inner)"
          opacity="0.7"
        />

        <!-- Internal flow patterns (suggests organs/life inside) -->
        <g class="inner-flow">
          <ellipse cx="195" cy="175" rx="22" ry="14" fill="#fff" opacity="0.18"
            transform="rotate(-20 195 175)"/>
          <ellipse cx="218" cy="210" rx="14" ry="9" fill="#A7F3D0" opacity="0.3"
            transform="rotate(40 218 210)"/>
          <ellipse cx="180" cy="215" rx="10" ry="6" fill="#67E8F9" opacity="0.35"/>
        </g>

        <!-- Surface highlights for translucency -->
        <ellipse cx="185" cy="165" rx="14" ry="8" fill="#fff" opacity="0.35"
          transform="rotate(-25 185 165)"/>
        <ellipse cx="180" cy="160" rx="5" ry="3" fill="#fff" opacity="0.85"
          transform="rotate(-25 180 160)"/>
      </g>

      <!-- LIGHT MOTES (drifting particles) -->
      <g class="motes" style="mix-blend-mode: screen;">
        <circle class="mote mote-1" cx="170" cy="160" r="1.2" fill="#A7F3D0"/>
        <circle class="mote mote-2" cx="230" cy="180" r="1" fill="#67E8F9"/>
        <circle class="mote mote-3" cx="190" cy="220" r="1.3" fill="#A7F3D0"/>
        <circle class="mote mote-4" cx="220" cy="200" r="1" fill="#5EEAD4"/>
        <circle class="mote mote-5" cx="160" cy="190" r="0.8" fill="#fff"/>
        <circle class="mote mote-6" cx="240" cy="210" r="1.1" fill="#A7F3D0"/>
      </g>

      <!-- REACHING TENDRIL: one of Olwen's own arms, extended to a target -->
      <g v-if="reachD" style="filter: url(#olwen-soft-glow);">
        <path :d="reachD" class="reach-tendril" fill="none" stroke="url(#olwen-tendril)" stroke-width="7" stroke-linecap="round"/>
        <path :d="reachD" class="reach-tendril-core" fill="none" stroke="#A7F3D0" stroke-width="2.5" stroke-linecap="round"/>
      </g>

      <!-- RECEIVE REACTION: one-shot ripple of recognition when a notification arrives. -->
      <!-- Layered ON TOP; separate elements so the body/tendril/state animations are untouched. -->
      <g v-if="receiving" class="recv-group" aria-hidden="true">
        <!-- Soft bloom flash over the core (does NOT touch .body-core's own animation) -->
        <circle class="recv-bloom" cx="200" cy="195" r="70" fill="var(--recv, #5EEAD4)"/>
        <!-- Expanding rings emanating from the core center -->
        <circle class="recv-ring recv-ring-1" cx="200" cy="195" r="60" fill="none"
          stroke="var(--recv, #5EEAD4)" stroke-width="3"/>
        <circle class="recv-ring recv-ring-2" cx="200" cy="195" r="60" fill="none"
          stroke="var(--recv, #5EEAD4)" stroke-width="2"/>
      </g>
    </svg>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = withDefaults(defineProps<{
  state?: 'idle' | 'listening' | 'thinking' | 'speaking' | 'working'
  // screen-space point (clientX/clientY) for a tendril to reach toward; null = retract
  reachTarget?: { x: number, y: number } | null
  // monotonically increasing counter — bumps each time a notification arrives
  pulse?: number
  // the channel the notification arrived on
  pulseKind?: string
}>(), {
  pulse: 0,
  pulseKind: '',
})

const svgRef = ref<SVGSVGElement>()
const reachD = ref('')
let raf = 0
let phase = 0
let lastT = 0

// --- "receive" reaction: a one-shot ripple of recognition on incoming notifications ---
const receiving = ref(false)
const recvColor = ref('var(--accent, #5EEAD4)')
let recvTimer: ReturnType<typeof setTimeout> | null = null

function kindColor(kind: string): string {
  switch (kind) {
    case 'telegram': return '#34B7F1'
    case 'whatsapp': return '#25D366'
    case 'email':    return '#FBBF24'
    default:         return 'var(--accent, #5EEAD4)'
  }
}

watch(() => props.pulse, (n, o) => {
  // only react when the counter genuinely increases (a new arrival)
  if ((n ?? 0) <= (o ?? 0)) return
  recvColor.value = kindColor(props.pulseKind || '')
  // reset any in-flight reaction so rapid arrivals re-trigger cleanly
  if (recvTimer) clearTimeout(recvTimer)
  receiving.value = false
  // force a fresh paint cycle so the one-shot animations restart
  requestAnimationFrame(() => {
    receiving.value = true
    recvTimer = setTimeout(() => {
      receiving.value = false
      recvTimer = null
    }, 1100)
  })
})

// the tendrils all originate around (200, 200) in the SVG's own coordinates
const ORIGIN = { x: 200, y: 202 }

function toLocal(clientX: number, clientY: number): { x: number, y: number } | null {
  const svg = svgRef.value
  if (!svg || typeof svg.getScreenCTM !== 'function') return null
  const m = svg.getScreenCTM()
  if (!m) return null
  const pt = svg.createSVGPoint()
  pt.x = clientX
  pt.y = clientY
  const p = pt.matrixTransform(m.inverse())
  return { x: p.x, y: p.y }
}

function buildReach(ex: number, ey: number, ph: number): string {
  const sx = ORIGIN.x, sy = ORIGIN.y
  const dx = ex - sx, dy = ey - sy
  const len = Math.hypot(dx, dy) || 1
  const px = -dy / len, py = dx / len // perpendicular
  const N = 26
  const pts: string[] = []
  for (let i = 0; i < N; i++) {
    const f = i / (N - 1)
    const env = Math.sin(f * Math.PI) // 0 at ends, 1 mid
    const wave = Math.sin(f * Math.PI * 3 - ph) * 16 * env
    const droop = env * 20
    const cx = sx + dx * f + px * wave
    const cy = sy + dy * f + py * wave + droop
    pts.push(`${cx.toFixed(1)} ${cy.toFixed(1)}`)
  }
  return `M ${pts.join(' L ')}`
}

function frame(t: number) {
  const dt = lastT ? Math.min(0.05, (t - lastT) / 1000) : 0
  lastT = t
  phase += dt * 5
  const tgt = props.reachTarget
  if (tgt) {
    const local = toLocal(tgt.x, tgt.y)
    reachD.value = local ? buildReach(local.x, local.y, phase) : ''
  } else if (reachD.value) {
    reachD.value = ''
  }
  raf = requestAnimationFrame(frame)
}

onMounted(() => { raf = requestAnimationFrame(frame) })
onBeforeUnmount(() => {
  cancelAnimationFrame(raf)
  if (recvTimer) clearTimeout(recvTimer)
})
</script>

<style scoped>
.olwen-entity-wrapper {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.olwen-entity {
  max-width: 100%;
  height: auto;
  overflow: visible; /* let a reaching tendril extend beyond the body */
}
.olwen-entity-wrapper { overflow: visible; }
.reach-tendril { opacity: 0.85; }
.reach-tendril-core { opacity: 0.9; }

/* ============================================ */
/* BREATHING - the body pulses gently           */
/* ============================================ */
@keyframes olwen-breathe {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.04); }
}
.body-core {
  animation: olwen-breathe 4s ease-in-out infinite;
  transform-origin: 200px 195px;
}

/* ============================================ */
/* HALO PULSE - atmospheric glow                */
/* ============================================ */
@keyframes olwen-halo-pulse {
  0%, 100% { opacity: 0.5; transform: scale(1); }
  50% { opacity: 0.9; transform: scale(1.08); }
}
.halo {
  animation: olwen-halo-pulse 5s ease-in-out infinite;
  transform-origin: 200px 195px;
}

/* ============================================ */
/* INNER FLOW - life inside the body            */
/* ============================================ */
@keyframes olwen-inner-flow {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}
.inner-flow {
  animation: olwen-inner-flow 14s linear infinite;
  transform-origin: 200px 195px;
}

/* ============================================ */
/* TENDRILS - each animates independently       */
/* CRITICAL: different timing for each!         */
/* ============================================ */
@keyframes olwen-tendril-1 {
  0%, 100% { d: path("M 200 200 Q 180 240 165 290 Q 155 340 170 380"); }
  50%      { d: path("M 200 200 Q 175 235 158 295 Q 150 345 175 385"); }
}
@keyframes olwen-tendril-2 {
  0%, 100% { d: path("M 200 200 Q 230 230 250 280 Q 265 330 245 380"); }
  50%      { d: path("M 200 200 Q 235 225 258 285 Q 270 335 240 385"); }
}
@keyframes olwen-tendril-3 {
  0%, 100% { d: path("M 200 200 Q 160 220 130 250 Q 100 285 90 330"); }
  50%      { d: path("M 200 200 Q 155 218 125 255 Q 95 290 85 335"); }
}
@keyframes olwen-tendril-4 {
  0%, 100% { d: path("M 200 200 Q 245 215 280 240 Q 320 270 335 310"); }
  50%      { d: path("M 200 200 Q 250 212 285 245 Q 325 275 340 315"); }
}
@keyframes olwen-tendril-5 {
  0%, 100% { d: path("M 200 200 Q 200 250 195 300 Q 200 350 210 395"); }
  50%      { d: path("M 200 200 Q 205 252 198 305 Q 195 355 215 398"); }
}
@keyframes olwen-tendril-6 {
  0%, 100% { d: path("M 200 200 Q 150 195 105 200 Q 60 210 35 235"); }
  50%      { d: path("M 200 200 Q 145 193 100 205 Q 55 215 30 240"); }
}
@keyframes olwen-tendril-7 {
  0%, 100% { d: path("M 200 200 Q 255 198 305 205 Q 350 215 380 235"); }
  50%      { d: path("M 200 200 Q 260 195 310 210 Q 355 220 385 240"); }
}

.tendril-1   { animation: olwen-tendril-1 7s   ease-in-out infinite; }
.tendril-2   { animation: olwen-tendril-2 8s   ease-in-out infinite 0.5s; }
.tendril-3   { animation: olwen-tendril-3 6.5s ease-in-out infinite 1s; }
.tendril-4   { animation: olwen-tendril-4 7.5s ease-in-out infinite 1.5s; }
.tendril-5   { animation: olwen-tendril-5 9s   ease-in-out infinite 0.8s; }
.tendril-6   { animation: olwen-tendril-6 8.5s ease-in-out infinite 2s; }
.tendril-7   { animation: olwen-tendril-7 7.2s ease-in-out infinite 1.2s; }
.tendril-h-1 { animation: olwen-tendril-1 7s   ease-in-out infinite; }
.tendril-h-5 { animation: olwen-tendril-5 9s   ease-in-out infinite 0.8s; }

/* ============================================ */
/* MIST - drifts slowly in background           */
/* ============================================ */
@keyframes olwen-mist-drift {
  0%, 100% { opacity: 0.15; transform: scale(1) rotate(0deg); }
  50% { opacity: 0.3; transform: scale(1.1) rotate(45deg); }
}
.mist-1 { animation: olwen-mist-drift 8s  ease-in-out infinite;       transform-origin: 130px 350px; }
.mist-2 { animation: olwen-mist-drift 10s ease-in-out infinite 2s;    transform-origin: 290px 320px; }
.mist-3 { animation: olwen-mist-drift 12s ease-in-out infinite 4s;    transform-origin: 200px 410px; }

/* ============================================ */
/* MOTES - light particles drifting up          */
/* ============================================ */
@keyframes olwen-mote-1 {
  0%   { transform: translate(0, 0);     opacity: 0; }
  30%  { opacity: 0.9; }
  100% { transform: translate(20px, -60px);  opacity: 0; }
}
@keyframes olwen-mote-2 {
  0%   { transform: translate(0, 0);     opacity: 0; }
  30%  { opacity: 0.8; }
  100% { transform: translate(-30px, -50px); opacity: 0; }
}
@keyframes olwen-mote-3 {
  0%   { transform: translate(0, 0);     opacity: 0; }
  30%  { opacity: 0.9; }
  100% { transform: translate(40px, 30px);   opacity: 0; }
}
@keyframes olwen-mote-4 {
  0%   { transform: translate(0, 0);     opacity: 0; }
  30%  { opacity: 0.8; }
  100% { transform: translate(-25px, 55px);  opacity: 0; }
}

.mote-1 { animation: olwen-mote-1 4s   ease-in-out infinite; }
.mote-2 { animation: olwen-mote-2 5s   ease-in-out infinite 1s; }
.mote-3 { animation: olwen-mote-3 4.5s ease-in-out infinite 2s; }
.mote-4 { animation: olwen-mote-4 5.5s ease-in-out infinite 0.5s; }
.mote-5 { animation: olwen-mote-1 6s   ease-in-out infinite 3s; }
.mote-6 { animation: olwen-mote-2 4.8s ease-in-out infinite 2.5s; }

/* ============================================ */
/* STATE VARIATIONS                              */
/* ============================================ */

/* LISTENING - faster breathing */
.state-listening .body-core { animation-duration: 3s; }
.state-listening .halo      { animation-duration: 3s; opacity: 0.7; }

/* THINKING - tendrils contract upward, slower */
.state-thinking .body-core { animation-duration: 5s; }
.state-thinking .tendril {
  transform-origin: 200px 200px;
  transform: scaleY(0.85);
  transition: transform 0.6s ease;
}

/* SPEAKING - body pulses faster with subtle brightness shift */
@keyframes olwen-speak-pulse {
  0%, 100% { transform: scale(1);    filter: brightness(1); }
  25%      { transform: scale(1.06); filter: brightness(1.2); }
  50%      { transform: scale(1.03); filter: brightness(1.1); }
  75%      { transform: scale(1.08); filter: brightness(1.25); }
}
.state-speaking .body-core {
  animation: olwen-speak-pulse 0.6s ease-in-out infinite;
}

/* WORKING - intensity increases */
.state-working .halo      { opacity: 0.85; }
.state-working .body-core { animation-duration: 3s; }

/* ============================================ */
/* RECEIVE REACTION - one-shot ripple on arrival */
/* Additive: layered over whatever state runs.   */
/* ============================================ */

/* Expanding rings emanate from the core center (200,195). */
@keyframes olwen-recv-ring {
  0%   { transform: scale(0.3);  opacity: 0; }
  12%  { opacity: 0.8; }
  100% { transform: scale(2.2);  opacity: 0; }
}
.recv-ring {
  transform-origin: 200px 195px;
  opacity: 0;
}
.receiving .recv-ring-1 {
  animation: olwen-recv-ring 1s cubic-bezier(0.16, 0.84, 0.44, 1) both;
}
.receiving .recv-ring-2 {
  animation: olwen-recv-ring 1.05s cubic-bezier(0.16, 0.84, 0.44, 1) 0.18s both;
}

/* Core bloom flash — a separate overlay circle, NOT the .body-core animation. */
@keyframes olwen-recv-bloom {
  0%   { transform: scale(0.7); opacity: 0; }
  25%  { transform: scale(1);   opacity: 0.55; }
  100% { transform: scale(1.25); opacity: 0; }
}
.recv-bloom {
  transform-origin: 200px 195px;
  opacity: 0;
  mix-blend-mode: screen;
  filter: url(#olwen-soft-glow);
}
.receiving .recv-bloom {
  animation: olwen-recv-bloom 0.95s ease-out both;
}

/* Tendrils briefly energize — brighten via opacity (keeps inline soft-glow filter intact). */
.tendrils,
.tendril-highlights {
  transition: opacity 0.9s ease-out;
}
.receiving .tendrils {
  opacity: 1;
  animation: olwen-recv-energize 1s ease-out both;
}
.receiving .tendril-highlights {
  animation: olwen-recv-energize 1s ease-out both;
}
@keyframes olwen-recv-energize {
  0%   { opacity: 1; }
  18%  { opacity: 1.6; }   /* clamped to 1 by the engine — reads as a bright flick */
  100% { opacity: 1; }
}

/* ============================================ */
/* ACCESSIBILITY - respect reduced motion       */
/* ============================================ */
@media (prefers-reduced-motion: reduce) {
  .body-core,
  .halo,
  .inner-flow,
  .tendril,
  .tendril-h-1,
  .tendril-h-5,
  .mist-1,
  .mist-2,
  .mist-3,
  .mote-1,
  .mote-2,
  .mote-3,
  .mote-4,
  .mote-5,
  .mote-6 {
    animation: none !important;
  }

  /* RECEIVE: drop the expanding rings; keep only a brief core/tendril brighten. */
  .recv-ring {
    display: none;
  }
  .receiving .recv-bloom {
    animation: olwen-recv-bloom-reduced 0.9s ease-out both;
  }
  @keyframes olwen-recv-bloom-reduced {
    0%   { transform: scale(1); opacity: 0; }
    30%  { opacity: 0.5; }
    100% { transform: scale(1); opacity: 0; }
  }
  /* the energize fade still reads as a gentle brighten — no scale/position motion */
}
</style>
