export interface AppEntry {
  key: string
  name: string
  glyph: string
  color: string
  description: string
  live: boolean
}

/** Shared state: which apps are currently open + the dock catalog. */
export function useApps() {
  const apiBase = useRuntimeConfig().public.apiBase as string

  // Persistent across navigation — useState is SSR-safe shared state.
  const open = useState<string[]>('apps:open', () => [])
  const catalog = useState<AppEntry[]>('apps:catalog', () => [])

  async function loadCatalog() {
    try {
      const r = await $fetch<{ apps: AppEntry[] }>(`${apiBase}/api/apps/catalog`)
      catalog.value = r.apps
    } catch { /* */ }
  }

  function launch(key: string) {
    if (!open.value.includes(key)) open.value = [...open.value, key]
  }
  function closeApp(key: string) {
    open.value = open.value.filter(k => k !== key)
  }
  function isOpen(key: string): boolean {
    return open.value.includes(key)
  }

  return { open, catalog, loadCatalog, launch, closeApp, isOpen }
}
