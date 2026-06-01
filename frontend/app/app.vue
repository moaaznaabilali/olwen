<script setup lang="ts">
import { onMounted, ref } from 'vue'

const { isAuthenticated, ready, init } = useAuth()
const { init: initTheme } = useTheme()

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
  initTheme()
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
/* ── Theme token contract ───────────────────────────────────────────────
 * ~10 semantic tokens. Dark is default; [data-theme="light"] flips the
 * STRUCTURAL ones (bg / surface / text / border). Accents (teal, priority
 * colors) stay roughly constant across both. Glass-fill and text are a
 * coupled pair — they flip together, never independently. */
:root {
  color-scheme: dark;
  --bg: #02060A;
  --bg-from: #0A1419;
  --bg-to: #02060A;
  --surface-solid: #04101A;       /* opaque panels (boards, overlays) */
  --surface: rgba(8, 51, 68, 0.18); /* translucent glass panel fill */
  --surface-2: rgba(8, 51, 68, 0.30); /* inset chips / hud cells */
  --text: #E2F5F1;                /* body text */
  --text-strong: #ECFEFF;         /* headings / values */
  --text-muted: rgba(167, 243, 208, 0.55);
  --border: rgba(94, 234, 212, 0.12);
  --border-strong: rgba(94, 234, 212, 0.30);
  --accent: #5EEAD4;
  --accent-2: #A7F3D0;
  --star: #CFFAFE;
  --star-opacity: 0.5;
  --nebula-1: rgba(6, 182, 212, 0.10);
  --nebula-2: rgba(94, 234, 212, 0.08);
  --glow: 0 0 16px rgba(94, 234, 212, 0.18);
}
:root[data-theme="light"] {
  color-scheme: light;
  --bg: #EEF4F5;
  --bg-from: #F7FBFB;
  --bg-to: #DDE9EA;
  --surface-solid: #FFFFFF;
  --surface: rgba(255, 255, 255, 0.72);
  --surface-2: rgba(13, 148, 136, 0.07);
  --text: #103A3E;
  --text-strong: #04252A;
  --text-muted: rgba(15, 90, 88, 0.62);
  --border: rgba(13, 148, 136, 0.18);
  --border-strong: rgba(13, 148, 136, 0.42);
  --accent: #0D9488;
  --accent-2: #0F766E;
  --star: #5EEAD4;
  --star-opacity: 0.28;
  --nebula-1: rgba(13, 148, 136, 0.08);
  --nebula-2: rgba(45, 212, 191, 0.07);
  --glow: 0 0 14px rgba(13, 148, 136, 0.12);
}
* { box-sizing: border-box; }
/* Ensure the native cursor is always visible (custom cursor was removed). */
html, body, #__nuxt { margin: 0; height: 100%; cursor: auto; }
body {
  font-family: Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  background: var(--bg);
  color: var(--text);
  transition: background 0.4s ease, color 0.4s ease;
}
</style>

<style scoped>
.root {
  position: relative;
  height: 100vh;
  overflow: hidden;
  background: radial-gradient(ellipse at 50% 40%, var(--bg-from) 0%, var(--bg-to) 72%);
  transition: background 0.4s ease;
}

.nebula {
  position: absolute; inset: 0; pointer-events: none; z-index: 0;
  background:
    radial-gradient(40% 50% at 28% 30%, var(--nebula-1), transparent 60%),
    radial-gradient(45% 55% at 74% 68%, var(--nebula-2), transparent 60%);
}
.stars { position: absolute; inset: 0; pointer-events: none; z-index: 0; }
.stars span { position: absolute; border-radius: 50%; background: var(--star); opacity: var(--star-opacity); }
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
  color: var(--accent);
}

.fade-enter-active, .fade-leave-active { transition: opacity 0.4s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
