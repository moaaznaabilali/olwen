export interface OlwenNotification {
  id: string
  kind: string // telegram | whatsapp | email | system
  title: string
  body: string | null
  meta: Record<string, unknown>
  read: boolean
  created_at: string | null
}

/**
 * Live notification hub. Connects to the backend SSE stream via fetch-streaming
 * (so we can send the auth header), keeps a shared list + unread count, and
 * queues fresh arrivals as `toasts` for the on-screen popups. State is useState
 * so the bell and the toast layer stay in sync.
 */
export function useNotifications() {
  const apiBase = useRuntimeConfig().public.apiBase as string
  const items = useState<OlwenNotification[]>('olwen:notifs', () => [])
  const unread = useState<number>('olwen:notifs:unread', () => 0)
  const connected = useState<boolean>('olwen:notifs:connected', () => false)
  const toasts = useState<OlwenNotification[]>('olwen:notifs:toasts', () => [])
  const started = useState<boolean>('olwen:notifs:started', () => false)
  // bumps on every live arrival — the creature watches this to play a "receive"
  // ripple (Olwen's whole idea is the visual process: it SHOWS that it felt it).
  const arrivals = useState<number>('olwen:notifs:arrivals', () => 0)
  const lastKind = useState<string>('olwen:notifs:lastkind', () => '')

  function authToken(): string | null {
    return import.meta.client ? localStorage.getItem('olwen_access') : null
  }
  function h(): Record<string, string> {
    const t = authToken()
    return t ? { Authorization: `Bearer ${t}` } : {}
  }
  const sleep = (ms: number) => new Promise(r => setTimeout(r, ms))

  async function load(): Promise<void> {
    try {
      const d = await $fetch<{ unread: number; items: OlwenNotification[] }>(
        `${apiBase}/api/notifications`, { headers: h() },
      )
      items.value = d.items
      unread.value = d.unread
    } catch { /* offline — the stream will catch up */ }
  }

  function ingest(n: OlwenNotification): void {
    if (items.value.some(x => x.id === n.id)) return
    items.value = [n, ...items.value].slice(0, 60)
    if (!n.read) unread.value++
    toasts.value = [...toasts.value, n]
    arrivals.value++
    lastKind.value = n.kind
  }

  function dismissToast(id: string): void {
    toasts.value = toasts.value.filter(t => t.id !== id)
  }

  async function markRead(id: string): Promise<void> {
    const n = items.value.find(x => x.id === id)
    if (n && !n.read) { n.read = true; unread.value = Math.max(0, unread.value - 1) }
    try { await $fetch(`${apiBase}/api/notifications/${id}/read`, { method: 'POST', headers: h() }) } catch { /* */ }
  }

  async function markAllRead(): Promise<void> {
    items.value.forEach(n => { n.read = true })
    unread.value = 0
    try { await $fetch(`${apiBase}/api/notifications/read-all`, { method: 'POST', headers: h() }) } catch { /* */ }
  }

  async function streamLoop(): Promise<void> {
    while (true) {
      try {
        const res = await fetch(`${apiBase}/api/notifications/stream`, { headers: h() })
        if (!res.ok || !res.body) { await sleep(3000); continue }
        connected.value = true
        const reader = res.body.getReader()
        const dec = new TextDecoder()
        let buf = ''
        for (;;) {
          const { value, done } = await reader.read()
          if (done) break
          buf += dec.decode(value, { stream: true })
          const frames = buf.split('\n\n')
          buf = frames.pop() || ''
          for (const frame of frames) {
            const dataLine = frame.split('\n').find(l => l.startsWith('data:'))
            if (!dataLine) continue
            try {
              const ev = JSON.parse(dataLine.slice(5).trim())
              if (ev.type === 'notification') ingest(ev as OlwenNotification)
            } catch { /* */ }
          }
        }
      } catch { /* network blip */ }
      connected.value = false
      await sleep(3000) // reconnect
    }
  }

  /** Call once (e.g. on dashboard mount). Loads history + opens the live stream. */
  function start(): void {
    if (started.value || !import.meta.client) return
    started.value = true
    load()
    streamLoop()
  }

  return { items, unread, connected, toasts, arrivals, lastKind, start, load, markRead, markAllRead, dismissToast }
}
