<script setup lang="ts">
import { computed, ref } from 'vue'
import OlwenEntity from './OlwenEntity.vue'

const { login, register, verifyEmail, resendOtp } = useAuth()

type Mode = 'login' | 'register' | 'verify'
const mode = ref<Mode>('login')

const email = ref('')
const password = ref('')
const displayName = ref('')
const code = ref('')
const devCode = ref<string | null>(null) // shown only in dev console mode
const loading = ref(false)
const error = ref('')
const notice = ref('')

const isRegister = computed(() => mode.value === 'register')
const isVerify = computed(() => mode.value === 'verify')
const entityState = computed(() => (loading.value ? 'thinking' : 'idle'))

function setMode(m: Mode) {
  mode.value = m
  error.value = ''
  notice.value = ''
}

function pickError(e: unknown): string {
  const detail = (e as { data?: { detail?: string } })?.data?.detail
  return detail || 'Something went wrong. Is the backend running?'
}

async function submitAuth() {
  if (loading.value) return
  error.value = ''
  if (!email.value || !password.value) {
    error.value = 'Email and password are required.'
    return
  }
  if (isRegister.value && password.value.length < 8) {
    error.value = 'Password must be at least 8 characters.'
    return
  }
  loading.value = true
  try {
    if (isRegister.value) {
      const res = await register(email.value, password.value, displayName.value || undefined)
      devCode.value = res.dev_code
      notice.value = res.message
      setMode('verify')
      notice.value = res.message
    } else {
      await login(email.value, password.value)
      // success → app swaps to dashboard
    }
  } catch (e: unknown) {
    const status = (e as { status?: number; statusCode?: number })?.status
      ?? (e as { statusCode?: number })?.statusCode
    if (!isRegister.value && status === 403) {
      // Email not verified — send a fresh code and go to verify step.
      try {
        const r = await resendOtp(email.value)
        devCode.value = r.dev_code
      } catch { /* ignore */ }
      notice.value = 'Please verify your email first — we sent a code.'
      setMode('verify')
      notice.value = 'Please verify your email first — we sent a code.'
    } else {
      error.value = pickError(e)
    }
  } finally {
    loading.value = false
  }
}

async function submitVerify() {
  if (loading.value) return
  error.value = ''
  if (code.value.trim().length < 4) {
    error.value = 'Enter the code from your email.'
    return
  }
  loading.value = true
  try {
    await verifyEmail(email.value, code.value.trim())
    // success → app swaps to dashboard
  } catch (e: unknown) {
    error.value = pickError(e)
  } finally {
    loading.value = false
  }
}

async function resend() {
  if (loading.value) return
  error.value = ''
  loading.value = true
  try {
    const r = await resendOtp(email.value)
    devCode.value = r.dev_code
    notice.value = 'A new code was sent.'
  } catch (e: unknown) {
    error.value = pickError(e)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login">
    <div class="login__entity">
      <OlwenEntity :state="entityState" />
    </div>

    <!-- VERIFY step -->
    <form v-if="isVerify" class="card" @submit.prevent="submitVerify">
      <div class="card__head">
        <span class="brand">OLWEN</span>
        <span class="brand__sub">quietly knows everything</span>
      </div>
      <p class="card__title">Verify your email</p>
      <p class="card__hint">We sent a 6-digit code to <b>{{ email }}</b>.</p>

      <p v-if="devCode" class="devcode">
        dev mode — your code is <b>{{ devCode }}</b>
      </p>

      <label class="field">
        <span class="field__label">Verification code</span>
        <input
          v-model="code"
          class="code-input"
          type="text"
          inputmode="numeric"
          maxlength="6"
          autocomplete="one-time-code"
          placeholder="••••••"
        >
      </label>

      <p v-if="error" class="error">{{ error }}</p>

      <button class="submit" type="submit" :disabled="loading">
        {{ loading ? 'Verifying…' : 'Verify & enter' }}
      </button>

      <p class="switch">
        Didn’t get it?
        <button type="button" class="switch__btn" @click="resend">Resend code</button>
        ·
        <button type="button" class="switch__btn" @click="setMode('login')">Back</button>
      </p>
    </form>

    <!-- LOGIN / REGISTER step -->
    <form v-else class="card" @submit.prevent="submitAuth">
      <div class="card__head">
        <span class="brand">OLWEN</span>
        <span class="brand__sub">quietly knows everything</span>
      </div>

      <p class="card__title">
        {{ isRegister ? 'Create your presence' : 'Welcome back' }}
      </p>

      <label v-if="isRegister" class="field">
        <span class="field__label">Name</span>
        <input v-model="displayName" type="text" autocomplete="name" placeholder="Your name">
      </label>

      <label class="field">
        <span class="field__label">Email</span>
        <input v-model="email" type="email" autocomplete="email" placeholder="you@email.com" required>
      </label>

      <label class="field">
        <span class="field__label">Password</span>
        <input
          v-model="password"
          type="password"
          :autocomplete="isRegister ? 'new-password' : 'current-password'"
          placeholder="••••••••"
          required
        >
      </label>

      <p v-if="error" class="error">{{ error }}</p>

      <button class="submit" type="submit" :disabled="loading">
        {{ loading ? 'Awakening…' : (isRegister ? 'Create account' : 'Enter') }}
      </button>

      <p class="switch">
        {{ isRegister ? 'Already have an account?' : 'New here?' }}
        <button type="button" class="switch__btn" @click="setMode(isRegister ? 'login' : 'register')">
          {{ isRegister ? 'Sign in' : 'Create one' }}
        </button>
      </p>
    </form>
  </div>
</template>

<style scoped>
.login {
  position: relative;
  z-index: 1;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 24px;
}
.login__entity { width: 200px; height: 200px; margin-bottom: -10px; }

.card {
  width: min(380px, 92%);
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 28px;
  border-radius: 16px;
  border: 0.5px solid var(--border-strong);
  background: var(--surface-2);
  backdrop-filter: blur(14px);
}
.card__head { display: flex; align-items: baseline; gap: 10px; justify-content: center; }
.brand {
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  letter-spacing: 4px; font-size: 16px; color: var(--accent);
}
.brand__sub { font-size: 10px; letter-spacing: 1.5px; color: var(--text-muted); }
.card__title {
  margin: 2px 0 0; text-align: center;
  font-size: 18px; font-weight: 300; color: var(--text-strong);
}
.card__hint { margin: 0; text-align: center; font-size: 12px; color: var(--text-muted); }
.card__hint b { color: var(--accent-2); font-weight: 500; }

.devcode {
  margin: 0; text-align: center; font-size: 11px;
  font-family: 'JetBrains Mono', monospace; color: #FBBF24;
  border: 0.5px dashed rgba(251, 191, 36, 0.4); border-radius: 8px; padding: 7px;
}
.devcode b { letter-spacing: 3px; }

.field { display: flex; flex-direction: column; gap: 5px; }
.field__label {
  font-family: 'JetBrains Mono', monospace;
  font-size: 9px; letter-spacing: 1.6px; text-transform: uppercase;
  color: var(--text-muted);
}
.field input {
  padding: 11px 13px; border-radius: 9px;
  border: 0.5px solid var(--border-strong);
  background: color-mix(in srgb, var(--bg) 40%, transparent);
  color: var(--text); font-size: 14px; outline: none;
  transition: border-color .2s ease;
}
.field input:focus { border-color: var(--accent); }
.field input::placeholder { color: var(--text-muted); }
.code-input {
  text-align: center; letter-spacing: 10px; font-size: 22px;
  font-family: 'JetBrains Mono', monospace;
}

.error {
  margin: 0; font-size: 12px; color: #FCA5A5;
  border-left: 2px solid #F87171; padding-left: 10px;
}

.submit {
  margin-top: 4px; padding: 12px; border-radius: 9px; cursor: pointer;
  border: 0.5px solid var(--accent);
  background: var(--border-strong); color: var(--text-strong);
  font-size: 13px; letter-spacing: 1.5px; text-transform: uppercase;
  transition: all .2s ease;
}
.submit:hover:not(:disabled) { background: var(--border-strong); box-shadow: 0 0 18px rgba(94, 234, 212, 0.25); }
.submit:disabled { opacity: 0.6; cursor: progress; }

.switch { margin: 4px 0 0; text-align: center; font-size: 12px; color: var(--text-muted); }
.switch__btn {
  border: none; background: transparent; cursor: pointer;
  color: var(--accent); font-size: 12px; text-decoration: underline; padding: 0 2px;
}
</style>
