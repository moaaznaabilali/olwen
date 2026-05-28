import { computed } from 'vue'

export interface OlwenUser {
  id: string
  email: string
  display_name: string | null
  is_active: boolean
  created_at: string
}

interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
}

export interface RegisterResult {
  message: string
  email: string
  dev_code: string | null
}

const ACCESS_KEY = 'olwen_access'
const REFRESH_KEY = 'olwen_refresh'

/**
 * Auth state + actions, backed by the FastAPI account system.
 *
 * Tokens are stored in localStorage (demo-first choice — simple, but exposed to
 * XSS). If we harden later, switch to httpOnly cookies + CSRF on the backend.
 */
export function useAuth() {
  const apiBase = useRuntimeConfig().public.apiBase as string

  // SSR-safe shared state (survives across components in one request/app).
  const user = useState<OlwenUser | null>('auth:user', () => null)
  const accessToken = useState<string | null>('auth:access', () => null)
  const ready = useState<boolean>('auth:ready', () => false)

  const isAuthenticated = computed(() => user.value !== null)

  function setTokens(access: string, refresh: string) {
    accessToken.value = access
    if (import.meta.client) {
      localStorage.setItem(ACCESS_KEY, access)
      localStorage.setItem(REFRESH_KEY, refresh)
    }
  }

  function clear() {
    accessToken.value = null
    user.value = null
    if (import.meta.client) {
      localStorage.removeItem(ACCESS_KEY)
      localStorage.removeItem(REFRESH_KEY)
    }
  }

  async function fetchMe(): Promise<boolean> {
    if (!accessToken.value) return false
    try {
      user.value = await $fetch<OlwenUser>(`${apiBase}/api/users/me`, {
        headers: { Authorization: `Bearer ${accessToken.value}` },
      })
      return true
    } catch {
      clear()
      return false
    }
  }

  async function login(email: string, password: string): Promise<void> {
    // Backend uses the OAuth2 form: "username" carries the email.
    const body = new URLSearchParams({ username: email, password })
    const res = await $fetch<TokenResponse>(`${apiBase}/api/auth/login`, {
      method: 'POST',
      body,
    })
    setTokens(res.access_token, res.refresh_token)
    await fetchMe()
  }

  async function register(
    email: string,
    password: string,
    displayName?: string,
  ): Promise<RegisterResult> {
    // Returns a verification prompt (NOT tokens) — user must verify email next.
    return await $fetch<RegisterResult>(`${apiBase}/api/auth/register`, {
      method: 'POST',
      body: { email, password, display_name: displayName || null },
    })
  }

  async function verifyEmail(email: string, code: string): Promise<void> {
    const res = await $fetch<TokenResponse>(`${apiBase}/api/auth/verify-email`, {
      method: 'POST',
      body: { email, code },
    })
    setTokens(res.access_token, res.refresh_token)
    await fetchMe()
  }

  async function resendOtp(email: string): Promise<{ message: string; dev_code: string | null }> {
    return await $fetch(`${apiBase}/api/auth/resend-otp`, {
      method: 'POST',
      body: { email },
    })
  }

  function logout(): void {
    clear()
  }

  /** Restore session from localStorage on first client load. */
  async function init(): Promise<void> {
    if (!import.meta.client || ready.value) return
    accessToken.value = localStorage.getItem(ACCESS_KEY)
    if (accessToken.value) await fetchMe()
    ready.value = true
  }

  return {
    user, isAuthenticated, ready,
    login, register, verifyEmail, resendOtp, logout, fetchMe, init,
  }
}
