<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import WidgetPanel from './WidgetPanel.vue'
import type { NewsItem } from '../composables/useNews'

const emit = defineEmits<{ openSettings: []; readWithOlwen: [] }>()
const { feed } = useNews()

const items = ref<NewsItem[]>([])
const loading = ref(true)
const topics = ref<string[]>([])
const error = ref('')

async function load() {
  loading.value = true; error.value = ''
  try {
    const r = await feed(10)
    items.value = r.items
    topics.value = r.topics
  } catch (e: unknown) {
    error.value = (e as { data?: { detail?: string } })?.data?.detail || 'Could not load news.'
  } finally { loading.value = false }
}

function ago(iso: string): string {
  if (!iso) return ''
  const t = new Date(iso).getTime()
  if (!isFinite(t)) return ''
  const s = Math.max(0, (Date.now() - t) / 1000)
  if (s < 60) return `${Math.floor(s)}s`
  if (s < 3600) return `${Math.floor(s / 60)}m`
  if (s < 86400) return `${Math.floor(s / 3600)}h`
  return `${Math.floor(s / 86400)}d`
}

const title = computed(() => topics.value.length
  ? topics.value.slice(0, 3).map(t => t === 'ai' ? 'AI' : t[0].toUpperCase() + t.slice(1)).join(' · ')
  : 'News')

onMounted(load)
</script>

<template>
  <WidgetPanel :title="title" badge="live" accent="#22D3EE">
    <div class="news">
      <p v-if="error" class="error">{{ error }}</p>

      <button
        v-if="!loading && items.length"
        class="read-cta"
        title="Olwen picks the top stories and reads them to you"
        @click="emit('readWithOlwen')"
      >
        <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12 3l1.8 4.7L18.5 9.5 13.8 11.3 12 16l-1.8-4.7L5.5 9.5l4.7-1.8L12 3z" />
        </svg>
        Read with Olwen
      </button>

      <ul v-if="loading" class="list">
        <li v-for="i in 3" :key="i" class="skel" :style="{ '--d': `${i * 90}ms` }">
          <span class="skel__tag" />
          <div class="skel__main"><span class="skel__line" /><span class="skel__line skel__line--sub" /></div>
        </li>
      </ul>

      <p v-else-if="!items.length" class="muted">
        No items right now. Add topics in Settings → News.
        <br>
        <button class="link" @click="emit('openSettings')">Pick topics →</button>
      </p>

      <ul v-else class="list">
        <li v-for="(n, i) in items" :key="i" class="row">
          <span class="row__tag">{{ n.tag }}</span>
          <div class="row__main">
            <a v-if="n.url" :href="n.url" target="_blank" rel="noopener" class="row__title">{{ n.title }}</a>
            <span v-else class="row__title">{{ n.title }}</span>
            <span class="row__meta">{{ n.source }}</span>
          </div>
          <span class="time">{{ ago(n.published) }}</span>
        </li>
      </ul>
    </div>
  </WidgetPanel>
</template>

<style scoped>
.news { display: flex; flex-direction: column; gap: 6px; }
.error { margin: 0; font-size: 11.5px; color: #FCA5A5; border-left: 2px solid #F87171; padding-left: 9px; }

.read-cta {
  display: flex; align-items: center; justify-content: center; gap: 8px;
  width: 100%; padding: 9px; border-radius: 9px; cursor: pointer; margin-bottom: 2px;
  border: 0.5px solid rgba(34,211,238,0.25); background: rgba(34,211,238,0.08);
  color: #22D3EE; font-family: 'JetBrains Mono', monospace; font-size: 10px;
  letter-spacing: 1.2px; text-transform: uppercase; transition: all .2s ease;
}
.read-cta:hover { background: rgba(34,211,238,0.18); border-color: #22D3EE; box-shadow: 0 0 14px rgba(34,211,238,0.18); }
.muted { margin: 8px 2px 0; font-size: 12px; color: var(--text-muted); line-height: 1.5; }
.link { background: transparent; border: none; cursor: pointer; color: #22D3EE; font-size: 12px; padding: 0; }
.link:hover { text-decoration: underline; }

.list { list-style: none; margin: 0; padding: 0; }
.row { display: flex; align-items: flex-start; gap: 9px; padding: 8px 2px; border-bottom: 0.5px solid var(--border); }
.row:last-child { border-bottom: none; }
.row__tag { font-family: 'JetBrains Mono', monospace; font-size: 8px; letter-spacing: 1px; text-transform: uppercase; color: #22D3EE; border: 0.5px solid rgba(34,211,238,0.35); border-radius: 999px; padding: 2px 6px; white-space: nowrap; margin-top: 1px; flex-shrink: 0; }
.row__main { flex: 1; display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.row__title { color: var(--text); font-size: 12.5px; line-height: 1.3; text-decoration: none; }
a.row__title:hover { color: var(--text-strong); text-decoration: underline; }
.row__meta { font-size: 10.5px; color: var(--text-muted); }
.time { font-family: 'JetBrains Mono', monospace; font-size: 10px; color: var(--text-muted); white-space: nowrap; }

.skel { display: flex; gap: 9px; padding: 8px 2px; opacity: 0; animation: in .35s ease forwards; animation-delay: var(--d); }
.skel__tag { width: 36px; height: 14px; border-radius: 999px; background: linear-gradient(90deg, rgba(34,211,238,0.06), rgba(34,211,238,0.25), rgba(34,211,238,0.06)); background-size: 220% 100%; animation: shim 1.5s ease-in-out infinite; flex-shrink: 0; }
.skel__main { flex: 1; display: flex; flex-direction: column; gap: 4px; }
.skel__line { height: 9px; border-radius: 3px; background: linear-gradient(90deg, rgba(34,211,238,0.06), rgba(34,211,238,0.25), rgba(34,211,238,0.06)); background-size: 220% 100%; animation: shim 1.5s ease-in-out infinite; }
.skel__line--sub { width: 50%; opacity: 0.55; }
@keyframes in { to { opacity: 1; } }
@keyframes shim { 0%,100% { background-position: 100% 0; } 50% { background-position: 0 0; } }
</style>
