export interface OlwenTask {
  id: string
  list_id: string
  list_name: string
  text: string
  priority: 'high' | 'med' | 'low' | string
  done: boolean
  created_at: string
}

export interface OlwenList {
  id: string
  name: string
}

export interface ReviewTask {
  id: string
  text: string
  priority: string
  list_name: string
  suggestion: string
}

export interface ReviewResult {
  tasks: ReviewTask[]
  start_index: number
  start_reason: string
}

/**
 * Shared tasks store — lists + tasks with real CRUD. State is shared (useState)
 * so the dashboard HUD and the Tasks widget stay in sync. Errors are surfaced
 * (not swallowed) so failures are visible.
 */
export function useTasks() {
  const apiBase = useRuntimeConfig().public.apiBase as string
  function h(): Record<string, string> {
    const t = import.meta.client ? localStorage.getItem('olwen_access') : null
    return t ? { Authorization: `Bearer ${t}` } : {}
  }

  const tasks = useState<OlwenTask[]>('olwen:tasks', () => [])
  const lists = useState<OlwenList[]>('olwen:lists', () => [])
  const error = useState<string>('olwen:tasksError', () => '')
  const loading = useState<boolean>('olwen:tasksLoading', () => false)

  function detail(e: unknown, fallback: string): string {
    return (e as { data?: { detail?: string } })?.data?.detail || fallback
  }

  async function load(): Promise<void> {
    loading.value = true
    error.value = ''
    try {
      const [t, l] = await Promise.all([
        $fetch<OlwenTask[]>(`${apiBase}/api/tasks`, { headers: h() }),
        $fetch<OlwenList[]>(`${apiBase}/api/tasks/lists`, { headers: h() }),
      ])
      tasks.value = t
      lists.value = l
    } catch (e) {
      error.value = detail(e, 'Could not load tasks.')
    } finally {
      loading.value = false
    }
  }

  async function add(listId: string, text: string, priority = 'med'): Promise<void> {
    error.value = ''
    try {
      await $fetch(`${apiBase}/api/tasks`, {
        method: 'POST', headers: h(), body: { list_id: listId, text, priority },
      })
      await load()
    } catch (e) {
      error.value = detail(e, 'Could not add task.')
    }
  }

  async function toggle(t: OlwenTask): Promise<void> {
    error.value = ''
    try {
      await $fetch(`${apiBase}/api/tasks/${t.id}`, {
        method: 'PATCH', headers: h(), body: { done: !t.done },
      })
      await load()
    } catch (e) {
      error.value = detail(e, 'Could not update task.')
    }
  }

  async function remove(t: OlwenTask): Promise<void> {
    error.value = ''
    try {
      await $fetch(`${apiBase}/api/tasks/${t.id}`, { method: 'DELETE', headers: h() })
      await load()
    } catch (e) {
      error.value = detail(e, 'Could not delete task.')
    }
  }

  async function review(): Promise<ReviewResult> {
    return await $fetch<ReviewResult>(`${apiBase}/api/tasks/review`, {
      method: 'POST', headers: h(),
    })
  }

  return { tasks, lists, error, loading, load, add, toggle, remove, review }
}
