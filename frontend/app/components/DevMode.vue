<script setup lang="ts">
/* Dev Mode — the "hacker focus" environment.
   Black canvas, Olwen + tendrils only, project picker. Pick one and a
   terminal opens cwd'd into that project. */
import { computed, nextTick, onMounted, ref } from 'vue'
import OlwenEntity from './OlwenEntity.vue'
import TerminalApp from './TerminalApp.vue'
import type { GhProject, LocalProject } from '../composables/useDevMode'

const emit = defineEmits<{ close: [] }>()

const { projects } = useDevMode()

const loading = ref(true)
const local = ref<LocalProject[]>([])
const github = ref<GhProject[]>([])
const homeDir = ref('')
const tab = ref<'local' | 'github'>('local')
const filter = ref('')
const entered = ref(false)
const error = ref('')

// Terminal session — when a local project is picked
const terminal = ref<{ cwd: string; title: string; autoStart: string | null } | null>(null)

async function openInFinder(path: string) {
  const apiBase = useRuntimeConfig().public.apiBase as string
  const token = localStorage.getItem('olwen_access') || ''
  try {
    await fetch(`${apiBase}/api/devmode/open-in-finder`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ path }),
    })
  } catch { /* non-fatal */ }
}

// Banner text typed out like a TTY boot sequence
const banner = ref('')
const BANNER_LINES = [
  '[OLWEN] dev-mode :: focus channel engaged',
  '[OLWEN] enumerating workspace…',
  '[OLWEN] github sync OK',
  '[OLWEN] standing by.',
]
async function typeBanner() {
  for (const line of BANNER_LINES) {
    for (const ch of line) {
      banner.value += ch
      await new Promise(r => setTimeout(r, 12))
    }
    banner.value += '\n'
    await new Promise(r => setTimeout(r, 90))
  }
}

const filteredLocal = computed(() => {
  if (!filter.value) return local.value
  const q = filter.value.toLowerCase()
  return local.value.filter(p => p.name.toLowerCase().includes(q) || p.rel.toLowerCase().includes(q))
})
const filteredGithub = computed(() => {
  if (!filter.value) return github.value
  const q = filter.value.toLowerCase()
  return github.value.filter(r => r.name.toLowerCase().includes(q)
    || r.full_name.toLowerCase().includes(q)
    || (r.description || '').toLowerCase().includes(q)
    || (r.language || '').toLowerCase().includes(q))
})

function pickLocal(p: LocalProject) {
  // 1. Open the project folder in the host's Finder
  openInFinder(p.path)
  // 2. Open the terminal cd'd to the project, auto-running Claude Code in
  //    --dangerously-skip-permissions (yolo) mode so it doesn't ask before edits.
  terminal.value = {
    cwd: p.path,
    title: `Terminal · ${p.name}`,
    autoStart: 'claude --dangerously-skip-permissions',
  }
}
function pickGithub(r: GhProject) {
  try { navigator.clipboard.writeText(`git clone ${r.clone_url}`) } catch { /* */ }
  terminal.value = {
    cwd: homeDir.value,
    title: `Terminal · clone ${r.name}`,
    autoStart: null,
  }
}
function closeTerminal() { terminal.value = null }

async function load() {
  loading.value = true; error.value = ''
  try {
    const r = await projects()
    local.value = r.local
    github.value = r.github
    homeDir.value = r.home
    if (!local.value.length && github.value.length) tab.value = 'github'
  } catch (e: unknown) {
    error.value = (e as { data?: { detail?: string } })?.data?.detail || 'Could not load projects.'
  } finally { loading.value = false }
}

function ago(iso?: string | null): string {
  if (!iso) return ''
  const t = new Date(iso).getTime()
  if (!isFinite(t)) return ''
  const s = Math.max(0, (Date.now() - t) / 1000)
  if (s < 3600) return `${Math.floor(s / 60)}m`
  if (s < 86400) return `${Math.floor(s / 3600)}h`
  if (s < 30 * 86400) return `${Math.floor(s / 86400)}d`
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

function close() {
  entered.value = false
  setTimeout(() => emit('close'), 380)
}

// ESC to exit
function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape' && !terminal.value) close()
}

onMounted(async () => {
  requestAnimationFrame(() => { entered.value = true })
  document.addEventListener('keydown', onKey)
  typeBanner()
  await nextTick()
  load()
})
</script>

<template>
  <div class="dev" :class="{ entered }">
    <!-- subtle code-rain / grid backdrop -->
    <div class="rain" aria-hidden="true">
      <div class="grid" />
      <div class="scan" />
    </div>

    <!-- top-left: boot banner -->
    <pre class="banner">{{ banner }}<span class="banner__cursor">▍</span></pre>

    <!-- top-right: exit -->
    <button class="exit" title="Exit dev mode (Esc)" @click="close">
      <span>exit</span><span class="exit__key">esc</span>
    </button>

    <!-- center column: Olwen + project picker -->
    <div class="stage">
      <div class="entity-frame" data-olwen>
        <OlwenEntity state="idle" />
      </div>

      <div class="prompt">
        <span class="prompt__caret">&gt;</span>
        <span class="prompt__text">choose your battleground</span>
      </div>

      <!-- tabs -->
      <div class="tabs">
        <button class="tab" :class="{ active: tab === 'local' }" @click="tab = 'local'">
          <span>local</span>
          <span class="tab__count">{{ local.length }}</span>
        </button>
        <button class="tab" :class="{ active: tab === 'github' }" @click="tab = 'github'">
          <span>github</span>
          <span class="tab__count">{{ github.length }}</span>
        </button>
        <input v-model="filter" class="search" placeholder="filter…" spellcheck="false">
      </div>

      <div v-if="loading" class="loading">
        <span class="loading__dot" /><span class="loading__dot" /><span class="loading__dot" />
        <span class="loading__text">scanning workspace…</span>
      </div>

      <p v-else-if="error" class="error">{{ error }}</p>

      <!-- LOCAL -->
      <ul v-else-if="tab === 'local'" class="list">
        <li v-if="!filteredLocal.length" class="empty">
          <span>no local git repos found.</span><br>
          <span class="empty__sub">tried: ~/Documents/projects, ~/code, ~/Workspace, ~/Developer …</span>
        </li>
        <li v-for="p in filteredLocal" :key="p.key" class="row" @click="pickLocal(p)">
          <span class="row__glyph">▢</span>
          <div class="row__main">
            <span class="row__name">{{ p.name }}</span>
            <span class="row__sub">{{ p.rel }}</span>
          </div>
          <span class="row__age">{{ ago(p.modified) }}</span>
          <span class="row__cta">enter →</span>
        </li>
      </ul>

      <!-- GITHUB -->
      <ul v-else class="list">
        <li v-if="!filteredGithub.length" class="empty">
          <span>no github repos visible.</span><br>
          <span class="empty__sub">connect github in settings → connections.</span>
        </li>
        <li v-for="r in filteredGithub" :key="r.key" class="row row--gh" @click="pickGithub(r)">
          <span class="row__glyph">⌗</span>
          <div class="row__main">
            <span class="row__name">{{ r.full_name }} <span v-if="r.private" class="lock">private</span></span>
            <span class="row__sub">
              <span v-if="r.language" class="lang">{{ r.language }}</span>
              <span v-if="r.description" class="desc">{{ r.description }}</span>
            </span>
          </div>
          <span class="row__stars">★ {{ r.stars }}</span>
          <span class="row__age">{{ ago(r.pushed_at) }}</span>
          <span class="row__cta">clone →</span>
        </li>
      </ul>
    </div>

    <!-- footer hint -->
    <div class="footer">
      <span class="footer__bit">tap a project to enter</span>
      <span class="footer__bit">⌘+K filter</span>
      <span class="footer__bit">esc to exit</span>
    </div>

    <!-- The terminal becomes available when a project is chosen -->
    <TerminalApp
      v-if="terminal"
      :cwd="terminal.cwd"
      :title="terminal.title"
      :auto-start="terminal.autoStart"
      @close="closeTerminal"
    />
  </div>
</template>

<style scoped>
.dev {
  position: fixed; inset: 0; z-index: 80;
  background: #000;
  color: #5EEAD4;
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  opacity: 0; transition: opacity .35s ease;
  overflow: hidden;
}
.dev.entered { opacity: 1; }

/* faint grid + scanline */
.rain { position: absolute; inset: 0; pointer-events: none; }
.grid {
  position: absolute; inset: 0;
  background:
    linear-gradient(rgba(94,234,212,0.05) 1px, transparent 1px) 0 0 / 40px 40px,
    linear-gradient(90deg, rgba(94,234,212,0.05) 1px, transparent 1px) 0 0 / 40px 40px;
  mask-image: radial-gradient(ellipse at center, rgba(0,0,0,0.95) 30%, rgba(0,0,0,0.4) 80%);
}
.scan {
  position: absolute; inset: 0;
  background: repeating-linear-gradient(180deg, rgba(94,234,212,0.025) 0px, rgba(94,234,212,0.025) 1px, transparent 1px, transparent 3px);
  pointer-events: none;
  animation: scanmove 12s linear infinite;
}
@keyframes scanmove { from { background-position: 0 0; } to { background-position: 0 100px; } }

/* boot banner top-left */
.banner {
  position: absolute; top: 20px; left: 24px; margin: 0;
  font-size: 11px; line-height: 1.55; color: rgba(94,234,212,0.6);
  white-space: pre; pointer-events: none;
}
.banner__cursor { color: #5EEAD4; animation: blink 1s step-start infinite; }
@keyframes blink { 50% { opacity: 0; } }

/* exit top-right */
.exit {
  position: absolute; top: 18px; right: 22px;
  display: flex; align-items: center; gap: 8px;
  padding: 6px 12px; border-radius: 999px;
  border: 0.5px solid rgba(94,234,212,0.35); background: transparent;
  color: rgba(94,234,212,0.7); cursor: pointer;
  font-family: inherit; font-size: 10px; letter-spacing: 1.4px; text-transform: uppercase;
}
.exit:hover { color: #ECFEFF; border-color: #5EEAD4; }
.exit__key { font-size: 8.5px; padding: 1px 6px; border-radius: 4px; border: 0.5px solid rgba(94,234,212,0.4); }

/* center stage */
.stage {
  position: relative;
  width: min(880px, 92vw); max-height: 86vh;
  margin: 0 auto;
  padding: 60px 0 20px;
  display: flex; flex-direction: column; align-items: stretch;
  height: 100vh;
}
.entity-frame {
  width: 200px; height: 200px; margin: 0 auto 18px;
  filter: drop-shadow(0 0 32px rgba(94,234,212,0.3));
}

.prompt {
  display: flex; align-items: center; justify-content: center; gap: 12px;
  margin: 4px 0 24px;
  font-size: 19px; color: #ECFEFF; letter-spacing: 1.2px;
}
.prompt__caret { color: #5EEAD4; animation: blink 1.2s step-start infinite; }
.prompt__text { font-weight: 200; text-transform: lowercase; }

/* tabs row */
.tabs { display: flex; align-items: center; gap: 8px; margin-bottom: 14px; }
.tab {
  display: flex; align-items: center; gap: 8px;
  padding: 7px 14px; border-radius: 8px; cursor: pointer;
  border: 0.5px solid rgba(94,234,212,0.25); background: transparent;
  color: rgba(94,234,212,0.7);
  font-family: inherit; font-size: 11px; letter-spacing: 1.4px; text-transform: uppercase;
  transition: all .15s ease;
}
.tab:hover { color: #ECFEFF; border-color: #5EEAD4; }
.tab.active { background: rgba(94,234,212,0.1); border-color: #5EEAD4; color: #ECFEFF; }
.tab__count { font-size: 9px; padding: 2px 6px; border-radius: 999px; background: rgba(94,234,212,0.16); color: #5EEAD4; }

.search {
  flex: 1; margin-left: 8px;
  padding: 8px 14px; border-radius: 8px;
  border: 0.5px solid rgba(94,234,212,0.18); background: rgba(0,0,0,0.7);
  color: #5EEAD4; font-family: inherit; font-size: 12px; outline: none;
}
.search:focus { border-color: #5EEAD4; box-shadow: 0 0 16px rgba(94,234,212,0.18); }
.search::placeholder { color: rgba(94,234,212,0.4); }

/* project list */
.list { list-style: none; margin: 0; padding: 0; overflow-y: auto; flex: 1; display: flex; flex-direction: column; gap: 4px; }
.list::-webkit-scrollbar { width: 4px; }
.list::-webkit-scrollbar-thumb { background: rgba(94,234,212,0.25); border-radius: 3px; }

.row {
  display: flex; align-items: center; gap: 12px;
  padding: 12px 14px; border-radius: 8px; cursor: pointer;
  border: 0.5px solid transparent;
  transition: all .12s ease;
  position: relative;
}
.row:hover { background: rgba(94,234,212,0.08); border-color: rgba(94,234,212,0.3); padding-left: 16px; }
.row::before {
  content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 2px;
  background: transparent; transition: background .12s ease;
}
.row:hover::before { background: #5EEAD4; box-shadow: 0 0 12px #5EEAD4; }

.row__glyph { font-size: 13px; color: #5EEAD4; width: 18px; text-align: center; }
.row--gh .row__glyph { color: #A78BFA; }
.row__main { flex: 1; display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.row__name { font-size: 13px; color: #ECFEFF; letter-spacing: 0.3px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.row__sub { font-size: 10.5px; color: rgba(94,234,212,0.55); display: flex; align-items: center; gap: 8px; }
.lang { padding: 1px 6px; border-radius: 4px; background: rgba(167,139,250,0.15); color: #C4B5FD; font-size: 9.5px; letter-spacing: 0.5px; }
.desc { color: rgba(167,243,208,0.55); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.lock { font-size: 8.5px; padding: 1px 5px; border-radius: 4px; background: rgba(251,191,36,0.15); color: #FBBF24; letter-spacing: 0.5px; margin-left: 6px; }
.row__stars { font-size: 10.5px; color: rgba(251,191,36,0.7); }
.row__age { font-size: 10.5px; color: rgba(94,234,212,0.45); min-width: 36px; text-align: right; }
.row__cta {
  font-size: 9.5px; letter-spacing: 1.4px; text-transform: uppercase;
  color: rgba(94,234,212,0.4);
  padding: 3px 10px; border-radius: 999px; border: 0.5px solid rgba(94,234,212,0.2);
  opacity: 0; transition: opacity .15s ease;
}
.row:hover .row__cta { opacity: 1; color: #5EEAD4; border-color: #5EEAD4; }

.empty { text-align: center; padding: 36px 16px; color: rgba(94,234,212,0.55); font-size: 12.5px; line-height: 1.6; }
.empty__sub { font-size: 10.5px; color: rgba(94,234,212,0.4); }

.loading { display: flex; align-items: center; gap: 10px; padding: 30px 0; color: rgba(94,234,212,0.65); }
.loading__dot { width: 6px; height: 6px; border-radius: 50%; background: #5EEAD4; box-shadow: 0 0 8px #5EEAD4; animation: bob 1.2s ease-in-out infinite; }
.loading__dot:nth-child(2) { animation-delay: .18s; }
.loading__dot:nth-child(3) { animation-delay: .36s; }
.loading__text { font-size: 10.5px; letter-spacing: 1.4px; text-transform: uppercase; }
@keyframes bob { 0%,100% { opacity: 0.4; transform: translateY(0); } 50% { opacity: 1; transform: translateY(-4px); } }

.error { color: #FCA5A5; font-size: 12px; border-left: 2px solid #F87171; padding-left: 9px; margin: 14px 0; }

.footer {
  position: absolute; bottom: 16px; left: 0; right: 0;
  display: flex; align-items: center; justify-content: center; gap: 18px;
  font-size: 9.5px; letter-spacing: 1.5px; text-transform: uppercase;
  color: rgba(94,234,212,0.4);
}
.footer__bit { padding: 0 10px; border-right: 0.5px solid rgba(94,234,212,0.15); }
.footer__bit:last-child { border-right: none; }
</style>
