<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import OlwenEntity from './OlwenEntity.vue'

const emit = defineEmits<{ connected: []; cancel: [] }>()
const { connect, oauthConfigured, oauthStart } = useEmail()
const oauthAvailable = ref(false)
async function startGoogleOAuth() {
  try {
    const { auth_url } = await oauthStart()
    window.location.href = auth_url
  } catch (e: unknown) {
    error.value = (e as { data?: { detail?: string } })?.data?.detail || 'Could not start Google sign-in.'
  }
}

type Provider = 'gmail' | 'outlook' | 'yahoo' | 'icloud' | 'other'
const provider = ref<Provider | null>(null)
const step = ref<1 | 2 | 3>(1)
const busy = ref(false)
const error = ref('')

const form = reactive({ email: '', password: '', imap_host: '', smtp_host: '', imap_port: 993, smtp_port: 587 })

interface Guide {
  label: string
  glyph: string
  color: string
  hostHint: string
  appPasswordUrl: string
  buttonLabel: string
  steps: string[]
  narrate: string[]   // what Olwen says (one per step transition)
  preview: { brand: string, code: string } // visual hint of what the user will see
  trouble: string     // one-line troubleshoot
}

const guides: Record<Provider, Guide> = {
  gmail: {
    label: 'Gmail', glyph: '✉', color: '#67E8F9',
    hostHint: 'imap.gmail.com',
    appPasswordUrl: 'https://myaccount.google.com/apppasswords',
    buttonLabel: 'Open Google for me',
    steps: [
      'Tap the button below — Google opens in a new tab.',
      'If Google asks, sign in like normal.',
      'You\'ll see a page that says "App passwords". Type Olwen as the name, tap Create.',
      'Google shows 16 letters in a yellow box. Copy them.',
    ],
    narrate: [
      "Gmail. Don't worry — I won't ever see your real password. Google just gives me a one-time code.",
      "Tap the button. Google opens. Type Olwen, tap Create, and copy the 16 letters they show you.",
      "Now paste your address and those 16 letters. I'll log in once to make sure it works.",
    ],
    preview: { brand: 'Google', code: 'abcd  efgh  ijkl  mnop' },
    trouble: "Can't find the page? Google needs 2-Step Verification on first. Turn that on and come back.",
  },
  outlook: {
    label: 'Outlook / Hotmail', glyph: '◧', color: '#A78BFA',
    hostHint: 'outlook.office365.com',
    appPasswordUrl: 'https://account.microsoft.com/security/advanced-security-options',
    buttonLabel: 'Open Microsoft for me',
    steps: [
      'Tap the button — Microsoft opens.',
      'Sign in if it asks.',
      'On "Advanced security", find "App passwords" and tap Create.',
      'Microsoft shows a long code — copy it.',
    ],
    narrate: [
      "Outlook. Microsoft will hand me a one-time code so I never touch your real password.",
      "Tap the button, find App passwords, create one, copy what they show.",
      "Paste your email and that code here. One test login and we're in.",
    ],
    preview: { brand: 'Microsoft', code: 'pqrstu vwxyzab cdefgh' },
    trouble: "If you don't see App passwords, turn on two-step verification first in Security.",
  },
  yahoo: {
    label: 'Yahoo', glyph: '⊙', color: '#F472B6',
    hostHint: 'imap.mail.yahoo.com',
    appPasswordUrl: 'https://login.yahoo.com/account/security',
    buttonLabel: 'Open Yahoo for me',
    steps: [
      'Tap the button — Yahoo opens.',
      'Sign in if asked.',
      'Find "Generate app password" → choose "Other app" → name it Olwen.',
      'Copy the password Yahoo shows you.',
    ],
    narrate: [
      "Yahoo. Same idea — Yahoo gives me a code so your real password stays yours.",
      "Tap the button, generate an app password named Olwen, copy it.",
      "Paste your address + the code below. I'll verify and we're set.",
    ],
    preview: { brand: 'Yahoo', code: 'aaaa bbbb cccc dddd' },
    trouble: "If 'Generate app password' isn't there, turn on 2-Step Verification first.",
  },
  icloud: {
    label: 'iCloud', glyph: '☁', color: '#A7F3D0',
    hostHint: 'imap.mail.me.com',
    appPasswordUrl: 'https://appleid.apple.com/account/manage',
    buttonLabel: 'Open Apple ID for me',
    steps: [
      'Tap the button — Apple ID opens.',
      'Sign in if asked.',
      'Find "App-Specific Passwords" → Generate. Name it Olwen.',
      'Copy what Apple shows.',
    ],
    narrate: [
      "iCloud. Apple will give me an app-specific password — your real one stays private.",
      "Tap the button, generate one in Sign-In and Security, copy it.",
      "Paste your @icloud address and the code. One log-in and we're connected.",
    ],
    preview: { brand: 'Apple ID', code: 'xxxx-yyyy-zzzz-aaaa' },
    trouble: "App-Specific Passwords require two-factor authentication on your Apple ID.",
  },
  other: {
    label: 'Other (IMAP)', glyph: '⌗', color: '#5EEAD4',
    hostHint: 'imap.your-host.com',
    appPasswordUrl: '',
    buttonLabel: '',
    steps: [
      'Find your provider\'s IMAP and SMTP server names.',
      'Make sure IMAP is enabled on your account.',
      'If your provider requires it, generate an app password.',
      'Paste your address, password, and the server names below.',
    ],
    narrate: [
      "Custom server — sure. Grab your IMAP and SMTP hostnames; I handle the rest.",
      "If your provider needs an app password, generate one first.",
      "Paste everything below. I'll try to sign in and confirm.",
    ],
    preview: { brand: 'Custom', code: '' },
    trouble: "Most modern providers require an app password (not your normal one).",
  },
}

const guide = computed<Guide | null>(() => (provider.value ? guides[provider.value] : null))

/* ---------- Olwen narration (typed-out bubble) ---------- */
const said = ref('')
const entityState = ref<'idle' | 'speaking'>('idle')
let typeTimer: ReturnType<typeof setInterval> | undefined

function clearType() { if (typeTimer) clearInterval(typeTimer) }

function say(text: string) {
  clearType()
  said.value = ''
  entityState.value = 'speaking'
  let n = 0
  typeTimer = setInterval(() => {
    n += 1
    said.value = text.slice(0, n)
    if (n >= text.length) {
      clearType()
      entityState.value = 'idle'
    }
  }, 22)
}

// Olwen greets when wizard opens; also check if Google OAuth is configured
onMounted(async () => {
  say("Hi. Let's connect your email — pick the one you use, I'll guide you.")
  try { oauthAvailable.value = (await oauthConfigured()).configured } catch { /* */ }
})
onBeforeUnmount(clearType)

// Narrate on step change
watch([provider, step], () => {
  const g = guide.value
  if (!g) return
  const idx = step.value - 1
  if (idx >= 0 && idx < g.narrate.length) say(g.narrate[idx])
})

function pickProvider(p: Provider) {
  provider.value = p
  step.value = p === 'other' ? 3 : 2 // jump straight to credentials for custom
}

function goNext() { if (step.value < 3) step.value = (step.value + 1) as 1 | 2 | 3 }
function goBack() {
  error.value = ''
  if (step.value > 1) step.value = (step.value - 1) as 1 | 2 | 3
  else { provider.value = null }
}

async function submit() {
  if (busy.value) return
  if (!form.email.trim() || !form.password) { error.value = 'Email and app password are required.'; return }
  busy.value = true; error.value = ''
  try {
    const body: Record<string, string | number> = {
      email: form.email.trim(), password: form.password,
    }
    if (provider.value === 'other') {
      if (form.imap_host.trim()) { body.imap_host = form.imap_host.trim(); body.imap_port = form.imap_port }
      if (form.smtp_host.trim()) { body.smtp_host = form.smtp_host.trim(); body.smtp_port = form.smtp_port }
    }
    await connect(body as never)
    say("Connected. I'll keep watch on this inbox.")
    setTimeout(() => emit('connected'), 700)
  } catch (e: unknown) {
    const detail = (e as { data?: { detail?: string } })?.data?.detail || ''
    error.value = detail || 'I couldn\'t sign in — double-check the address and app password.'
    say("That didn't work — check the email + app password and try again. (Not your normal password.)")
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="wiz">
    <div class="wiz__steps">
      <span class="dot" :class="{ on: step >= 1 }" />
      <span class="dot" :class="{ on: step >= 2 }" />
      <span class="dot" :class="{ on: step >= 3 }" />
    </div>

    <!-- STEP 1: pick provider (Sign in with Google up top when available) -->
    <div v-if="!provider" class="pane">
      <p class="pane__title">Which email do you use?</p>

      <button v-if="oauthAvailable" class="google" @click="startGoogleOAuth">
        <span class="google__g">G</span>
        <span class="google__label">Sign in with Google</span>
        <span class="google__sub">one click · no app passwords</span>
      </button>
      <div v-if="oauthAvailable" class="divider"><span>or pick another</span></div>

      <div class="picks">
        <button v-for="(g, key) in guides" :key="key" class="pick" :style="{ '--c': g.color }" @click="pickProvider(key as Provider)">
          <span class="pick__glyph">{{ g.glyph }}</span>
          <span class="pick__label">{{ g.label }}</span>
        </button>
      </div>
    </div>

    <!-- STEP 2: how to get the code (plain language + visual hint) -->
    <div v-else-if="step === 2 && guide" class="pane">
      <p class="pane__title">Get a one-time code from {{ guide.label }}</p>
      <p class="pane__desc">
        I never see your real password. {{ guide.label }} gives you a special code
        that only works with me — that's the safe way.
      </p>

      <div class="how">
        <ol class="howsteps">
          <li v-for="(s, i) in guide.steps" :key="i" :style="{ '--i': i }">{{ s }}</li>
        </ol>

        <!-- visual hint: what they'll see on the provider's page -->
        <div class="hint">
          <span class="hint__label">This is what you'll see</span>
          <div class="hint__card">
            <div class="hint__brand">{{ guide.preview.brand }}</div>
            <div class="hint__title">App password for Olwen</div>
            <div class="hint__code">{{ guide.preview.code || '— paste your password —' }}</div>
            <div class="hint__caption">copy this →</div>
          </div>
        </div>
      </div>

      <p class="trouble">⚠ {{ guide.trouble }}</p>

      <div class="row">
        <a v-if="guide.appPasswordUrl" class="btn btn--primary" :href="guide.appPasswordUrl" target="_blank" rel="noopener">{{ guide.buttonLabel }}</a>
        <button class="btn btn--ghost" @click="step = 3">I have the code →</button>
      </div>
    </div>

    <!-- STEP 3: paste credentials -->
    <div v-else class="pane">
      <p class="pane__title">Paste it here</p>
      <p class="pane__desc">Your address + the app password from {{ guide?.label || 'your provider' }}.</p>

      <input v-model="form.email" class="field" type="email" placeholder="you@example.com">
      <input v-model="form.password" class="field" type="password" :placeholder="provider === 'other' ? 'Password' : '16-character app password'">

      <template v-if="provider === 'other'">
        <div class="row">
          <input v-model="form.imap_host" class="field" :placeholder="`IMAP host (e.g. ${guide?.hostHint})`">
          <input v-model.number="form.imap_port" class="field" type="number" style="max-width:90px" placeholder="993">
        </div>
        <div class="row">
          <input v-model="form.smtp_host" class="field" placeholder="SMTP host (e.g. smtp.example.com)">
          <input v-model.number="form.smtp_port" class="field" type="number" style="max-width:90px" placeholder="587">
        </div>
      </template>

      <p v-if="error" class="error">{{ error }}</p>
      <div class="row">
        <button class="btn btn--primary" :disabled="busy" @click="submit">{{ busy ? 'Verifying…' : 'Connect email' }}</button>
        <button class="btn btn--ghost" :disabled="busy" @click="goBack">Back</button>
      </div>
    </div>

    <!-- Olwen narration bubble + tiny entity (he talks at the bottom) -->
    <div class="olwen">
      <div class="olwen__entity"><OlwenEntity :state="entityState" /></div>
      <div class="olwen__bubble">
        <span class="olwen__text">{{ said }}</span><span v-if="entityState === 'speaking'" class="olwen__cursor">▍</span>
      </div>
    </div>

    <button class="cancel" :disabled="busy" @click="emit('cancel')">Cancel</button>
  </div>
</template>

<style scoped>
.wiz {
  position: relative;
  display: flex; flex-direction: column; gap: 18px;
  padding: 20px 22px 200px; /* extra bottom space for Olwen bubble */
  border-radius: 14px;
  border: 0.5px solid var(--border-strong);
  background: color-mix(in srgb, var(--bg) 40%, transparent);
  min-height: 460px;
}
.wiz__steps { display: flex; gap: 8px; }
.dot { width: 7px; height: 7px; border-radius: 50%; background: var(--text-muted); transition: all .3s ease; }
.dot.on { background: var(--accent); box-shadow: 0 0 8px #5EEAD4; width: 24px; border-radius: 4px; }

.pane__title { margin: 0; font-size: 20px; font-weight: 300; color: var(--text-strong); }
.pane__desc { margin: 0; font-size: 13px; line-height: 1.55; color: var(--text-muted); max-width: 540px; }

.google {
  display: flex; align-items: center; gap: 12px; width: 100%;
  padding: 14px 16px; border-radius: 12px; cursor: pointer;
  background: #FFFFFF; color: #1F2937;
  border: 1px solid rgba(0,0,0,0.08); box-shadow: 0 12px 28px rgba(0,0,0,0.35);
  transition: transform .15s ease, box-shadow .15s ease;
}
.google:hover { transform: translateY(-1px); box-shadow: 0 16px 36px rgba(0,0,0,0.45); }
.google__g {
  width: 26px; height: 26px; border-radius: 50%;
  background: conic-gradient(from 180deg, #EA4335 0% 25%, #FBBC05 25% 50%, #34A853 50%, #4285F4 75% 100%);
  color: white; display: grid; place-items: center; font-weight: 700; font-size: 14px;
}
.google__label { font-size: 14px; font-weight: 500; flex: 1; text-align: left; }
.google__sub { font-size: 10px; color: #6B7280; letter-spacing: 0.3px; }
.divider { display: flex; align-items: center; gap: 10px; margin: 14px 0 6px; color: var(--text-muted); font-family: 'JetBrains Mono', monospace; font-size: 9px; letter-spacing: 1.5px; text-transform: uppercase; }
.divider::before, .divider::after { content: ''; flex: 1; height: 0.5px; background: var(--border-strong); }

.picks { display: grid; grid-template-columns: repeat(auto-fill, minmax(170px, 1fr)); gap: 12px; margin-top: 6px; }
.pick {
  display: flex; flex-direction: column; align-items: center; gap: 10px;
  padding: 22px 14px; border-radius: 14px; cursor: pointer;
  border: 0.5px solid var(--border);
  background: var(--surface-2);
  color: var(--text-strong); transition: all .2s ease;
}
.pick:hover { border-color: var(--c); background: var(--surface-2); transform: translateY(-2px); }
.pick__glyph {
  display: grid; place-items: center; width: 44px; height: 44px; border-radius: 12px;
  font-size: 20px; color: var(--c);
  background: color-mix(in srgb, var(--c) 14%, transparent);
  border: 0.5px solid color-mix(in srgb, var(--c) 40%, transparent);
}
.pick__label { font-family: 'JetBrains Mono', monospace; font-size: 10px; letter-spacing: 1.4px; text-transform: uppercase; color: var(--text-muted); }

.howsteps {
  list-style: none; counter-reset: step;
  margin: 6px 0 0; padding: 0;
  display: flex; flex-direction: column; gap: 8px;
}
.howsteps li {
  counter-increment: step;
  position: relative; padding: 12px 14px 12px 46px;
  border-radius: 10px;
  border: 0.5px solid var(--border);
  background: var(--surface-2);
  font-size: 13px; color: var(--text); line-height: 1.45;
  animation: stepIn .35s ease backwards;
  animation-delay: calc(var(--i) * 90ms);
}
.howsteps li::before {
  content: counter(step);
  position: absolute; left: 12px; top: 50%; transform: translateY(-50%);
  width: 24px; height: 24px; border-radius: 50%;
  display: grid; place-items: center;
  background: var(--surface-2); color: var(--accent);
  font-family: 'JetBrains Mono', monospace; font-size: 11px;
  border: 0.5px solid var(--border-strong);
}
@keyframes stepIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }

/* the side-by-side: steps on the left, visual hint of what they'll see on the right */
.how { display: grid; grid-template-columns: 1fr 220px; gap: 18px; align-items: start; }
.hint { display: flex; flex-direction: column; gap: 7px; }
.hint__label { font-family: 'JetBrains Mono', monospace; font-size: 9px; letter-spacing: 1.4px; text-transform: uppercase; color: var(--text-muted); }
.hint__card {
  border-radius: 10px; padding: 14px;
  background: #F9FAFB; color: #1F2937;
  border: 1px solid rgba(0,0,0,0.08);
  box-shadow: 0 12px 32px rgba(0,0,0,0.45);
  font-family: -apple-system, 'Segoe UI', system-ui, sans-serif;
}
.hint__brand { font-size: 10px; color: #6B7280; letter-spacing: 0.5px; text-transform: uppercase; margin-bottom: 8px; }
.hint__title { font-size: 13px; color: #111827; margin-bottom: 8px; }
.hint__code {
  background: #FEF3C7; color: #92400E; border: 1px dashed #F59E0B;
  border-radius: 6px; padding: 7px 9px;
  font-family: 'JetBrains Mono', monospace; font-size: 11px; letter-spacing: 1px;
  text-align: center;
}
.hint__caption { font-size: 9px; color: #6B7280; margin-top: 6px; text-align: right; letter-spacing: 0.5px; }
.trouble { margin: 4px 0 0; font-size: 11.5px; color: #FBBF24; }

@media (max-width: 720px) { .how { grid-template-columns: 1fr; } .hint { order: -1; } }

.row { display: flex; gap: 10px; align-items: center; }
.btn { padding: 10px 16px; border-radius: 9px; cursor: pointer; font-size: 11px; letter-spacing: 1.2px; text-transform: uppercase; transition: all .2s ease; text-decoration: none; display: inline-flex; align-items: center; }
.btn:disabled { opacity: 0.5; cursor: progress; }
.btn--primary { border: 0.5px solid var(--accent); background: var(--surface-2); color: var(--text-strong); }
.btn--primary:hover:not(:disabled) { background: var(--surface-2); }
.btn--ghost { border: 0.5px solid var(--border-strong); background: transparent; color: var(--text-muted); }
.btn--ghost:hover:not(:disabled) { color: var(--text-strong); border-color: var(--accent); }

.field { padding: 11px 13px; border-radius: 9px; outline: none; font-size: 13.5px; border: 0.5px solid var(--border-strong); background: color-mix(in srgb, var(--bg) 50%, transparent); color: var(--text); }
.field:focus { border-color: var(--accent); }
.field::placeholder { color: var(--text-muted); }
.error { margin: 0; font-size: 12px; color: #FCA5A5; border-left: 2px solid #F87171; padding-left: 10px; }

/* Olwen talking at the bottom */
.olwen {
  position: absolute; left: 18px; right: 18px; bottom: 18px;
  display: flex; align-items: flex-end; gap: 14px;
}
.olwen__entity { width: 84px; height: 84px; flex-shrink: 0; }
.olwen__bubble {
  position: relative; flex: 1;
  padding: 14px 16px; border-radius: 14px 14px 14px 2px;
  border: 0.5px solid var(--border-strong);
  background: var(--surface-2); backdrop-filter: blur(8px);
  font-size: 13.5px; line-height: 1.5; color: var(--text-strong); min-height: 1.5em;
}
.olwen__bubble::before {
  content: ''; position: absolute; left: -6px; bottom: 14px;
  width: 12px; height: 12px; transform: rotate(45deg);
  background: var(--surface-2);
  border-left: 0.5px solid var(--border-strong);
  border-bottom: 0.5px solid var(--border-strong);
}
.olwen__cursor { color: var(--accent); animation: blink 1s step-start infinite; }
@keyframes blink { 50% { opacity: 0; } }

.cancel {
  position: absolute; top: 18px; right: 18px;
  border: none; background: transparent; cursor: pointer;
  color: var(--text-muted); font-family: 'JetBrains Mono', monospace; font-size: 10px;
  letter-spacing: 1.3px; text-transform: uppercase;
}
.cancel:hover { color: #FCA5A5; }
</style>
