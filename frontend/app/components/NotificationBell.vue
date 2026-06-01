<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref } from 'vue'
import { useNotifications, type OlwenNotification } from '~/composables/useNotifications'

const { items, unread, markRead, markAllRead } = useNotifications()

const open = ref(false)
const pulsing = ref(false)
const root = ref<HTMLElement | null>(null)

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
      return 'M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z'
    case 'whatsapp':
      return 'M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z'
    case 'email':
      return 'M4 4h16a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2zm18 2l-10 7L2 6'
    default:
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

const badge = computed(() => (unread.value > 99 ? '99+' : String(unread.value)))

// One-shot pulse whenever the unread count climbs.
watch(unread, (n, o) => {
  if (n > (o ?? 0)) {
    pulsing.value = false
    requestAnimationFrame(() => { pulsing.value = true })
  }
})

function toggle(): void {
  open.value = !open.value
}
function onRow(n: OlwenNotification): void {
  if (!n.read) markRead(n.id)
}

function onDocClick(e: MouseEvent): void {
  if (!open.value) return
  if (root.value && !root.value.contains(e.target as Node)) open.value = false
}
function onKey(e: KeyboardEvent): void {
  if (e.key === 'Escape' && open.value) open.value = false
}

onMounted(() => {
  document.addEventListener('click', onDocClick)
  document.addEventListener('keydown', onKey)
})
onBeforeUnmount(() => {
  document.removeEventListener('click', onDocClick)
  document.removeEventListener('keydown', onKey)
})
</script>

<template>
  <div ref="root" class="bellwrap">
    <button
      class="bell"
      type="button"
      :class="{ 'bell--on': open }"
      :aria-label="unread > 0 ? `Notifications, ${unread} unread` : 'Notifications'"
      :aria-expanded="open"
      @click.stop="toggle"
    >
      <svg viewBox="0 0 24 24" width="15" height="15" fill="none"
           stroke="currentColor" stroke-width="1.7"
           stroke-linecap="round" stroke-linejoin="round">
        <path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" />
        <path d="M13.7 21a2 2 0 0 1-3.4 0" />
      </svg>
      <span
        v-if="unread > 0"
        class="bell__badge"
        :class="{ 'bell__badge--pulse': pulsing }"
        @animationend="pulsing = false"
      >{{ badge }}</span>
    </button>

    <Transition name="panel">
      <div v-if="open" class="panel" role="dialog" aria-label="Notifications">
        <header class="panel__head">
          <span class="panel__title">Notifications</span>
          <button
            class="panel__markall"
            type="button"
            :disabled="unread === 0"
            @click="markAllRead()"
          >Mark all read</button>
        </header>

        <div v-if="items.length === 0" class="empty">
          <span class="empty__glyph" aria-hidden="true">
            <svg viewBox="0 0 24 24" width="22" height="22" fill="none"
                 stroke="currentColor" stroke-width="1.5"
                 stroke-linecap="round" stroke-linejoin="round">
              <path d="M12 3l1.8 4.7L18.5 9.5 13.8 11.3 12 16l-1.8-4.7L5.5 9.5l4.7-1.8L12 3z" />
            </svg>
          </span>
          <p class="empty__text">You're all caught up.</p>
        </div>

        <ul v-else class="list">
          <li
            v-for="n in items"
            :key="n.id"
            class="row"
            :class="{ 'row--unread': !n.read }"
            :style="{ '--k': accentFor(n.kind) }"
            @click="onRow(n)"
          >
            <span class="row__icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" width="14" height="14" fill="none"
                   stroke="currentColor" stroke-width="1.7"
                   stroke-linecap="round" stroke-linejoin="round">
                <path :d="iconFor(n.kind)" />
              </svg>
            </span>
            <div class="row__main">
              <div class="row__top">
                <span class="row__title">{{ n.title }}</span>
                <span class="row__time">{{ relativeTime(n.created_at) }}</span>
              </div>
              <p v-if="n.body" class="row__body">{{ n.body }}</p>
            </div>
            <span v-if="!n.read" class="row__dot" aria-label="unread" />
          </li>
        </ul>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.bellwrap {
  position: relative;
  display: inline-flex;
}

.bell {
  position: relative;
  width: 30px;
  height: 30px;
  border-radius: 999px;
  cursor: pointer;
  border: 0.5px solid var(--border-strong);
  background: var(--surface-2);
  color: var(--text-muted);
  display: grid;
  place-items: center;
  transition: color .2s ease, border-color .2s ease, background .2s ease;
}
.bell:hover,
.bell--on {
  color: var(--accent);
  border-color: var(--accent);
}

.bell__badge {
  position: absolute;
  top: -4px;
  right: -4px;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  border-radius: 999px;
  background: var(--accent);
  color: var(--bg);
  font-size: 10px;
  font-weight: 700;
  line-height: 16px;
  text-align: center;
  box-shadow: 0 0 0 2px var(--surface-solid);
}
.bell__badge--pulse {
  animation: badgePulse .5s cubic-bezier(0.34, 1.56, 0.64, 1);
}
@keyframes badgePulse {
  0% { transform: scale(0.5); }
  55% { transform: scale(1.3); }
  100% { transform: scale(1); }
}

.panel {
  position: absolute;
  top: calc(100% + 10px);
  right: 0;
  width: 340px;
  max-width: calc(100vw - 24px);
  max-height: 70vh;
  display: flex;
  flex-direction: column;
  border-radius: 14px;
  border: 1px solid var(--border-strong);
  background: var(--surface-solid);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  box-shadow:
    0 18px 50px -18px rgba(0, 0, 0, 0.6),
    0 0 0 1px color-mix(in srgb, var(--accent) 8%, transparent);
  overflow: hidden;
  z-index: 85;
}

.panel__head {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  border-bottom: 1px solid var(--border);
}
.panel__title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-strong);
}
.panel__markall {
  border: none;
  background: transparent;
  color: var(--accent);
  font-size: 11.5px;
  font-weight: 500;
  cursor: pointer;
  padding: 2px 4px;
  border-radius: 6px;
  transition: opacity .15s ease, background .15s ease;
}
.panel__markall:hover:not(:disabled) {
  background: color-mix(in srgb, var(--accent) 12%, transparent);
}
.panel__markall:disabled {
  color: var(--text-muted);
  opacity: 0.45;
  cursor: default;
}

.list {
  list-style: none;
  margin: 0;
  padding: 4px;
  overflow-y: auto;
  flex: 1 1 auto;
}

.row {
  position: relative;
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 12px 10px 10px;
  border-radius: 10px;
  cursor: pointer;
  transition: background .15s ease;
}
.row:hover {
  background: var(--surface-2);
}
.row--unread {
  background: color-mix(in srgb, var(--accent) 6%, transparent);
}
.row--unread:hover {
  background: color-mix(in srgb, var(--accent) 11%, transparent);
}

.row__icon {
  flex: 0 0 auto;
  width: 26px;
  height: 26px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  color: var(--k);
  background: color-mix(in srgb, var(--k) 13%, transparent);
  border: 1px solid color-mix(in srgb, var(--k) 26%, transparent);
}

.row__main {
  flex: 1 1 auto;
  min-width: 0;
}
.row__top {
  display: flex;
  align-items: baseline;
  gap: 8px;
}
.row__title {
  flex: 1 1 auto;
  min-width: 0;
  font-size: 12.5px;
  font-weight: 600;
  color: var(--text-strong);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.row__time {
  flex: 0 0 auto;
  font-size: 10px;
  color: var(--text-muted);
  opacity: 0.7;
}
.row__body {
  margin: 2px 0 0;
  font-size: 11.5px;
  line-height: 1.35;
  color: var(--text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.row__dot {
  flex: 0 0 auto;
  align-self: center;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--accent);
  box-shadow: var(--glow);
}

.empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 34px 20px 38px;
  text-align: center;
}
.empty__glyph {
  display: grid;
  place-items: center;
  width: 42px;
  height: 42px;
  border-radius: 50%;
  color: var(--accent);
  background: color-mix(in srgb, var(--accent) 10%, transparent);
  border: 1px solid var(--border);
}
.empty__text {
  margin: 0;
  font-size: 12.5px;
  color: var(--text-muted);
}

/* Panel open / close */
.panel-enter-active {
  transition: opacity .2s ease, transform .26s cubic-bezier(0.22, 1, 0.36, 1);
  transform-origin: top right;
}
.panel-leave-active {
  transition: opacity .14s ease, transform .14s ease;
  transform-origin: top right;
}
.panel-enter-from,
.panel-leave-to {
  opacity: 0;
  transform: translateY(-6px) scale(0.97);
}

@media (prefers-reduced-motion: reduce) {
  .panel-enter-active,
  .panel-leave-active {
    transition: opacity .15s ease;
  }
  .panel-enter-from,
  .panel-leave-to {
    transform: none;
  }
  .bell__badge--pulse {
    animation: none;
  }
}
</style>
