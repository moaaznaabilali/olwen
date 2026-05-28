<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'

/* A bioluminescent cursor: a soft outer aura that lerps behind the precise
   inner dot, plus a teal trail of fading particles. The aura grows + spins
   when hovering Olwen, and a click fires a quick ring-burst. Touch devices
   are detected and the whole thing is suppressed. */

const x = ref(0); const y = ref(0)
const tx = ref(0); const ty = ref(0)        // lagging aura position
const visible = ref(false)
const isTouch = ref(false)
const hovering = ref(false)                  // over an interactive target
const onOlwen = ref(false)                   // over the creature
const pressing = ref(false)
const rings = ref<{ id: number; x: number; y: number }[]>([])
const trail = ref<{ id: number; x: number; y: number }[]>([])
let ringId = 0; let trailId = 0
let raf = 0
let lastTrail = 0

function onMove(ev: PointerEvent) {
  if (ev.pointerType === 'touch') { isTouch.value = true; return }
  x.value = ev.clientX
  y.value = ev.clientY
  visible.value = true

  // detect targets we care about
  const t = ev.target as HTMLElement | null
  onOlwen.value = !!t?.closest?.('[data-olwen]')
  hovering.value = onOlwen.value || !!t?.closest?.(
    'button, a, input, textarea, select, [role="button"], .row, .card, .ctl, .act, .cmdbtn',
  )

  // sparse trail particles so it doesn't look spammy
  const now = performance.now()
  if (now - lastTrail > 38) {
    lastTrail = now
    const id = ++trailId
    trail.value.push({ id, x: ev.clientX, y: ev.clientY })
    setTimeout(() => {
      const i = trail.value.findIndex(p => p.id === id)
      if (i >= 0) trail.value.splice(i, 1)
    }, 700)
    if (trail.value.length > 24) trail.value.shift()
  }
}

function onDown(ev: PointerEvent) {
  if (ev.pointerType === 'touch') return
  pressing.value = true
  const id = ++ringId
  rings.value.push({ id, x: ev.clientX, y: ev.clientY })
  setTimeout(() => {
    const i = rings.value.findIndex(r => r.id === id)
    if (i >= 0) rings.value.splice(i, 1)
  }, 700)
}
function onUp() { pressing.value = false }
function onLeave() { visible.value = false }

function tick() {
  // lerp the aura toward the precise dot for a satiny lag
  tx.value += (x.value - tx.value) * 0.18
  ty.value += (y.value - ty.value) * 0.18
  raf = requestAnimationFrame(tick)
}

onMounted(() => {
  window.addEventListener('pointermove', onMove)
  window.addEventListener('pointerdown', onDown)
  window.addEventListener('pointerup', onUp)
  window.addEventListener('pointercancel', onUp)
  document.addEventListener('mouseleave', onLeave)
  raf = requestAnimationFrame(tick)
})
onBeforeUnmount(() => {
  window.removeEventListener('pointermove', onMove)
  window.removeEventListener('pointerdown', onDown)
  window.removeEventListener('pointerup', onUp)
  window.removeEventListener('pointercancel', onUp)
  document.removeEventListener('mouseleave', onLeave)
  cancelAnimationFrame(raf)
})
</script>

<template>
  <div v-if="!isTouch" class="cur" :class="{ visible }" aria-hidden="true">
    <!-- trail particles -->
    <span
      v-for="p in trail"
      :key="`t-${p.id}`"
      class="cur__trail"
      :style="{ left: p.x + 'px', top: p.y + 'px' }"
    />

    <!-- click burst rings -->
    <span
      v-for="r in rings"
      :key="`r-${r.id}`"
      class="cur__ring"
      :style="{ left: r.x + 'px', top: r.y + 'px' }"
    />

    <!-- lagging aura (large, rotates over Olwen) -->
    <span
      class="cur__aura"
      :class="{ onOlwen, pressing, hovering }"
      :style="{ transform: `translate(${tx}px, ${ty}px) translate(-50%, -50%)` }"
    >
      <svg viewBox="0 0 80 80" width="80" height="80">
        <defs>
          <radialGradient id="cur-g" cx="0.5" cy="0.5" r="0.5">
            <stop offset="0%" stop-color="#A7F3D0" stop-opacity="0.9" />
            <stop offset="55%" stop-color="#5EEAD4" stop-opacity="0.35" />
            <stop offset="100%" stop-color="#06B6D4" stop-opacity="0" />
          </radialGradient>
        </defs>
        <circle cx="40" cy="40" r="34" fill="url(#cur-g)" />
        <!-- four orbiting nibs that only show when hovering -->
        <g class="cur__nibs">
          <circle cx="40" cy="6"  r="2" fill="#A7F3D0" />
          <circle cx="74" cy="40" r="2" fill="#A7F3D0" />
          <circle cx="40" cy="74" r="2" fill="#A7F3D0" />
          <circle cx="6"  cy="40" r="2" fill="#A7F3D0" />
        </g>
      </svg>
    </span>

    <!-- precise leader dot -->
    <span
      class="cur__dot"
      :class="{ pressing, hovering, onOlwen }"
      :style="{ transform: `translate(${x}px, ${y}px) translate(-50%, -50%)` }"
    />
  </div>
</template>

<style>
/* Hide the native cursor app-wide once the custom one is mounted. */
@media (hover: hover) and (pointer: fine) {
  html, body, * { cursor: none !important; }
}
</style>

<style scoped>
.cur { position: fixed; inset: 0; pointer-events: none; z-index: 9999; opacity: 0; transition: opacity .25s ease; }
.cur.visible { opacity: 1; }

.cur__dot {
  position: fixed; top: 0; left: 0; width: 8px; height: 8px; border-radius: 50%;
  background: #ECFEFF;
  box-shadow: 0 0 6px #5EEAD4, 0 0 16px rgba(94,234,212,0.7);
  transition: width .18s ease, height .18s ease, background .18s ease, box-shadow .25s ease;
  mix-blend-mode: screen;
}
.cur__dot.hovering { width: 14px; height: 14px; background: #5EEAD4; box-shadow: 0 0 10px #5EEAD4, 0 0 24px rgba(94,234,212,0.9); }
.cur__dot.onOlwen  { width: 4px; height: 4px; background: #ECFEFF; box-shadow: 0 0 22px #5EEAD4, 0 0 60px rgba(167,243,208,0.7); }
.cur__dot.pressing { width: 5px; height: 5px; }

.cur__aura {
  position: fixed; top: 0; left: 0; width: 80px; height: 80px;
  opacity: 0.85;
  transition: width .25s ease, height .25s ease, opacity .25s ease, filter .25s ease;
}
.cur__aura svg { display: block; }
.cur__aura .cur__nibs { opacity: 0; transform-origin: 40px 40px; transition: opacity .25s ease; }
.cur__aura.hovering { width: 110px; height: 110px; }
.cur__aura.hovering .cur__nibs { opacity: 1; animation: nibspin 4s linear infinite; }
.cur__aura.onOlwen {
  width: 180px; height: 180px;
  filter: drop-shadow(0 0 14px rgba(94,234,212,0.8)) drop-shadow(0 0 38px rgba(6,182,212,0.5));
}
.cur__aura.onOlwen .cur__nibs { opacity: 1; animation: nibspin 1.8s linear infinite; }
.cur__aura.pressing { filter: brightness(1.6) drop-shadow(0 0 22px #5EEAD4); }
@keyframes nibspin { to { transform: rotate(360deg); } }

/* trail */
.cur__trail {
  position: fixed; width: 4px; height: 4px; border-radius: 50%;
  background: #5EEAD4; box-shadow: 0 0 8px #5EEAD4;
  transform: translate(-50%, -50%);
  animation: trailfade .7s ease-out forwards;
  mix-blend-mode: screen;
}
@keyframes trailfade {
  0%   { opacity: 0.9; transform: translate(-50%, -50%) scale(1); }
  100% { opacity: 0; transform: translate(-50%, -50%) scale(0.2); }
}

/* click burst rings */
.cur__ring {
  position: fixed; width: 24px; height: 24px; border-radius: 50%;
  border: 1.5px solid #5EEAD4;
  transform: translate(-50%, -50%);
  animation: ringburst .7s cubic-bezier(.18,.6,.32,1) forwards;
  box-shadow: 0 0 18px rgba(94,234,212,0.6);
  mix-blend-mode: screen;
}
@keyframes ringburst {
  0%   { width: 18px; height: 18px; opacity: 0.9; }
  100% { width: 110px; height: 110px; opacity: 0; }
}

@media (prefers-reduced-motion: reduce) {
  .cur__trail, .cur__ring, .cur__nibs { display: none; }
  .cur__aura { transition: none; }
}
</style>
