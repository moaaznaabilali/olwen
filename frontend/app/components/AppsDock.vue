<script setup lang="ts">
/* The Apps Dock — bottom-pinned, expandable launcher.
   Collapsed: a single ⊞ button.
   Expanded: a row of glyph tiles, one per app in the catalog. */
import { computed, onMounted, ref } from 'vue'

const { catalog, open, launch, loadCatalog, isOpen } = useApps()
const expanded = ref(false)

const visibleApps = computed(() => catalog.value.length ? catalog.value : [])

function pick(key: string, live: boolean) {
  if (!live) return
  launch(key)
  expanded.value = false
}

onMounted(() => { loadCatalog() })
</script>

<template>
  <div class="dock-anchor">
    <Transition name="dock">
      <div v-if="expanded" class="dock">
        <button
          v-for="a in visibleApps"
          :key="a.key"
          class="tile"
          :class="{ disabled: !a.live, on: isOpen(a.key) }"
          :style="{ '--c': a.color }"
          :title="a.live ? a.description : `${a.description} (coming soon)`"
          @click="pick(a.key, a.live)"
        >
          <span class="tile__glyph">{{ a.glyph }}</span>
          <span class="tile__name">{{ a.name }}</span>
          <span v-if="!a.live" class="tile__chip">Soon</span>
        </button>
      </div>
    </Transition>

    <button class="trigger" :class="{ open: expanded || open.length }" :title="expanded ? 'Close dock' : 'Olwen apps'" @click="expanded = !expanded">
      <span class="trigger__glyph">⊞</span>
      <span v-if="open.length" class="trigger__count">{{ open.length }}</span>
    </button>
  </div>
</template>

<style scoped>
.dock-anchor { position: fixed; bottom: 22px; left: 50%; transform: translateX(-50%); z-index: 55; display: flex; flex-direction: column; align-items: center; gap: 10px; }

.dock {
  display: flex; gap: 10px;
  padding: 10px 12px; border-radius: 18px;
  background: rgba(8,30,38,0.85); backdrop-filter: blur(18px);
  border: 0.5px solid rgba(94,234,212,0.22);
  box-shadow: 0 24px 60px rgba(0,0,0,0.5), 0 0 28px rgba(94,234,212,0.1);
}

.tile {
  position: relative;
  display: flex; flex-direction: column; align-items: center; gap: 4px;
  width: 76px; padding: 10px 8px; border-radius: 12px; cursor: pointer;
  border: 0.5px solid rgba(94,234,212,0.16); background: rgba(2,6,10,0.5);
  transition: all .2s ease;
}
.tile:hover { border-color: var(--c, #5EEAD4); transform: translateY(-3px); box-shadow: 0 10px 24px rgba(0,0,0,0.4), 0 0 22px color-mix(in srgb, var(--c, #5EEAD4) 35%, transparent); }
.tile.on { border-color: var(--c); background: color-mix(in srgb, var(--c) 12%, rgba(2,6,10,0.5)); }
.tile.disabled { opacity: 0.45; cursor: not-allowed; }
.tile.disabled:hover { transform: none; box-shadow: none; }

.tile__glyph {
  width: 38px; height: 38px; display: grid; place-items: center;
  border-radius: 10px; background: color-mix(in srgb, var(--c) 14%, rgba(2,6,10,0.6));
  border: 0.5px solid color-mix(in srgb, var(--c) 32%, transparent);
  color: var(--c); font-size: 19px; line-height: 1;
}
.tile__name { font-family: 'JetBrains Mono', monospace; font-size: 9px; letter-spacing: 1px; text-transform: uppercase; color: #DCFCF5; }
.tile__chip {
  position: absolute; top: -6px; right: -6px;
  font-family: 'JetBrains Mono', monospace; font-size: 8px; letter-spacing: 1px; text-transform: uppercase;
  padding: 2px 6px; border-radius: 999px; background: rgba(251,191,36,0.18); border: 0.5px solid rgba(251,191,36,0.45); color: #FBBF24;
}

.trigger {
  position: relative;
  width: 46px; height: 46px; border-radius: 999px;
  display: grid; place-items: center; cursor: pointer;
  border: 0.5px solid rgba(94,234,212,0.3);
  background: rgba(8,30,38,0.85); backdrop-filter: blur(18px);
  color: #5EEAD4;
  box-shadow: 0 12px 32px rgba(0,0,0,0.4), 0 0 18px rgba(94,234,212,0.15);
  transition: all .2s ease;
}
.trigger:hover { transform: translateY(-2px); box-shadow: 0 14px 36px rgba(0,0,0,0.5), 0 0 28px rgba(94,234,212,0.25); border-color: #5EEAD4; color: #ECFEFF; }
.trigger.open { background: #5EEAD4; color: #02060A; border-color: #5EEAD4; box-shadow: 0 0 24px rgba(94,234,212,0.5); }
.trigger__glyph { font-size: 19px; line-height: 1; }
.trigger__count {
  position: absolute; top: -3px; right: -3px;
  min-width: 18px; height: 18px; padding: 0 5px; border-radius: 999px;
  background: #F472B6; color: #02060A;
  font-family: 'JetBrains Mono', monospace; font-size: 9px; font-weight: 600;
  display: grid; place-items: center;
}

.dock-enter-active, .dock-leave-active { transition: opacity .25s ease, transform .3s cubic-bezier(.22,.7,.36,1); }
.dock-enter-from, .dock-leave-to { opacity: 0; transform: translateY(8px) scale(0.95); }
</style>
