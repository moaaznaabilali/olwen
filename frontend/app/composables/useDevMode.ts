export interface LocalProject {
  key: string
  name: string
  path: string
  rel: string
  modified: string | null
}
export interface GhProject {
  key: string
  name: string
  full_name: string
  description: string
  language: string
  stars: number
  private: boolean
  pushed_at: string
  url: string
  clone_url: string
  ssh_url: string
}

export function useDevMode() {
  const apiBase = useRuntimeConfig().public.apiBase as string
  function h(): Record<string, string> {
    const t = import.meta.client ? localStorage.getItem('olwen_access') : null
    return t ? { Authorization: `Bearer ${t}` } : {}
  }
  const projects = () => $fetch<{ local: LocalProject[]; github: GhProject[]; home: string }>(
    `${apiBase}/api/devmode/projects`, { headers: h() },
  )

  // Shared state — what's the currently chosen project, and is dev mode showing?
  const active = useState<{ name: string; path: string } | null>('devmode:active', () => null)
  const open = useState<boolean>('devmode:open', () => false)

  return { projects, active, open }
}
