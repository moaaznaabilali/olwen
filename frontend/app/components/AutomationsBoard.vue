<script setup lang="ts">
/* Automations overlay — a quick-access, full-screen shell around the same
 * WorkflowsStudio that lives in Settings → Workflows. One builder, two doors.
 * Opened from the dashboard clock icon. Escape closes. */
import { onBeforeUnmount, onMounted, ref } from 'vue'
import WorkflowsStudio from './WorkflowsStudio.vue'

const emit = defineEmits<{ close: [] }>()
const entered = ref(false)

function close() { entered.value = false; setTimeout(() => emit('close'), 250) }
function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape' && !(document.activeElement as HTMLElement)?.closest?.('input, textarea, select')) close()
}

onMounted(() => {
  requestAnimationFrame(() => { entered.value = true })
  document.addEventListener('keydown', onKey)
})
onBeforeUnmount(() => document.removeEventListener('keydown', onKey))
</script>

<template>
  <div class="ab" :class="{ entered }">
    <header class="ab-bar">
      <div class="ab-brand"><span class="ab-dot" /> WORKFLOWS</div>
      <div class="ab-meta">scheduled automations</div>
      <button class="ab-x" title="Close (Esc)" @click="close">✕</button>
    </header>
    <div class="ab-body">
      <div class="ab-col">
        <WorkflowsStudio />
      </div>
    </div>
  </div>
</template>

<style scoped>
.ab { position: fixed; inset: 0; z-index: 70; background: var(--bg); color: var(--text);
  font-family: system-ui, -apple-system, 'Segoe UI', sans-serif; display: flex; flex-direction: column;
  opacity: 0; transition: opacity .25s ease; }
.ab.entered { opacity: 1; }
.ab-bar { display: flex; align-items: center; gap: 1rem; padding: .9rem 1.4rem; border-bottom: 1px solid var(--border-strong); }
.ab-brand { display: flex; align-items: center; gap: .55rem; font-family: 'JetBrains Mono', monospace; letter-spacing: .3em; font-size: .82rem; color: var(--accent); }
.ab-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--accent); box-shadow: var(--glow); }
.ab-meta { font-family: 'JetBrains Mono', monospace; font-size: .72rem; color: var(--text-muted); letter-spacing: .06em; }
.ab-x { margin-left: auto; background: none; border: 1px solid var(--border-strong); color: var(--text-muted); border-radius: 8px; width: 30px; height: 30px; cursor: pointer; font-size: .9rem; }
.ab-x:hover { color: #FCA5A5; border-color: #7F1D1D; }
.ab-body { flex: 1; overflow: auto; padding: 1.4rem; }
.ab-col { width: min(760px, 100%); margin: 0 auto; }
</style>
