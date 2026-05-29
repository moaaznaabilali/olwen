<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import OlwenEntity from './OlwenEntity.vue'
import WidgetPanel from './WidgetPanel.vue'
import TasksWidget from './TasksWidget.vue'
import WorkMode from './WorkMode.vue'
import EmailWorkMode from './EmailWorkMode.vue'
import EmailReader from './EmailReader.vue'
import EmailComposer from './EmailComposer.vue'
import MorningBrief from './MorningBrief.vue'
import NewsBrief from './NewsBrief.vue'
import AppsDock from './AppsDock.vue'
import TerminalApp from './TerminalApp.vue'
import DevMode from './DevMode.vue'
import ComputerUse from './ComputerUse.vue'
import type { Brief } from '../composables/useBrief'
import type { NewsItem } from '../composables/useNews'
import type { OlwenTask, ReviewResult } from '../composables/useTasks'
import type { EmailMessage, TriagedEmail } from '../composables/useEmail'

type EntityState = 'idle' | 'listening' | 'thinking' | 'speaking' | 'working'

const { user, logout } = useAuth()
const showSettings = ref(false)

// First name for the greeting / pill, from the real account.
const firstName = computed(() => {
  const name = user.value?.display_name || user.value?.email || 'there'
  return name.split(/[@\s]/)[0]
})

/* ---- which widgets the user has enabled ---- */
const enabledWidgets = useState<string[]>(
  'dash:widgets',
  () => ['tasks', 'github', 'inbox', 'calendar', 'news'],
)
const show = (key: string) => enabledWidgets.value.includes(key)

/* ---- entity state (demo switcher) ---- */
const states: EntityState[] = ['idle', 'listening', 'thinking', 'speaking', 'working']
const current = ref<EntityState>('idle')

const command = ref('')

/* ---- talk to Olwen (streaming) + voice ---- */
const olwen = useOlwen()
const voice = useVoice()
const { fetchSettings, updateVoice } = useSettings()
// Voice prefs are SHARED (useState) so the Settings modal and dashboard stay in sync.
const voiceOn = useState<boolean>('voice:on', () => true)
const voiceLang = useState<string>('voice:lang', () => 'en-US')

function toggleVoiceOutput() {
  voiceOn.value = !voiceOn.value
  if (!voiceOn.value) voice.cancelSpeak()
  updateVoice({ enabled: voiceOn.value }).catch(() => {})
}

// listening (mic) and speaking (TTS) drive the creature; else the AI state; else demo switcher.
const entityShown = computed<EntityState>(() => {
  if (reviewing.value) return 'thinking'
  if (voice.listening.value) return 'listening'
  if (voice.speaking.value) return 'speaking'
  if (olwen.active.value) return olwen.entityState.value as EntityState
  return current.value
})

async function runAsk(prompt: string, label?: string) {
  await olwen.ask(prompt, label)
  if (voiceOn.value && olwen.answer.value) voice.speak(olwen.answer.value, voiceLang.value)
}

async function submitCommand() {
  const q = command.value.trim()
  if (!q || olwen.busy.value) return
  command.value = ''
  // "show me my tasks" / "review my tasks" / "what are my tasks" → cinematic work mode (1 AI call)
  if (/\btasks?\b/i.test(q) && /(show|see|view|what|list|bring|review|go through|organi|check|manage|plan|handle)/i.test(q)) {
    startReview()
    return
  }
  await runAsk(q)
}

function toggleMic() {
  if (voice.listening.value) {
    voice.stopListening()
    return
  }
  voice.startListening((text) => {
    command.value = text
    submitCommand()
  }, voiceLang.value)
}

/* ---- tasks: shared store (HUD count) + suggest + cinematic review ---- */
const { tasks, review } = useTasks()
const reviewResult = ref<ReviewResult | null>(null)
const reviewing = ref(false)

// Cinematic email reading (Olwen reads each triaged email like he reads tasks).
const emailReview = ref<TriagedEmail[] | null>(null)
function onEmailReviewed(items: TriagedEmail[]) {
  emailReview.value = items
}

// Clicking an email opens it in Olwen's reader (he summarizes; user can ask for full read).
const openedEmail = ref<EmailMessage | TriagedEmail | null>(null)
function onEmailOpen(e: EmailMessage | TriagedEmail) {
  openedEmail.value = e
}
const composerOpen = ref(false)

// Morning brief — auto-show once a day after user's brief time
const briefData = ref<Brief | null>(null)
const briefLoading = ref(false)
const { today: briefToday, shouldShow: briefShouldShow, markSeen: briefMarkSeen } = useBrief()

async function runBriefNow() {
  if (briefLoading.value) return
  briefLoading.value = true
  try {
    briefData.value = await briefToday()
    briefMarkSeen().catch(() => {})
  } catch { /* */ } finally { briefLoading.value = false }
}
function closeBrief() { briefData.value = null }

const newsBriefData = ref<{ narrative: string; items: (NewsItem & { why: string })[]; topics: string[] } | null>(null)
async function runNewsBrief() {
  if (newsBriefData.value) return
  try { newsBriefData.value = await useNews().brief() } catch { /* */ }
}
function closeNewsBrief() { newsBriefData.value = null }

// Apps dock: which apps are currently open
const { open: openApps, closeApp } = useApps()

// Dev mode — hacker-themed focus environment for picking a project
const devModeOpen = ref(false)
function enterDevMode() { devModeOpen.value = true }
function exitDevMode() { devModeOpen.value = false }

// Computer Use — Olwen drives the user's mouse + keyboard via olwen-bridge
const computerUseOpen = ref(false)
function exitComputerUse() { computerUseOpen.value = false }

// Terminal launched by an agent UI action (so we can pass cwd / autoStart)
const agentTerminal = ref<{ cwd: string | null; command: string | null } | null>(null)

// Dispatcher: react when the chat agent emits a UI action.
const { launch: launchApp } = useApps()
watch(() => olwen.lastUiAction.value, (val) => {
  if (!val) return
  const a = val.action
  switch (a.ui_action) {
    case 'open_terminal': {
      // Open via the agent-controlled slot so we can pass cwd + auto-start command
      agentTerminal.value = {
        cwd: (a.cwd as string) || null,
        command: (a.command as string) || null,
      }
      launchApp('terminal')                                                       // also flag it as open in the dock
      break
    }
    case 'open_dev_mode':           devModeOpen.value = true; break
    case 'open_computer_use':       computerUseOpen.value = true; break
    case 'open_settings': {
      const sec = (a.section as string) || 'connections'
      useState<string>('settings:section', () => 'connections').value = sec
      showSettings.value = true
      break
    }
    case 'open_compose_email':      composerOpen.value = true; break
    case 'run_morning_brief':       runBriefNow(); break
    case 'read_news':               runNewsBrief(); break
    case 'triage_inbox':            /* widget owns this; nothing yet */ break
  }
})

function suggestTask(t: OlwenTask) {
  runAsk(
    `Here is one of my tasks: "${t.text}" (priority: ${t.priority}, list: ${t.list_name}). `
    + 'In 2–3 short sentences, suggest concretely how I should tackle it or move it forward.',
    `Suggest · ${t.text}`,
  )
}

// Cinematic "work mode": one AI call reviews all tasks, then the animation plays.
async function startReview() {
  if (reviewing.value || reviewResult.value) return
  reviewing.value = true
  try {
    const result = await review()
    if (result.tasks.length) reviewResult.value = result
  } catch { /* ignore */ } finally {
    reviewing.value = false
  }
}

// Olwen's "thoughts" cycle on the loading screen so it feels alive, not generic.
const loadingPhrases = ['Gathering your day', 'Reading your tasks', 'Weighing what matters', 'Choosing where to start']
const loadingPhrase = ref(loadingPhrases[0])
let phraseTimer: ReturnType<typeof setInterval> | undefined
watch(reviewing, (on) => {
  if (phraseTimer) clearInterval(phraseTimer)
  if (on) {
    let i = 0
    loadingPhrase.value = loadingPhrases[0]
    phraseTimer = setInterval(() => {
      i = (i + 1) % loadingPhrases.length
      loadingPhrase.value = loadingPhrases[i]
    }, 1400)
  }
})

const commits = [
  { repo: 'olwen/frontend', msg: 'feat: login screen', time: '2m' },
  { repo: 'olwen/backend', msg: 'feat: account system', time: '30m' },
  { repo: 'olwen/frontend', msg: 'feat: dashboard layout', time: '2h' },
  { repo: 'olwen/frontend', msg: 'chore: init nuxt scaffold', time: '5h' },
]

const emails = [
  { from: 'Sarah Chen', subject: 'Can you review the deck?', time: '9:12', unread: true },
  { from: 'GitHub', subject: '[olwen] CI pipeline passed', time: '8:40', unread: true },
  { from: 'Namecheap', subject: 'Your domain renews soon', time: 'Tue', unread: false },
  { from: 'LinkedIn', subject: '5 people viewed your profile', time: 'Mon', unread: false },
]

const today = [
  { at: '10:00', label: 'Team standup', soon: false },
  { at: '13:00', label: 'Lunch with client', soon: true },
  { at: '16:30', label: 'Deploy window', soon: false },
]

const news = [
  { title: 'Anthropic releases Claude Opus 4.7', source: 'The Verge', time: '1h', tag: 'Models' },
  { title: 'OpenAI unveils new reasoning model', source: 'TechCrunch', time: '3h', tag: 'Models' },
  { title: 'Gemini 3 benchmark results leak online', source: 'Ars Technica', time: '5h', tag: 'Research' },
  { title: 'EU AI Act enforcement phase begins', source: 'Reuters', time: '8h', tag: 'Policy' },
  { title: 'Nvidia announces next-gen AI chips', source: 'Bloomberg', time: '12h', tag: 'Hardware' },
]

/* ---- live clock + greeting ---- */
const now = ref(new Date())
let clockTimer: ReturnType<typeof setInterval> | undefined

const timeStr = computed(() => {
  let h = now.value.getHours()
  const m = now.value.getMinutes().toString().padStart(2, '0')
  const unit = h >= 12 ? 'PM' : 'AM'
  h = h % 12 || 12
  return { value: `${h}:${m}`, unit }
})
const greeting = computed(() => {
  const h = now.value.getHours()
  return h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening'
})

/* ---- real weather (Open-Meteo: free, no key) for Riyadh ---- */
const weather = ref({ temp: '—', desc: '…' })
function weatherDesc(code: number): string {
  if (code === 0) return 'CLEAR'
  if (code <= 3) return 'CLOUDS'
  if (code <= 67) return 'RAIN'
  if (code <= 77) return 'SNOW'
  return 'STORM'
}
async function loadWeather() {
  try {
    const r = await $fetch<{ current: { temperature_2m: number; weather_code: number } }>(
      'https://api.open-meteo.com/v1/forecast',
      { query: { latitude: 24.71, longitude: 46.68, current: 'temperature_2m,weather_code' } },
    )
    weather.value = {
      temp: `${Math.round(r.current.temperature_2m)}°`,
      desc: weatherDesc(r.current.weather_code),
    }
  } catch {
    weather.value = { temp: '—', desc: '' }
  }
}

onMounted(async () => {
  clockTimer = setInterval(() => { now.value = new Date() }, 30_000)
  loadWeather()
  // tasks load inside TasksWidget; HUD reads the shared store reactively.

  // Post-OAuth return → open Console straight to the right tab.
  if (import.meta.client) {
    const params = new URLSearchParams(window.location.search)
    if (params.get('settings') === 'email') {
      useState<string>('settings:section', () => 'connections').value = 'email'
      showSettings.value = true
      window.history.replaceState(null, '', '/')
    } else if (params.get('settings') === 'connections' || params.get('github') === '1') {
      useState<string>('settings:section', () => 'connections').value = 'connections'
      showSettings.value = true
      window.history.replaceState(null, '', '/')
    }
  }
  // load the user's saved voice + dashboard preferences
  try {
    const s = await fetchSettings()
    voiceOn.value = s.voice.enabled
    voiceLang.value = s.voice.lang
    if (s.dashboard_widgets?.length) enabledWidgets.value = s.dashboard_widgets
  } catch { /* keep defaults */ }

  // Morning brief: fire it once per day, after the user's chosen time
  try {
    const check = await briefShouldShow()
    if (check.show) runBriefNow()
  } catch { /* */ }
})
onBeforeUnmount(() => { if (clockTimer) clearInterval(clockTimer) })

/* ---- HUD from real / live data ---- */
const hud = computed(() => [
  { label: 'Local time', value: timeStr.value.value, unit: timeStr.value.unit, accent: '#5EEAD4' },
  { label: 'Riyadh', value: weather.value.temp, unit: weather.value.desc, accent: '#FBBF24' },
  { label: 'Inbox', value: String(emails.filter(e => e.unread).length), unit: 'UNREAD', accent: '#5EEAD4' },
  { label: 'Tasks', value: String(tasks.value.filter(t => !t.done).length), unit: 'OPEN', accent: '#F87171' },
  { label: 'Today', value: String(today.length), unit: 'EVENTS', accent: '#A78BFA' },
])

const priorityColor: Record<string, string> = {
  high: '#F87171',
  med: '#FBBF24',
  low: '#5EEAD4',
}
</script>

<template>
  <div class="dashboard">
    <!-- header -->
    <header class="topbar">
      <div class="brand-wrap">
        <span class="brand">OLWEN</span>
        <span class="brand__sub">quietly knows everything</span>
      </div>
      <div class="topbar__right">
        <!-- temporary dev control to preview entity states -->
        <div class="state-switch">
          <button
            v-for="s in states"
            :key="s"
            :class="{ active: current === s }"
            @click="current = s"
          >{{ s }}</button>
        </div>
        <button class="iconbtn iconbtn--dev" title="Enter Dev Mode" @click="enterDevMode">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="8 5 3 12 8 19" /><polyline points="16 5 21 12 16 19" />
          </svg>
        </button>
        <button class="iconbtn iconbtn--cu" title="Give Olwen the wheel — control mouse & keyboard" @click="computerUseOpen = true">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
            <rect x="2" y="4" width="20" height="13" rx="2" />
            <path d="M8 21h8M12 17v4" />
            <path d="M9 9l3 3 5-5" />
          </svg>
        </button>
        <button class="iconbtn" title="Run morning brief" :disabled="briefLoading" @click="runBriefNow">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
            <path d="M12 2v3M4.5 4.5l2.1 2.1M2 12h3M4.5 19.5l2.1-2.1M12 22v-3M19.5 19.5l-2.1-2.1M22 12h-3M19.5 4.5l-2.1 2.1" />
            <circle cx="12" cy="12" r="4" />
          </svg>
        </button>
        <button class="iconbtn" title="Settings" @click="showSettings = true">⚙</button>
        <div class="userpill">
          <span class="userpill__dot" />
          <span class="userpill__name">{{ firstName }}</span>
          <button class="userpill__out" title="Sign out" @click="logout">⏻</button>
        </div>
      </div>
    </header>

    <!-- HUD stat strip -->
    <div class="hud">
      <div v-for="(h, i) in hud" :key="i" class="hud__tile" :style="{ '--accent': h.accent }">
        <span class="hud__label">{{ h.label }}</span>
        <span class="hud__value">{{ h.value }}<small>{{ h.unit }}</small></span>
      </div>
    </div>

    <!-- dashboard grid -->
    <main class="grid">
      <!-- LEFT -->
      <div class="col col--left">
        <TasksWidget v-if="show('tasks')" @suggest="suggestTask" @review="startReview" />
        <GithubWidget v-if="show('github')" @open-settings="showSettings = true" />
      </div>

      <!-- CENTER -->
      <div class="col col--center">
        <!-- conversation when Olwen is answering, else the greeting -->
        <div v-if="olwen.active.value" class="convo">
          <p class="convo__q">{{ olwen.lastQuestion.value }}</p>
          <p class="convo__a">{{ olwen.answer.value
            }}<span v-if="olwen.busy.value" class="convo__cursor">▍</span></p>
        </div>
        <template v-else>
          <p class="greeting">{{ greeting }}, {{ firstName }}.</p>
          <p class="greeting__sub">3 things need you today. I’ve handled the rest.</p>
        </template>

        <div class="entity-hold">
          <div class="entity-frame" data-olwen>
            <OlwenEntity :state="entityShown" />
          </div>
        </div>

        <div class="commandbar" :class="{ busy: olwen.busy.value, listening: voice.listening.value }">
          <button
            v-if="voice.supported.value"
            class="cmdbtn mic"
            :class="{ on: voice.listening.value }"
            :title="voice.listening.value ? 'Stop listening' : 'Speak to Olwen'"
            @click="toggleMic"
          >
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round">
              <rect x="9" y="2.5" width="6" height="11" rx="3" /><path d="M5 11a7 7 0 0 0 14 0" /><line x1="12" y1="18" x2="12" y2="21" />
            </svg>
          </button>
          <span v-else class="commandbar__glyph">✦</span>

          <input
            v-model="command"
            class="commandbar__input"
            type="text"
            :placeholder="voice.listening.value ? 'Listening…' : (olwen.busy.value ? 'Olwen is thinking…' : 'Ask Olwen, or tap the mic…')"
            :disabled="olwen.busy.value"
            @keyup.enter="submitCommand"
          >

          <button
            v-if="voice.supported.value"
            class="cmdbtn mute"
            :class="{ off: !voiceOn }"
            :title="voiceOn ? 'Voice reply: on' : 'Voice reply: off'"
            @click="toggleVoiceOutput"
          >
            <svg v-if="voiceOn" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
              <path d="M4 9v6h4l5 4V5L8 9H4z" /><path d="M16.5 8.5a4 4 0 0 1 0 7" />
            </svg>
            <svg v-else viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
              <path d="M4 9v6h4l5 4V5L8 9H4z" /><line x1="16" y1="9" x2="21" y2="15" /><line x1="21" y1="9" x2="16" y2="15" />
            </svg>
          </button>
          <span v-else class="commandbar__hint">⏎</span>
        </div>
      </div>

      <!-- RIGHT -->
      <div class="col col--right">
        <InboxWidget
          v-if="show('inbox')"
          @open-settings="showSettings = true"
          @reviewed="onEmailReviewed"
          @open="onEmailOpen"
          @compose="composerOpen = true"
        />
        <CalendarWidget v-if="show('calendar')" @open-settings="showSettings = true" />
        <NewsWidget
          v-if="show('news')"
          @open-settings="showSettings = true"
          @read-with-olwen="runNewsBrief"
        />
        <HealthWidget v-if="show('health')" @open-settings="showSettings = true" />
      </div>
    </main>

    <SettingsScreen v-if="showSettings" @close="showSettings = false" />

    <!-- loading veil while Olwen scans the day (the 1 AI call) -->
    <Transition name="veil">
      <div v-if="reviewing" class="reviewing">
        <div class="reviewing__core" aria-hidden="true">
          <span class="sonar" /><span class="sonar" /><span class="sonar" /><span class="sonar" />
          <div class="reviewing__glow" />
          <div class="reviewing__entity"><OlwenEntity state="thinking" /></div>
        </div>
        <Transition name="phrase" mode="out-in">
          <p :key="loadingPhrase" class="reviewing__label">{{ loadingPhrase }}</p>
        </Transition>
      </div>
    </Transition>
    <WorkMode
      v-if="reviewResult"
      :items="reviewResult.tasks"
      :start-index="reviewResult.start_index"
      :start-reason="reviewResult.start_reason"
      @close="reviewResult = null"
    />
    <EmailWorkMode
      v-if="emailReview"
      :items="emailReview"
      @close="emailReview = null"
    />
    <EmailReader
      v-if="openedEmail"
      :initial="openedEmail"
      @close="() => { voice.cancelSpeak(); openedEmail = null }"
    />
    <EmailComposer
      v-if="composerOpen"
      @close="composerOpen = false"
      @sent="composerOpen = false"
    />
    <MorningBrief
      v-if="briefData"
      :brief="briefData"
      @close="closeBrief"
    />
    <NewsBrief
      v-if="newsBriefData"
      :narrative="newsBriefData.narrative"
      :items="newsBriefData.items"
      :topics="newsBriefData.topics"
      @close="closeNewsBrief"
    />

    <!-- Apps dock + any open app windows -->
    <AppsDock />
    <TerminalApp
      v-if="openApps.includes('terminal')"
      :cwd="agentTerminal?.cwd ?? null"
      :auto-start="agentTerminal?.command ?? null"
      @close="() => { closeApp('terminal'); agentTerminal = null }"
    />

    <!-- Dev mode focus environment (full-screen overlay) -->
    <DevMode v-if="devModeOpen" @close="exitDevMode" />

    <!-- Computer Use — Olwen drives the OS-level mouse/keyboard via olwen-bridge -->
    <div v-if="computerUseOpen" class="cu-overlay" role="dialog" aria-label="Computer Use">
      <ComputerUse @close="exitComputerUse" />
    </div>
  </div>
</template>

<style scoped>
.dashboard {
  position: relative;
  z-index: 1;
  height: 100%;
  display: grid;
  grid-template-rows: auto auto 1fr;
  min-height: 0;
}

/* ---- header ---- */
.topbar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 16px 24px;
}
.brand-wrap { display: flex; align-items: baseline; gap: 12px; }
.brand {
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  letter-spacing: 4px; font-size: 15px; color: #5EEAD4;
}
.brand__sub { font-size: 11px; letter-spacing: 1.5px; color: rgba(167,243,208,0.4); }
.topbar__right { display: flex; align-items: center; gap: 14px; }
.state-switch { display: flex; gap: 6px; }
.state-switch button {
  padding: 5px 11px; border-radius: 999px;
  border: 0.5px solid rgba(94,234,212,0.18); background: transparent;
  color: rgba(167,243,208,0.6);
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 9.5px; letter-spacing: 1.2px; text-transform: uppercase; cursor: pointer;
  transition: all .2s ease;
}
.state-switch button.active {
  background: rgba(94,234,212,0.14); border-color: #5EEAD4; color: #ECFEFF;
}
/* loading veil — "Olwen scans your day" */
.reviewing {
  position: fixed; inset: 0; z-index: 55;
  display: grid; place-items: center;
  background: radial-gradient(ellipse at 50% 45%, #08131a 0%, #02060A 72%);
}
.reviewing__core { position: relative; display: grid; place-items: center; width: 420px; height: 420px; }
.reviewing__entity { position: relative; z-index: 2; width: 250px; height: 250px; display: grid; place-items: center; }

/* breathing glow behind the creature */
.reviewing__glow {
  position: absolute; width: 240px; height: 240px; border-radius: 50%; z-index: 1;
  background: radial-gradient(circle, rgba(94,234,212,0.22), rgba(6,182,212,0.06) 55%, transparent 72%);
  filter: blur(8px); animation: corebreath 3.2s ease-in-out infinite;
}
@keyframes corebreath { 0%,100% { transform: scale(1); opacity: 0.7; } 50% { transform: scale(1.12); opacity: 1; } }

/* sonar rings pulsing out — like Olwen scanning */
.sonar {
  position: absolute; width: 230px; height: 230px; border-radius: 50%;
  border: 1px solid rgba(94,234,212,0.5); opacity: 0;
}
@media (prefers-reduced-motion: no-preference) {
  .sonar { animation: sonar 3.4s cubic-bezier(.22,.61,.36,1) infinite; }
  .sonar:nth-child(2) { animation-delay: .85s; }
  .sonar:nth-child(3) { animation-delay: 1.7s; }
  .sonar:nth-child(4) { animation-delay: 2.55s; }
}
@keyframes sonar {
  0% { transform: scale(0.55); opacity: 0; }
  12% { opacity: 0.7; }
  100% { transform: scale(2.1); opacity: 0; }
}

.reviewing__label {
  position: absolute; bottom: 24%;
  font-family: 'JetBrains Mono', monospace; font-size: 11px; letter-spacing: 3px;
  text-transform: uppercase; color: #A7F3D0; text-align: center;
}
.reviewing__label::after { content: '…'; color: #5EEAD4; }

.phrase-enter-active, .phrase-leave-active { transition: opacity .35s ease, transform .35s ease; }
.phrase-enter-from { opacity: 0; transform: translateY(6px); }
.phrase-leave-to { opacity: 0; transform: translateY(-6px); }

.veil-enter-active, .veil-leave-active { transition: opacity .45s ease; }
.veil-enter-from, .veil-leave-to { opacity: 0; }

.iconbtn {
  width: 30px; height: 30px; border-radius: 999px; cursor: pointer;
  border: 0.5px solid rgba(94,234,212,0.2); background: rgba(8,51,68,0.3);
  color: rgba(167,243,208,0.7); font-size: 14px; line-height: 1;
  transition: all .2s ease;
}
.iconbtn:hover { color: #5EEAD4; border-color: #5EEAD4; }
.iconbtn--cu { color: rgba(167,243,208,0.85); border-color: rgba(94,234,212,0.35); }
.iconbtn--cu:hover { color: #02060A; background: linear-gradient(135deg, #A7F3D0, #5EEAD4); border-color: transparent; }

/* Computer-Use full-screen overlay */
.cu-overlay {
  position: fixed; inset: 0; z-index: 90;
  background: rgba(2,6,10,0.86);
  backdrop-filter: blur(20px);
  display: flex; align-items: stretch; justify-content: center;
  padding: 32px;
  animation: cuOverlayIn .25s ease;
}
.cu-overlay > * {
  width: min(960px, 100%);
  max-height: 100%;
  border-radius: 18px;
  border: 0.5px solid rgba(94,234,212,0.18);
  box-shadow: 0 30px 80px -20px rgba(0,0,0,0.6);
  overflow: hidden;
}
@keyframes cuOverlayIn { from { opacity: 0; } to { opacity: 1; } }
.userpill {
  display: flex; align-items: center; gap: 8px;
  padding: 5px 8px 5px 12px; border-radius: 999px;
  border: 0.5px solid rgba(94,234,212,0.2); background: rgba(8,51,68,0.3);
}
.userpill__dot { width: 7px; height: 7px; border-radius: 50%; background: #5EEAD4; box-shadow: 0 0 8px #5EEAD4; }
.userpill__name {
  font-size: 12px; letter-spacing: 0.5px; color: #DCFCF5; text-transform: capitalize;
}
.userpill__out {
  border: none; background: transparent; cursor: pointer;
  color: rgba(167,243,208,0.5); font-size: 13px; padding: 0 2px;
  transition: color .2s ease;
}
.userpill__out:hover { color: #F87171; }

/* ---- HUD strip ---- */
.hud {
  display: flex; gap: 10px; padding: 2px 24px 10px;
}
.hud__tile {
  flex: 1;
  display: flex; flex-direction: column; gap: 3px;
  padding: 9px 14px; border-radius: 10px;
  border: 0.5px solid rgba(94,234,212,0.10);
  border-left: 2px solid var(--accent);
  background: rgba(8,51,68,0.16); backdrop-filter: blur(6px);
}
.hud__label {
  font-family: 'JetBrains Mono', monospace;
  font-size: 9px; letter-spacing: 1.6px; text-transform: uppercase;
  color: rgba(167,243,208,0.5);
}
.hud__value { font-size: 20px; font-weight: 300; color: #ECFEFF; line-height: 1; }
.hud__value small {
  font-family: 'JetBrains Mono', monospace;
  font-size: 9px; letter-spacing: 1px; color: var(--accent); margin-left: 5px;
}

/* ---- grid ---- */
.grid {
  display: grid;
  grid-template-columns: minmax(300px, 370px) 1fr minmax(300px, 370px);
  gap: 18px; padding: 4px 24px 22px; min-height: 0;
}
.col { display: flex; flex-direction: column; gap: 18px; min-height: 0; }
.col--left, .col--right { overflow: hidden; }
.col--left > .panel, .col--right > .panel { flex: 1; }
.col--center {
  align-items: center; justify-content: space-between;
  padding: 10px 0 4px; text-align: center;
}
.greeting { margin: 4px 0 0; font-size: 26px; font-weight: 300; letter-spacing: 0.3px; color: #ECFEFF; }
.greeting__sub { margin: 8px 0 0; font-size: 13px; color: rgba(167,243,208,0.55); }

/* ---- conversation ---- */
.convo {
  width: min(620px, 92%);
  max-height: 30vh; overflow-y: auto;
  display: flex; flex-direction: column; gap: 8px;
  padding: 4px 2px;
}
.convo__q {
  margin: 0; align-self: flex-end;
  font-size: 13px; color: rgba(167,243,208,0.6);
  border: 0.5px solid rgba(94,234,212,0.18); border-radius: 12px 12px 2px 12px;
  padding: 7px 12px; background: rgba(8,51,68,0.3); max-width: 80%;
}
.convo__a {
  margin: 0; align-self: flex-start; text-align: left;
  font-size: 15px; line-height: 1.55; color: #ECFEFF; font-weight: 300;
  white-space: pre-wrap;
}
.convo__cursor { color: #5EEAD4; animation: blink 1s step-start infinite; }
@keyframes blink { 50% { opacity: 0; } }
.entity-hold { flex: 1; display: grid; place-items: center; width: 100%; min-height: 0; }
.entity-frame { width: min(360px, 70%); }

/* ---- command bar ---- */
.commandbar {
  width: min(560px, 90%);
  display: flex; align-items: center; gap: 10px;
  padding: 12px 16px; border-radius: 999px;
  border: 0.5px solid rgba(94,234,212,0.22);
  background: rgba(8,51,68,0.30); backdrop-filter: blur(8px);
}
.commandbar__glyph { color: #5EEAD4; font-size: 13px; }
.commandbar__input {
  flex: 1; background: transparent; border: none; outline: none;
  color: #E2F5F1; font-size: 14px; letter-spacing: 0.3px;
}
.commandbar.busy { border-color: rgba(94,234,212,0.4); box-shadow: 0 0 18px rgba(94,234,212,0.18); }
.commandbar.listening { border-color: #5EEAD4; box-shadow: 0 0 22px rgba(94,234,212,0.28); }
.cmdbtn {
  display: grid; place-items: center; width: 30px; height: 30px; flex-shrink: 0;
  border-radius: 50%; border: 0.5px solid rgba(94,234,212,0.25);
  background: transparent; color: #5EEAD4; cursor: pointer; transition: all .2s ease;
}
.cmdbtn:hover { border-color: #5EEAD4; background: rgba(94,234,212,0.10); }
.cmdbtn.mic.on { background: #5EEAD4; color: #02060A; border-color: #5EEAD4; animation: micpulse 1.2s ease-in-out infinite; }
.cmdbtn.mute.off { color: rgba(167,243,208,0.4); border-color: rgba(167,243,208,0.18); }
@keyframes micpulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(94,234,212,0.5); }
  50% { box-shadow: 0 0 0 7px rgba(94,234,212,0); }
}
.commandbar__input:disabled { opacity: 0.6; cursor: progress; }
.commandbar__input::placeholder { color: rgba(167,243,208,0.4); }
.commandbar__hint {
  font-family: 'JetBrains Mono', monospace; font-size: 11px;
  color: rgba(167,243,208,0.4);
  border: 0.5px solid rgba(94,234,212,0.2); border-radius: 6px; padding: 1px 6px;
}

/* ---- shared list styling ---- */
.list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; }
.list > li {
  display: flex; align-items: center; gap: 10px;
  padding: 9px 2px; border-bottom: 0.5px solid rgba(255,255,255,0.04); font-size: 13px;
}
.list > li:last-child { border-bottom: none; }
.time { font-family: 'JetBrains Mono', monospace; font-size: 10px; color: rgba(167,243,208,0.4); white-space: nowrap; }
.dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }

/* tasks */
.task__box { width: 15px; height: 15px; border-radius: 4px; flex-shrink: 0; padding: 0; cursor: pointer; border: 1px solid rgba(94,234,212,0.4); background: transparent; transition: all .15s ease; }
.task__box:hover { border-color: #5EEAD4; }
.task__box.checked { background: #5EEAD4; border-color: #5EEAD4; }
.task__main { flex: 1; display: flex; flex-direction: column; gap: 1px; min-width: 0; }
.task__text { color: #DCFCF5; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.task__list { font-size: 8.5px; letter-spacing: 0.8px; text-transform: uppercase; color: rgba(167,243,208,0.4); }
.task.done .task__text { color: rgba(167,243,208,0.35); text-decoration: line-through; }
.task__act { border: none; background: transparent; cursor: pointer; flex-shrink: 0; color: rgba(167,243,208,0.4); font-size: 13px; padding: 0 2px; opacity: 0; transition: all .15s ease; }
.task:hover .task__act { opacity: 1; }
.task__act:hover { color: #5EEAD4; }
.task__act.del:hover { color: #F87171; }
.addtask { display: flex; align-items: center; gap: 8px; margin-top: 8px; padding-top: 10px; border-top: 0.5px solid rgba(255,255,255,0.05); }
.addtask__list { background: rgba(2,6,10,0.5); color: #A7F3D0; cursor: pointer; border: 0.5px solid rgba(94,234,212,0.18); border-radius: 6px; font-size: 10px; padding: 4px 6px; outline: none; }
.addtask__input { flex: 1; background: transparent; border: none; outline: none; color: #E2F5F1; font-size: 12px; }
.addtask__input::placeholder { color: rgba(167,243,208,0.35); }

/* commits */
.commit__icon { color: #A78BFA; font-family: monospace; }
.commit__main { flex: 1; display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.commit__msg { color: #DCFCF5; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.commit__repo { font-family: 'JetBrains Mono', monospace; font-size: 10px; color: rgba(167,139,250,0.6); }

/* emails */
.email__dot { width: 7px; height: 7px; border-radius: 50%; background: transparent; flex-shrink: 0; }
.email__dot.on { background: #5EEAD4; box-shadow: 0 0 8px #5EEAD4; }
.email__main { flex: 1; display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.email__from { color: #DCFCF5; }
.email.unread .email__from { color: #ECFEFF; font-weight: 500; }
.email__subject { font-size: 11.5px; color: rgba(167,243,208,0.5); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

/* ai news */
.news { align-items: flex-start; }
.news__tag {
  font-family: 'JetBrains Mono', monospace;
  font-size: 8px; letter-spacing: 1px; text-transform: uppercase;
  color: #22D3EE; border: 0.5px solid rgba(34,211,238,0.35);
  border-radius: 999px; padding: 2px 6px; white-space: nowrap; margin-top: 1px;
}
.news__main { flex: 1; display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.news__title { color: #DCFCF5; line-height: 1.3; }
.news__meta { font-size: 10.5px; color: rgba(167,243,208,0.45); }

/* events */
.event__at { font-family: 'JetBrains Mono', monospace; font-size: 11px; color: #5EEAD4; width: 40px; }
.event__label { flex: 1; color: #DCFCF5; }
.event__tag {
  font-size: 9px; letter-spacing: 1px; text-transform: uppercase;
  color: #FBBF24; border: 0.5px solid rgba(251,191,36,0.4); border-radius: 999px; padding: 1px 7px;
}

@media (max-width: 1000px) {
  .grid { grid-template-columns: 1fr; overflow-y: auto; }
}
</style>
