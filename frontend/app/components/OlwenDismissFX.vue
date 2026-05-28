<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

/* Dismissal effect built around Olwen's tendrils.

  From the entity's center, ~14 curved tendril paths whip outward across the
  whole screen — drawn from origin to edge with the same teal gradient as his
  real arms — then retract back through themselves. Teleported to <body> so
  nothing clips them. */
const props = defineProps<{ center: { x: number, y: number } }>()

const vw = ref(1280); const vh = ref(800)
onMounted(() => { vw.value = window.innerWidth; vh.value = window.innerHeight })

interface Tendril { d: string; width: number; len: number; delay: number; reverse: boolean }

const tendrils = computed<Tendril[]>(() => {
  const cx = props.center.x; const cy = props.center.y
  const reach = Math.max(vw.value, vh.value) * 1.05
  const out: Tendril[] = []
  const N = 14
  for (let i = 0; i < N; i++) {
    const angle = (i / N) * Math.PI * 2 + (Math.random() - 0.5) * 0.35
    const r1 = reach * (0.75 + Math.random() * 0.35)
    const ex = cx + Math.cos(angle) * r1
    const ey = cy + Math.sin(angle) * r1

    // two control points along the path with perpendicular offset → an S-curve
    // that looks alive, like a real tendril whipping
    const cp1x = cx + Math.cos(angle) * (r1 * 0.35)
    const cp1y = cy + Math.sin(angle) * (r1 * 0.35)
    const cp2x = cx + Math.cos(angle) * (r1 * 0.7)
    const cp2y = cy + Math.sin(angle) * (r1 * 0.7)
    const perp = angle + Math.PI / 2
    const swing1 = (Math.random() - 0.5) * 220
    const swing2 = (Math.random() - 0.5) * 220
    const cp1xS = cp1x + Math.cos(perp) * swing1
    const cp1yS = cp1y + Math.sin(perp) * swing1
    const cp2xS = cp2x + Math.cos(perp) * swing2
    const cp2yS = cp2y + Math.sin(perp) * swing2

    out.push({
      d: `M ${cx},${cy} C ${cp1xS},${cp1yS} ${cp2xS},${cp2yS} ${ex},${ey}`,
      width: 2 + Math.random() * 5,
      // length estimate — generous so dashoffset fully covers the path
      len: r1 * 1.4,
      delay: Math.random() * 220,
      reverse: i % 3 === 0,
    })
  }
  return out
})
</script>

<template>
  <Teleport to="body">
    <div class="fx" aria-hidden="true">
      <svg
        class="fx__svg"
        :viewBox="`0 0 ${vw} ${vh}`"
        :width="vw"
        :height="vh"
        preserveAspectRatio="none"
      >
        <defs>
          <!-- match Olwen's real tendril gradient -->
          <linearGradient id="fx-tendril" gradientUnits="userSpaceOnUse"
            :x1="center.x" :y1="center.y" :x2="vw" :y2="vh">
            <stop offset="0%"  stop-color="#ECFEFF" stop-opacity="1" />
            <stop offset="15%" stop-color="#A7F3D0" stop-opacity="0.95" />
            <stop offset="55%" stop-color="#5EEAD4" stop-opacity="0.7" />
            <stop offset="100%" stop-color="#06B6D4" stop-opacity="0" />
          </linearGradient>
          <filter id="fx-glow" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="3" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        <g filter="url(#fx-glow)">
          <!-- bright bioluminescent point at his core -->
          <circle :cx="center.x" :cy="center.y" r="0" fill="#ECFEFF" class="fx__core" />

          <!-- each tendril whips outward then retracts -->
          <path
            v-for="(t, i) in tendrils"
            :key="i"
            :d="t.d"
            stroke="url(#fx-tendril)"
            :stroke-width="t.width"
            stroke-linecap="round"
            fill="none"
            class="fx__tendril"
            :class="{ reverse: t.reverse }"
            :style="{
              '--len': t.len,
              '--delay': t.delay + 'ms',
              strokeDasharray: t.len,
              strokeDashoffset: t.len,
            }"
          />
        </g>
      </svg>

      <!-- a thin iris vignette that softly closes around the action -->
      <div class="fx__iris" :style="{ '--cx': center.x + 'px', '--cy': center.y + 'px' }" />
    </div>
  </Teleport>
</template>

<style scoped>
.fx { position: fixed; inset: 0; pointer-events: none; z-index: 95; }
.fx__svg { display: block; position: absolute; inset: 0; }

/* the tendril whip — shoot out, then retract through itself */
.fx__tendril {
  animation: tendril-whip 1.05s cubic-bezier(.22,.7,.28,1) forwards;
  animation-delay: var(--delay);
  filter: drop-shadow(0 0 6px #5EEAD4);
}
.fx__tendril.reverse { animation-name: tendril-whip-rev; animation-duration: 1.2s; }

@keyframes tendril-whip {
  0%   { stroke-dashoffset: var(--len); opacity: 0; }
  10%  { opacity: 1; }
  55%  { stroke-dashoffset: 0;         opacity: 1; }
  100% { stroke-dashoffset: calc(var(--len) * -1); opacity: 0; }
}
/* alternate tendrils retract from the OPPOSITE direction for organic chaos */
@keyframes tendril-whip-rev {
  0%   { stroke-dashoffset: calc(var(--len) * -1); opacity: 0; }
  10%  { opacity: 1; }
  55%  { stroke-dashoffset: 0; opacity: 1; }
  100% { stroke-dashoffset: var(--len); opacity: 0; }
}

/* a tiny luminous point pulses where Olwen stood */
.fx__core { animation: core-pulse 1.1s cubic-bezier(.18,.7,.28,1) forwards; }
@keyframes core-pulse {
  0%   { r: 0;  opacity: 0; }
  20%  { r: 26; opacity: 1; }
  60%  { r: 6;  opacity: 1; }
  100% { r: 0;  opacity: 0; }
}

/* the iris vignette stays subtle — frames the moment without stealing focus from the tendrils */
.fx__iris {
  position: absolute; inset: 0;
  background: radial-gradient(circle at var(--cx) var(--cy),
    transparent 0%, transparent 22%,
    rgba(2,6,10,0.0) 30%, rgba(2,6,10,0.7) 78%);
  opacity: 0;
  animation: iris .9s ease-out .2s forwards;
}
@keyframes iris {
  0%   { opacity: 0; }
  60%  { opacity: 0.85; }
  100% { opacity: 0.6; }
}

@media (prefers-reduced-motion: reduce) {
  .fx__tendril, .fx__core, .fx__iris { animation: none !important; }
  .fx__iris { opacity: 0.5; }
}
</style>
