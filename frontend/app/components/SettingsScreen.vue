<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import OlwenEntity from './OlwenEntity.vue'
import type { OlwenSettings, Provider } from '../composables/useSettings'
import type { OlwenMemory } from '../composables/useMemory'
import type { CatalogSkill, CustomSkill } from '../composables/useSkills'
import type { EmailAccount } from '../composables/useEmail'

const emit = defineEmits<{ close: [] }>()

type Section = 'connections' | 'dashboard' | 'voice' | 'memory' | 'skills' | 'email' | 'news'
// shared with DashboardView so post-OAuth can open us straight to "email"
const initialSection = useState<string>('settings:section', () => 'connections')
const section = ref<Section>((initialSection.value as Section) || 'connections')
initialSection.value = 'connections' // consume the hint
const nav: { key: Section, label: string, sub: string, glyph: string }[] = [
  { key: 'connections', label: 'Connections', sub: 'AI brain · GitHub',         glyph: '⊙' },
  { key: 'dashboard',   label: 'Dashboard',   sub: 'pick your widgets',          glyph: '▦' },
  { key: 'voice',       label: 'Voice',       sub: 'speech in & out',            glyph: '◜' },
  { key: 'email',       label: 'Email',       sub: 'inbox & accounts',           glyph: '✉' },
  { key: 'news',        label: 'News',        sub: 'topics you follow',          glyph: '✦' },
  { key: 'memory',      label: 'Memory',      sub: 'what Olwen knows',           glyph: '◈' },
  { key: 'skills',      label: 'Skills',      sub: 'marketplace & custom',       glyph: '⌗' },
]
const error = ref('')

/* ---- AI connections ---- */
const { fetchSettings, connectProvider, disconnectProvider, selectProvider, updateVoice, updateEmailPrefs, updateDashboard, updateNews } = useSettings()
const settings = ref<OlwenSettings | null>(null)
const busy = ref<Provider | null>(null)
const keyInput = reactive<Record<Provider, string>>({ claude: '', gemini: '', groq: '' })
const connectErr = reactive<Record<Provider, string>>({ claude: '', gemini: '', groq: '' })
const pmeta: Record<Provider, { name: string, tag: string, link: string, placeholder: string, steps: string[] }> = {
  groq: { name: 'Groq', tag: 'free · fast', link: 'https://console.groq.com/keys', placeholder: 'gsk_…',
    steps: ['Open console.groq.com → sign in', 'API Keys → Create API Key', 'Copy the gsk_… key, paste below'] },
  gemini: { name: 'Google Gemini', tag: 'free tier', link: 'https://aistudio.google.com/apikey', placeholder: 'AIza…',
    steps: ['Open aistudio.google.com/apikey', 'Create API key', 'Copy the AIza… key, paste below'] },
  claude: { name: 'Claude', tag: 'paid · smartest + computer use', link: 'https://console.anthropic.com/settings/keys', placeholder: 'sk-ant-…',
    steps: ['Add credit at console.anthropic.com → Billing (min $5)', 'Settings → API Keys → Create Key', 'Copy the sk-ant-… key, paste below', 'Required for "give Olwen the wheel" (screen control)'] },
}
const porder: Provider[] = ['groq', 'gemini', 'claude']

async function connect(p: Provider) {
  connectErr[p] = ''
  if (busy.value) return
  if (keyInput[p].trim().length < 10) { connectErr[p] = `That doesn't look like a ${pmeta[p].name} key — it should start with "${pmeta[p].placeholder.replace('…','')}".`; return }
  busy.value = p; error.value = ''
  try { settings.value = await connectProvider(p, keyInput[p].trim()); keyInput[p] = '' }
  catch (e: unknown) {
    const detail = (e as { data?: { detail?: string } })?.data?.detail || ''
    // Translate common Claude billing/auth failures into plain language
    if (p === 'claude' && /credit|balance|billing|quota|402/i.test(detail)) {
      connectErr[p] = 'Key is valid, but your Anthropic account has no credit. Add at least $5 at console.anthropic.com → Billing, then try again.'
    } else if (/401|invalid|unauthor/i.test(detail)) {
      connectErr[p] = 'That key was rejected. Copy it again from the key page (no spaces).'
    } else {
      connectErr[p] = detail || 'Could not connect — check the key and your internet.'
    }
  }
  finally { busy.value = null }
}
async function disconnect(p: Provider) {
  busy.value = p
  try { settings.value = await disconnectProvider(p) } catch { error.value = 'Could not disconnect.' } finally { busy.value = null }
}
async function use(p: Provider | 'auto') {
  busy.value = p as Provider
  try { settings.value = await selectProvider(p) } catch (e: unknown) { error.value = (e as { data?: { detail?: string } })?.data?.detail || 'Connect it first.' } finally { busy.value = null }
}

/* ---- voice ---- */
const voiceOn = useState<boolean>('voice:on', () => true)
const voiceLang = useState<string>('voice:lang', () => 'en-US')
const langs = [{ v: 'en-US', label: 'English' }, { v: 'ar-SA', label: 'Arabic' }]
async function toggleVoice() { voiceOn.value = !voiceOn.value; try { settings.value = await updateVoice({ enabled: voiceOn.value }) } catch { /* */ } }
async function setLang(l: string) { voiceLang.value = l; try { settings.value = await updateVoice({ lang: l }) } catch { /* */ } }

/* ---- morning brief preferences ---- */
const briefEnabled = ref(true)
const briefTime = ref('08:00')
const briefApi = useBrief()
async function toggleBrief() {
  briefEnabled.value = !briefEnabled.value
  try { await briefApi.updatePrefs({ enabled: briefEnabled.value }) }
  catch { briefEnabled.value = !briefEnabled.value }
}
async function setBriefTime(t: string) {
  briefTime.value = t
  try { await briefApi.updatePrefs({ time: t }) } catch { /* */ }
}

/* ---- memory ---- */
const { list: listMem, add: addMem, remove: rmMem } = useMemory()
const memories = ref<OlwenMemory[]>([])
const newMemory = ref('')
async function loadMem() { try { memories.value = await listMem() } catch { /* */ } }
async function saveMem() { const c = newMemory.value.trim(); if (!c) return; newMemory.value = ''; try { await addMem(c); await loadMem() } catch { /* */ } }
async function forget(id: string) { try { await rmMem(id); await loadMem() } catch { /* */ } }

/* ---- skills marketplace ---- */
const { catalog: getCatalog, installed: getInstalled, install: installSkill, uninstall: uninstallSkill, customList, addCustom, removeCustom } = useSkills()
const skills = ref<CatalogSkill[]>([])
const skillCategory = ref<string>('All')
const skillCategories = computed(() => {
  const set = new Set<string>()
  for (const s of skills.value) if (s.category) set.add(s.category)
  // Pin "Core" first, "Health" up top so it's discoverable, then alphabetical.
  const all = Array.from(set)
  const pinned = ['Core', 'Health']
  return ['All', ...pinned.filter(c => set.has(c)), ...all.filter(c => !pinned.includes(c)).sort()]
})
const filteredSkills = computed(() =>
  skillCategory.value === 'All' ? skills.value : skills.value.filter(s => s.category === skillCategory.value),
)
const installed = ref<string[]>([])
const customs = ref<CustomSkill[]>([])
const skillBusy = ref<string | null>(null)
const isInstalled = (k: string) => installed.value.includes(k)
async function loadSkills() {
  try { [skills.value, installed.value, customs.value] = await Promise.all([getCatalog(), getInstalled(), customList()]) } catch { /* */ }
}

// custom skill form
const showCustom = ref(false)
const cForm = reactive({ name: '', url: '', auth: '' })
async function saveCustom() {
  if (!cForm.name.trim() || !cForm.url.trim()) return
  try {
    await addCustom({ name: cForm.name.trim(), url: cForm.url.trim(), auth: cForm.auth.trim() || undefined })
    cForm.name = ''; cForm.url = ''; cForm.auth = ''; showCustom.value = false
    customs.value = await customList()
  } catch { /* */ }
}
async function dropCustom(id: string) { try { await removeCustom(id); customs.value = await customList() } catch { /* */ } }

/* ---- dashboard widget toggles ---- */
const enabledWidgets = useState<string[]>('dash:widgets', () => ['tasks', 'github', 'inbox', 'calendar', 'news'])
const isOn = (key: string) => enabledWidgets.value.includes(key)
async function toggleWidget(key: string, live: boolean, core: boolean) {
  if (core || !live) return
  const next = isOn(key) ? enabledWidgets.value.filter(k => k !== key) : [...enabledWidgets.value, key]
  enabledWidgets.value = next
  try { settings.value = await updateDashboard(next) } catch { /* */ }
}

/* ---- news topics ---- */
const newsTopics = useState<string[]>('news:topics', () => ['ai', 'tech'])
const isTopicOn = (t: string) => newsTopics.value.includes(t)
async function toggleTopic(t: string) {
  const next = isTopicOn(t) ? newsTopics.value.filter(k => k !== t) : [...newsTopics.value, t]
  newsTopics.value = next
  try { settings.value = await updateNews(next) } catch { /* */ }
}
const allTopics = ref<{ key: string; label: string; feed_count: number }[]>([])
async function loadTopics() {
  try { allTopics.value = (await useNews().topics()).topics } catch { /* */ }
}

/* ---- GitHub connection ---- */
const gh = useGithub()
const ghAccount = ref<{ connected: boolean; login?: string; avatar_url?: string }>({ connected: false })
const ghShowWizard = ref(false)
async function loadGithub() {
  try { ghAccount.value = await gh.account() } catch { /* */ }
}
async function disconnectGithub() {
  try { await gh.disconnect(); ghAccount.value = { connected: false } } catch { /* */ }
}
function onGithubConnected(p: { login: string }) {
  ghAccount.value = { connected: true, login: p.login }
  ghShowWizard.value = false
}

/* ---- Google OAuth server-side setup state ---- */
const googleOAuthReady = ref(false)
const showGoogleSetup = ref(false)
async function loadGoogleOAuthState() {
  try { googleOAuthReady.value = (await useEmail().oauthConfigured()).configured } catch { /* */ }
}
function onGoogleSetupDone() {
  googleOAuthReady.value = true
  showGoogleSetup.value = false
}

/* ---- email behaviour preferences ---- */
const autoMarkRead = useState<boolean>('email:autoMarkRead', () => false)
async function toggleAutoMarkRead() {
  autoMarkRead.value = !autoMarkRead.value
  try { settings.value = await updateEmailPrefs({ auto_mark_read: autoMarkRead.value }) }
  catch { autoMarkRead.value = !autoMarkRead.value /* revert on failure */ }
}

/* ---- email accounts ---- */
const { accounts: listAccounts, disconnect: disconnectEmail } = useEmail()
const emailAccounts = ref<EmailAccount[]>([])
const showWizard = ref(false)
async function loadEmail() { try { emailAccounts.value = await listAccounts() } catch { /* */ } }
async function upgradeToGoogle() {
  try {
    const r = await useEmail().oauthStart()
    if (r.auth_url) { window.location.href = r.auth_url }
  } catch (e: unknown) { error.value = (e as { data?: { detail?: string } })?.data?.detail || 'Sign-in failed.' }
}
function isImapGmail(a: EmailAccount): boolean {
  return a.provider === 'imap' && /@(gmail|googlemail)\.com$/i.test(a.email)
}

// Google's Test Users page URL — appends the user's project ID if remembered
const testUsersUrl = computed(() => {
  const pid = import.meta.client ? localStorage.getItem('olwen_google_project_id') : null
  const suffix = pid ? `?project=${encodeURIComponent(pid)}` : ''
  return `https://console.cloud.google.com/auth/audience${suffix}`
})
async function onEmailConnected() { showWizard.value = false; await loadEmail() }
async function dropEmail(id: string) { try { await disconnectEmail(id); emailAccounts.value = await listAccounts() } catch { /* */ } }
async function toggleSkill(s: CatalogSkill) {
  if (s.core || skillBusy.value) return
  skillBusy.value = s.key
  try { installed.value = isInstalled(s.key) ? await uninstallSkill(s.key) : await installSkill(s.key) }
  catch { /* */ } finally { skillBusy.value = null }
}

onMounted(async () => {
  try {
    settings.value = await fetchSettings()
    voiceOn.value = settings.value.voice.enabled
    voiceLang.value = settings.value.voice.lang
    autoMarkRead.value = !!settings.value.auto_mark_read
    if (settings.value.dashboard_widgets?.length) enabledWidgets.value = settings.value.dashboard_widgets
    if (settings.value.news_topics?.length) newsTopics.value = settings.value.news_topics
  } catch { /* */ }
  loadTopics()
  loadMem(); loadSkills(); loadEmail(); loadGithub(); loadGoogleOAuthState(); loadTelegram()
})

/* ---- Telegram link ---- */
const _apiBase = useRuntimeConfig().public.apiBase as string
function _authH(): Record<string, string> {
  const t = import.meta.client ? localStorage.getItem('olwen_access') : null
  return t ? { Authorization: `Bearer ${t}`, 'Content-Type': 'application/json' } : { 'Content-Type': 'application/json' }
}
const tg = ref<{ connected: boolean; linked: boolean; bot?: string; link?: string }>({ connected: false, linked: false })
const tgToken = ref('')
const tgBusy = ref(false)
const tgError = ref('')
async function loadTelegram() {
  try {
    const r = await fetch(`${_apiBase}/api/telegram/status`, { headers: _authH() })
    if (r.ok) { const d = await r.json(); tg.value = { ...tg.value, connected: !!d.connected, linked: !!d.linked } }
  } catch { /* */ }
}
async function connectTelegram() {
  const t = tgToken.value.trim(); if (!t) return
  tgBusy.value = true; tgError.value = ''
  try {
    const r = await fetch(`${_apiBase}/api/telegram/connect`, { method: 'POST', headers: _authH(), body: JSON.stringify({ token: t }) })
    const d = await r.json()
    if (d.error) tgError.value = d.error
    else { tgToken.value = ''; tg.value = { connected: true, linked: false, bot: d.bot, link: d.link } }
  } catch { tgError.value = 'Could not reach the backend.' } finally { tgBusy.value = false }
}
async function disconnectTelegram() {
  try { await fetch(`${_apiBase}/api/telegram/disconnect`, { method: 'DELETE', headers: _authH() }) } catch { /* */ }
  tg.value = { connected: false, linked: false }
}

const activeProvider = computed(() => settings.value?.active_provider ?? null)
const anyConnected = computed(() => porder.some(p => settings.value?.[p]?.connected))
const fmtStars = (n: number) => (n >= 1000 ? `${(n / 1000).toFixed(1).replace(/\.0$/, '')}k` : String(n))
</script>

<template>
  <div class="screen">
    <div class="screen__bg" aria-hidden="true" />
    <header class="screen__head">
      <span class="brand">OLWEN</span><span class="brand__sub">console</span>
      <button class="close" aria-label="Close" @click="emit('close')">✕</button>
    </header>

    <div class="body">
      <!-- nav rail — richer items with subtitle + glyph -->
      <nav class="rail">
        <div class="rail__entity"><OlwenEntity state="idle" /></div>
        <span class="rail__heading">Console</span>
        <button
          v-for="n in nav" :key="n.key"
          class="rail__item" :class="{ active: section === n.key }"
          @click="section = n.key"
        >
          <span class="rail__glyph" :class="{ active: section === n.key }">{{ n.glyph }}</span>
          <span class="rail__main">
            <span class="rail__label">{{ n.label }}</span>
            <span class="rail__sub">{{ n.sub }}</span>
          </span>
          <span v-if="section === n.key" class="rail__dot" />
        </button>
      </nav>

      <!-- content -->
      <section class="content">
        <!-- CONNECTIONS -->
        <div v-show="section === 'connections'" class="pane">
          <h2 class="pane__title">Your AI</h2>
          <p class="pane__desc">Choose which AI powers Olwen and connect your own key.</p>

          <!-- Auto: let Olwen pick the model per task -->
          <div class="autocard" :class="{ active: activeProvider === 'auto' }">
            <div class="autocard__main">
              <div class="autocard__name">
                ✦ Auto <span class="tag">smart routing</span>
                <span v-if="activeProvider === 'auto'" class="badge--on">In use</span>
              </div>
              <p class="autocard__desc">
                Olwen picks the best connected model for each task — Gemini for actions
                (open apps, send messages, take the wheel), the fastest model for quick chat.
                Connect one or more below.
              </p>
            </div>
            <button
              class="btn"
              :class="activeProvider === 'auto' ? 'btn--ghost' : 'btn--primary'"
              :disabled="!!busy || !anyConnected"
              @click="use('auto')"
            >
              {{ activeProvider === 'auto' ? 'Active' : 'Use Auto' }}
            </button>
          </div>

          <div class="grid">
            <div v-for="p in porder" :key="p" class="pcard" :class="{ active: activeProvider === p }">
              <div class="pcard__head">
                <div class="pcard__name">{{ pmeta[p].name }} <span class="tag">{{ pmeta[p].tag }}</span></div>
                <span v-if="activeProvider === p" class="badge--on">In use</span>
              </div>
              <p class="pcard__model">{{ settings?.[p].model }}</p>
              <template v-if="settings?.[p].connected">
                <div class="keyrow"><span class="keyrow__key">{{ settings[p].key_masked }}</span><span class="keyrow__ok">connected ✓</span></div>
                <div class="row">
                  <button v-if="activeProvider !== p" class="btn btn--primary" :disabled="!!busy" @click="use(p)">Use this</button>
                  <span v-else class="using">Active</span>
                  <button class="btn btn--ghost" :disabled="!!busy" @click="disconnect(p)">Disconnect</button>
                </div>
              </template>
              <template v-else>
                <ol class="psteps">
                  <li v-for="(s, i) in pmeta[p].steps" :key="i">{{ s }}</li>
                </ol>
                <input v-model="keyInput[p]" class="field" type="password" :placeholder="pmeta[p].placeholder" @keyup.enter="connect(p)">
                <div class="row">
                  <button class="btn btn--primary" :disabled="!!busy" @click="connect(p)">{{ busy === p ? 'Verifying…' : 'Connect' }}</button>
                  <a class="link" :href="pmeta[p].link" target="_blank" rel="noopener">Open key page →</a>
                </div>
                <p v-if="connectErr[p]" class="perr">{{ connectErr[p] }}</p>
              </template>
            </div>
          </div>

          <!-- Strava: health connector -->
          <StravaSetupCard />

          <!-- GitHub: connected view OR the wizard -->
          <div class="ghcard">
            <div class="ghcard__head">
              <div class="ghcard__name">GitHub <span class="tag">live activity</span></div>
              <span v-if="ghAccount.connected" class="badge--on">Connected</span>
            </div>

            <template v-if="ghAccount.connected && !ghShowWizard">
              <p class="pane__desc" style="margin: 4px 0 12px;">Real push events, PRs, and issues in your dashboard.</p>
              <div class="ghrow">
                <img v-if="ghAccount.avatar_url" :src="ghAccount.avatar_url" class="ghavatar" alt="">
                <div class="ghrow__main">
                  <span class="ghrow__name">@{{ ghAccount.login }}</span>
                  <span class="ghrow__sub">Olwen reads your recent activity</span>
                </div>
                <button class="btn btn--ghost" @click="disconnectGithub">Disconnect</button>
              </div>
            </template>

            <GithubConnectWizard
              v-else
              @connected="onGithubConnected"
              @cancel="ghShowWizard = false"
            />
          </div>

          <!-- Telegram: chat with Olwen from your phone -->
          <div class="ghcard">
            <div class="ghcard__head">
              <div class="ghcard__name">Telegram <span class="tag">chat &amp; tasks</span></div>
              <span v-if="tg.connected" class="badge--on">{{ tg.linked ? 'Linked' : 'Awaiting /start' }}</span>
            </div>
            <template v-if="tg.connected">
              <p class="pane__desc" style="margin: 4px 0 12px;">
                {{ tg.linked
                  ? 'Text Olwen anything — add tasks, send a message, check your day, or run a coding job. He replies in Telegram.'
                  : 'Almost there — open Telegram and send your bot /start to link your chat.' }}
              </p>
              <div class="ghrow">
                <div class="ghrow__main">
                  <span class="ghrow__name">@{{ tg.bot || 'your bot' }}</span>
                  <a v-if="tg.link" :href="tg.link" target="_blank" rel="noopener" class="ghrow__sub">open in Telegram ↗</a>
                  <span v-else class="ghrow__sub">connected</span>
                </div>
                <button class="btn btn--ghost" @click="disconnectTelegram">Disconnect</button>
              </div>
            </template>
            <template v-else>
              <p class="pane__desc" style="margin: 4px 0 10px;">
                Create a bot in <a href="https://t.me/BotFather" target="_blank" rel="noopener">@BotFather</a>
                (send <code>/newbot</code>), paste the token here, then send your bot <code>/start</code>.
              </p>
              <div class="ghrow">
                <input v-model="tgToken" class="field" type="password" placeholder="123456:ABC-your-bot-token…"
                       style="flex:1;" @keyup.enter="connectTelegram">
                <button class="btn btn--primary" :disabled="tgBusy" @click="connectTelegram">{{ tgBusy ? 'Verifying…' : 'Connect' }}</button>
              </div>
              <p v-if="tgError" class="pane__desc" style="color:#FCA5A5; margin-top:8px;">{{ tgError }}</p>
            </template>
          </div>
        </div>

        <!-- DASHBOARD WIDGETS -->
        <div v-show="section === 'dashboard'" class="pane">
          <header class="pane__head">
            <div>
              <h2 class="pane__title">Your dashboard</h2>
              <p class="pane__desc">Pick the cards Olwen surfaces. They turn on as soon as you toggle them.</p>
            </div>
            <span class="pane__count">{{ enabledWidgets.length }} of {{ settings?.widget_catalog?.length || 0 }} on</span>
          </header>

          <div class="wgrid">
            <div
              v-for="w in settings?.widget_catalog || []"
              :key="w.key"
              class="wcard"
              :class="{ on: isOn(w.key), core: w.core, soon: !w.live }"
              :style="{ '--c': w.color }"
              @click="toggleWidget(w.key, w.live, w.core)"
            >
              <div class="wcard__top">
                <span class="wcard__glyph">{{ w.glyph }}</span>
                <span v-if="w.core" class="wcard__chip wcard__chip--core">Core</span>
                <span v-else-if="!w.live" class="wcard__chip wcard__chip--soon">Soon</span>
                <span v-else-if="isOn(w.key)" class="wcard__chip wcard__chip--on">On</span>
                <span v-else class="wcard__chip">Off</span>
              </div>
              <div class="wcard__name">{{ w.name }}</div>
              <p class="wcard__desc">{{ w.description }}</p>
              <div class="wcard__foot">
                <span class="wcard__col">{{ w.column === 'left' ? '← left' : 'right →' }}</span>
                <span v-if="w.live && !w.core" class="wcard__hint">{{ isOn(w.key) ? 'Tap to hide' : 'Tap to show' }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- NEWS TOPICS -->
        <div v-show="section === 'news'" class="pane">
          <header class="pane__head">
            <div>
              <h2 class="pane__title">News you care about</h2>
              <p class="pane__desc">Olwen pulls fresh stories from real RSS feeds, never a static list.</p>
            </div>
            <span class="pane__count">{{ newsTopics.length }} topic{{ newsTopics.length === 1 ? '' : 's' }} on</span>
          </header>

          <div class="topics">
            <button
              v-for="t in allTopics" :key="t.key"
              class="topic" :class="{ active: isTopicOn(t.key) }"
              @click="toggleTopic(t.key)"
            >
              <span class="topic__name">{{ t.label }}</span>
              <span class="topic__count">{{ t.feed_count }} feed{{ t.feed_count === 1 ? '' : 's' }}</span>
              <span class="topic__mark">{{ isTopicOn(t.key) ? '✓' : '+' }}</span>
            </button>
          </div>

          <p v-if="!newsTopics.length" class="empty-note">
            Olwen will default to AI + Tech until you pick something.
          </p>
        </div>

        <!-- VOICE -->
        <div v-show="section === 'voice'" class="pane">
          <h2 class="pane__title">Voice</h2>
          <div class="vrow">
            <div><div class="vrow__t">Voice replies</div><div class="vrow__s">Olwen speaks its answers aloud</div></div>
            <button class="toggle" :class="{ on: voiceOn }" @click="toggleVoice"><span /></button>
          </div>
          <div class="vrow">
            <div class="vrow__t">Language</div>
            <div class="row">
              <button v-for="l in langs" :key="l.v" class="chip" :class="{ active: voiceLang === l.v }" @click="setLang(l.v)">{{ l.label }}</button>
            </div>
          </div>

          <h3 class="pane__sub">Morning brief</h3>
          <div class="vrow">
            <div>
              <div class="vrow__t">Daily wake-up</div>
              <div class="vrow__s">Olwen narrates your weather, calendar, tasks, inbox, and news — once a day.</div>
            </div>
            <button class="toggle" :class="{ on: briefEnabled }" @click="toggleBrief"><span /></button>
          </div>
          <div class="vrow" v-if="briefEnabled">
            <div class="vrow__t">Time</div>
            <input type="time" :value="briefTime" @change="setBriefTime(($event.target as HTMLInputElement).value)" class="timefield">
          </div>
        </div>

        <!-- MEMORY -->
        <div v-show="section === 'memory'" class="pane">
          <h2 class="pane__title">What Olwen remembers</h2>
          <p class="pane__desc">Used naturally in chat. Tip: just say “remember that…”.</p>
          <ul v-if="memories.length" class="mlist">
            <li v-for="m in memories" :key="m.id"><span class="mdot" /><span class="mtext">{{ m.content }}</span><button class="mx" @click="forget(m.id)">✕</button></li>
          </ul>
          <p v-else class="muted">Nothing yet — Olwen will learn as you talk.</p>
          <div class="row">
            <input v-model="newMemory" class="field" placeholder="Add something Olwen should know…" @keyup.enter="saveMem">
            <button class="btn btn--primary" @click="saveMem">Add</button>
          </div>
        </div>

        <!-- SKILLS MARKETPLACE -->
        <div v-show="section === 'skills'" class="pane">
          <h2 class="pane__title">Skills</h2>
          <p class="pane__desc">Add abilities to Olwen. New skills are published by the team.</p>
          <!-- category filter strip -->
          <div class="catstrip">
            <button
              v-for="c in skillCategories" :key="c"
              class="catchip"
              :class="{ active: skillCategory === c, health: c === 'Health' }"
              @click="skillCategory = c"
            >{{ c }}</button>
          </div>
          <div class="grid grid--skills">
            <div v-for="s in filteredSkills" :key="s.key" class="scard" :style="{ '--c': s.color }">
              <div class="scard__top">
                <span class="scard__glyph">{{ s.glyph }}</span>
                <span v-if="s.core" class="badge--core">Core</span>
                <span v-else class="scard__stars">★ {{ fmtStars(s.stars) }}</span>
              </div>
              <div class="scard__name">{{ s.name }}</div>
              <div class="scard__by">by {{ s.author }} · {{ s.category }}</div>
              <p class="scard__desc">{{ s.description }}</p>
              <div class="scard__actions">
                <button
                  class="sbtn"
                  :class="{ on: isInstalled(s.key), core: s.core }"
                  :disabled="s.core || skillBusy === s.key"
                  @click="toggleSkill(s)"
                >
                  {{ s.core ? 'Always on' : isInstalled(s.key) ? 'Added ✓' : 'Add skill' }}
                </button>
                <a v-if="s.repo" class="scard__repo" :href="s.repo" target="_blank" rel="noopener">View →</a>
              </div>
            </div>
          </div>
          <p class="note">Task Manager runs for real today. Other skills: “Add” makes Olwen aware; live execution is wired one at a time.</p>

          <!-- custom skills -->
          <div class="custom">
            <div class="custom__head">
              <span class="pane__title" style="font-size:16px">Your custom skills</span>
              <button class="btn btn--primary" @click="showCustom = !showCustom">{{ showCustom ? 'Close' : '+ Add custom' }}</button>
            </div>
            <p class="pane__desc">Point Olwen at any MCP server URL — not just the marketplace.</p>

            <div v-if="showCustom" class="cform">
              <input v-model="cForm.name" class="field" placeholder="Name (e.g. My company tools)">
              <input v-model="cForm.url" class="field" placeholder="MCP server URL — https://mcp.example.com/sse">
              <input v-model="cForm.auth" class="field" type="password" placeholder="Auth header (optional)">
              <button class="btn btn--primary" @click="saveCustom">Add skill</button>
            </div>

            <ul v-if="customs.length" class="clist">
              <li v-for="c in customs" :key="c.id" class="citem">
                <span class="cglyph">⊹</span>
                <div class="cmain"><span class="cname">{{ c.name }}</span><span class="curl">{{ c.url }}</span></div>
                <span class="badge--soon">Custom</span>
                <button class="mx" @click="dropCustom(c.id)">✕</button>
              </li>
            </ul>
            <p v-else class="muted">None yet — add a remote MCP server above.</p>
          </div>
        </div>

        <!-- EMAIL -->
        <div v-show="section === 'email'" class="pane">
          <h2 class="pane__title">Your email</h2>
          <p class="pane__desc">
            Works with Gmail, Outlook, Hotmail, Yahoo, iCloud, or any IMAP. Olwen
            reads your inbox, marks what's important, and tells you what needs a reply.
          </p>

          <!-- behaviour preferences -->
          <div class="prefs">
            <div class="prefs__row">
              <div class="prefs__main">
                <span class="prefs__name">Mark as read when Olwen reads it</span>
                <span class="prefs__desc">When ON, opening or summarising an email flags it as read in your mailbox.</span>
                <span class="prefs__hint">Gmail OAuth users: if this fails, disconnect and reconnect to grant write permission.</span>
              </div>
              <button class="toggle" :class="{ on: autoMarkRead }" @click="toggleAutoMarkRead"><span /></button>
            </div>
          </div>

          <ul v-if="emailAccounts.length && !showWizard" class="clist" style="margin-bottom:18px">
            <li v-for="a in emailAccounts" :key="a.id" class="citem citem--col">
              <div class="citem__row">
                <span class="cglyph">✉</span>
                <div class="cmain">
                  <span class="cname">{{ a.email }}</span>
                  <span class="curl">{{ a.provider === 'google' ? 'Google · OAuth' : a.imap_host }}</span>
                </div>
                <span v-if="a.provider === 'google'" class="badge--on">Sign-in · Google</span>
                <span v-else class="badge--soon">App password</span>
                <button class="mx" title="Disconnect" @click="dropEmail(a.id)">✕</button>
              </div>
              <!-- IMAP-Gmail-only nudge: one-click upgrade to Google OAuth (calendar needs this) -->
              <div v-if="isImapGmail(a) && googleOAuthReady" class="upsell">
                <div class="upsell__main">
                  <span class="upsell__tag">★ Calendar still locked</span>
                  <span class="upsell__txt">
                    This is the app-password connection. One click upgrades it to "Sign in with Google",
                    grants calendar permission, and your Today widget will populate.
                  </span>
                </div>
                <button class="upsell__btn" @click="upgradeToGoogle">↗ Sign in with Google</button>
              </div>

              <!-- "Access blocked" recovery — VERY visible inline help for the common failure -->
              <details v-if="isImapGmail(a) && googleOAuthReady" class="recover">
                <summary>
                  <span class="recover__icon">⚠</span>
                  <span class="recover__title">Did Google say <em>"Access blocked — Olwen has not completed Google verification"</em>?</span>
                  <span class="recover__caret">▾</span>
                </summary>
                <div class="recover__body">
                  <p>This means Google sees you as a regular user, not a test user. Fix in 30 seconds:</p>
                  <ol>
                    <li>Open the <a class="link" :href="testUsersUrl" target="_blank" rel="noopener">Audience page</a> on Google Cloud
                      (the link locks to your Olwen project if you remembered the ID).</li>
                    <li>Scroll down to <strong>Test users</strong>.</li>
                    <li>Click <strong>+ Add users</strong>, type <code>{{ a.email }}</code>, click <strong>Save</strong>.</li>
                    <li>Come back here and click <strong>↗ Sign in with Google</strong> again — it'll work this time.</li>
                  </ol>
                  <a class="cta-small" :href="testUsersUrl" target="_blank" rel="noopener">↗ Open Audience page now</a>
                </div>
              </details>
            </li>
          </ul>

          <!-- Google OAuth setup banner: shown when the server has no creds yet. -->
          <div v-if="!googleOAuthReady && !showGoogleSetup" class="oauth-banner">
            <div class="oauth-banner__main">
              <span class="oauth-banner__tag">Sign-in with Google</span>
              <span class="oauth-banner__txt">Not set up yet — calendar & one-click Gmail need this. ~3 minutes, one-time.</span>
            </div>
            <button class="btn btn--primary" @click="showGoogleSetup = true">Set up now</button>
          </div>

          <GoogleSetupWizard
            v-if="showGoogleSetup"
            @done="onGoogleSetupDone"
            @cancel="showGoogleSetup = false"
          />

          <EmailConnectWizard
            v-if="(!emailAccounts.length || showWizard) && !showGoogleSetup"
            @connected="onEmailConnected"
            @cancel="showWizard = false"
          />
          <button v-if="emailAccounts.length && !showWizard && !showGoogleSetup" class="btn btn--primary" @click="showWizard = true">+ Add another email</button>
        </div>

        <p v-if="error" class="error">{{ error }}</p>
      </section>
    </div>
  </div>
</template>

<style scoped>
.screen { position: fixed; inset: 0; z-index: 60; display: flex; flex-direction: column; }
.screen__bg { position: absolute; inset: 0; z-index: -1; background: radial-gradient(ellipse at 30% 20%, #0A1419 0%, #02060A 70%); }
.screen__head { display: flex; align-items: baseline; gap: 12px; padding: 20px 28px; border-bottom: 0.5px solid rgba(94,234,212,0.1); }
.brand { font-family: 'JetBrains Mono', monospace; letter-spacing: 4px; font-size: 15px; color: #5EEAD4; }
.brand__sub { font-size: 11px; letter-spacing: 1.5px; color: rgba(167,243,208,0.4); text-transform: uppercase; }
.close { margin-left: auto; border: none; background: transparent; color: rgba(167,243,208,0.5); font-size: 16px; cursor: pointer; }
.close:hover { color: #ECFEFF; }

.body { flex: 1; display: grid; grid-template-columns: 280px 1fr; min-height: 0; }
.rail {
  display: flex; flex-direction: column; gap: 4px;
  padding: 28px 14px; border-right: 0.5px solid rgba(94,234,212,0.08);
  background: linear-gradient(180deg, rgba(8,30,38,0.4), rgba(2,6,10,0.1));
}
.rail__entity { width: 130px; height: 130px; margin: 0 auto 20px; }
.rail__heading {
  display: block; padding: 0 16px 10px;
  font-family: 'JetBrains Mono', monospace; font-size: 9px; letter-spacing: 2.4px;
  text-transform: uppercase; color: rgba(94,234,212,0.45);
}
.rail__item {
  position: relative;
  display: flex; align-items: center; gap: 12px;
  text-align: left; padding: 11px 14px; border-radius: 10px; cursor: pointer;
  border: 0.5px solid transparent; background: transparent;
  color: rgba(167,243,208,0.6);
  transition: all .2s ease;
}
.rail__glyph {
  display: grid; place-items: center;
  width: 28px; height: 28px; border-radius: 8px; flex-shrink: 0;
  background: rgba(94,234,212,0.06); border: 0.5px solid rgba(94,234,212,0.16);
  color: rgba(167,243,208,0.7); font-size: 14px; line-height: 1;
  transition: all .2s ease;
}
.rail__main { display: flex; flex-direction: column; gap: 1px; flex: 1; min-width: 0; }
.rail__label { font-size: 12.5px; color: #DCFCF5; letter-spacing: 0.3px; }
.rail__sub { font-family: 'JetBrains Mono', monospace; font-size: 9px; letter-spacing: 0.8px; color: rgba(167,243,208,0.4); }
.rail__dot { width: 6px; height: 6px; border-radius: 50%; background: #5EEAD4; box-shadow: 0 0 8px #5EEAD4; flex-shrink: 0; }
.rail__item:hover { background: rgba(94,234,212,0.05); border-color: rgba(94,234,212,0.18); }
.rail__item:hover .rail__glyph { color: #5EEAD4; border-color: rgba(94,234,212,0.35); }
.rail__item.active { background: rgba(94,234,212,0.10); border-color: rgba(94,234,212,0.35); }
.rail__item.active .rail__label { color: #ECFEFF; }
.rail__item.active .rail__glyph { background: rgba(94,234,212,0.18); border-color: #5EEAD4; color: #5EEAD4; box-shadow: 0 0 12px rgba(94,234,212,0.25); }

/* ---- pane header ---- */
.pane__head { display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; margin-bottom: 22px; }
.pane__head .pane__title { margin-bottom: 4px; }
.pane__head .pane__desc { margin: 0; }
.pane__sub { margin: 28px 0 10px; font-size: 14px; font-weight: 400; color: #ECFEFF; padding-top: 18px; border-top: 0.5px solid rgba(94,234,212,0.12); letter-spacing: 0.3px; }
.timefield { padding: 8px 12px; border-radius: 9px; border: 0.5px solid rgba(94,234,212,0.25); background: rgba(2,6,10,0.55); color: #ECFEFF; font-family: 'JetBrains Mono', monospace; font-size: 13px; }
.timefield:focus { outline: none; border-color: #5EEAD4; box-shadow: 0 0 18px rgba(94,234,212,0.15); }

.pane__count {
  flex-shrink: 0; padding: 5px 12px; border-radius: 999px;
  border: 0.5px solid rgba(94,234,212,0.25); background: rgba(94,234,212,0.06);
  font-family: 'JetBrains Mono', monospace; font-size: 10px; letter-spacing: 1.2px; color: #5EEAD4;
}

/* ---- widget toggle grid ---- */
.wgrid {
  display: grid; gap: 14px;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
}
.wcard {
  position: relative;
  padding: 16px 16px 12px; border-radius: 14px;
  border: 0.5px solid rgba(94,234,212,0.14);
  background: linear-gradient(180deg, rgba(8,30,38,0.55), rgba(2,6,10,0.4));
  cursor: pointer; transition: all .2s ease;
  display: flex; flex-direction: column; gap: 8px;
  min-height: 150px;
}
.wcard:hover { transform: translateY(-2px); border-color: rgba(94,234,212,0.35); box-shadow: 0 10px 30px rgba(0,0,0,0.25), 0 0 18px rgba(94,234,212,0.08); }
.wcard.on { border-color: var(--c); box-shadow: 0 0 0 0.5px var(--c), 0 12px 30px rgba(0,0,0,0.3), 0 0 24px color-mix(in srgb, var(--c) 25%, transparent); background: linear-gradient(180deg, color-mix(in srgb, var(--c) 9%, rgba(8,30,38,0.55)), rgba(2,6,10,0.4)); }
.wcard.core { cursor: default; }
.wcard.soon { cursor: not-allowed; opacity: 0.55; }
.wcard.soon:hover { transform: none; box-shadow: none; }

.wcard__top { display: flex; align-items: center; justify-content: space-between; }
.wcard__glyph {
  display: grid; place-items: center; width: 32px; height: 32px; border-radius: 10px;
  background: color-mix(in srgb, var(--c) 14%, rgba(2,6,10,0.5));
  color: var(--c); font-size: 17px; line-height: 1;
  border: 0.5px solid color-mix(in srgb, var(--c) 25%, transparent);
}
.wcard__chip {
  font-family: 'JetBrains Mono', monospace; font-size: 9px; letter-spacing: 1.4px; text-transform: uppercase;
  padding: 3px 8px; border-radius: 999px;
  border: 0.5px solid rgba(167,243,208,0.2); color: rgba(167,243,208,0.5);
}
.wcard__chip--on   { background: color-mix(in srgb, var(--c) 18%, transparent); border-color: var(--c); color: #ECFEFF; }
.wcard__chip--core { background: rgba(94,234,212,0.16); border-color: #5EEAD4; color: #ECFEFF; }
.wcard__chip--soon { color: rgba(251,191,36,0.8); border-color: rgba(251,191,36,0.4); }
.wcard__name { font-size: 15px; color: #ECFEFF; font-weight: 400; }
.wcard__desc { margin: 0; font-size: 11.5px; color: rgba(167,243,208,0.55); line-height: 1.45; flex: 1; }
.wcard__foot {
  display: flex; align-items: center; justify-content: space-between; margin-top: 2px;
  padding-top: 8px; border-top: 0.5px solid rgba(255,255,255,0.04);
}
.wcard__col, .wcard__hint {
  font-family: 'JetBrains Mono', monospace; font-size: 9px; letter-spacing: 1.2px; text-transform: uppercase;
  color: rgba(167,243,208,0.4);
}
.wcard__hint { color: var(--c); opacity: 0.7; }
.wcard.on .wcard__hint { opacity: 1; }

/* ---- news topics ---- */
.topics { display: grid; gap: 10px; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); }
.topic {
  display: flex; align-items: center; gap: 10px;
  padding: 12px 14px; border-radius: 12px; cursor: pointer;
  border: 0.5px solid rgba(94,234,212,0.18); background: rgba(8,30,38,0.45);
  color: #DCFCF5; transition: all .15s ease;
}
.topic:hover { border-color: rgba(94,234,212,0.4); transform: translateY(-1px); }
.topic.active { background: rgba(34,211,238,0.12); border-color: #22D3EE; box-shadow: 0 0 18px rgba(34,211,238,0.18); }
.topic__name { flex: 1; font-size: 13px; color: #ECFEFF; text-align: left; }
.topic__count { font-family: 'JetBrains Mono', monospace; font-size: 9px; letter-spacing: 0.8px; color: rgba(167,243,208,0.45); }
.topic__mark {
  width: 24px; height: 24px; border-radius: 50%; display: grid; place-items: center;
  background: rgba(2,6,10,0.6); color: rgba(167,243,208,0.5);
  font-family: 'JetBrains Mono', monospace; font-size: 12px;
  border: 0.5px solid rgba(94,234,212,0.2);
}
.topic.active .topic__mark { background: #22D3EE; color: #02060A; border-color: #22D3EE; }
.empty-note { margin: 14px 4px 0; font-size: 12px; color: rgba(167,243,208,0.45); font-style: italic; }

.oauth-banner { display: flex; align-items: center; gap: 14px; padding: 14px 16px; margin-bottom: 18px; border-radius: 12px; border: 0.5px solid rgba(251,191,36,0.4); background: rgba(251,191,36,0.06); }
.oauth-banner__main { flex: 1; display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.oauth-banner__tag { font-family: 'JetBrains Mono', monospace; font-size: 9px; letter-spacing: 1.6px; text-transform: uppercase; color: #FBBF24; }
.oauth-banner__txt { font-size: 12.5px; color: #ECFEFF; line-height: 1.4; }

.citem--col { display: flex; flex-direction: column; gap: 12px; align-items: stretch; padding: 14px 16px; }
.citem__row { display: flex; align-items: center; gap: 12px; }
.upsell {
  display: flex; align-items: center; gap: 14px;
  padding: 12px 14px; border-radius: 10px;
  background: linear-gradient(180deg, rgba(94,234,212,0.10), rgba(94,234,212,0.04));
  border: 0.5px solid rgba(94,234,212,0.4);
  box-shadow: 0 0 22px rgba(94,234,212,0.12);
}
.upsell__main { flex: 1; display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.upsell__tag { font-family: 'JetBrains Mono', monospace; font-size: 9px; letter-spacing: 1.4px; text-transform: uppercase; color: #FBBF24; }
.upsell__txt { font-size: 12.5px; color: #ECFEFF; line-height: 1.5; }
.upsell__btn {
  flex-shrink: 0; padding: 10px 16px; border-radius: 999px; cursor: pointer;
  border: 0.5px solid #5EEAD4; background: #5EEAD4; color: #02060A;
  font-family: 'JetBrains Mono', monospace; font-size: 10.5px; letter-spacing: 1.2px; text-transform: uppercase;
  transition: all .15s ease;
}
.upsell__btn:hover { background: #67E8F9; box-shadow: 0 0 22px rgba(94,234,212,0.45); }

/* "Access blocked" troubleshooter */
.recover { padding: 10px 14px; border-radius: 10px; border: 0.5px solid rgba(248,113,113,0.35); background: rgba(248,113,113,0.06); }
.recover summary { display: flex; align-items: center; gap: 9px; cursor: pointer; list-style: none; color: #FCA5A5; }
.recover summary::-webkit-details-marker { display: none; }
.recover__icon { display: grid; place-items: center; width: 22px; height: 22px; border-radius: 50%; background: rgba(248,113,113,0.18); color: #F87171; font-size: 12px; flex-shrink: 0; }
.recover__title { flex: 1; font-size: 12px; color: #FECACA; line-height: 1.5; }
.recover__title em { color: #FECACA; background: rgba(248,113,113,0.18); padding: 1px 6px; border-radius: 4px; font-style: normal; font-family: 'JetBrains Mono', monospace; font-size: 11px; }
.recover__caret { color: rgba(252,165,165,0.6); transition: transform .2s ease; }
.recover[open] .recover__caret { transform: rotate(180deg); }
.recover__body { margin: 10px 0 4px 31px; color: rgba(252,165,165,0.85); font-size: 12px; line-height: 1.6; }
.recover__body p { margin: 0 0 8px; }
.recover__body ol { margin: 0 0 12px; padding-left: 18px; display: flex; flex-direction: column; gap: 6px; }
.recover__body strong { color: #ECFEFF; }
.recover__body code { font-family: 'JetBrains Mono', monospace; font-size: 11px; padding: 1px 6px; border-radius: 4px; background: rgba(255,255,255,0.06); border: 0.5px solid rgba(248,113,113,0.3); color: #FDE68A; }
.recover__body .link { color: #67E8F9; }

.cta-small {
  display: inline-flex; align-items: center; gap: 6px; padding: 8px 14px; border-radius: 999px;
  text-decoration: none; border: 0.5px solid #F87171; background: rgba(248,113,113,0.18); color: #FECACA;
  font-family: 'JetBrains Mono', monospace; font-size: 10px; letter-spacing: 1.2px; text-transform: uppercase;
  transition: all .2s ease;
}
.cta-small:hover { background: #F87171; color: #02060A; }

.content { overflow-y: auto; padding: 32px 40px; }
.pane { max-width: 720px; }
.pane__title { margin: 0 0 4px; font-size: 22px; font-weight: 300; color: #ECFEFF; }
.pane__desc { margin: 0 0 22px; font-size: 13px; color: rgba(167,243,208,0.55); }

.grid { display: grid; gap: 14px; }
.grid--skills { grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); }

/* provider cards */
.pcard { border-radius: 13px; padding: 16px; border: 0.5px solid rgba(94,234,212,0.12); border-left: 2px solid rgba(94,234,212,0.2); background: rgba(8,30,38,0.4); display: flex; flex-direction: column; gap: 9px; }
.pcard.active { border-left-color: #5EEAD4; box-shadow: 0 0 18px rgba(94,234,212,0.1); }
.pcard__head { display: flex; align-items: center; justify-content: space-between; }
.pcard__name { font-size: 14px; color: #ECFEFF; }
.tag { font-family: 'JetBrains Mono', monospace; font-size: 8px; letter-spacing: 1px; text-transform: uppercase; color: #5EEAD4; border: 0.5px solid rgba(94,234,212,0.3); border-radius: 999px; padding: 2px 6px; }
.pcard__model { margin: 0; font-family: 'JetBrains Mono', monospace; font-size: 10px; color: rgba(167,243,208,0.45); }
.badge--on { font-family: 'JetBrains Mono', monospace; font-size: 9px; letter-spacing: 1px; text-transform: uppercase; color: #02060A; background: #5EEAD4; border-radius: 999px; padding: 3px 9px; }
.keyrow { display: flex; align-items: center; justify-content: space-between; }
.keyrow__key { font-family: 'JetBrains Mono', monospace; font-size: 12px; color: #A7F3D0; }
.keyrow__ok { font-size: 11px; color: #5EEAD4; }
.using { font-size: 11px; color: #5EEAD4; }

.field { padding: 10px 12px; border-radius: 8px; outline: none; font-size: 13px; border: 0.5px solid rgba(94,234,212,0.18); background: rgba(2,6,10,0.5); color: #E2F5F1; flex: 1; }
.field:focus { border-color: #5EEAD4; }
.field::placeholder { color: rgba(167,243,208,0.3); }
.autocard {
  display: flex; align-items: center; gap: 16px;
  padding: 16px 18px; margin-bottom: 18px;
  border-radius: 14px;
  border: 0.5px solid rgba(94,234,212,0.25);
  background: linear-gradient(135deg, rgba(94,234,212,0.06), rgba(103,232,249,0.03));
}
.autocard.active { border-color: rgba(94,234,212,0.6); background: linear-gradient(135deg, rgba(94,234,212,0.12), rgba(103,232,249,0.05)); }
.autocard__main { flex: 1; min-width: 0; }
.autocard__name { display: flex; align-items: center; gap: 8px; font-size: 15px; color: #ECFEFF; font-weight: 500; }
.autocard__desc { margin: 6px 0 0; font-size: 12.5px; line-height: 1.5; color: rgba(167,243,208,0.6); }

.psteps {
  margin: 4px 0 12px; padding-left: 18px;
  font-size: 12px; line-height: 1.6; color: rgba(167,243,208,0.6);
}
.psteps li { margin: 2px 0; }
.perr {
  margin: 10px 0 0; padding: 8px 10px;
  font-size: 12px; line-height: 1.45;
  color: #FCA5A5;
  background: rgba(252,165,165,0.08);
  border: 0.5px solid rgba(252,165,165,0.3);
  border-radius: 8px;
}
.row { display: flex; align-items: center; gap: 10px; }
.btn { padding: 9px 14px; border-radius: 8px; cursor: pointer; font-size: 11px; letter-spacing: 1px; text-transform: uppercase; transition: all .2s ease; }
.btn:disabled { opacity: 0.5; cursor: progress; }
.btn--primary { border: 0.5px solid #5EEAD4; background: rgba(94,234,212,0.16); color: #ECFEFF; }
.btn--primary:hover:not(:disabled) { background: rgba(94,234,212,0.26); }
.btn--ghost { border: 0.5px solid rgba(248,113,113,0.4); background: transparent; color: #FCA5A5; }
.link { font-size: 11px; color: #5EEAD4; text-decoration: none; }
.link:hover { text-decoration: underline; }

/* voice */
.vrow { display: flex; align-items: center; justify-content: space-between; padding: 14px 0; border-bottom: 0.5px solid rgba(255,255,255,0.05); }
.vrow__t { font-size: 14px; color: #ECFEFF; }
.vrow__s { font-size: 12px; color: rgba(167,243,208,0.45); margin-top: 2px; }
.ghcard {
  margin-top: 22px; padding: 18px 20px; border-radius: 14px;
  border: 0.5px solid rgba(167,139,250,0.25);
  background: linear-gradient(180deg, rgba(167,139,250,0.06), rgba(8,30,38,0.4));
}
.ghcard__head { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.ghcard__name { font-size: 17px; color: #ECFEFF; font-weight: 300; }
.ghrow { display: flex; align-items: center; gap: 12px; padding: 8px 0 2px; }
.ghavatar { width: 36px; height: 36px; border-radius: 50%; flex-shrink: 0; border: 0.5px solid rgba(167,139,250,0.4); }
.ghrow__main { flex: 1; display: flex; flex-direction: column; gap: 2px; }
.ghrow__name { font-size: 14px; color: #ECFEFF; }
.ghrow__sub { font-size: 11.5px; color: rgba(167,243,208,0.5); }
.ghconnect { display: inline-flex; align-items: center; gap: 9px; }
.ghhint { margin: 10px 0 0; font-size: 11px; color: rgba(167,243,208,0.55); line-height: 1.6; }
.ghhint code { font-family: 'JetBrains Mono', monospace; font-size: 10.5px; color: #A78BFA; }
.ghhint a { color: #67E8F9; }

.catstrip { display: flex; flex-wrap: wrap; gap: 6px; margin: 0 0 16px; }
.catchip {
  padding: 6px 13px; border-radius: 999px; cursor: pointer;
  border: 0.5px solid rgba(94,234,212,0.18); background: transparent;
  color: rgba(167,243,208,0.55);
  font-family: 'JetBrains Mono', monospace; font-size: 9.5px; letter-spacing: 1.2px; text-transform: uppercase;
  transition: all .15s ease;
}
.catchip:hover { color: #ECFEFF; border-color: rgba(94,234,212,0.45); }
.catchip.active { background: rgba(94,234,212,0.14); border-color: #5EEAD4; color: #ECFEFF; }
.catchip.health { color: #F472B6; border-color: rgba(244,114,182,0.3); }
.catchip.health.active { background: rgba(244,114,182,0.15); border-color: #F472B6; color: #FBCFE8; }

.prefs { margin-bottom: 18px; }
.prefs__row { display: flex; align-items: center; gap: 18px; padding: 14px 16px; border-radius: 12px; border: 0.5px solid rgba(94,234,212,0.18); background: rgba(8,30,38,0.4); }
.prefs__main { flex: 1; display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.prefs__name { font-size: 14px; color: #ECFEFF; font-weight: 500; }
.prefs__desc { font-size: 12px; color: rgba(167,243,208,0.6); line-height: 1.4; }
.prefs__hint { font-family: 'JetBrains Mono', monospace; font-size: 10px; letter-spacing: 0.4px; color: rgba(251,191,36,0.65); }

.toggle { width: 44px; height: 24px; border-radius: 999px; position: relative; cursor: pointer; border: 0.5px solid rgba(94,234,212,0.3); background: rgba(2,6,10,0.6); }
.toggle.on { background: rgba(94,234,212,0.25); border-color: #5EEAD4; }
.toggle span { position: absolute; top: 2px; left: 2px; width: 18px; height: 18px; border-radius: 50%; background: rgba(167,243,208,0.6); transition: all .2s ease; }
.toggle.on span { left: 21px; background: #5EEAD4; }
.chip { padding: 7px 14px; border-radius: 8px; cursor: pointer; font-size: 12px; border: 0.5px solid rgba(94,234,212,0.2); background: transparent; color: rgba(167,243,208,0.6); }
.chip.active { border-color: #5EEAD4; background: rgba(94,234,212,0.15); color: #ECFEFF; }

/* memory */
.mlist { list-style: none; margin: 0 0 14px; padding: 0; display: flex; flex-direction: column; gap: 8px; }
.mlist li { display: flex; align-items: center; gap: 10px; font-size: 13.5px; color: #DCFCF5; }
.mdot { width: 5px; height: 5px; border-radius: 50%; background: #5EEAD4; flex-shrink: 0; }
.mtext { flex: 1; }
.mx { border: none; background: transparent; color: rgba(167,243,208,0.35); cursor: pointer; }
.mx:hover { color: #F87171; }
.muted { font-size: 12px; color: rgba(167,243,208,0.4); margin: 0 0 14px; }

/* skills marketplace */
.scard { border-radius: 14px; padding: 18px; border: 0.5px solid rgba(94,234,212,0.12); background: rgba(8,30,38,0.4); display: flex; flex-direction: column; gap: 6px; }
.scard__top { display: flex; align-items: center; justify-content: space-between; }
.scard__glyph { display: grid; place-items: center; width: 38px; height: 38px; border-radius: 11px; font-size: 18px; color: var(--c); background: color-mix(in srgb, var(--c) 14%, transparent); border: 0.5px solid color-mix(in srgb, var(--c) 35%, transparent); }
.badge--core { font-family: 'JetBrains Mono', monospace; font-size: 8px; letter-spacing: 1px; text-transform: uppercase; color: #02060A; background: #5EEAD4; border-radius: 999px; padding: 3px 8px; }
.scard__stars { font-family: 'JetBrains Mono', monospace; font-size: 10px; color: #FBBF24; }
.scard__name { font-size: 15px; color: #ECFEFF; margin-top: 4px; }
.scard__by { font-family: 'JetBrains Mono', monospace; font-size: 8.5px; letter-spacing: 1px; text-transform: uppercase; color: rgba(94,234,212,0.6); }
.scard__desc { margin: 5px 0 12px; font-size: 12px; line-height: 1.5; color: rgba(167,243,208,0.6); flex: 1; }
.scard__actions { display: flex; align-items: center; gap: 10px; }
.sbtn { flex: 1; padding: 9px; border-radius: 9px; cursor: pointer; font-size: 11px; letter-spacing: 1px; text-transform: uppercase; border: 0.5px solid rgba(94,234,212,0.25); background: rgba(94,234,212,0.08); color: #5EEAD4; transition: all .2s ease; }
.sbtn:hover:not(:disabled) { background: rgba(94,234,212,0.18); border-color: #5EEAD4; }
.sbtn.on { border-color: rgba(94,234,212,0.4); color: #A7F3D0; background: rgba(94,234,212,0.04); }
.sbtn.core { opacity: 0.6; cursor: default; }
.scard__repo { font-size: 10px; color: rgba(167,243,208,0.5); text-decoration: none; white-space: nowrap; }
.scard__repo:hover { color: #5EEAD4; }
.note { margin: 18px 0 0; font-size: 11.5px; color: rgba(167,243,208,0.4); }

/* custom skills */
.custom { margin-top: 28px; padding-top: 22px; border-top: 0.5px solid rgba(94,234,212,0.1); }
.custom__head { display: flex; align-items: center; justify-content: space-between; }
.cform { display: flex; flex-direction: column; gap: 8px; margin: 12px 0 16px; padding: 14px; border-radius: 12px; border: 0.5px solid rgba(94,234,212,0.18); background: rgba(2,6,10,0.4); }
.clist { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 8px; }
.citem { display: flex; align-items: center; gap: 11px; padding: 11px 13px; border-radius: 10px; border: 0.5px solid rgba(94,234,212,0.12); background: rgba(8,30,38,0.4); }
.cglyph { display: grid; place-items: center; width: 32px; height: 32px; border-radius: 9px; color: #A78BFA; background: rgba(167,139,250,0.12); border: 0.5px solid rgba(167,139,250,0.3); }
.cmain { flex: 1; display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.cname { font-size: 13.5px; color: #ECFEFF; }
.curl { font-family: 'JetBrains Mono', monospace; font-size: 10px; color: rgba(167,243,208,0.45); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.badge--soon { font-family: 'JetBrains Mono', monospace; font-size: 8px; letter-spacing: 1px; text-transform: uppercase; color: rgba(167,243,208,0.6); border: 0.5px solid rgba(167,243,208,0.25); border-radius: 999px; padding: 3px 8px; }
.howto { margin-top: 18px; font-size: 12px; color: rgba(167,243,208,0.55); }
.howto summary { cursor: pointer; color: #5EEAD4; letter-spacing: 1px; font-family: 'JetBrains Mono', monospace; font-size: 10px; text-transform: uppercase; }
.howto div { padding: 10px 0; line-height: 1.6; }
.howto p { margin: 0 0 6px; }
.howto b { color: #A7F3D0; }
.error { margin: 16px 0 0; font-size: 12px; color: #FCA5A5; }

@media (max-width: 820px) {
  .body { grid-template-columns: 1fr; }
  .rail { flex-direction: row; flex-wrap: wrap; border-right: none; border-bottom: 0.5px solid rgba(94,234,212,0.08); }
  .rail__entity { display: none; }
}
</style>
