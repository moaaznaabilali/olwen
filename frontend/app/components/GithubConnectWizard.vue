<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import OlwenEntity from './OlwenEntity.vue'

const emit = defineEmits<{
  connected: [{ login: string }]
  cancel: []
}>()

const gh = useGithub()
const oauthAvailable = ref(false)
const redirectUri = ref('http://localhost:8000/api/github/oauth/callback')

type Step = 1 | 2 | 3 | 'oauth-setup'
const step = ref<Step>(1)
const path = ref<'pat' | 'oauth' | ''>('')
const token = ref('')
const busy = ref(false)
const error = ref('')
const narration = ref('')

// OAuth setup form
const clientId = ref('')
const clientSecret = ref('')

// pre-built token URL with the scopes we want already selected — one click and
// the user lands on the right page with read:user + repo checked.
const tokenUrl =
  'https://github.com/settings/tokens/new?'
  + 'description=Olwen%20(dashboard%20access)'
  + '&scopes=read:user,repo'

const SCRIPT: Record<string, string> = {
  pickPath:
    "Two ways to connect, both safe — your password never leaves GitHub. "
    + "Token is fastest; one-click works too if your server's set up for it.",
  patSteps:
    "I'll open the GitHub token page in a new tab. The scopes (read:user + repo) "
    + "are already ticked — you just click Generate, then copy the token here.",
  patPaste:
    "Paste the token below. It starts with 'ghp_' or 'github_pat_'. "
    + "I'll verify it with GitHub right away.",
  oauthGo:
    "I'll bounce you to GitHub. Approve once, and you're back here connected.",
  setupHelp:
    "Sign-in needs a one-time setup: create a free OAuth App on GitHub, "
    + "paste the two values here, and it'll work forever after — for everyone. "
    + "Takes about a minute. Or just use the Token path; same result.",
  ok:
    "Beautiful — we're hooked up. Your real GitHub activity will start flowing into the dashboard.",
}

watch(step, (n) => {
  if (n === 1) narration.value = SCRIPT.pickPath
  if (n === 2) narration.value = path.value === 'pat' ? SCRIPT.patSteps : SCRIPT.oauthGo
  if (n === 3) narration.value = path.value === 'pat' ? SCRIPT.patPaste : SCRIPT.oauthGo
}, { immediate: false })

function pick(p: 'pat' | 'oauth') {
  path.value = p
  if (p === 'oauth' && !oauthAvailable.value) {
    step.value = 'oauth-setup'
    narration.value = SCRIPT.setupHelp
    return
  }
  step.value = 2
}

async function saveOAuthSetup() {
  if (clientId.value.length < 10 || clientSecret.value.length < 10) {
    error.value = 'Paste both the Client ID and the Client Secret from your GitHub OAuth App.'
    return
  }
  busy.value = true; error.value = ''
  try {
    await gh.oauthSetup(clientId.value.trim(), clientSecret.value.trim())
    oauthAvailable.value = true
    step.value = 2                 // continue straight into the OAuth redirect
    narration.value = SCRIPT.oauthGo
  } catch (e: unknown) {
    error.value = (e as { data?: { detail?: string } })?.data?.detail || 'Could not save OAuth credentials.'
  } finally { busy.value = false }
}

function openTokenPage() {
  window.open(tokenUrl, '_blank', 'noopener')
  step.value = 3
}

async function startOAuth() {
  try { busy.value = true; const r = await gh.start(); window.location.href = r.auth_url }
  catch (e: unknown) {
    error.value = (e as { data?: { detail?: string } })?.data?.detail || 'OAuth not configured.'
    busy.value = false
  }
}

async function submitPat() {
  const t = token.value.trim()
  if (t.length < 20) { error.value = 'Paste a real token (starts with ghp_ or github_pat_).'; return }
  busy.value = true; error.value = ''
  try {
    const r = await gh.connectPat(t)
    narration.value = SCRIPT.ok
    emit('connected', { login: r.login })
  } catch (e: unknown) {
    error.value = (e as { data?: { detail?: string } })?.data?.detail || 'GitHub rejected the token.'
  } finally { busy.value = false }
}

onMounted(async () => {
  try {
    const c = await gh.configured()
    oauthAvailable.value = c.oauth_configured
    if (c.redirect_uri) redirectUri.value = c.redirect_uri
  } catch { /* */ }
  narration.value = SCRIPT.pickPath
})

// GitHub's "New OAuth App" page — no reliable URL prefill, so we show a copy
// cheat-sheet next to it instead.
const newAppUrl = 'https://github.com/settings/applications/new'
const homepageUrl = computed(() => {
  // Best guess: same origin as the front-end (works in dev + prod).
  if (import.meta.client) return window.location.origin
  return 'http://localhost:3100'
})

const copiedKey = ref<string>('')                                   // which field's copy button glowed
async function copy(text: string, key: string) {
  try { await navigator.clipboard.writeText(text); copiedKey.value = key; setTimeout(() => { copiedKey.value = '' }, 1500) } catch { /* */ }
}
</script>

<template>
  <div class="wiz">
    <!-- progress trail -->
    <div class="trail">
      <span class="trail__dot" :class="{ on: step >= 1 }">1</span>
      <span class="trail__line" :class="{ on: step >= 2 }" />
      <span class="trail__dot" :class="{ on: step >= 2 }">2</span>
      <span class="trail__line" :class="{ on: step >= 3 }" />
      <span class="trail__dot" :class="{ on: step >= 3 }">3</span>
    </div>

    <!-- STEP 1: pick path -->
    <div v-if="step === 1" class="card">
      <h3 class="card__title">Connect GitHub</h3>
      <p class="card__sub">Choose how Olwen reaches your repos. Both are safe; both can be removed any time.</p>

      <div class="paths">
        <button class="path path--reco" @click="pick('pat')">
          <div class="path__head">
            <span class="path__glyph">⚡</span>
            <div>
              <div class="path__name">Personal Access Token</div>
              <div class="path__sub">~60 seconds · no admin needed</div>
            </div>
            <span class="path__badge">Recommended</span>
          </div>
          <p class="path__desc">
            Click once to open GitHub's token page (with the right boxes pre-ticked),
            copy the token, paste it back. Easiest path.
          </p>
        </button>

        <button class="path" @click="pick('oauth')">
          <div class="path__head">
            <span class="path__glyph">⌗</span>
            <div>
              <div class="path__name">Sign in with GitHub</div>
              <div class="path__sub">{{ oauthAvailable ? 'One click · OAuth' : '1-min setup, then one-click forever' }}</div>
            </div>
          </div>
          <p class="path__desc">
            {{ oauthAvailable
              ? 'Standard OAuth — GitHub asks once, you approve, you\'re back here connected.'
              : 'First time? I\'ll walk you through creating a tiny OAuth App on GitHub (about a minute). After that, it\'s one click for every user.' }}
          </p>
        </button>
      </div>
    </div>

    <!-- STEP 2 (PAT): show GitHub mockup, then open the real page -->
    <div v-else-if="step === 2 && path === 'pat'" class="card">
      <button class="back" @click="step = 1">‹ Back</button>
      <h3 class="card__title">Generate the token</h3>
      <p class="card__sub">Here's what you'll see on the GitHub page I'm about to open:</p>

      <!-- visual hint card mocking GitHub's UI -->
      <div class="mock">
        <div class="mock__bar">
          <span class="mock__dot" /><span class="mock__dot" /><span class="mock__dot" />
          <span class="mock__url">github.com / Settings / Developer settings / Personal access tokens / New</span>
        </div>
        <div class="mock__body">
          <div class="mock__row"><span class="mock__label">Note</span><span class="mock__field">Olwen (dashboard access)</span></div>
          <div class="mock__row"><span class="mock__label">Expiration</span><span class="mock__field mock__field--ghost">90 days (pick whatever you like)</span></div>
          <div class="mock__row mock__row--scopes">
            <span class="mock__label">Scopes</span>
            <div class="mock__scopes">
              <span class="mock__scope on">☑ read:user</span>
              <span class="mock__scope on">☑ repo</span>
              <span class="mock__scope">☐ admin:org</span>
              <span class="mock__scope">☐ delete_repo</span>
            </div>
          </div>
          <div class="mock__cta">
            <span class="mock__btn">Generate token</span>
          </div>
        </div>
      </div>

      <ol class="steps">
        <li>Click the green <strong>Generate token</strong> button at the bottom of GitHub's page.</li>
        <li>GitHub shows the token <em>once</em>. Copy it.</li>
        <li>Come back here — I'll be waiting.</li>
      </ol>

      <button class="cta" @click="openTokenPage">↗ Open GitHub token page</button>
    </div>

    <!-- STEP 3 (PAT): paste -->
    <div v-else-if="step === 3 && path === 'pat'" class="card">
      <button class="back" @click="step = 2">‹ Back</button>
      <h3 class="card__title">Paste the token</h3>
      <p class="card__sub">Starts with <code>ghp_</code> (classic) or <code>github_pat_</code> (fine-grained).</p>

      <input
        v-model="token"
        class="field"
        type="password"
        placeholder="ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
        autocomplete="off" spellcheck="false"
        @keyup.enter="submitPat"
      >
      <p v-if="error" class="error">{{ error }}</p>

      <div class="row">
        <button class="cta" :disabled="busy" @click="submitPat">{{ busy ? 'Verifying…' : 'Connect' }}</button>
        <button class="link" type="button" @click="emit('cancel')">Cancel</button>
      </div>
    </div>

    <!-- OAUTH SETUP: one-time creation of the OAuth App so Sign-in starts working -->
    <div v-else-if="step === 'oauth-setup'" class="card">
      <button class="back" @click="step = 1">‹ Back</button>
      <h3 class="card__title">Set up Sign-in with GitHub</h3>
      <p class="card__sub">
        I'll send you to GitHub's "New OAuth App" form. Here's exactly what to paste in each field —
        tap a value to copy it. Or if this feels like too much, the
        <button class="inline-link" @click="pick('pat')">Token path</button>
        takes 30 seconds.
      </p>

      <!-- Big "Open GitHub" CTA at the top -->
      <a class="cta cta--block" :href="newAppUrl" target="_blank" rel="noopener">
        ↗ Open GitHub's New OAuth App page
      </a>

      <p class="cheat__title">
        <span class="cheat__num">2</span>
        Then on GitHub, fill in these 3 fields (tap to copy):
      </p>

      <!-- cheat sheet: exact values for each field -->
      <div class="cheat">
        <div class="cheat__row" :class="{ copied: copiedKey === 'name' }" @click="copy('Olwen', 'name')">
          <div class="cheat__field">
            <span class="cheat__label">Application name</span>
            <span class="cheat__value">Olwen</span>
          </div>
          <span class="cheat__copy">{{ copiedKey === 'name' ? '✓ Copied' : 'Copy' }}</span>
        </div>

        <div class="cheat__row" :class="{ copied: copiedKey === 'home' }" @click="copy(homepageUrl, 'home')">
          <div class="cheat__field">
            <span class="cheat__label">Homepage URL</span>
            <span class="cheat__value">{{ homepageUrl }}</span>
          </div>
          <span class="cheat__copy">{{ copiedKey === 'home' ? '✓ Copied' : 'Copy' }}</span>
        </div>

        <div class="cheat__row cheat__row--important" :class="{ copied: copiedKey === 'cb' }" @click="copy(redirectUri, 'cb')">
          <div class="cheat__field">
            <span class="cheat__label">Authorization callback URL  <span class="cheat__star">★ critical</span></span>
            <span class="cheat__value">{{ redirectUri }}</span>
          </div>
          <span class="cheat__copy">{{ copiedKey === 'cb' ? '✓ Copied' : 'Copy' }}</span>
        </div>
      </div>

      <p class="cheat__skip">
        <strong>Application description</strong> — leave blank. <strong>Enable Device Flow</strong> — leave unchecked.
      </p>

      <p class="cheat__title">
        <span class="cheat__num">3</span>
        Click the green <strong>Register application</strong> button.
      </p>
      <p class="cheat__title">
        <span class="cheat__num">4</span>
        On the page that loads, you'll see:
      </p>

      <!-- mini diagram of what they'll see -->
      <div class="mock">
        <div class="mock__bar"><span class="mock__dot" /><span class="mock__dot" /><span class="mock__dot" /><span class="mock__url">Your OAuth app · Olwen</span></div>
        <div class="mock__body">
          <div class="mock__row">
            <span class="mock__label">Client ID</span>
            <span class="mock__field">Iv23liXXXXXXXXXXXXXX <span class="mock__sub">← copy this</span></span>
          </div>
          <div class="mock__row">
            <span class="mock__label">Client secrets</span>
            <span class="mock__field mock__field--ghost">No client secret yet  →  <span class="mock__sub">click "Generate a new client secret"</span></span>
          </div>
        </div>
      </div>

      <p class="cheat__title"><span class="cheat__num">5</span> Paste them here:</p>

      <div class="setup-form">
        <label>
          <span class="setup-form__label">Client ID</span>
          <input v-model="clientId" class="field" placeholder="Iv23li…  or  Iv1.…" autocomplete="off" spellcheck="false">
        </label>
        <label>
          <span class="setup-form__label">Client Secret  <span class="cheat__star">(shown once on GitHub — copy it now)</span></span>
          <input v-model="clientSecret" class="field" type="password" placeholder="ghcs_…" autocomplete="off" spellcheck="false">
        </label>
        <p v-if="error" class="error">{{ error }}</p>
        <div class="row">
          <button class="cta" :disabled="busy" @click="saveOAuthSetup">{{ busy ? 'Saving…' : 'Save & continue to GitHub →' }}</button>
          <button class="link" @click="pick('pat')">Use Token instead</button>
        </div>
      </div>
    </div>

    <!-- STEP 2 (OAuth): redirect -->
    <div v-else-if="step === 2 && path === 'oauth'" class="card">
      <button class="back" @click="step = 1">‹ Back</button>
      <h3 class="card__title">Sign in with GitHub</h3>
      <p class="card__sub">I'll send you to github.com. You approve, you come back — that's it.</p>
      <button class="cta" :disabled="busy" @click="startOAuth">
        <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor"><path d="M8 0C3.58 0 0 3.58 0 8a8 8 0 0 0 5.47 7.59c.4.07.55-.17.55-.38v-1.5c-2.22.48-2.69-1.06-2.69-1.06-.36-.92-.89-1.16-.89-1.16-.73-.5.05-.49.05-.49.81.06 1.24.83 1.24.83.72 1.23 1.88.88 2.34.67.07-.52.28-.88.5-1.08-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.13 0 0 .67-.21 2.2.82a7.5 7.5 0 0 1 4 0c1.53-1.04 2.2-.82 2.2-.82.44 1.11.16 1.93.08 2.13.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.74.54 1.5v2.22c0 .21.15.46.55.38A8 8 0 0 0 16 8c0-4.42-3.58-8-8-8z"/></svg>
        {{ busy ? 'Redirecting…' : 'Continue to GitHub' }}
      </button>
    </div>

    <!-- Olwen narrates from the bottom -->
    <div class="narrator">
      <div class="narrator__entity"><OlwenEntity state="speaking" /></div>
      <div class="narrator__bubble">{{ narration }}</div>
    </div>
  </div>
</template>

<style scoped>
.wiz { display: flex; flex-direction: column; gap: 18px; }

.trail { display: flex; align-items: center; gap: 8px; padding: 0 2px 4px; }
.trail__dot {
  width: 24px; height: 24px; border-radius: 50%; display: grid; place-items: center;
  font-family: 'JetBrains Mono', monospace; font-size: 10px;
  background: rgba(2,6,10,0.5); color: rgba(167,243,208,0.5);
  border: 0.5px solid rgba(94,234,212,0.2); transition: all .2s ease;
}
.trail__dot.on { background: rgba(94,234,212,0.18); border-color: #5EEAD4; color: #ECFEFF; box-shadow: 0 0 10px rgba(94,234,212,0.4); }
.trail__line { flex: 1; height: 0.5px; background: rgba(94,234,212,0.15); }
.trail__line.on { background: #5EEAD4; box-shadow: 0 0 8px rgba(94,234,212,0.5); }

.card { padding: 22px 24px; border-radius: 14px; border: 0.5px solid rgba(94,234,212,0.18); background: linear-gradient(180deg, rgba(8,30,38,0.6), rgba(2,6,10,0.45)); position: relative; }
.card__title { margin: 0 0 4px; font-size: 19px; font-weight: 300; color: #ECFEFF; }
.card__sub { margin: 0 0 18px; font-size: 13px; line-height: 1.55; color: rgba(167,243,208,0.6); }
.card__sub code { font-family: 'JetBrains Mono', monospace; font-size: 12px; color: #A78BFA; }

.back { position: absolute; top: 16px; right: 18px; background: transparent; border: none; color: rgba(167,243,208,0.55); font-family: 'JetBrains Mono', monospace; font-size: 10px; letter-spacing: 1px; cursor: pointer; }
.back:hover { color: #5EEAD4; }

.paths { display: flex; flex-direction: column; gap: 12px; }
.path { text-align: left; padding: 16px 18px; border-radius: 12px; cursor: pointer; border: 0.5px solid rgba(94,234,212,0.18); background: rgba(8,30,38,0.4); transition: all .15s ease; }
.path:hover:not(:disabled) { border-color: #5EEAD4; transform: translateY(-1px); box-shadow: 0 0 18px rgba(94,234,212,0.12); }
.path.path--reco { border-color: rgba(94,234,212,0.4); background: rgba(94,234,212,0.06); }
.path.disabled { opacity: 0.4; cursor: not-allowed; }
.path__head { display: flex; align-items: center; gap: 12px; }
.path__glyph { width: 36px; height: 36px; border-radius: 10px; display: grid; place-items: center; background: rgba(94,234,212,0.14); color: #5EEAD4; font-size: 18px; flex-shrink: 0; }
.path__name { font-size: 14.5px; color: #ECFEFF; }
.path__sub { font-family: 'JetBrains Mono', monospace; font-size: 10px; letter-spacing: 0.8px; color: rgba(167,243,208,0.5); margin-top: 2px; }
.path__badge { margin-left: auto; font-family: 'JetBrains Mono', monospace; font-size: 9px; letter-spacing: 1.4px; text-transform: uppercase; padding: 4px 9px; border-radius: 999px; background: rgba(94,234,212,0.18); color: #5EEAD4; border: 0.5px solid #5EEAD4; }
.path__desc { margin: 10px 0 0; font-size: 12px; line-height: 1.5; color: rgba(167,243,208,0.55); }

/* GitHub UI mockup */
.mock { border-radius: 12px; overflow: hidden; border: 0.5px solid rgba(94,234,212,0.18); background: #0a121c; margin-bottom: 14px; }
.mock__bar { display: flex; align-items: center; gap: 6px; padding: 9px 12px; background: rgba(255,255,255,0.04); border-bottom: 0.5px solid rgba(94,234,212,0.1); }
.mock__dot { width: 8px; height: 8px; border-radius: 50%; background: rgba(167,243,208,0.18); }
.mock__url { margin-left: 10px; font-family: 'JetBrains Mono', monospace; font-size: 10px; color: rgba(167,243,208,0.5); }
.mock__body { padding: 14px 16px; display: flex; flex-direction: column; gap: 10px; }
.mock__row { display: flex; align-items: flex-start; gap: 10px; }
.mock__label { width: 76px; flex-shrink: 0; font-family: 'JetBrains Mono', monospace; font-size: 10px; letter-spacing: 0.8px; color: rgba(167,243,208,0.5); text-transform: uppercase; padding-top: 2px; }
.mock__field { flex: 1; padding: 6px 10px; border-radius: 6px; background: rgba(255,255,255,0.04); border: 0.5px solid rgba(94,234,212,0.18); color: #ECFEFF; font-size: 12px; }
.mock__field--ghost { color: rgba(167,243,208,0.5); }
.mock__row--scopes { align-items: flex-start; }
.mock__scopes { display: flex; flex-wrap: wrap; gap: 6px; }
.mock__scope { padding: 4px 9px; border-radius: 6px; background: rgba(255,255,255,0.04); border: 0.5px solid rgba(94,234,212,0.15); font-family: 'JetBrains Mono', monospace; font-size: 11px; color: rgba(167,243,208,0.5); }
.mock__scope.on { background: rgba(94,234,212,0.18); border-color: #5EEAD4; color: #ECFEFF; font-weight: 500; }
.mock__cta { display: flex; justify-content: flex-end; padding-top: 6px; }
.mock__btn { padding: 7px 16px; border-radius: 6px; background: #2ea043; color: #ffffff; font-size: 12px; font-weight: 600; }

.steps { margin: 0 0 14px; padding-left: 20px; display: flex; flex-direction: column; gap: 6px; color: rgba(167,243,208,0.65); font-size: 12.5px; line-height: 1.55; }
.steps strong { color: #ECFEFF; }
.steps em { color: #FBBF24; font-style: normal; }

.cta {
  display: inline-flex; align-items: center; gap: 9px; justify-content: center;
  padding: 11px 20px; border-radius: 999px; cursor: pointer; border: 0.5px solid #5EEAD4;
  background: rgba(94,234,212,0.16); color: #ECFEFF;
  font-family: 'JetBrains Mono', monospace; font-size: 11px; letter-spacing: 1.5px; text-transform: uppercase;
  transition: all .2s ease;
}
.cta:hover:not(:disabled) { background: #5EEAD4; color: #02060A; box-shadow: 0 0 22px rgba(94,234,212,0.4); }
.cta:disabled { opacity: 0.6; cursor: progress; }

.field { width: 100%; padding: 12px 14px; border-radius: 10px; border: 0.5px solid rgba(94,234,212,0.25); background: rgba(2,6,10,0.55); color: #ECFEFF; font-family: 'JetBrains Mono', monospace; font-size: 12px; letter-spacing: 0.5px; margin-bottom: 12px; }
.field:focus { outline: none; border-color: #5EEAD4; box-shadow: 0 0 18px rgba(94,234,212,0.18); }

.row { display: flex; align-items: center; gap: 14px; }
.link { background: transparent; border: none; color: rgba(167,243,208,0.55); cursor: pointer; font-size: 12px; }
.link:hover { color: #5EEAD4; }
.error { margin: 0 0 12px; font-size: 12px; color: #FCA5A5; border-left: 2px solid #F87171; padding-left: 9px; }

/* ---- OAuth setup screen ---- */
.steps--big li { margin-bottom: 10px; }
.inline-cta {
  display: inline-flex; align-items: center; gap: 6px; margin-left: 8px;
  padding: 4px 10px; border-radius: 999px; text-decoration: none;
  background: rgba(94,234,212,0.16); border: 0.5px solid #5EEAD4; color: #ECFEFF;
  font-family: 'JetBrains Mono', monospace; font-size: 10px; letter-spacing: 1px; text-transform: uppercase;
}
.inline-cta:hover { background: #5EEAD4; color: #02060A; }
.inline-link { background: transparent; border: none; cursor: pointer; color: #67E8F9; text-decoration: underline; padding: 0; font: inherit; }
.inline-link:hover { color: #5EEAD4; }

.hint { margin: 4px 0 14px; font-size: 11.5px; color: rgba(167,243,208,0.5); }
.hint code { font-family: 'JetBrains Mono', monospace; font-size: 11px; padding: 2px 7px; border-radius: 5px; background: rgba(255,255,255,0.05); border: 0.5px solid rgba(94,234,212,0.18); color: #A7F3D0; }

.setup-form { display: flex; flex-direction: column; gap: 10px; }
.setup-form label { display: flex; flex-direction: column; gap: 4px; }
.setup-form__label { font-family: 'JetBrains Mono', monospace; font-size: 9.5px; letter-spacing: 1.4px; text-transform: uppercase; color: rgba(167,243,208,0.5); }
.setup-form .field { margin-bottom: 0; }

/* ---- copy-cheat-sheet ---- */
.cta--block { display: flex; width: 100%; padding: 13px 18px; margin-bottom: 18px; font-size: 12px; }

.cheat__title { display: flex; align-items: center; gap: 10px; margin: 14px 0 8px; font-size: 12.5px; color: #DCFCF5; }
.cheat__title strong { color: #ECFEFF; }
.cheat__num {
  display: grid; place-items: center; width: 22px; height: 22px; border-radius: 50%;
  background: rgba(94,234,212,0.18); color: #5EEAD4; border: 0.5px solid #5EEAD4;
  font-family: 'JetBrains Mono', monospace; font-size: 10px; font-weight: 600; flex-shrink: 0;
}

.cheat { display: flex; flex-direction: column; gap: 8px; margin-bottom: 8px; }
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
.cheat__star { color: #FBBF24; font-size: 9px; letter-spacing: 0.5px; text-transform: none; margin-left: 6px; }
.cheat__value {
  font-family: 'JetBrains Mono', monospace; font-size: 13px; color: #ECFEFF;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.cheat__copy {
  flex-shrink: 0; padding: 6px 11px; border-radius: 999px;
  background: rgba(94,234,212,0.14); border: 0.5px solid rgba(94,234,212,0.35); color: #5EEAD4;
  font-family: 'JetBrains Mono', monospace; font-size: 9.5px; letter-spacing: 1.2px; text-transform: uppercase;
}
.cheat__row.copied .cheat__copy { background: #5EEAD4; color: #02060A; }

.cheat__skip { margin: 4px 0 6px; padding: 8px 12px; font-size: 11.5px; color: rgba(167,243,208,0.55); border-radius: 8px; background: rgba(255,255,255,0.03); border-left: 2px solid rgba(167,243,208,0.2); }
.cheat__skip strong { color: rgba(220,252,245,0.8); }

/* Olwen narrator at the bottom */
.narrator { display: flex; align-items: center; gap: 12px; padding: 14px 16px; border-radius: 12px; border: 0.5px solid rgba(94,234,212,0.15); background: rgba(8,30,38,0.4); }
.narrator__entity { width: 56px; height: 56px; flex-shrink: 0; }
.narrator__bubble { flex: 1; font-size: 12.5px; line-height: 1.55; color: #DCFCF5; padding: 8px 14px; border-radius: 10px; background: rgba(94,234,212,0.06); border: 0.5px solid rgba(94,234,212,0.15); position: relative; }
.narrator__bubble::before { content: ''; position: absolute; left: -6px; top: 50%; transform: translateY(-50%); width: 0; height: 0; border-top: 6px solid transparent; border-bottom: 6px solid transparent; border-right: 6px solid rgba(94,234,212,0.15); }
</style>
