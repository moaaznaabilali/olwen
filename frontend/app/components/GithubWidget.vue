<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import WidgetPanel from './WidgetPanel.vue'
import type { GhEvent } from '../composables/useGithub'

const emit = defineEmits<{ openSettings: [] }>()
const { configured, account, start, events: fetchEvents } = useGithub()

const oauthAvailable = ref(false)
const connected = ref(false)
const login = ref('')
const events = ref<GhEvent[]>([])
const loading = ref(false)
const error = ref('')

const glyph: Record<string, string> = { push: '↑', pr: '⇄', issue: '◉', create: '✶' }

async function load() {
  loading.value = true; error.value = ''
  try {
    const [cfg, acc] = await Promise.all([configured(), account()])
    oauthAvailable.value = cfg.configured
    connected.value = acc.connected
    login.value = acc.login || ''
    if (connected.value) {
      const r = await fetchEvents(8)
      events.value = r.events
    }
  } catch (e: unknown) {
    error.value = (e as { data?: { detail?: string } })?.data?.detail || 'Could not load GitHub.'
  } finally { loading.value = false }
}

async function connect() {
  try {
    const r = await start()
    window.location.href = r.auth_url
  } catch (e: unknown) {
    error.value = (e as { data?: { detail?: string } })?.data?.detail || 'GitHub OAuth not configured.'
  }
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

const count = computed(() => events.value.length)
onMounted(load)
</script>

<template>
  <WidgetPanel title="GitHub" :badge="count || undefined" accent="#A78BFA">
    <div class="gh">
      <p v-if="error" class="error">{{ error }}</p>

      <template v-if="!connected && !loading">
        <p class="empty">Connect GitHub to see your real push activity, PRs, and issues.</p>
        <button class="cta" @click="emit('openSettings')">
          <svg width="13" height="13" viewBox="0 0 16 16" fill="currentColor"><path d="M8 0C3.58 0 0 3.58 0 8a8 8 0 0 0 5.47 7.59c.4.07.55-.17.55-.38v-1.5c-2.22.48-2.69-1.06-2.69-1.06-.36-.92-.89-1.16-.89-1.16-.73-.5.05-.49.05-.49.81.06 1.24.83 1.24.83.72 1.23 1.88.88 2.34.67.07-.52.28-.88.5-1.08-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.13 0 0 .67-.21 2.2.82a7.5 7.5 0 0 1 4 0c1.53-1.04 2.2-.82 2.2-.82.44 1.11.16 1.93.08 2.13.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.74.54 1.5v2.22c0 .21.15.46.55.38A8 8 0 0 0 16 8c0-4.42-3.58-8-8-8z"/></svg>
          Connect GitHub · 1 min
        </button>
        <p class="muted">Olwen will walk you through it — no terminal, no env vars.</p>
      </template>

      <template v-else-if="connected">
        <p v-if="login" class="who">@{{ login }}</p>

        <ul v-if="loading" class="list">
          <li v-for="i in 3" :key="i" class="skel" :style="{ '--d': `${i * 80}ms` }">
            <span class="skel__icon" />
            <div class="skel__main"><span class="skel__line" /><span class="skel__line skel__line--short" /></div>
          </li>
        </ul>

        <p v-else-if="!events.length" class="muted">No recent public activity.</p>

        <ul v-else class="list">
          <li v-for="(e, i) in events" :key="i" class="ev" :class="`k-${e.kind}`">
            <span class="ev__icon">{{ glyph[e.kind] || '·' }}</span>
            <div class="ev__main">
              <span class="ev__msg">{{ e.msg }}</span>
              <span class="ev__repo">{{ e.repo }}</span>
            </div>
            <span class="time">{{ ago(e.when) }}</span>
          </li>
        </ul>
      </template>
    </div>
  </WidgetPanel>
</template>

<style scoped>
.gh { display: flex; flex-direction: column; gap: 8px; }
.error { margin: 0; font-size: 11.5px; color: #FCA5A5; border-left: 2px solid #F87171; padding-left: 9px; }
.empty { margin: 6px 2px 10px; font-size: 12.5px; line-height: 1.5; color: rgba(167,243,208,0.55); }
.muted { margin: 4px 2px 0; font-size: 11px; color: rgba(167,243,208,0.4); line-height: 1.5; }
.muted code { font-family: 'JetBrains Mono', monospace; font-size: 10.5px; color: #A78BFA; }

.cta {
  display: inline-flex; align-items: center; gap: 9px; justify-content: center;
  padding: 9px; border-radius: 9px; cursor: pointer; width: 100%;
  border: 0.5px solid rgba(167,139,250,0.4); background: rgba(167,139,250,0.12);
  color: #C4B5FD; font-family: 'JetBrains Mono', monospace; font-size: 10px;
  letter-spacing: 1.2px; text-transform: uppercase;
}
.cta:hover { background: rgba(167,139,250,0.22); border-color: #A78BFA; color: #ECFEFF; }

.who { margin: 0 0 2px; font-family: 'JetBrains Mono', monospace; font-size: 10px; letter-spacing: 1.4px; color: rgba(167,139,250,0.7); }

.list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; }
.ev { display: flex; align-items: flex-start; gap: 9px; padding: 8px 2px; border-bottom: 0.5px solid rgba(255,255,255,0.04); }
.ev:last-child { border-bottom: none; }
.ev__icon { color: #A78BFA; font-family: monospace; flex-shrink: 0; margin-top: 1px; }
.ev.k-pr .ev__icon { color: #67E8F9; }
.ev.k-issue .ev__icon { color: #FBBF24; }
.ev.k-create .ev__icon { color: #5EEAD4; }
.ev__main { flex: 1; display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.ev__msg { font-size: 12.5px; color: #DCFCF5; line-height: 1.35; }
.ev__repo { font-family: 'JetBrains Mono', monospace; font-size: 10px; color: rgba(167,139,250,0.6); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.time { font-family: 'JetBrains Mono', monospace; font-size: 10px; color: rgba(167,243,208,0.4); white-space: nowrap; }

.skel { display: flex; gap: 9px; padding: 8px 2px; opacity: 0; animation: skelin .35s ease forwards; animation-delay: var(--d); }
.skel__icon { width: 8px; height: 8px; border-radius: 2px; background: rgba(167,139,250,0.25); flex-shrink: 0; margin-top: 6px; }
.skel__main { flex: 1; display: flex; flex-direction: column; gap: 4px; }
.skel__line { height: 9px; border-radius: 3px;
  background: linear-gradient(90deg, rgba(167,139,250,0.06) 0%, rgba(167,139,250,0.25) 50%, rgba(167,139,250,0.06) 100%);
  background-size: 220% 100%; animation: shim 1.5s ease-in-out infinite; }
.skel__line--short { width: 60%; opacity: 0.6; }
@keyframes skelin { to { opacity: 1; } }
@keyframes shim { 0%,100% { background-position: 100% 0; } 50% { background-position: 0 0; } }
</style>
