export type ThemeName = 'dark' | 'light'

/**
 * Theme store — flips a small set of semantic CSS variables (see app.vue) by
 * setting `data-theme` on <html>. Persisted to localStorage so it survives
 * reloads. Dark is the default; light is a real, designed palette (not invert).
 */
export function useTheme() {
  const theme = useState<ThemeName>('olwen:theme', () => 'dark')

  function apply(t: ThemeName): void {
    if (import.meta.client) document.documentElement.setAttribute('data-theme', t)
  }

  function init(): void {
    if (!import.meta.client) return
    const saved = localStorage.getItem('olwen_theme') as ThemeName | null
    theme.value = saved === 'light' || saved === 'dark' ? saved : 'dark'
    apply(theme.value)
  }

  function toggle(): void {
    theme.value = theme.value === 'dark' ? 'light' : 'dark'
    if (import.meta.client) localStorage.setItem('olwen_theme', theme.value)
    apply(theme.value)
  }

  return { theme, init, toggle }
}
