export interface OlwenTask {
  id: string
  list_id: string
  list_name: string
  text: string
  priority: 'high' | 'med' | 'low' | string
  done: boolean
  due_date?: string | null  // ISO date 'YYYY-MM-DD'
  tags?: string[]
  created_at: string
}

export interface OlwenList {
  id: string
  name: string
  position?: number
  pos_x?: number | null  // free-canvas position
  pos_y?: number | null
  width?: number | null  // resizable list width (px)
  collapsed?: boolean    // minimized to header
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

  async function update(
    t: OlwenTask,
    fields: { text?: string; priority?: string; done?: boolean; list_id?: string; due_date?: string | null; tags?: string[]; clear_due?: boolean },
  ): Promise<void> {
    error.value = ''
    try {
      await $fetch(`${apiBase}/api/tasks/${t.id}`, { method: 'PATCH', headers: h(), body: fields })
      await load()
    } catch (e) {
      error.value = detail(e, 'Could not update task.')
    }
  }

  // Move a task to another list. Optimistic: flip locally first so the drag feels instant.
  async function moveTask(t: OlwenTask, listId: string): Promise<void> {
    if (t.list_id === listId) return
    const prev = t.list_id
    const found = tasks.value.find(x => x.id === t.id)
    if (found) found.list_id = listId
    error.value = ''
    try {
      await $fetch(`${apiBase}/api/tasks/${t.id}`, {
        method: 'PATCH', headers: h(), body: { list_id: listId },
      })
      await load()
    } catch (e) {
      if (found) found.list_id = prev
      error.value = detail(e, 'Could not move task.')
    }
  }

  async function addList(name: string): Promise<void> {
    error.value = ''
    try {
      await $fetch(`${apiBase}/api/tasks/lists`, { method: 'POST', headers: h(), body: { name } })
      await load()
    } catch (e) {
      error.value = detail(e, 'Could not add list.')
    }
  }

  async function renameList(id: string, name: string): Promise<void> {
    error.value = ''
    try {
      await $fetch(`${apiBase}/api/tasks/lists/${id}`, { method: 'PATCH', headers: h(), body: { name } })
      await load()
    } catch (e) {
      error.value = detail(e, 'Could not rename list.')
    }
  }

  // Persist a list's free-canvas position. Optimistic: update local first.
  async function moveListTo(id: string, x: number, y: number): Promise<void> {
    const px = Math.round(x), py = Math.round(y)
    const l = lists.value.find(z => z.id === id)
    if (l) { l.pos_x = px; l.pos_y = py }
    try {
      await $fetch(`${apiBase}/api/tasks/lists/${id}`, { method: 'PATCH', headers: h(), body: { pos_x: px, pos_y: py } })
    } catch (e) {
      error.value = detail(e, 'Could not move list.')
    }
  }

  // Persist a list's width (window-style resize). Optimistic.
  async function resizeList(id: string, width: number): Promise<void> {
    const w = Math.round(width)
    const l = lists.value.find(z => z.id === id)
    if (l) l.width = w
    try {
      await $fetch(`${apiBase}/api/tasks/lists/${id}`, { method: 'PATCH', headers: h(), body: { width: w } })
    } catch (e) {
      error.value = detail(e, 'Could not resize list.')
    }
  }

  // Minimize/restore a list (collapsed = header only). Optimistic.
  async function setCollapsed(id: string, collapsed: boolean): Promise<void> {
    const l = lists.value.find(z => z.id === id)
    if (l) l.collapsed = collapsed
    try {
      await $fetch(`${apiBase}/api/tasks/lists/${id}`, { method: 'PATCH', headers: h(), body: { collapsed } })
    } catch (e) {
      error.value = detail(e, 'Could not update list.')
    }
  }

  async function deleteList(id: string): Promise<void> {
    error.value = ''
    try {
      await $fetch(`${apiBase}/api/tasks/lists/${id}`, { method: 'DELETE', headers: h() })
      await load()
    } catch (e) {
      error.value = detail(e, 'Could not delete list.')
    }
  }

  // Persist a new column order. Optimistic: reorder local state first.
  async function reorderLists(ids: string[]): Promise<void> {
    const order = new Map(ids.map((id, i) => [id, i]))
    lists.value = [...lists.value].sort((a, b) => (order.get(a.id) ?? 0) - (order.get(b.id) ?? 0))
    error.value = ''
    try {
      await $fetch(`${apiBase}/api/tasks/lists/reorder`, { method: 'POST', headers: h(), body: { ids } })
    } catch (e) {
      error.value = detail(e, 'Could not reorder lists.')
      await load()
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

  return {
    tasks, lists, error, loading, load, add, update, moveTask,
    addList, renameList, deleteList, reorderLists, moveListTo, resizeList, setCollapsed, toggle, remove, review,
  }
}
