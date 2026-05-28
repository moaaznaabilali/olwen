export interface ProviderState {
  connected: boolean
  key_masked: string | null
  model: string
}

export interface VoiceState {
  enabled: boolean
  lang: string
}

export interface WidgetEntry {
  key: string
  name: string
  column: 'left' | 'right' | string
  live: boolean
  description: string
  glyph: string
  color: string
  core: boolean
}

export interface OlwenSettings {
  active_provider: 'claude' | 'gemini' | 'groq' | null
  claude: ProviderState
  gemini: ProviderState
  groq: ProviderState
  voice: VoiceState
  auto_mark_read: boolean
  dashboard_widgets: string[]
  news_topics: string[]
  widget_catalog: WidgetEntry[]
}

export type Provider = 'claude' | 'gemini' | 'groq'

/** Read/update the user's AI provider settings (connect Claude or Gemini). */
export function useSettings() {
  const apiBase = useRuntimeConfig().public.apiBase as string

  function authHeaders(): Record<string, string> {
    const t = import.meta.client ? localStorage.getItem('olwen_access') : null
    return t ? { Authorization: `Bearer ${t}` } : {}
  }

  async function fetchSettings(): Promise<OlwenSettings> {
    return await $fetch<OlwenSettings>(`${apiBase}/api/users/settings`, {
      headers: authHeaders(),
    })
  }

  async function connectProvider(provider: Provider, apiKey: string): Promise<OlwenSettings> {
    return await $fetch<OlwenSettings>(`${apiBase}/api/users/settings/${provider}`, {
      method: 'PUT',
      headers: authHeaders(),
      body: { api_key: apiKey },
    })
  }

  async function disconnectProvider(provider: Provider): Promise<OlwenSettings> {
    return await $fetch<OlwenSettings>(`${apiBase}/api/users/settings/${provider}`, {
      method: 'DELETE',
      headers: authHeaders(),
    })
  }

  async function selectProvider(provider: Provider): Promise<OlwenSettings> {
    return await $fetch<OlwenSettings>(`${apiBase}/api/users/settings`, {
      method: 'PUT',
      headers: authHeaders(),
      body: { provider },
    })
  }

  async function updateVoice(payload: { enabled?: boolean; lang?: string }): Promise<OlwenSettings> {
    return await $fetch<OlwenSettings>(`${apiBase}/api/users/settings/voice`, {
      method: 'PUT',
      headers: authHeaders(),
      body: payload,
    })
  }

  async function updateEmailPrefs(payload: { auto_mark_read?: boolean }): Promise<OlwenSettings> {
    return await $fetch<OlwenSettings>(`${apiBase}/api/users/settings/email`, {
      method: 'PUT',
      headers: authHeaders(),
      body: payload,
    })
  }

  async function updateDashboard(widgets: string[]): Promise<OlwenSettings> {
    return await $fetch<OlwenSettings>(`${apiBase}/api/users/settings/dashboard`, {
      method: 'PUT', headers: authHeaders(), body: { widgets },
    })
  }

  async function updateNews(topics: string[]): Promise<OlwenSettings> {
    return await $fetch<OlwenSettings>(`${apiBase}/api/users/settings/news`, {
      method: 'PUT', headers: authHeaders(), body: { topics },
    })
  }

  return {
    fetchSettings, connectProvider, disconnectProvider, selectProvider,
    updateVoice, updateEmailPrefs, updateDashboard, updateNews,
  }
}
