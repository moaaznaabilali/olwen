<script setup lang="ts">
import { onMounted, ref } from 'vue'

const { isAuthenticated, ready, init } = useAuth()

// Cosmic starfield — generated CLIENT-SIDE ONLY so SSR doesn't bake random
// values that mismatch the hydrated DOM (was flooding the console).
interface Star { id: number; top: number; left: number; size: number; delay: number; dur: number }
const stars = ref<Star[]>([])

onMounted(() => {
  if (window.location.pathname !== '/') {
    window.history.replaceState(null, '', '/')
  }
  stars.value = Array.from({ length: 80 }, (_, i) => ({
    id: i,
    top: Math.random() * 100,
    left: Math.random() * 100,
    size: Math.random() < 0.85 ? 1 : 2,
    delay: Math.random() * 6,
    dur: 3 + Math.random() * 5,
  }))
  init()
})
</script>

<template>
  <div class="root">
    <!-- cosmic background -->
    <div class="nebula" aria-hidden="true" />
    <div class="stars" aria-hidden="true">
      <span
        v-for="s in stars"
        :key="s.id"
        :style="{
          top: `${s.top}%`, left: `${s.left}%`,
          width: `${s.size}px`, height: `${s.size}px`,
          '--delay': `${s.delay}s`, '--dur': `${s.dur}s`,
        }"
      />
    </div>

    <Transition name="fade" mode="out-in">
      <DashboardView v-if="ready && isAuthenticated" key="dash" />
      <LoginScreen v-else-if="ready && !isAuthenticated" key="login" />
      <div v-else key="splash" class="splash">
        <span class="splash__text">awakening…</span>
      </div>
    </Transition>

    <!-- custom cursor removed — native pointer is calmer and avoids click conflicts -->
  </div>
</template>

<style>
:root { color-scheme: dark; }
* { box-sizing: border-box; }
/* Ensure the native cursor is always visible (custom cursor was removed). */
html, body, #__nuxt { margin: 0; height: 100%; cursor: auto; }
body {
  font-family: Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  background: #02060A;
  color: #E2F5F1;
}
</style>

<style scoped>
.root {
  position: relative;
  height: 100vh;
  overflow: hidden;
  background: radial-gradient(ellipse at 50% 40%, #0A1419 0%, #02060A 72%);
}

.nebula {
  position: absolute; inset: 0; pointer-events: none; z-index: 0;
  background:
    radial-gradient(40% 50% at 28% 30%, rgba(6, 182, 212, 0.10), transparent 60%),
    radial-gradient(45% 55% at 74% 68%, rgba(94, 234, 212, 0.08), transparent 60%);
}
.stars { position: absolute; inset: 0; pointer-events: none; z-index: 0; }
.stars span { position: absolute; border-radius: 50%; background: #CFFAFE; opacity: 0.5; }
@media (prefers-reduced-motion: no-preference) {
  .stars span { animation: twinkle var(--dur) ease-in-out infinite; animation-delay: var(--delay); }
  @keyframes twinkle { 0%,100% { opacity: 0.12; } 50% { opacity: 0.65; } }
}

.splash {
  position: relative; z-index: 1;
  height: 100%; display: grid; place-items: center;
}
.splash__text {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px; letter-spacing: 3px; text-transform: uppercase;
  color: rgba(94, 234, 212, 0.6);
}

.fade-enter-active, .fade-leave-active { transition: opacity 0.4s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
