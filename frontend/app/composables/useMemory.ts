export type MemType = 'semantic' | 'episodic' | 'procedural'
export type MemSource = 'user_explicit' | 'extracted'

export interface OlwenMemory {
  id: string
  content: string
  mem_type: MemType
  importance: number
  subject: string | null
  source: MemSource
  superseded_by: string | null
  access_count: number
  last_accessed: string | null
  created_at: string
}

/** What Olwen remembers about the user — its professional memory system. */
export function useMemory() {
  const apiBase = useRuntimeConfig().public.apiBase as string
  function h(): Record<string, string> {
    const t = import.meta.client ? localStorage.getItem('olwen_access') : null
    return t ? { Authorization: `Bearer ${t}` } : {}
  }

  const list = (includeArchived = false) =>
    $fetch<OlwenMemory[]>(`${apiBase}/api/memory`, {
      headers: h(),
      query: { include_archived: includeArchived },
    })

  const search = (q: string) =>
    $fetch<OlwenMemory[]>(`${apiBase}/api/memory/search`, {
      headers: h(),
      query: { q, include_archived: true },
    })

  const add = (
    content: string,
    opts?: { mem_type?: string; subject?: string; importance?: number },
  ) =>
    $fetch<OlwenMemory>(`${apiBase}/api/memory`, {
      method: 'POST',
      headers: h(),
      body: { content, ...opts },
    })

  const remove = (id: string) =>
    $fetch(`${apiBase}/api/memory/${id}`, { method: 'DELETE', headers: h() })

  return { list, search, add, remove }
}
