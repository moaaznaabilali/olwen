export interface GhEvent {
  kind: 'push' | 'pr' | 'issue' | 'create' | string
  repo: string
  msg: string
  when: string
}

export interface GhAccount {
  connected: boolean
  login?: string
  avatar_url?: string
}

export function useGithub() {
  const apiBase = useRuntimeConfig().public.apiBase as string
  function h(): Record<string, string> {
    const t = import.meta.client ? localStorage.getItem('olwen_access') : null
    return t ? { Authorization: `Bearer ${t}` } : {}
  }

  const configured = () =>
    $fetch<{ configured: boolean; oauth_configured: boolean; pat_supported: boolean; redirect_uri: string }>(
      `${apiBase}/api/github/configured`,
      { headers: h() },
    )
  const oauthSetup = (client_id: string, client_secret: string) =>
    $fetch<{ ok: boolean }>(`${apiBase}/api/github/oauth/setup`, {
      method: 'POST', headers: h(), body: { client_id, client_secret },
    })
  const account    = () => $fetch<GhAccount>(`${apiBase}/api/github/account`, { headers: h() })
  const start      = () => $fetch<{ auth_url: string }>(`${apiBase}/api/github/oauth/start`, { headers: h() })
  const disconnect = () => $fetch(`${apiBase}/api/github/account`, { method: 'DELETE', headers: h() })
  const connectPat = (token: string) =>
    $fetch<{ ok: boolean; login: string }>(`${apiBase}/api/github/pat`, {
      method: 'POST', headers: h(), body: { token },
    })
  const events     = (limit = 8) =>
    $fetch<{ login: string; events: GhEvent[] }>(`${apiBase}/api/github/events`, { headers: h(), query: { limit } })

  return { configured, account, start, disconnect, connectPat, events, oauthSetup }
}
