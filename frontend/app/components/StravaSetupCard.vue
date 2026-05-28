<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

const emit = defineEmits<{ connected: [] }>()

const { configured, account, setup, start, disconnect } = useStrava()

const ready = ref(false)
const redirectUri = ref('http://localhost:8000/api/strava/oauth/callback')
const acc = ref<{ connected: boolean; athlete_name?: string; avatar_url?: string }>({ connected: false })

const clientId = ref('')
const clientSecret = ref('')
const busy = ref(false)
const error = ref('')

const newAppUrl = 'https://www.strava.com/settings/api'
const copiedKey = ref('')
async function copy(text: string, k: string) {
  try { await navigator.clipboard.writeText(text); copiedKey.value = k; setTimeout(() => { copiedKey.value = '' }, 1500) } catch { /* */ }
}

async function load() {
  try {
    const c = await configured()
    ready.value = c.configured
    if (c.redirect_uri) redirectUri.value = c.redirect_uri
    acc.value = await account()
  } catch { /* */ }
}

async function saveSetup() {
  if (clientId.value.length < 1 || clientSecret.value.length < 10) {
    error.value = 'Paste both your Client ID and Client Secret from Strava.'
    return
  }
  busy.value = true; error.value = ''
  try {
    await setup(clientId.value.trim(), clientSecret.value.trim())
    ready.value = true
    await signIn()
  } catch (e: unknown) {
    error.value = (e as { data?: { detail?: string } })?.data?.detail || 'Could not save credentials.'
  } finally { busy.value = false }
}

async function signIn() {
  busy.value = true
  try {
    const r = await start()
    window.location.href = r.auth_url
  } catch (e: unknown) {
    error.value = (e as { data?: { detail?: string } })?.data?.detail || 'Sign-in failed.'
    busy.value = false
  }
}

async function disconnectNow() {
  try { await disconnect(); acc.value = { connected: false } } catch { /* */ }
}

const localOrigin = computed(() => import.meta.client ? window.location.host.split(':')[0] : 'localhost')

onMounted(load)
</script>

<template>
  <div class="card">
    <div class="card__head">
      <div class="card__name">
        <svg viewBox="0 0 24 24" width="16" height="16" fill="#FB923C"><path d="M15.387 17.944l-2.089-4.116h-3.065L15.387 24l5.15-10.172h-3.066m-7.008-5.599l2.836 5.598h4.172L10.463 0l-7 13.828h4.169" /></svg>
        Strava <span class="tag">runs · rides · training</span>
      </div>
      <span v-if="acc.connected" class="badge--on">Connected</span>
    </div>

    <template v-if="acc.connected">
      <div class="row">
        <img v-if="acc.avatar_url" :src="acc.avatar_url" class="avatar" alt="">
        <div class="row__main">
          <span class="row__name">{{ acc.athlete_name }}</span>
          <span class="row__sub">Olwen reads your recent activities</span>
        </div>
        <button class="btn btn--ghost" @click="disconnectNow">Disconnect</button>
      </div>
    </template>

    <template v-else-if="ready">
      <p class="desc">Server already has Strava credentials — one click connects your athlete account.</p>
      <button class="btn btn--primary" :disabled="busy" @click="signIn">
        {{ busy ? 'Redirecting…' : '↗ Authorize with Strava' }}
      </button>
    </template>

    <template v-else>
      <p class="desc">
        First-time setup. Strava needs an "API Application" registered so it knows who's asking.
        ~60 seconds, one-time.
      </p>

      <ol class="steps">
        <li>
          Open <a class="link" :href="newAppUrl" target="_blank" rel="noopener">Strava API settings</a>
          → create an application. Fill in:
        </li>
      </ol>

      <div class="cheat">
        <div class="cheat__row" :class="{ copied: copiedKey === 'name' }" @click="copy('Olwen', 'name')">
          <div class="cheat__field"><span class="cheat__label">Application name</span><span class="cheat__value">Olwen</span></div>
          <span class="cheat__copy">{{ copiedKey === 'name' ? '✓' : 'Copy' }}</span>
        </div>
        <div class="cheat__row" :class="{ copied: copiedKey === 'host' }" @click="copy(localOrigin, 'host')">
          <div class="cheat__field"><span class="cheat__label">Authorization callback domain</span><span class="cheat__value">{{ localOrigin }}</span></div>
          <span class="cheat__copy">{{ copiedKey === 'host' ? '✓' : 'Copy' }}</span>
        </div>
        <div class="cheat__row cheat__row--important" :class="{ copied: copiedKey === 'cb' }" @click="copy(redirectUri, 'cb')">
          <div class="cheat__field"><span class="cheat__label">Website / Redirect URI <span class="star">★</span></span><span class="cheat__value">{{ redirectUri }}</span></div>
          <span class="cheat__copy">{{ copiedKey === 'cb' ? '✓' : 'Copy' }}</span>
        </div>
      </div>

      <ol class="steps" start="2">
        <li>After saving, Strava shows <strong>Client ID</strong> and a <strong>Client Secret</strong> (click "show" to reveal). Paste them here:</li>
      </ol>

      <div class="form">
        <label>
          <span class="label">Client ID</span>
          <input v-model="clientId" class="input" placeholder="e.g. 123456" autocomplete="off" spellcheck="false">
        </label>
        <label>
          <span class="label">Client Secret</span>
          <input v-model="clientSecret" class="input" type="password" placeholder="40-char secret" autocomplete="off" spellcheck="false">
        </label>
        <p v-if="error" class="error">{{ error }}</p>
        <button class="btn btn--primary" :disabled="busy" @click="saveSetup">
          {{ busy ? 'Saving…' : 'Save & authorize' }}
        </button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.card { margin-top: 22px; padding: 18px 20px; border-radius: 14px; border: 0.5px solid rgba(251,146,60,0.25); background: linear-gradient(180deg, rgba(251,146,60,0.06), rgba(8,30,38,0.4)); }
.card__head { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 10px; }
.card__name { display: flex; align-items: center; gap: 9px; font-size: 17px; color: #ECFEFF; font-weight: 300; }
.tag { font-family: 'JetBrains Mono', monospace; font-size: 9px; letter-spacing: 1.2px; color: rgba(251,146,60,0.7); margin-left: 4px; }

.desc { margin: 0 0 12px; font-size: 12.5px; line-height: 1.55; color: rgba(220,252,245,0.7); }

.row { display: flex; align-items: center; gap: 12px; padding: 6px 0 2px; }
.avatar { width: 36px; height: 36px; border-radius: 50%; flex-shrink: 0; border: 0.5px solid rgba(251,146,60,0.4); }
.row__main { flex: 1; display: flex; flex-direction: column; gap: 2px; }
.row__name { font-size: 14px; color: #ECFEFF; }
.row__sub { font-size: 11.5px; color: rgba(167,243,208,0.5); }

.steps { margin: 8px 0; padding-left: 18px; display: flex; flex-direction: column; gap: 6px; font-size: 12.5px; color: rgba(220,252,245,0.75); line-height: 1.55; }
.steps strong { color: #ECFEFF; }
.steps .link { color: #67E8F9; }

.cheat { display: flex; flex-direction: column; gap: 8px; margin: 6px 0 12px; }
.cheat__row { display: flex; align-items: center; gap: 12px; padding: 10px 12px; border-radius: 10px; cursor: pointer; border: 0.5px solid rgba(251,146,60,0.22); background: rgba(8,30,38,0.5); transition: all .15s ease; }
.cheat__row:hover { border-color: #FB923C; background: rgba(251,146,60,0.06); }
.cheat__row.copied { border-color: #FB923C; background: rgba(251,146,60,0.16); }
.cheat__row--important { border-left: 3px solid #FBBF24; }
.cheat__field { flex: 1; display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.cheat__label { font-family: 'JetBrains Mono', monospace; font-size: 9.5px; letter-spacing: 1.2px; text-transform: uppercase; color: rgba(167,243,208,0.55); }
.cheat__value { font-family: 'JetBrains Mono', monospace; font-size: 12.5px; color: #ECFEFF; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.cheat__copy { flex-shrink: 0; padding: 5px 10px; border-radius: 999px; background: rgba(251,146,60,0.14); border: 0.5px solid rgba(251,146,60,0.35); color: #FB923C; font-family: 'JetBrains Mono', monospace; font-size: 9.5px; letter-spacing: 1.2px; text-transform: uppercase; }
.cheat__row.copied .cheat__copy { background: #FB923C; color: #02060A; }
.star { color: #FBBF24; }

.form { display: flex; flex-direction: column; gap: 10px; }
.form label { display: flex; flex-direction: column; gap: 4px; }
.label { font-family: 'JetBrains Mono', monospace; font-size: 9.5px; letter-spacing: 1.4px; text-transform: uppercase; color: rgba(167,243,208,0.5); }
.input { width: 100%; padding: 11px 14px; border-radius: 10px; border: 0.5px solid rgba(94,234,212,0.22); background: rgba(2,6,10,0.55); color: #ECFEFF; font-family: 'JetBrains Mono', monospace; font-size: 12px; }
.input:focus { outline: none; border-color: #5EEAD4; box-shadow: 0 0 18px rgba(94,234,212,0.18); }
.error { margin: 0; font-size: 12px; color: #FCA5A5; border-left: 2px solid #F87171; padding-left: 9px; }
</style>
