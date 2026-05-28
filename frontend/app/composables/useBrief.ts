export interface BriefTask { text: string; priority: 'high' | 'med' | 'low' | string }
export interface BriefEvent { id: string; title: string; start: string; end: string; location: string; url: string }
export interface BriefInboxItem { uid: string; sender: string; subject: string; snippet?: string; date?: string; unread?: boolean }
export interface BriefNewsItem { title: string; source: string; url: string; published: string; tag: string }
export interface BriefWeather { now_c: number; high_c: number; low_c: number; code: number }

export interface Brief {
  narrative: string
  weather: BriefWeather | null
  calendar: BriefEvent[]
  tasks: BriefTask[]
  inbox: BriefInboxItem[]
  news: BriefNewsItem[]
  generated_at: string
}

export function useBrief() {
  const apiBase = useRuntimeConfig().public.apiBase as string
  function h(): Record<string, string> {
    const t = import.meta.client ? localStorage.getItem('olwen_access') : null
    return t ? { Authorization: `Bearer ${t}` } : {}
  }

  const today = () => $fetch<Brief>(`${apiBase}/api/brief/today`, { headers: h() })
  const shouldShow = () => $fetch<{ show: boolean; reason?: string }>(`${apiBase}/api/brief/should-show`, { headers: h() })
  const markSeen = () => $fetch<{ ok: boolean }>(`${apiBase}/api/brief/today/seen`, { method: 'POST', headers: h() })
  const updatePrefs = (body: { enabled?: boolean; time?: string }) =>
    $fetch<{ enabled: boolean; time: string }>(`${apiBase}/api/brief/prefs`, { method: 'PUT', headers: h(), body })

  return { today, shouldShow, markSeen, updatePrefs }
}
