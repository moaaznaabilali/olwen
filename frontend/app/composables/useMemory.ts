export interface OlwenMemory {
  id: string
  content: string
  created_at: string
}

/** What Olwen remembers about the user. */
export function useMemory() {
  const apiBase = useRuntimeConfig().public.apiBase as string
  function h(): Record<string, string> {
    const t = import.meta.client ? localStorage.getItem('olwen_access') : null
    return t ? { Authorization: `Bearer ${t}` } : {}
  }

  const list = () => $fetch<OlwenMemory[]>(`${apiBase}/api/memory`, { headers: h() })
  const add = (content: string) =>
    $fetch<OlwenMemory>(`${apiBase}/api/memory`, { method: 'POST', headers: h(), body: { content } })
  const remove = (id: string) =>
    $fetch(`${apiBase}/api/memory/${id}`, { method: 'DELETE', headers: h() })

  return { list, add, remove }
}
