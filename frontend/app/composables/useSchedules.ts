export type ScheduleKind = 'daily' | 'cron'
export type NotifyChannel = 'inapp' | 'email' | 'telegram' | 'both'
export type LastStatus = 'ok' | 'error' | 'skipped' | 'running' | null

/** The `action` object stored on a schedule. Discriminated by `type`. */
export interface ScheduleAction {
  type: 'morning_brief' | 'read_news' | 'reminder' | 'send_email' | 'agent_goal'
  // reminder
  text?: string
  // send_email
  subject?: string
  body?: string
  prompt?: string
  to?: string[]
  // agent_goal
  goal?: string
}

export interface OlwenSchedule {
  id: string
  name: string
  action: ScheduleAction
  schedule_kind: ScheduleKind
  cron_expr: string
  daily_time: string | null
  tz: string
  notify_channel: NotifyChannel
  enabled: boolean
  next_run: string | null
  last_run: string | null
  last_status: LastStatus
  last_error: string | null
  last_output: string | null
  last_duration_ms: number | null
  created_at: string
}

/** Payload for create/update. All fields optional on PATCH. */
export interface SchedulePayload {
  name?: string
  action?: ScheduleAction
  schedule_kind?: ScheduleKind
  daily_time?: string | null
  cron_expr?: string
  tz?: string
  notify_channel?: NotifyChannel
  enabled?: boolean
}

/**
 * Shared schedules store — user-configurable scheduled automations with real
 * CRUD. State is shared (useState) so the board and any HUD surface stay in
 * sync. Errors are surfaced (not swallowed) so failures are visible.
 */
export function useSchedules() {
  const apiBase = useRuntimeConfig().public.apiBase as string
  function h(): Record<string, string> {
    const t = import.meta.client ? localStorage.getItem('olwen_access') : null
    return t ? { Authorization: `Bearer ${t}` } : {}
  }

  const schedules = useState<OlwenSchedule[]>('olwen:schedules', () => [])
  const error = useState<string>('olwen:schedulesError', () => '')
  const loading = useState<boolean>('olwen:schedulesLoading', () => false)

  function detail(e: unknown, fallback: string): string {
    return (e as { data?: { detail?: string } })?.data?.detail || fallback
  }

  // Replace one schedule in the shared list (or append if new).
  function upsert(s: OlwenSchedule): void {
    const i = schedules.value.findIndex(x => x.id === s.id)
    if (i === -1) schedules.value = [...schedules.value, s]
    else schedules.value = schedules.value.map(x => (x.id === s.id ? s : x))
  }

  async function load(): Promise<void> {
    loading.value = true
    error.value = ''
    try {
      schedules.value = await $fetch<OlwenSchedule[]>(`${apiBase}/api/schedules`, { headers: h() })
    } catch (e) {
      error.value = detail(e, 'Could not load automations.')
    } finally {
      loading.value = false
    }
  }

  async function create(payload: SchedulePayload): Promise<OlwenSchedule | null> {
    error.value = ''
    try {
      const s = await $fetch<OlwenSchedule>(`${apiBase}/api/schedules`, {
        method: 'POST', headers: h(), body: payload,
      })
      upsert(s)
      return s
    } catch (e) {
      error.value = detail(e, 'Could not create automation.')
      return null
    }
  }

  async function update(id: string, payload: SchedulePayload): Promise<OlwenSchedule | null> {
    error.value = ''
    try {
      const s = await $fetch<OlwenSchedule>(`${apiBase}/api/schedules/${id}`, {
        method: 'PATCH', headers: h(), body: payload,
      })
      upsert(s)
      return s
    } catch (e) {
      error.value = detail(e, 'Could not update automation.')
      return null
    }
  }

  async function toggle(id: string): Promise<OlwenSchedule | null> {
    error.value = ''
    try {
      const s = await $fetch<OlwenSchedule>(`${apiBase}/api/schedules/${id}/toggle`, {
        method: 'POST', headers: h(),
      })
      upsert(s)
      return s
    } catch (e) {
      error.value = detail(e, 'Could not toggle automation.')
      return null
    }
  }

  async function runNow(id: string): Promise<OlwenSchedule | null> {
    error.value = ''
    try {
      const s = await $fetch<OlwenSchedule>(`${apiBase}/api/schedules/${id}/run-now`, {
        method: 'POST', headers: h(),
      })
      upsert(s)
      return s
    } catch (e) {
      error.value = detail(e, 'Could not run automation.')
      return null
    }
  }

  async function remove(id: string): Promise<void> {
    error.value = ''
    try {
      await $fetch(`${apiBase}/api/schedules/${id}`, { method: 'DELETE', headers: h() })
      schedules.value = schedules.value.filter(s => s.id !== id)
    } catch (e) {
      error.value = detail(e, 'Could not delete automation.')
    }
  }

  return { schedules, error, loading, load, create, update, toggle, runNow, remove }
}
