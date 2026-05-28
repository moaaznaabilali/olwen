<script setup lang="ts">
/**
 * WidgetPanel — the glass shell every dashboard widget sits in.
 * Header label (mono, uppercase, wide tracking) + optional badge, then a slot.
 */
withDefaults(defineProps<{
  title: string
  badge?: string | number
  accent?: string
}>(), {
  accent: '#5EEAD4',
})
</script>

<template>
  <section class="panel" :style="{ '--accent': accent }">
    <header class="panel__head">
      <span class="panel__title">{{ title }}</span>
      <span v-if="badge !== undefined" class="panel__badge">{{ badge }}</span>
    </header>
    <div class="panel__body">
      <slot />
    </div>
  </section>
</template>

<style scoped>
.panel {
  display: flex;
  flex-direction: column;
  min-height: 0;
  border-radius: 12px;
  border: 0.5px solid rgba(94, 234, 212, 0.12);
  background: rgba(8, 51, 68, 0.18);
  backdrop-filter: blur(8px);
  overflow: hidden;
}
.panel__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  border-bottom: 0.5px solid rgba(94, 234, 212, 0.10);
}
.panel__title {
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 10.5px;
  letter-spacing: 2px;
  text-transform: uppercase;
  color: var(--accent);
  opacity: 0.85;
}
.panel__badge {
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 10px;
  padding: 2px 8px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--accent) 18%, transparent);
  color: var(--accent);
}
.panel__body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 6px 14px 12px;
}
/* slim scrollbar */
.panel__body::-webkit-scrollbar { width: 5px; }
.panel__body::-webkit-scrollbar-thumb {
  background: rgba(94, 234, 212, 0.2);
  border-radius: 3px;
}
</style>
