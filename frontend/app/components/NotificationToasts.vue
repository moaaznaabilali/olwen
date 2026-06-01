<script setup lang="ts">
import { onBeforeUnmount } from 'vue'
import { useNotifications, type OlwenNotification } from '~/composables/useNotifications'

const { toasts, markRead, dismissToast } = useNotifications()

const KIND_ACCENT: Record<string, string> = {
  telegram: '#34B7F1',
  whatsapp: '#25D366',
  email: '#FBBF24',
}

function accentFor(kind: string): string {
  return KIND_ACCENT[kind] ?? 'var(--accent)'
}

function iconFor(kind: string): string {
  switch (kind) {
    case 'telegram':
      // paper-plane
      return 'M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z'
    case 'whatsapp':
      // chat bubble
      return 'M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z'
    case 'email':
      // envelope (drawn as two paths joined for the flap)
      return 'M4 4h16a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2zm18 2l-10 7L2 6'
    default:
      // 4-point star / spark
      return 'M12 3l1.8 4.7L18.5 9.5 13.8 11.3 12 16l-1.8-4.7L5.5 9.5l4.7-1.8L12 3z'
  }
}

function relativeTime(iso: string | null): string {
  if (!iso) return 'now'
  const t = new Date(iso).getTime()
  if (Number.isNaN(t)) return 'now'
  const diff = Math.max(0, Date.now() - t)
  const s = Math.floor(diff / 1000)
  if (s < 45) return 'now'
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h`
  const d = Math.floor(h / 24)
  return `${d}d`
}

// Per-toast auto-dismiss timers, keyed by id.
const timers = new Map<string, ReturnType<typeof setTimeout>>()
const SHOWN = 6000
const RESUME = 3000

function arm(id: string, ms: number): void {
  clear(id)
  timers.set(id, setTimeout(() => {
    timers.delete(id)
    dismissToast(id)
  }, ms))
}

function clear(id: string): void {
  const t = timers.get(id)
  if (t) { clearTimeout(t); timers.delete(id) }
}

// Visible queue, newest on top, cap at 4.
const visible = computed<OlwenNotification[]>(() =>
  [...toasts.value].reverse().slice(0, 4),
)

// Arm a timer the moment a toast becomes visible; clear timers for ones gone.
watch(visible, (list) => {
  const ids = new Set(list.map(n => n.id))
  for (const id of timers.keys()) if (!ids.has(id)) clear(id)
  for (const n of list) if (!timers.has(n.id)) arm(n.id, SHOWN)
}, { immediate: true })

function onEnter(id: string): void {
  clear(id)
}
function onLeave(id: string): void {
  arm(id, RESUME)
}

function onClose(id: string): void {
  clear(id)
  dismissToast(id)
}

function onActivate(id: string): void {
  markRead(id)
  clear(id)
  dismissToast(id)
}

onBeforeUnmount(() => {
  for (const t of timers.values()) clearTimeout(t)
  timers.clear()
})
</script>

<template>
  <div class="toast-layer" aria-live="polite">
    <TransitionGroup name="toast" tag="div" class="toast-stack">
      <article
        v-for="n in visible"
        :key="n.id"
        class="toast"
        :style="{ '--k': accentFor(n.kind) }"
        role="status"
        @click="onActivate(n.id)"
        @mouseenter="onEnter(n.id)"
        @mouseleave="onLeave(n.id)"
      >
        <span class="toast__bar" aria-hidden="true" />
        <span class="toast__icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none"
               stroke="currentColor" stroke-width="1.8"
               stroke-linecap="round" stroke-linejoin="round">
            <path :d="iconFor(n.kind)" />
          </svg>
        </span>
        <div class="toast__main">
          <div class="toast__top">
            <p class="toast__title">{{ n.title }}</p>
            <span class="toast__time">{{ relativeTime(n.created_at) }}</span>
          </div>
          <p v-if="n.body" class="toast__body">{{ n.body }}</p>
        </div>
        <button class="toast__close" type="button"
                aria-label="Dismiss"
                @click.stop="onClose(n.id)">
          <svg viewBox="0 0 24 24" width="13" height="13" fill="none"
               stroke="currentColor" stroke-width="2" stroke-linecap="round">
            <path d="M6 6l12 12M18 6L6 18" />
          </svg>
        </button>
      </article>
    </TransitionGroup>
  </div>
</template>

<style scoped>
.toast-layer {
  position: fixed;
  top: 64px;
  right: 20px;
  z-index: 80;
  pointer-events: none;
  width: 340px;
  max-width: calc(100vw - 32px);
}
.toast-stack {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.toast {
  position: relative;
  pointer-events: auto;
  display: flex;
  align-items: flex-start;
  gap: 11px;
  padding: 12px 12px 12px 16px;
  border-radius: 14px;
  border: 1px solid var(--border-strong);
  background: var(--surface-2);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  cursor: pointer;
  overflow: hidden;
  box-shadow:
    0 10px 30px -12px rgba(0, 0, 0, 0.55),
    0 0 0 1px color-mix(in srgb, var(--k) 14%, transparent),
    0 6px 24px -16px color-mix(in srgb, var(--k) 60%, transparent);
  transition: border-color .2s ease, box-shadow .2s ease, transform .2s ease;
}
.toast:hover {
  border-color: color-mix(in srgb, var(--k) 55%, var(--border-strong));
  box-shadow:
    0 14px 36px -12px rgba(0, 0, 0, 0.6),
    0 0 0 1px color-mix(in srgb, var(--k) 24%, transparent),
    0 8px 30px -14px color-mix(in srgb, var(--k) 70%, transparent);
}

.toast__bar {
  position: absolute;
  top: 10px;
  bottom: 10px;
  left: 6px;
  width: 3px;
  border-radius: 3px;
  background: var(--k);
  box-shadow: 0 0 10px -1px color-mix(in srgb, var(--k) 80%, transparent);
}

.toast__icon {
  flex: 0 0 auto;
  width: 30px;
  height: 30px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  color: var(--k);
  background: color-mix(in srgb, var(--k) 14%, transparent);
  border: 1px solid color-mix(in srgb, var(--k) 30%, transparent);
}

.toast__main {
  flex: 1 1 auto;
  min-width: 0;
}
.toast__top {
  display: flex;
  align-items: baseline;
  gap: 8px;
}
.toast__title {
  margin: 0;
  flex: 1 1 auto;
  min-width: 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-strong);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.toast__time {
  flex: 0 0 auto;
  font-size: 10.5px;
  color: var(--text-muted);
  opacity: 0.7;
}
.toast__body {
  margin: 3px 0 0;
  font-size: 12px;
  line-height: 1.4;
  color: var(--text-muted);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.toast__close {
  flex: 0 0 auto;
  display: grid;
  place-items: center;
  width: 20px;
  height: 20px;
  margin: -2px -2px 0 0;
  padding: 0;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  opacity: 0.55;
  transition: opacity .15s ease, color .15s ease, background .15s ease;
}
.toast__close:hover {
  opacity: 1;
  color: var(--text-strong);
  background: var(--surface);
}

/* Entrance / exit — spring-ish slide from the right + fade + scale */
.toast-enter-active {
  transition:
    transform .42s cubic-bezier(0.22, 1.2, 0.36, 1),
    opacity .32s ease;
}
.toast-leave-active {
  transition:
    transform .3s cubic-bezier(0.4, 0, 0.6, 1),
    opacity .26s ease;
  position: absolute;
  right: 0;
  width: 100%;
}
.toast-enter-from {
  opacity: 0;
  transform: translateX(36px) scale(0.96);
}
.toast-leave-to {
  opacity: 0;
  transform: translateX(36px) scale(0.97);
}
.toast-move {
  transition: transform .35s cubic-bezier(0.22, 1, 0.36, 1);
}

@media (prefers-reduced-motion: reduce) {
  .toast-enter-active,
  .toast-leave-active,
  .toast-move {
    transition: opacity .2s ease;
  }
  .toast-enter-from,
  .toast-leave-to {
    transform: none;
  }
}
</style>
