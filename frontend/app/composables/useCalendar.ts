export interface CalEvent {
  id: string
  title: string
  start: string                   // ISO datetime or date (all-day)
  end: string
  location: string
  url: string
}

export function useCalendar() {
  const apiBase = useRuntimeConfig().public.apiBase as string
  function h(): Record<string, string> {
    const t = import.meta.client ? localStorage.getItem('olwen_access') : null
    return t ? { Authorization: `Bearer ${t}` } : {}
  }

  const configured = () => $fetch<{
    connected: boolean
    has_gmail_imap: boolean
    server_oauth_ready: boolean
    needs: 'none' | 'connect_google' | 'switch_to_oauth' | 'setup_server_oauth' | 'reconsent'
  }>(`${apiBase}/api/calendar/configured`, { headers: h() })
  const events     = (hours = 36, limit = 10) =>
    $fetch<{ events: CalEvent[] }>(`${apiBase}/api/calendar/events`, { headers: h(), query: { hours, limit } })

  return { configured, events }
}
