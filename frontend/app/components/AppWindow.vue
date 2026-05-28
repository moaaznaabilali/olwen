<script setup lang="ts">
/* Floating, draggable, resizable window used by every Olwen app.
   Slots: header (left side), default (the app's body). */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

const props = withDefaults(defineProps<{
  title: string
  glyph?: string
  color?: string
  initialWidth?: number
  initialHeight?: number
}>(), {
  glyph: '▢', color: '#5EEAD4', initialWidth: 880, initialHeight: 520,
})
const emit = defineEmits<{ close: [] }>()

const rect = ref({
  x: 80, y: 100,
  w: props.initialWidth, h: props.initialHeight,
})
const maxed = ref(false)
const z = ref(50)

// Bring forward on click (simple z-bumping; future: shared z-stack composable)
function focusWindow() { z.value = Math.max(z.value, 100) }

// ---------- drag ----------
let dragOrigin = { mx: 0, my: 0, rx: 0, ry: 0 }
function onHeaderDown(e: PointerEvent) {
  if (maxed.value) return
  // Don't start a drag if the user is clicking a control inside the header
  // (close, maximize, tool buttons, etc.) — setPointerCapture would otherwise
  // swallow the subsequent click event before it reaches the button.
  const t = e.target as HTMLElement
  if (t.closest('button, input, select, textarea, [data-no-drag]')) return
  ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
  dragOrigin = { mx: e.clientX, my: e.clientY, rx: rect.value.x, ry: rect.value.y }
  window.addEventListener('pointermove', onHeaderMove)
  window.addEventListener('pointerup', onHeaderUp, { once: true })
}
function onHeaderMove(e: PointerEvent) {
  rect.value.x = Math.max(0, dragOrigin.rx + (e.clientX - dragOrigin.mx))
  rect.value.y = Math.max(0, dragOrigin.ry + (e.clientY - dragOrigin.my))
}
function onHeaderUp() {
  window.removeEventListener('pointermove', onHeaderMove)
}

// ---------- resize from SE corner ----------
let resizeOrigin = { mx: 0, my: 0, w: 0, h: 0 }
function onResizeDown(e: PointerEvent) {
  if (maxed.value) return
  e.stopPropagation()
  ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
  resizeOrigin = { mx: e.clientX, my: e.clientY, w: rect.value.w, h: rect.value.h }
  window.addEventListener('pointermove', onResizeMove)
  window.addEventListener('pointerup', onResizeUp, { once: true })
}
function onResizeMove(e: PointerEvent) {
  rect.value.w = Math.max(420, resizeOrigin.w + (e.clientX - resizeOrigin.mx))
  rect.value.h = Math.max(280, resizeOrigin.h + (e.clientY - resizeOrigin.my))
}
function onResizeUp() { window.removeEventListener('pointermove', onResizeMove) }

function toggleMax() { maxed.value = !maxed.value }

// keep window inside viewport on viewport resize
function onWinResize() {
  rect.value.x = Math.min(rect.value.x, window.innerWidth - rect.value.w - 8)
  rect.value.y = Math.min(rect.value.y, window.innerHeight - rect.value.h - 8)
}
onMounted(() => {
  rect.value.x = Math.max(40, Math.min(window.innerWidth - rect.value.w - 40, rect.value.x))
  window.addEventListener('resize', onWinResize)
})
onBeforeUnmount(() => window.removeEventListener('resize', onWinResize))

const style = computed(() => maxed.value
  ? { left: '0', top: '0', width: '100vw', height: '100vh', zIndex: z.value }
  : { left: rect.value.x + 'px', top: rect.value.y + 'px', width: rect.value.w + 'px', height: rect.value.h + 'px', zIndex: z.value }
)
</script>

<template>
  <div class="win" :class="{ maxed }" :style="style" @mousedown="focusWindow">
    <div class="win__head" :style="{ '--c': color }">
      <!-- DRAG REGION — only this captures pointers. Buttons stay outside. -->
      <div class="win__drag" @pointerdown="onHeaderDown">
        <span class="win__glyph">{{ glyph }}</span>
        <span class="win__title">{{ title }}</span>
      </div>
      <slot name="header" />
      <div class="win__btns">
        <button class="win__btn" :title="maxed ? 'Restore' : 'Maximize'" @click="toggleMax">{{ maxed ? '▢' : '▢' }}</button>
        <button class="win__btn win__btn--x" title="Close" @click="emit('close')">✕</button>
      </div>
    </div>
    <div class="win__body">
      <slot />
    </div>
    <div v-if="!maxed" class="win__resize" @pointerdown="onResizeDown" />
  </div>
</template>

<style scoped>
.win {
  position: fixed;
  display: flex; flex-direction: column;
  border-radius: 14px; overflow: hidden;
  background: rgba(8, 30, 38, 0.92);
  border: 0.5px solid rgba(94,234,212,0.25);
  box-shadow: 0 30px 80px rgba(0,0,0,0.6), 0 0 0 1px rgba(94,234,212,0.06), 0 0 36px rgba(94,234,212,0.08);
  backdrop-filter: blur(18px);
}
.win.maxed { border-radius: 0; border: none; }

.win__head {
  display: flex; align-items: center; gap: 10px;
  padding: 9px 12px;
  background: linear-gradient(180deg, rgba(94,234,212,0.08), rgba(94,234,212,0));
  border-bottom: 0.5px solid rgba(94,234,212,0.18);
  user-select: none;
}
.win__drag { display: flex; align-items: center; gap: 10px; cursor: grab; padding: 4px 0; }
.win__drag:active { cursor: grabbing; }
.win__glyph {
  width: 22px; height: 22px; display: grid; place-items: center;
  border-radius: 6px; background: rgba(2,6,10,0.5); border: 0.5px solid var(--c);
  color: var(--c); font-size: 12px;
}
.win__title { font-family: 'JetBrains Mono', monospace; font-size: 10.5px; letter-spacing: 1.4px; text-transform: uppercase; color: #ECFEFF; }
.win__btns { margin-left: auto; display: flex; gap: 4px; }
.win__btn {
  width: 24px; height: 24px; border-radius: 6px; display: grid; place-items: center;
  border: 0.5px solid rgba(167,243,208,0.18); background: transparent;
  color: rgba(167,243,208,0.6); cursor: pointer; font-size: 11px;
  transition: all .15s ease;
}
.win__btn:hover { border-color: #5EEAD4; color: #ECFEFF; }
.win__btn--x:hover { border-color: #F87171; color: #FCA5A5; }

.win__body { flex: 1; min-height: 0; overflow: hidden; background: #02060A; }

.win__resize {
  position: absolute; right: 0; bottom: 0; width: 18px; height: 18px;
  cursor: nwse-resize;
  background:
    linear-gradient(135deg, transparent 50%, rgba(94,234,212,0.55) 50%, rgba(94,234,212,0.55) 60%, transparent 60%),
    linear-gradient(135deg, transparent 70%, rgba(94,234,212,0.35) 70%, rgba(94,234,212,0.35) 80%, transparent 80%);
}
</style>
