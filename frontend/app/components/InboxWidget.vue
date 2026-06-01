<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import WidgetPanel from './WidgetPanel.vue'
import type { EmailMessage, TriagedEmail } from '../composables/useEmail'

const emit = defineEmits<{
  openSettings: []
  reviewed: [TriagedEmail[]]
  open: [EmailMessage | TriagedEmail]
  compose: []
}>()

const { accounts, inbox: fetchInbox, triage } = useEmail()

const connected = ref(false)
const emails = ref<(EmailMessage | TriagedEmail)[]>([])
const loading = ref(false)
const triaging = ref(false)
const error = ref('')
const gmailApiDisabled = ref(false)

// Direct link to enable Gmail API on Google Cloud — picks up the user's project
// id from localStorage (stored by the OAuth setup wizard) so it lands on the
// right project, not whichever Google last showed them.
const enableGmailUrl = computed(() => {
  const pid = import.meta.client ? localStorage.getItem('olwen_google_project_id') : null
  const suffix = pid ? `?project=${encodeURIComponent(pid)}` : ''
  return `https://console.cloud.google.com/apis/library/gmail.googleapis.com${suffix}`
})

const unreadCount = computed(() => emails.value.filter(e => e.unread).length)
const priorityColor: Record<string, string> = { high: '#F87171', med: '#FBBF24', low: '#5EEAD4' }
const isTriaged = (e: EmailMessage | TriagedEmail): e is TriagedEmail =>
  (e as TriagedEmail).priority !== undefined

function shortFrom(s: string): string {
  // "Sarah Chen <sarah@x.com>" → "Sarah Chen"
  const m = s.match(/^\s*"?([^"<]+?)"?\s*<.*>/)
  return (m ? m[1] : s).trim() || s
}

async function load() {
  loading.value = true; error.value = ''; gmailApiDisabled.value = false
  try {
    const list = await accounts()
    connected.value = list.length > 0
    if (connected.value) emails.value = await fetchInbox(8)
  } catch (e: unknown) {
    const detail = (e as { data?: { detail?: string } })?.data?.detail || ''
    if (detail.startsWith('GMAIL_API_DISABLED')) {
      gmailApiDisabled.value = true
      error.value = ''
    } else {
      error.value = detail || 'Could not load inbox.'
    }
  } finally {
    loading.value = false
  }
}

async function runTriage() {
  if (triaging.value || !connected.value) return
  triaging.value = true; error.value = ''
  try {
    const r = await triage(8)
    emails.value = r.emails
    // Desktop notification for the most urgent one — Olwen will read all of them aloud in the cinematic overlay.
    const high = r.emails.find(e => e.priority === 'high')
    if (high && import.meta.client && 'Notification' in window) {
      try {
        const perm = Notification.permission === 'default'
          ? await Notification.requestPermission()
          : Notification.permission
        if (perm === 'granted') {
          new Notification(`Important email from ${shortFrom(high.sender)}`, {
            body: `${high.subject}\n${high.suggestion}`,
          })
        }
      } catch { /* ignore */ }
    }
    // Hand the triaged list up — DashboardView will open the cinematic EmailWorkMode.
    if (r.emails.length) emit('reviewed', r.emails)
  } catch (e: unknown) {
    error.value = (e as { data?: { detail?: string } })?.data?.detail || 'Triage failed.'
  } finally {
    triaging.value = false
  }
}

onMounted(load)
</script>

<template>
  <WidgetPanel title="Inbox" :badge="unreadCount">
    <div class="inbox">
      <p v-if="error" class="error">{{ error }}</p>

      <!-- Specific recovery for the Gmail API 403: one-click "Enable Gmail API" -->
      <div v-if="gmailApiDisabled" class="apifix">
        <p class="apifix__title">⚠ Gmail API not enabled</p>
        <p class="apifix__txt">
          Your Google connection is fine, but the Gmail API isn't turned on in your
          Olwen project on Google Cloud. Click below → press the blue <strong>Enable</strong>
          button → wait a few seconds → come back and reload.
        </p>
        <a class="apifix__cta" :href="enableGmailUrl" target="_blank" rel="noopener">↗ Enable Gmail API</a>
        <button class="apifix__retry" @click="load">↻ Reload inbox</button>
      </div>

      <template v-if="!connected && !loading">
        <p class="empty">
          Connect any email (Gmail, Outlook, Yahoo, iCloud)<br>
          and Olwen will triage what matters.
        </p>
        <button class="cta" @click="emit('openSettings')">⚙ Connect email</button>
      </template>

      <template v-else-if="connected">
        <div class="inbox__row">
          <button class="triage-cta" :disabled="triaging || loading" @click="runTriage">
            <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
              <path d="M12 3l1.8 4.7L18.5 9.5 13.8 11.3 12 16l-1.8-4.7L5.5 9.5l4.7-1.8L12 3z" />
            </svg>
            {{ triaging ? 'Triaging…' : 'Triage with Olwen' }}
          </button>
          <button class="compose-cta" title="New email" @click="emit('compose')">✎ Compose</button>
        </div>

        <!-- skeleton loader: pulsing rows while emails come in over IMAP -->
        <ul v-if="loading || triaging" class="list">
          <li v-for="i in 4" :key="`skel-${i}`" class="srow" :style="{ '--d': `${i * 90}ms` }">
            <span class="srow__dot" />
            <div class="srow__main">
              <span class="srow__line srow__line--from" />
              <span class="srow__line srow__line--subj" />
            </div>
          </li>
        </ul>

        <p v-else-if="!emails.length" class="muted">Inbox is empty 🌌</p>

        <ul v-if="!loading && !triaging" class="list">
          <li
            v-for="e in emails"
            :key="e.uid"
            class="row"
            :class="[{ unread: e.unread }, isTriaged(e) ? `p-${(e as TriagedEmail).priority}` : '']"
            tabindex="0"
            role="button"
            @click="emit('open', e)"
            @keyup.enter="emit('open', e)"
          >
            <span class="row__dot" :class="{ on: e.unread }" />
            <div class="row__main">
              <div class="row__top">
                <span class="row__from">{{ shortFrom(e.sender) }}</span>
                <span v-if="isTriaged(e)" class="row__prio" :style="{ color: priorityColor[(e as TriagedEmail).priority] || '#5EEAD4' }">
                  {{ (e as TriagedEmail).priority.toUpperCase() }}
                </span>
              </div>
              <span class="row__subj">{{ e.subject }}</span>
              <span v-if="isTriaged(e) && (e as TriagedEmail).suggestion" class="row__sug">
                ✦ {{ (e as TriagedEmail).suggestion }}
              </span>
            </div>
          </li>
        </ul>
      </template>
    </div>
  </WidgetPanel>
</template>

<style scoped>
.inbox { display: flex; flex-direction: column; gap: 10px; }
.error { margin: 0; font-size: 11.5px; color: #FCA5A5; border-left: 2px solid #F87171; padding-left: 9px; }
.empty { margin: 6px 2px 10px; font-size: 12.5px; line-height: 1.5; color: var(--text-muted); }

.apifix { display: flex; flex-direction: column; gap: 8px; padding: 12px 14px; margin-bottom: 8px; border-radius: 10px; border: 0.5px solid rgba(251,191,36,0.4); background: rgba(251,191,36,0.06); }
.apifix__title { margin: 0; font-family: 'JetBrains Mono', monospace; font-size: 10.5px; letter-spacing: 1.4px; color: #FBBF24; }
.apifix__txt { margin: 0; font-size: 12px; line-height: 1.55; color: rgba(253,230,138,0.85); }
.apifix__txt strong { color: #FDE68A; }
.apifix__cta { display: inline-flex; align-items: center; justify-content: center; gap: 6px; padding: 9px 12px; border-radius: 999px; text-decoration: none; background: #FBBF24; color: var(--bg); font-family: 'JetBrains Mono', monospace; font-size: 10px; letter-spacing: 1.2px; text-transform: uppercase; }
.apifix__cta:hover { background: #FDE68A; box-shadow: 0 0 18px rgba(251,191,36,0.4); }
.apifix__retry { padding: 7px 12px; border-radius: 999px; cursor: pointer; border: 0.5px solid rgba(251,191,36,0.45); background: transparent; color: #FDE68A; font-family: 'JetBrains Mono', monospace; font-size: 9.5px; letter-spacing: 1.2px; text-transform: uppercase; }
.apifix__retry:hover { background: rgba(251,191,36,0.12); }
.cta {
  padding: 9px; border-radius: 9px; cursor: pointer; width: 100%;
  border: 0.5px solid var(--border-strong); background: var(--border);
  color: var(--accent); font-family: 'JetBrains Mono', monospace; font-size: 10px;
  letter-spacing: 1.2px; text-transform: uppercase;
}
.cta:hover { background: var(--border-strong); border-color: var(--accent); }
.muted { margin: 8px 2px 0; font-size: 12px; color: var(--text-muted); }

.triage-cta {
  display: flex; align-items: center; justify-content: center; gap: 8px;
  width: 100%; padding: 9px; border-radius: 9px; cursor: pointer;
  border: 0.5px solid var(--border-strong); background: var(--border);
  color: var(--accent); font-family: 'JetBrains Mono', monospace; font-size: 10px;
  letter-spacing: 1.2px; text-transform: uppercase; transition: all .2s ease;
}
.triage-cta:hover:not(:disabled) { background: var(--border-strong); border-color: var(--accent); box-shadow: 0 0 14px var(--border-strong); }
.triage-cta:disabled { opacity: 0.6; cursor: progress; }

.inbox__row { display: flex; gap: 6px; }
.inbox__row .triage-cta { flex: 1; }
.compose-cta {
  padding: 9px 12px; border-radius: 9px; cursor: pointer;
  border: 0.5px solid var(--border-strong); background: transparent; color: var(--accent);
  font-family: 'JetBrains Mono', monospace; font-size: 10px; letter-spacing: 1.2px; text-transform: uppercase;
  transition: all .2s ease; flex-shrink: 0;
}
.compose-cta:hover { background: var(--border); border-color: var(--accent); }

.list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 4px; }
.row { display: flex; align-items: flex-start; gap: 9px; padding: 7px 8px; border-radius: 8px; border-left: 2px solid transparent; transition: background .15s ease, transform .15s ease; cursor: pointer; }
.row:hover { background: var(--border); transform: translateX(2px); }
.row:focus-visible { outline: none; background: var(--border); box-shadow: inset 0 0 0 1px var(--border-strong); }
.row.p-high { border-left-color: #F87171; }
.row.p-med  { border-left-color: #FBBF24; }
.row.p-low  { border-left-color: var(--border-strong); }
.row__dot { width: 6px; height: 6px; border-radius: 50%; background: transparent; flex-shrink: 0; margin-top: 7px; }
.row__dot.on { background: var(--accent); box-shadow: 0 0 7px var(--accent); }
.row__main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.row__top { display: flex; align-items: center; gap: 8px; }
.row__from { font-size: 12.5px; color: var(--text); font-weight: 400; }
.row.unread .row__from { color: var(--text-strong); font-weight: 500; }
.row__prio { font-family: 'JetBrains Mono', monospace; font-size: 8px; letter-spacing: 1.2px; }
.row__subj { font-size: 11.5px; color: var(--text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.row__sug { font-size: 11px; color: var(--accent-2); margin-top: 2px; }

/* loading skeleton — pulsing rows with a soft teal shimmer */
.srow {
  display: flex; align-items: center; gap: 9px; padding: 8px 8px;
  border-radius: 8px; border-left: 2px solid var(--border);
  opacity: 0; animation: srowin .35s ease forwards; animation-delay: var(--d);
}
.srow__dot { width: 6px; height: 6px; border-radius: 50%; background: var(--border-strong); flex-shrink: 0; }
.srow__main { flex: 1; display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.srow__line { display: block; height: 9px; border-radius: 3px;
  background: linear-gradient(90deg, var(--border) 0%, var(--border-strong) 50%, var(--border) 100%);
  background-size: 220% 100%;
  animation: shimmer 1.5s ease-in-out infinite;
}
.srow__line--from { width: 32%; height: 10px; }
.srow__line--subj { width: 72%; height: 8px; opacity: 0.6; }
.srow:nth-child(2) .srow__line--from { width: 24%; }
.srow:nth-child(3) .srow__line--from { width: 38%; }
.srow:nth-child(4) .srow__line--from { width: 28%; }
@keyframes srowin { to { opacity: 1; } }
@keyframes shimmer { 0%,100% { background-position: 100% 0; } 50% { background-position: 0 0; } }
@media (prefers-reduced-motion: reduce) { .srow__line { animation: none; } }
</style>
