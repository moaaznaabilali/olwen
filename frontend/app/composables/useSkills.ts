export interface CatalogSkill {
  key: string
  name: string
  author: string
  stars: number
  description: string
  category: string
  glyph: string
  color: string
  status: 'ready' | 'available' | string
  core?: boolean
  repo?: string
}

/** Skills marketplace — browse the catalog, install/uninstall. */
export function useSkills() {
  const apiBase = useRuntimeConfig().public.apiBase as string
  function h(): Record<string, string> {
    const t = import.meta.client ? localStorage.getItem('olwen_access') : null
    return t ? { Authorization: `Bearer ${t}` } : {}
  }

  const catalog = () => $fetch<CatalogSkill[]>(`${apiBase}/api/skills/catalog`, { headers: h() })
  const customList = () => $fetch<CustomSkill[]>(`${apiBase}/api/skills/custom`, { headers: h() })
  const addCustom = (body: { name: string, url: string, auth?: string }) =>
    $fetch<CustomSkill>(`${apiBase}/api/skills/custom`, { method: 'POST', headers: h(), body })
  const removeCustom = (id: string) =>
    $fetch(`${apiBase}/api/skills/custom/${id}`, { method: 'DELETE', headers: h() })
  const installed = () =>
    $fetch<{ installed: string[] }>(`${apiBase}/api/skills/installed`, { headers: h() }).then(r => r.installed)
  const install = (key: string) =>
    $fetch<{ installed: string[] }>(`${apiBase}/api/skills/installed/${key}`, { method: 'POST', headers: h() }).then(r => r.installed)
  const uninstall = (key: string) =>
    $fetch<{ installed: string[] }>(`${apiBase}/api/skills/installed/${key}`, { method: 'DELETE', headers: h() }).then(r => r.installed)

  return { catalog, installed, install, uninstall, customList, addCustom, removeCustom }
}

export interface CustomSkill {
  id: string
  name: string
  url: string
  created_at: string
}
