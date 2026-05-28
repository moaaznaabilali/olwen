<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import WidgetPanel from './WidgetPanel.vue'
import type { CalEvent } from '../composables/useCalendar'

const emit = defineEmits<{ openSettings: [] }>()
const { configured, events: fetchEvents } = useCalendar()

const connected = ref(false)
const needs = ref<'none' | 'connect_google' | 'switch_to_oauth' | 'setup_server_oauth' | 'reconsent'>('connect_google')
const hasGmailImap = ref(false)
const events = ref<CalEvent[]>([])
const loading = ref(false)
const error = ref('')
const calApiDisabled = ref(false)

const enableCalUrl = computed(() => {
  const pid = import.meta.client ? localStorage.getItem('olwen_google_project_id') : null
  const suffix = pid ? `?project=${encodeURIComponent(pid)}` : ''
  return `https://console.cloud.google.com/apis/library/calendar-json.googleapis.com${suffix}`
})

async function load() {
  loading.value = true; error.value = ''; calApiDisabled.value = false
  try {
    const cfg = await configured()
    connected.value = cfg.connected
    needs.value = cfg.needs
    hasGmailImap.value = cfg.has_gmail_imap
    if (connected.value) {
      const r = await fetchEvents(36, 8)
      events.value = r.events
    }
  } catch (e: unknown) {
    const detail = (e as { data?: { detail?: string } })?.data?.detail || ''
    if (detail.startsWith('CALENDAR_API_DISABLED')) {
      calApiDisabled.value = true
    } else {
      error.value = detail || 'Could not load calendar.'
    }
  } finally { loading.value = false }
}

function openEmailSettings() {
  useState<string>('settings:section', () => 'connections').value = 'email'
  emit('openSettings')
}
async function signInWithGoogle() {
  try {
    const r = await useEmail().oauthStart()
    if (r.auth_url) { window.location.href = r.auth_url }
  } catch {
    // Fall back to settings if start failed (e.g. server creds not saved yet)
    openEmailSettings()
  }
}

function fmt(iso: string): string {
  if (!iso) return ''
  // all-day event has YYYY-MM-DD only
  if (iso.length === 10) return 'All day'
  const d = new Date(iso)
  return isFinite(d.getTime()) ? d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' }) : ''
}
function dayLabel(iso: string): string {
  if (!iso) return ''
  const d = new Date(iso); if (!isFinite(d.getTime())) return ''
  const today = new Date(); today.setHours(0, 0, 0, 0)
  const evDay = new Date(d); evDay.setHours(0, 0, 0, 0)
  const diff = Math.round((evDay.getTime() - today.getTime()) / 86400000)
  if (diff === 0) return ''
  if (diff === 1) return 'TOMORROW'
  return d.toLocaleDateString(undefined, { weekday: 'short' }).toUpperCase()
}
function soon(iso: string): boolean {
  if (!iso || iso.length === 10) return false
  const t = new Date(iso).getTime()
  return isFinite(t) && t - Date.now() < 90 * 60_000   // < 90 min away
}

const count = computed(() => events.value.length)
onMounted(load)
</script>

<template>
  <WidgetPanel title="Today" :badge="count || undefined" accent="#5EEAD4">
    <div class="cal">
      <p v-if="error" class="error">{{ error }}</p>

      <div v-if="calApiDisabled" class="apifix">
        <p class="apifix__title">⚠ Calendar API not enabled</p>
        <p class="apifix__txt">
          Your Google connection is fine, but the Calendar API isn't turned on in your
          Olwen project on Google Cloud. Click below → press <strong>Enable</strong>
          → wait a few seconds → reload.
        </p>
        <a class="apifix__cta" :href="enableCalUrl" target="_blank" rel="noopener">↗ Enable Calendar API</a>
        <button class="apifix__retry" @click="load">↻ Reload</button>
      </div>

      <template v-if="!connected && !loading">
        <!-- Case A: server has no Google OAuth credentials. The "Sign in with
             Google" button can't even appear in the email wizard until those
             are set up. THIS IS THE USER'S CURRENT CASE. -->
        <template v-if="needs === 'setup_server_oauth'">
          <p class="empty">
            <strong>Setup needed.</strong> The "Sign in with Google" path isn't
            wired up yet — that's why reconnecting your email gave you the
            password path only. One-time setup, about a minute.
          </p>
          <button class="cta" @click="openEmailSettings">⚙ Set up Sign-in with Google</button>
        </template>

        <!-- Case B: server is ready, but user's Gmail is connected by app password.
             Server creds exist — we can launch the OAuth flow with one click,
             no need to send them on a 4-step settings tour. -->
        <template v-else-if="needs === 'switch_to_oauth' || hasGmailImap">
          <p class="empty">
            Your Gmail is connected with an <strong>app password</strong>.
            One click upgrades it and grants calendar access.
          </p>
          <button class="cta" @click="signInWithGoogle">↗ Sign in with Google now</button>
          <p class="muted">Google will ask you to approve Gmail + Calendar permission. You bounce back here connected.</p>
        </template>

        <!-- Case C: nothing connected. -->
        <template v-else>
          <p class="empty">Connect Google to see your calendar.</p>
          <button class="cta" @click="openEmailSettings">⚙ Sign in with Google</button>
        </template>
      </template>

      <template v-else-if="connected">
        <ul v-if="loading" class="list">
          <li v-for="i in 2" :key="i" class="skel" :style="{ '--d': `${i * 100}ms` }">
            <span class="skel__at" /><span class="skel__line" />
          </li>
        </ul>

        <p v-else-if="!events.length" class="muted">Your next 36 hours are clear ✨</p>

        <ul v-else class="list">
          <li v-for="e in events" :key="e.id" class="event" :class="{ soon: soon(e.start) }">
            <div class="event__when">
              <span class="event__at">{{ fmt(e.start) }}</span>
              <span v-if="dayLabel(e.start)" class="event__day">{{ dayLabel(e.start) }}</span>
            </div>
            <div class="event__main">
              <a v-if="e.url" class="event__label" :href="e.url" target="_blank" rel="noopener">{{ e.title }}</a>
              <span v-else class="event__label">{{ e.title }}</span>
              <span v-if="e.location" class="event__loc">{{ e.location }}</span>
            </div>
            <span v-if="soon(e.start)" class="event__tag">soon</span>
          </li>
        </ul>
      </template>
    </div>
  </WidgetPanel>
</template>

<style scoped>
.cal { display: flex; flex-direction: column; gap: 6px; }
.error { margin: 0; font-size: 11.5px; color: #FCA5A5; border-left: 2px solid #F87171; padding-left: 9px; }
.empty { margin: 6px 2px 10px; font-size: 12.5px; line-height: 1.5; color: rgba(167,243,208,0.55); }
.muted { margin: 8px 2px 0; font-size: 12px; color: rgba(167,243,208,0.4); }
.cta { padding: 9px; border-radius: 9px; cursor: pointer; width: 100%; border: 0.5px solid rgba(94,234,212,0.3); background: rgba(94,234,212,0.1); color: #5EEAD4; font-family: 'JetBrains Mono', monospace; font-size: 10px; letter-spacing: 1.2px; text-transform: uppercase; }
.cta:hover { background: rgba(94,234,212,0.2); border-color: #5EEAD4; }

.empty strong { color: #ECFEFF; font-weight: 500; }
.muted { margin: 8px 2px 0; font-size: 10.5px; color: rgba(167,243,208,0.45); line-height: 1.55; }

.apifix { display: flex; flex-direction: column; gap: 8px; padding: 12px 14px; margin-bottom: 8px; border-radius: 10px; border: 0.5px solid rgba(251,191,36,0.4); background: rgba(251,191,36,0.06); }
.apifix__title { margin: 0; font-family: 'JetBrains Mono', monospace; font-size: 10.5px; letter-spacing: 1.4px; color: #FBBF24; }
.apifix__txt { margin: 0; font-size: 12px; line-height: 1.55; color: rgba(253,230,138,0.85); }
.apifix__txt strong { color: #FDE68A; }
.apifix__cta { display: inline-flex; align-items: center; justify-content: center; gap: 6px; padding: 9px 12px; border-radius: 999px; text-decoration: none; background: #FBBF24; color: #02060A; font-family: 'JetBrains Mono', monospace; font-size: 10px; letter-spacing: 1.2px; text-transform: uppercase; }
.apifix__cta:hover { background: #FDE68A; box-shadow: 0 0 18px rgba(251,191,36,0.4); }
.apifix__retry { padding: 7px 12px; border-radius: 999px; cursor: pointer; border: 0.5px solid rgba(251,191,36,0.45); background: transparent; color: #FDE68A; font-family: 'JetBrains Mono', monospace; font-size: 9.5px; letter-spacing: 1.2px; text-transform: uppercase; }
.apifix__retry:hover { background: rgba(251,191,36,0.12); }

.list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; }
.event { display: flex; align-items: flex-start; gap: 10px; padding: 8px 2px; border-bottom: 0.5px solid rgba(255,255,255,0.04); }
.event:last-child { border-bottom: none; }
.event__when { display: flex; flex-direction: column; gap: 1px; min-width: 52px; flex-shrink: 0; }
.event__at { font-family: 'JetBrains Mono', monospace; font-size: 11px; color: #5EEAD4; }
.event.soon .event__at { color: #FBBF24; }
.event__day { font-family: 'JetBrains Mono', monospace; font-size: 8.5px; letter-spacing: 1.2px; color: rgba(167,243,208,0.45); }
.event__main { flex: 1; display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.event__label { color: #DCFCF5; font-size: 12.5px; text-decoration: none; }
a.event__label:hover { color: #ECFEFF; text-decoration: underline; }
.event__loc { font-size: 10.5px; color: rgba(167,243,208,0.5); }
.event__tag { font-size: 9px; letter-spacing: 1px; text-transform: uppercase; color: #FBBF24; border: 0.5px solid rgba(251,191,36,0.4); border-radius: 999px; padding: 1px 7px; flex-shrink: 0; }

.skel { display: flex; gap: 10px; padding: 8px 2px; opacity: 0; animation: in .35s ease forwards; animation-delay: var(--d); }
.skel__at { width: 38px; height: 9px; border-radius: 3px; background: linear-gradient(90deg, rgba(94,234,212,0.06), rgba(94,234,212,0.25), rgba(94,234,212,0.06)); background-size: 220% 100%; animation: shim 1.5s ease-in-out infinite; }
.skel__line { flex: 1; height: 9px; border-radius: 3px; background: linear-gradient(90deg, rgba(94,234,212,0.06), rgba(94,234,212,0.25), rgba(94,234,212,0.06)); background-size: 220% 100%; animation: shim 1.5s ease-in-out infinite; }
@keyframes in { to { opacity: 1; } }
@keyframes shim { 0%,100% { background-position: 100% 0; } 50% { background-position: 0 0; } }
</style>
