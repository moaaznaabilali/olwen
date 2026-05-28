export interface EmailAccount {
  id: string
  email: string
  imap_host: string | null
  smtp_host: string | null
  provider: 'imap' | 'google' | string
  created_at: string
}

export interface EmailMessage {
  uid: string
  sender: string
  subject: string
  snippet: string
  date: string
  unread: boolean
}

export interface TriagedEmail extends EmailMessage {
  priority: 'high' | 'med' | 'low' | string
  suggestion: string
}

export interface FullEmail {
  uid: string
  sender: string
  subject: string
  body: string
  date: string
  unread: boolean
}

export interface EmailAction {
  label: string
  kind: 'open_url' | 'reply' | 'reminder' | 'task' | string
  payload: string
  description: string
}

export interface SummaryResponse {
  uid: string
  summary: string
  actions: EmailAction[]
}

/** Universal email (IMAP/SMTP) — Gmail, Outlook/Hotmail, Yahoo, iCloud, custom. */
export function useEmail() {
  const apiBase = useRuntimeConfig().public.apiBase as string
  function h(): Record<string, string> {
    const t = import.meta.client ? localStorage.getItem('olwen_access') : null
    return t ? { Authorization: `Bearer ${t}` } : {}
  }

  const accounts = () => $fetch<EmailAccount[]>(`${apiBase}/api/email/accounts`, { headers: h() })
  const connect = (body: {
    email: string; password: string;
    imap_host?: string; imap_port?: number; smtp_host?: string; smtp_port?: number;
  }) => $fetch<EmailAccount>(`${apiBase}/api/email/accounts`, { method: 'POST', headers: h(), body })
  const disconnect = (id: string) =>
    $fetch(`${apiBase}/api/email/accounts/${id}`, { method: 'DELETE', headers: h() })
  const inbox = (limit = 12) =>
    $fetch<EmailMessage[]>(`${apiBase}/api/email/inbox`, { headers: h(), query: { limit } })
  const triage = (limit = 10) =>
    $fetch<{ emails: TriagedEmail[] }>(`${apiBase}/api/email/triage`, { method: 'POST', headers: h(), query: { limit } })
  const oauthConfigured = () =>
    $fetch<{ configured: boolean; redirect_uri: string }>(`${apiBase}/api/email/oauth/google/configured`)
  const oauthSetup = (client_id: string, client_secret: string) =>
    $fetch<{ ok: boolean }>(`${apiBase}/api/email/oauth/google/setup`, {
      method: 'POST', headers: h(), body: { client_id, client_secret },
    })
  const oauthStart = () =>
    $fetch<{ auth_url: string }>(`${apiBase}/api/email/oauth/google/start`, { headers: h() })
  const message = (uid: string) =>
    $fetch<FullEmail>(`${apiBase}/api/email/messages/${encodeURIComponent(uid)}`, { headers: h() })
  const summarize = (uid: string, hints?: { sender?: string; subject?: string; snippet?: string }) =>
    $fetch<SummaryResponse>(
      `${apiBase}/api/email/messages/${encodeURIComponent(uid)}/summarize`,
      { method: 'POST', headers: h(), query: hints || {} },
    )
  const markRead = (uid: string) =>
    $fetch<{ ok: boolean; detail?: string }>(
      `${apiBase}/api/email/messages/${encodeURIComponent(uid)}/mark-read`,
      { method: 'POST', headers: h() },
    )
  const compose = (body: { to: string[]; subject: string; body: string }) =>
    $fetch<{ ok: boolean; message_id: string }>(`${apiBase}/api/email/compose`, {
      method: 'POST', headers: h(), body,
    })
  const reply = (uid: string, body: string) =>
    $fetch<{ ok: boolean; message_id: string }>(
      `${apiBase}/api/email/messages/${encodeURIComponent(uid)}/reply`,
      { method: 'POST', headers: h(), body: { body } },
    )
  const draftReply = (uid: string) =>
    $fetch<{ draft: string; subject: string }>(
      `${apiBase}/api/email/messages/${encodeURIComponent(uid)}/draft-reply`,
      { method: 'POST', headers: h() },
    )

  return {
    accounts, connect, disconnect, inbox, triage,
    oauthConfigured, oauthSetup, oauthStart,
    message, summarize, markRead,
    compose, reply, draftReply,
  }
}
