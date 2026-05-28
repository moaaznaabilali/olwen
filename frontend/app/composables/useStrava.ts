export interface StravaActivity {
  id: string
  name: string
  type: string
  sport_type: string
  distance_km: number
  duration_min: number
  moving_pace: string
  elevation_gain_m: number
  average_heartrate: number | null
  start_date: string
}
export interface StravaAccount {
  connected: boolean
  athlete_name?: string
  avatar_url?: string
}

export function useStrava() {
  const apiBase = useRuntimeConfig().public.apiBase as string
  function h(): Record<string, string> {
    const t = import.meta.client ? localStorage.getItem('olwen_access') : null
    return t ? { Authorization: `Bearer ${t}` } : {}
  }

  const configured = () =>
    $fetch<{ configured: boolean; redirect_uri: string }>(`${apiBase}/api/strava/configured`, { headers: h() })
  const account    = () => $fetch<StravaAccount>(`${apiBase}/api/strava/account`, { headers: h() })
  const start      = () => $fetch<{ auth_url: string }>(`${apiBase}/api/strava/oauth/start`, { headers: h() })
  const setup      = (client_id: string, client_secret: string) =>
    $fetch<{ ok: boolean }>(`${apiBase}/api/strava/oauth/setup`, {
      method: 'POST', headers: h(), body: { client_id, client_secret },
    })
  const disconnect = () => $fetch(`${apiBase}/api/strava/account`, { method: 'DELETE', headers: h() })
  const activities = (limit = 8) =>
    $fetch<{ athlete: string; activities: StravaActivity[] }>(`${apiBase}/api/strava/activities`, { headers: h(), query: { limit } })

  return { configured, account, start, setup, disconnect, activities }
}
