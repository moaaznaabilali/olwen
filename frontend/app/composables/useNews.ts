export interface NewsTopic { key: string; label: string; feed_count: number }
export interface NewsItem {
  title: string
  source: string
  url: string
  published: string
  tag: string
}

export function useNews() {
  const apiBase = useRuntimeConfig().public.apiBase as string
  function h(): Record<string, string> {
    const t = import.meta.client ? localStorage.getItem('olwen_access') : null
    return t ? { Authorization: `Bearer ${t}` } : {}
  }

  const topics = () => $fetch<{ topics: NewsTopic[] }>(`${apiBase}/api/news/topics`)
  const feed = (limit = 12) =>
    $fetch<{ topics: string[]; items: NewsItem[] }>(`${apiBase}/api/news/feed`, { headers: h(), query: { limit } })
  const brief = () =>
    $fetch<{ narrative: string; items: (NewsItem & { why: string })[]; topics: string[] }>(
      `${apiBase}/api/news/brief`, { headers: h() },
    )

  return { topics, feed, brief }
}
