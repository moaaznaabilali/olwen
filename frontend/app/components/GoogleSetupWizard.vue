<script setup lang="ts">
/* Step-by-step Google OAuth setup wizard.

   Branches early on "do you already have an Olwen project?" so we never ask
   for an ID the user doesn't have yet. Each screen has ONE job. */
import { computed, onMounted, ref, watch } from 'vue'
import OlwenEntity from './OlwenEntity.vue'

const emit = defineEmits<{ done: []; cancel: [] }>()

const { oauthConfigured, oauthSetup } = useEmail()
const redirectUri = ref('http://localhost:8000/api/email/oauth/google/callback')

type Step =
  | 'intro'
  | 'find-id'
  | 'create-project'
  | 'enable-apis'
  | 'consent'            // Google's unified "Project configuration" wizard
  | 'publish'            // flip from Testing to In production
  | 'create-client'
  | 'paste-creds'
  | 'done'
const step = ref<Step>('intro')

const projectId = ref('')
const clientId = ref('')
const clientSecret = ref('')
const busy = ref(false)
const error = ref('')

const PROJECT_ID_STORAGE = 'olwen_google_project_id'
onMounted(async () => {
  try {
    const c = await oauthConfigured()
    if (c.redirect_uri) redirectUri.value = c.redirect_uri
  } catch { /* */ }
  if (import.meta.client) {
    const saved = localStorage.getItem(PROJECT_ID_STORAGE)
    if (saved) projectId.value = saved
  }
})
watch(projectId, (v) => {
  if (import.meta.client && v.trim()) localStorage.setItem(PROJECT_ID_STORAGE, v.trim())
})

// Reactive URLs that always include the project ID (when known)
const projSuffix = computed(() => projectId.value.trim() ? `?project=${encodeURIComponent(projectId.value.trim())}` : '')
const projectListUrl = 'https://console.cloud.google.com/cloud-resource-manager'
const newProjectUrl  = 'https://console.cloud.google.com/projectcreate'
const enableGmailUrl = computed(() => `https://console.cloud.google.com/apis/library/gmail.googleapis.com${projSuffix.value}`)
const enableCalUrl   = computed(() => `https://console.cloud.google.com/apis/library/calendar-json.googleapis.com${projSuffix.value}`)
const brandingUrl    = computed(() => `https://console.cloud.google.com/auth/branding${projSuffix.value}`)
const audienceUrl    = computed(() => `https://console.cloud.google.com/auth/audience${projSuffix.value}`)
const clientsUrl     = computed(() => `https://console.cloud.google.com/auth/clients${projSuffix.value}`)

const homepageUrl = computed(() => {
  if (import.meta.client) return window.location.origin
  return 'http://localhost:3100'
})

const copiedKey = ref('')
async function copy(text: string, key: string) {
  try { await navigator.clipboard.writeText(text); copiedKey.value = key; setTimeout(() => { copiedKey.value = '' }, 1500) } catch { /* */ }
}

async function savePaste() {
  if (clientId.value.length < 10 || clientSecret.value.length < 10) {
    error.value = 'Paste both the Client ID and the Client Secret.'
    return
  }
  busy.value = true; error.value = ''
  try {
    await oauthSetup(clientId.value.trim(), clientSecret.value.trim())
    step.value = 'done'                                       // DON'T auto-close — user must sign in
  } catch (e: unknown) {
    error.value = (e as { data?: { detail?: string } })?.data?.detail || 'Could not save credentials.'
  } finally { busy.value = false }
}

async function signInNow() {
  busy.value = true; error.value = ''
  try {
    const r = await useEmail().oauthStart()
    if (r.auth_url) { window.location.href = r.auth_url; return }
  } catch (e: unknown) {
    error.value = (e as { data?: { detail?: string } })?.data?.detail || 'Could not start Google sign-in.'
  } finally { busy.value = false }
}

// Progress: maps Step → 0-1 for the trail bar
const TRAIL: Step[] = ['intro', 'enable-apis', 'consent', 'publish', 'create-client', 'paste-creds']
const trailIndex = computed(() => {
  if (step.value === 'create-project' || step.value === 'find-id') return 0
  if (step.value === 'done') return TRAIL.length
  return TRAIL.indexOf(step.value)
})

const narration = computed(() => {
  switch (step.value) {
    case 'intro':           return "Quick check first: do you already have a Google Cloud project for Olwen? Saves us creating duplicates."
    case 'create-project':  return "I opened Google Cloud's project creator. Name it 'Olwen' so you'll recognise it later. Tell me when it's created."
    case 'find-id':         return "Open your project list, find the Olwen one, copy its ID — looks like 'olwen-490417'. Paste it below."
    case 'enable-apis':     return "Two APIs to flip on — Gmail and Calendar. Click each link, then the blue Enable button on Google's page."
    case 'consent':         return "Google walks you through 4 mini-steps in one page: App Info, Audience, Contact, Finish. Fill them out, hit Create at the end."
    case 'publish':         return "Crucial step everyone skips: hit 'Publish app' so Google stops blocking strangers. You'll see a one-time 'unverified' warning later — that's normal."
    case 'create-client':   return "Last step on Google's side — create the OAuth client. Pick Web application, then paste these three values into Google's form."
    case 'paste-creds':     return "Google just gave you a Client ID and Secret. Paste them here and we're done."
    case 'done':            return "Server credentials saved. One last thing — actually sign in with Google so your Gmail upgrades from app-password to OAuth. Then calendar lights up."
  }
  return ''
})

function goto(s: Step) { error.value = ''; step.value = s }
</script>

<template>
  <div class="wiz">
    <!-- progress trail -->
    <div class="trail" v-if="step !== 'done'">
      <span
        v-for="(_, i) in TRAIL"
        :key="i"
        class="trail__dot"
        :class="{ on: i <= trailIndex, current: i === trailIndex }"
      />
    </div>

    <!-- INTRO: branch on whether they have a project -->
    <div v-if="step === 'intro'" class="card">
      <h3 class="card__title">Set up Sign-in with Google</h3>
      <p class="card__sub">
        First question: <strong>do you already have a Google Cloud project for Olwen?</strong>
      </p>
      <div class="choices">
        <button class="choice" @click="goto('find-id')">
          <span class="choice__glyph">✓</span>
          <div class="choice__main">
            <div class="choice__name">Yes, I created one</div>
            <div class="choice__sub">I'll help you find its ID</div>
          </div>
        </button>
        <button class="choice choice--primary" @click="goto('create-project')">
          <span class="choice__glyph">＋</span>
          <div class="choice__main">
            <div class="choice__name">No, let's create one</div>
            <div class="choice__sub">60 seconds — I'll walk through it</div>
          </div>
        </button>
      </div>
      <p class="hint">
        Not sure? Open <a class="link" :href="projectListUrl" target="_blank" rel="noopener">your project list</a>
        — if you see "Olwen" in there, pick "Yes".
      </p>
    </div>

    <!-- CREATE PROJECT -->
    <div v-else-if="step === 'create-project'" class="card">
      <button class="back" @click="goto('intro')">‹ Back</button>
      <h3 class="card__title">Create the project</h3>
      <p class="card__sub">Open Google's project creator and name it exactly <strong>Olwen</strong>. Leave everything else default. Hit <strong>Create</strong>.</p>
      <a class="cta cta--block" :href="newProjectUrl" target="_blank" rel="noopener">↗ Open project creator</a>
      <p class="hint">After Google says the project is ready, come back and click "I created it".</p>
      <button class="cta cta--block cta--solid" @click="goto('find-id')">I created it →</button>
    </div>

    <!-- FIND ID -->
    <div v-else-if="step === 'find-id'" class="card">
      <button class="back" @click="goto('intro')">‹ Back</button>
      <h3 class="card__title">Lock in your project ID</h3>
      <p class="card__sub">
        Open your <a class="link" :href="projectListUrl" target="_blank" rel="noopener">project list</a>.
        Find <strong>Olwen</strong> — the ID is in the second column, looks like <code>olwen-490417</code>.
      </p>

      <div class="proj">
        <input v-model="projectId" class="field" placeholder="olwen-490417" autocomplete="off" spellcheck="false">
      </div>

      <p class="hint">
        Without this, every link below would open whichever project Google last showed you —
        usually the wrong one.
      </p>

      <button class="cta cta--block cta--solid" :disabled="!projectId.trim()" @click="goto('enable-apis')">
        {{ projectId.trim() ? 'Continue →' : 'Paste your project ID to continue' }}
      </button>
    </div>

    <!-- ENABLE APIS -->
    <div v-else-if="step === 'enable-apis'" class="card">
      <button class="back" @click="goto('find-id')">‹ Back</button>
      <h3 class="card__title">Turn on the two APIs Olwen needs</h3>
      <p class="card__sub">Open each link → click the blue <strong>Enable</strong> button. 5 seconds each. Both go to project <code>{{ projectId }}</code>.</p>

      <div class="api-grid">
        <a class="api-tile" :href="enableGmailUrl" target="_blank" rel="noopener">
          <span class="api-tile__name">Gmail API</span>
          <span class="api-tile__arrow">↗ Enable</span>
        </a>
        <a class="api-tile" :href="enableCalUrl" target="_blank" rel="noopener">
          <span class="api-tile__name">Google Calendar API</span>
          <span class="api-tile__arrow">↗ Enable</span>
        </a>
      </div>

      <button class="cta cta--block cta--solid" @click="goto('consent')">Both enabled →</button>
    </div>

    <!-- CONSENT (merged: App info → Audience → Contact → Finish, all in Google's wizard) -->
    <div v-else-if="step === 'consent'" class="card">
      <button class="back" @click="goto('enable-apis')">‹ Back</button>
      <h3 class="card__title">Configure the consent screen</h3>
      <p class="card__sub">
        Open the page below. Google runs its <strong>own</strong> 4-step wizard for this.
        I'll tell you what to type at each step.
      </p>

      <a class="cta cta--block" :href="brandingUrl" target="_blank" rel="noopener">↗ Open Google's consent wizard</a>

      <!-- Walk-through of Google's 4 inner steps -->
      <div class="gflow">
        <div class="gflow__step">
          <div class="gflow__num">1</div>
          <div class="gflow__body">
            <div class="gflow__title">App Information</div>
            <div class="gflow__field" @click="copy('Olwen', 'name')">
              <span class="gflow__field-label">App name →</span>
              <span class="gflow__field-value">Olwen</span>
              <span class="gflow__copy">{{ copiedKey === 'name' ? '✓ Copied' : 'Copy' }}</span>
            </div>
            <div class="gflow__hint">User support email → pick your own Gmail. Click <strong>Next</strong>.</div>
          </div>
        </div>

        <div class="gflow__step">
          <div class="gflow__num">2</div>
          <div class="gflow__body">
            <div class="gflow__title">Audience</div>
            <div class="gflow__hint">
              Pick <strong>External</strong>. Click <strong>Next</strong>.
            </div>
          </div>
        </div>

        <div class="gflow__step">
          <div class="gflow__num">3</div>
          <div class="gflow__body">
            <div class="gflow__title">Contact Information</div>
            <div class="gflow__hint">Your own email again. Click <strong>Next</strong>.</div>
          </div>
        </div>

        <div class="gflow__step">
          <div class="gflow__num">4</div>
          <div class="gflow__body">
            <div class="gflow__title">Finish</div>
            <div class="gflow__hint">Tick the agreement, click <strong>Create</strong>. Done — come back here.</div>
          </div>
        </div>
      </div>

      <button class="cta cta--block cta--solid" @click="goto('publish')">Done with consent — next →</button>
    </div>

    <!-- PUBLISH the app — the simplest fix for "Access blocked" -->
    <div v-else-if="step === 'publish'" class="card">
      <button class="back" @click="goto('consent')">‹ Back</button>
      <h3 class="card__title">★ Publish the app (essential)</h3>
      <p class="card__sub">
        Right after consent setup, Google leaves your app in <strong>Testing</strong> mode —
        meaning <strong>only you, as a manually-added test user, can sign in</strong>.
        That's why most people get the "Access blocked: Olwen has not completed verification" screen.
      </p>

      <div class="why">
        <span class="why__tag">Solution</span>
        <span class="why__txt">
          Click <strong>Publish app</strong> on the Audience page. Anyone you trust can sign in then —
          starting with you. Google will show a one-time "unverified app" warning that you click past
          with <strong>Advanced → Go to Olwen (unsafe)</strong>. That's normal until Google formally
          verifies the app (weeks-long process, not worth it for personal use).
        </span>
      </div>

      <a class="cta cta--block" :href="audienceUrl" target="_blank" rel="noopener">↗ Open Audience page</a>

      <div class="gflow">
        <div class="gflow__step">
          <div class="gflow__num">1</div>
          <div class="gflow__body">
            <div class="gflow__title">Find the publishing-status box</div>
            <div class="gflow__hint">Top of the Audience page — shows <strong>Publishing status: Testing</strong>.</div>
          </div>
        </div>
        <div class="gflow__step">
          <div class="gflow__num">2</div>
          <div class="gflow__body">
            <div class="gflow__title">Click <strong>Publish app</strong></div>
            <div class="gflow__hint">Google asks "Push to production?". Confirm.</div>
          </div>
        </div>
        <div class="gflow__step">
          <div class="gflow__num">3</div>
          <div class="gflow__body">
            <div class="gflow__title">Status flips to <strong>In production</strong></div>
            <div class="gflow__hint">That's it. You'll <em>not</em> get charged or audited — Google just stops blocking strangers.</div>
          </div>
        </div>
      </div>

      <button class="cta cta--block cta--solid" @click="goto('create-client')">Published — next →</button>
    </div>

    <!-- CREATE CLIENT -->
    <div v-else-if="step === 'create-client'" class="card">
      <button class="back" @click="goto('consent')">‹ Back</button>
      <h3 class="card__title">Create the OAuth client</h3>
      <p class="card__sub">
        Open <strong>Clients</strong>, click <strong>+ Create client</strong>, pick
        <strong>Web application</strong>, then paste these into Google's form:
      </p>

      <a class="cta cta--block" :href="clientsUrl" target="_blank" rel="noopener">↗ Open Clients page</a>

      <div class="cheat">
        <div class="cheat__row" :class="{ copied: copiedKey === 'name' }" @click="copy('Olwen', 'name')">
          <div class="cheat__field"><span class="cheat__label">Name</span><span class="cheat__value">Olwen</span></div>
          <span class="cheat__copy">{{ copiedKey === 'name' ? '✓ Copied' : 'Copy' }}</span>
        </div>
        <div class="cheat__row" :class="{ copied: copiedKey === 'origins' }" @click="copy(homepageUrl, 'origins')">
          <div class="cheat__field"><span class="cheat__label">Authorized JavaScript origins</span><span class="cheat__value">{{ homepageUrl }}</span></div>
          <span class="cheat__copy">{{ copiedKey === 'origins' ? '✓ Copied' : 'Copy' }}</span>
        </div>
        <div class="cheat__row cheat__row--important" :class="{ copied: copiedKey === 'cb' }" @click="copy(redirectUri, 'cb')">
          <div class="cheat__field">
            <span class="cheat__label">Authorized redirect URIs  <span class="cheat__star">★ critical</span></span>
            <span class="cheat__value">{{ redirectUri }}</span>
          </div>
          <span class="cheat__copy">{{ copiedKey === 'cb' ? '✓ Copied' : 'Copy' }}</span>
        </div>
      </div>

      <button class="cta cta--block cta--solid" @click="goto('paste-creds')">Click Create on Google → next →</button>
    </div>

    <!-- PASTE CREDS -->
    <div v-else-if="step === 'paste-creds'" class="card">
      <button class="back" @click="goto('create-client')">‹ Back</button>
      <h3 class="card__title">Almost done — paste the two values</h3>
      <p class="card__sub">
        Google's popup shows <strong>Client ID</strong> and <strong>Client Secret</strong>.
        Copy each one and paste here. The Secret is shown only once.
      </p>

      <div class="setup-form">
        <label>
          <span class="setup-form__label">Client ID</span>
          <input v-model="clientId" class="field" placeholder="123456789-abcd…apps.googleusercontent.com" autocomplete="off" spellcheck="false">
        </label>
        <label>
          <span class="setup-form__label">Client Secret</span>
          <input v-model="clientSecret" class="field" type="password" placeholder="GOCSPX-…" autocomplete="off" spellcheck="false">
        </label>
        <p v-if="error" class="error">{{ error }}</p>
        <button class="cta cta--block cta--solid" :disabled="busy" @click="savePaste">{{ busy ? 'Saving…' : 'Save and finish ✓' }}</button>
      </div>
    </div>

    <!-- DONE: server creds saved → but USER still needs to actually sign in -->
    <div v-else-if="step === 'done'" class="card card--done">
      <div class="done__check">✓</div>
      <h3 class="card__title">Server credentials saved.</h3>
      <p class="card__sub">
        Sign-in with Google is now <strong>possible</strong> — but it hasn't happened yet for your account.
        One click finishes it: I'll send you to Google's consent screen for Gmail + Calendar.
      </p>
      <p v-if="error" class="error">{{ error }}</p>
      <button class="cta cta--block cta--solid" :disabled="busy" @click="signInNow">
        {{ busy ? 'Redirecting to Google…' : '↗ Sign in with Google now' }}
      </button>
      <button class="link link--center" @click="emit('done')">I'll do it later</button>
    </div>

    <div class="narrator">
      <div class="narrator__entity"><OlwenEntity state="speaking" /></div>
      <div class="narrator__bubble">{{ narration }}</div>
    </div>
  </div>
</template>

<style scoped>
.wiz { display: flex; flex-direction: column; gap: 18px; }

/* progress trail */
.trail { display: flex; align-items: center; gap: 8px; padding: 0 2px 4px; }
.trail__dot {
  flex: 1; height: 3px; border-radius: 2px;
  background: rgba(94,234,212,0.15);
  transition: background .3s ease, box-shadow .3s ease;
}
.trail__dot.on { background: rgba(94,234,212,0.5); }
.trail__dot.current { background: #5EEAD4; box-shadow: 0 0 8px rgba(94,234,212,0.5); }

/* cards */
.card {
  padding: 24px 26px;
  border-radius: 16px; border: 0.5px solid rgba(94,234,212,0.18);
  background: linear-gradient(180deg, rgba(8,30,38,0.6), rgba(2,6,10,0.45));
  position: relative;
}
.card__title { margin: 0 0 6px; font-size: 19px; font-weight: 300; color: #ECFEFF; }
.card__sub { margin: 0 0 18px; font-size: 13.5px; line-height: 1.6; color: rgba(220,252,245,0.75); }
.card__sub strong { color: #ECFEFF; }
.card__sub code { font-family: 'JetBrains Mono', monospace; font-size: 12px; padding: 2px 6px; border-radius: 4px; background: rgba(255,255,255,0.05); border: 0.5px solid rgba(94,234,212,0.2); color: #A7F3D0; }

.back { position: absolute; top: 18px; right: 20px; background: transparent; border: none; color: rgba(167,243,208,0.55); font-family: 'JetBrains Mono', monospace; font-size: 10px; letter-spacing: 1px; cursor: pointer; }
.back:hover { color: #5EEAD4; }

.hint { margin: 14px 0 0; font-size: 12px; line-height: 1.55; color: rgba(167,243,208,0.55); }
.hint strong { color: #ECFEFF; }
.link { color: #67E8F9; }
.link:hover { color: #5EEAD4; }
.link--center { display: block; width: 100%; margin: 14px auto 0; background: transparent; border: none; cursor: pointer; font-family: 'JetBrains Mono', monospace; font-size: 10px; letter-spacing: 1.3px; text-transform: uppercase; color: rgba(167,243,208,0.5); }
.link--center:hover { color: #5EEAD4; }

.error { margin: 0 0 6px; font-size: 12px; color: #FCA5A5; border-left: 2px solid #F87171; padding-left: 9px; }

/* choices on intro */
.choices { display: flex; flex-direction: column; gap: 10px; }
.choice {
  display: flex; align-items: center; gap: 14px;
  padding: 18px 18px; border-radius: 12px; cursor: pointer; text-align: left;
  border: 0.5px solid rgba(94,234,212,0.18); background: rgba(8,30,38,0.5);
  transition: all .15s ease;
}
.choice:hover { border-color: #5EEAD4; transform: translateY(-1px); box-shadow: 0 0 22px rgba(94,234,212,0.15); }
.choice--primary { border-color: rgba(94,234,212,0.4); background: rgba(94,234,212,0.07); }
.choice__glyph {
  width: 40px; height: 40px; border-radius: 12px; display: grid; place-items: center;
  background: rgba(94,234,212,0.16); color: #5EEAD4; font-size: 18px; flex-shrink: 0;
  border: 0.5px solid rgba(94,234,212,0.25);
}
.choice__name { font-size: 14.5px; color: #ECFEFF; }
.choice__sub { font-size: 11.5px; color: rgba(167,243,208,0.55); margin-top: 2px; }

/* CTAs — block forms used throughout the linear flow */
.cta {
  display: inline-flex; align-items: center; justify-content: center; gap: 9px;
  padding: 12px 22px; border-radius: 999px; cursor: pointer;
  border: 0.5px solid rgba(94,234,212,0.45);
  background: rgba(94,234,212,0.08);
  color: #ECFEFF; text-decoration: none;
  font-family: 'JetBrains Mono', monospace; font-size: 11px; letter-spacing: 1.5px; text-transform: uppercase;
  transition: all .2s ease;
}
.cta:hover:not(:disabled) { background: rgba(94,234,212,0.18); border-color: #5EEAD4; box-shadow: 0 0 22px rgba(94,234,212,0.18); }
.cta:disabled { opacity: 0.55; cursor: not-allowed; }
.cta--block { display: flex; width: 100%; margin: 6px 0 10px; }
.cta--solid { background: #5EEAD4; color: #02060A; border-color: #5EEAD4; }
.cta--solid:hover:not(:disabled) { background: #67E8F9; box-shadow: 0 0 26px rgba(94,234,212,0.5); }

/* project input */
.proj { margin-bottom: 8px; }
.field {
  width: 100%; padding: 13px 16px; border-radius: 10px;
  border: 0.5px solid rgba(94,234,212,0.25); background: rgba(2,6,10,0.55);
  color: #ECFEFF; font-family: 'JetBrains Mono', monospace; font-size: 13px; letter-spacing: 0.5px;
}
.field:focus { outline: none; border-color: #5EEAD4; box-shadow: 0 0 18px rgba(94,234,212,0.18); }

/* API enable pair */
.api-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 14px; }
.api-tile {
  display: flex; flex-direction: column; gap: 6px; padding: 14px 16px;
  border-radius: 10px; background: rgba(8,30,38,0.5); border: 0.5px solid rgba(94,234,212,0.2);
  text-decoration: none; transition: all .15s ease;
}
.api-tile:hover { border-color: #5EEAD4; background: rgba(94,234,212,0.06); }
.api-tile__name { color: #ECFEFF; font-size: 13px; }
.api-tile__arrow { font-family: 'JetBrains Mono', monospace; font-size: 9.5px; letter-spacing: 1.2px; color: #5EEAD4; }

/* copy cheat */
.cheat { display: flex; flex-direction: column; gap: 8px; margin: 4px 0 12px; }
.cheat__row {
  display: flex; align-items: center; gap: 12px;
  padding: 12px 14px; border-radius: 10px; cursor: pointer;
  border: 0.5px solid rgba(94,234,212,0.18); background: rgba(8,30,38,0.5);
  transition: all .15s ease;
}
.cheat__row:hover { border-color: #5EEAD4; background: rgba(94,234,212,0.06); }
.cheat__row.copied { border-color: #5EEAD4; background: rgba(94,234,212,0.18); }
.cheat__row--important { border-left: 3px solid #FBBF24; }
.cheat__field { flex: 1; display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.cheat__label { font-family: 'JetBrains Mono', monospace; font-size: 9.5px; letter-spacing: 1.2px; text-transform: uppercase; color: rgba(167,243,208,0.55); }
.cheat__star { color: #FBBF24; font-size: 9px; text-transform: none; margin-left: 6px; }
.cheat__value { font-family: 'JetBrains Mono', monospace; font-size: 13px; color: #ECFEFF; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.cheat__copy { flex-shrink: 0; padding: 6px 11px; border-radius: 999px; background: rgba(94,234,212,0.14); border: 0.5px solid rgba(94,234,212,0.35); color: #5EEAD4; font-family: 'JetBrains Mono', monospace; font-size: 9.5px; letter-spacing: 1.2px; text-transform: uppercase; }
.cheat__row.copied .cheat__copy { background: #5EEAD4; color: #02060A; }

/* mini walk-through of Google's own 4-step wizard */
.gflow { display: flex; flex-direction: column; gap: 10px; margin: 4px 0 12px; padding: 14px; border-radius: 12px; background: rgba(8,30,38,0.4); border: 0.5px solid rgba(94,234,212,0.14); }
.gflow__step { display: flex; gap: 12px; align-items: flex-start; }
.gflow__num {
  display: grid; place-items: center; width: 26px; height: 26px; border-radius: 50%; flex-shrink: 0;
  background: rgba(94,234,212,0.16); color: #5EEAD4; border: 0.5px solid rgba(94,234,212,0.4);
  font-family: 'JetBrains Mono', monospace; font-size: 10.5px; font-weight: 600;
}
.gflow__body { flex: 1; display: flex; flex-direction: column; gap: 5px; min-width: 0; }
.gflow__title { font-size: 13px; color: #ECFEFF; font-weight: 500; }
.gflow__field { display: flex; align-items: center; gap: 9px; padding: 8px 12px; border-radius: 8px; cursor: pointer; background: rgba(94,234,212,0.06); border: 0.5px solid rgba(94,234,212,0.2); transition: all .15s ease; }
.gflow__field:hover { border-color: #5EEAD4; background: rgba(94,234,212,0.1); }
.gflow__field-label { font-family: 'JetBrains Mono', monospace; font-size: 10px; letter-spacing: 0.8px; color: rgba(167,243,208,0.6); }
.gflow__field-value { flex: 1; font-family: 'JetBrains Mono', monospace; font-size: 12.5px; color: #ECFEFF; }
.gflow__copy { font-family: 'JetBrains Mono', monospace; font-size: 9px; letter-spacing: 1.2px; text-transform: uppercase; color: #5EEAD4; padding: 3px 8px; border-radius: 999px; border: 0.5px solid rgba(94,234,212,0.35); }
.gflow__hint { font-size: 12px; color: rgba(220,252,245,0.7); line-height: 1.5; }
.gflow__hint strong { color: #ECFEFF; }
.gflow__note { display: block; margin-top: 4px; font-family: 'JetBrains Mono', monospace; font-size: 10px; color: #FBBF24; }

.hint.after { padding: 10px 12px; border-radius: 8px; border-left: 2px solid #FBBF24; background: rgba(251,191,36,0.06); color: #FDE68A; }
.hint.after strong { color: #ECFEFF; }
.hint.after a { color: #67E8F9; }

.why { display: flex; flex-direction: column; gap: 4px; padding: 12px 14px; margin: 0 0 14px; border-radius: 10px; border: 0.5px solid rgba(94,234,212,0.3); background: rgba(94,234,212,0.06); }
.why__tag { font-family: 'JetBrains Mono', monospace; font-size: 9px; letter-spacing: 1.6px; text-transform: uppercase; color: #5EEAD4; }
.why__txt { font-size: 12.5px; color: rgba(220,252,245,0.85); line-height: 1.6; }
.why__txt strong { color: #ECFEFF; }
.why__txt em { color: #FBBF24; font-style: normal; }

/* paste form */
.setup-form { display: flex; flex-direction: column; gap: 12px; margin-top: 4px; }
.setup-form label { display: flex; flex-direction: column; gap: 5px; }
.setup-form__label { font-family: 'JetBrains Mono', monospace; font-size: 9.5px; letter-spacing: 1.4px; text-transform: uppercase; color: rgba(167,243,208,0.5); }

/* done */
.card--done { text-align: center; padding: 38px 26px; }
.done__check {
  width: 64px; height: 64px; border-radius: 50%; margin: 0 auto 14px;
  display: grid; place-items: center;
  background: rgba(94,234,212,0.18); border: 0.5px solid #5EEAD4;
  color: #5EEAD4; font-size: 32px;
  box-shadow: 0 0 36px rgba(94,234,212,0.4);
  animation: doneIn .55s cubic-bezier(.22,.7,.36,1) both;
}
@keyframes doneIn { 0% { opacity: 0; transform: scale(0.5); } 100% { opacity: 1; transform: scale(1); } }

/* narrator */
.narrator { display: flex; align-items: center; gap: 12px; padding: 14px 16px; border-radius: 12px; border: 0.5px solid rgba(94,234,212,0.15); background: rgba(8,30,38,0.4); }
.narrator__entity { width: 56px; height: 56px; flex-shrink: 0; }
.narrator__bubble {
  flex: 1; font-size: 12.5px; line-height: 1.55; color: #DCFCF5;
  padding: 8px 14px; border-radius: 10px; background: rgba(94,234,212,0.06);
  border: 0.5px solid rgba(94,234,212,0.15);
}
</style>
