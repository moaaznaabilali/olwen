import { computed, ref } from 'vue'

type AiState = 'idle' | 'thinking' | 'speaking'

/**
 * Talk to Olwen. Streams Claude's reply over SSE and drives the entity's state
 * (thinking while we wait, speaking as words arrive). The streaming + animation
 * is what makes the wait feel alive instead of slow.
 */
export interface UiAction {
  ui_action: string
  [k: string]: unknown
}

export function useOlwen() {
  const apiBase = useRuntimeConfig().public.apiBase as string

  const answer = ref('')
  const lastQuestion = ref('')
  const busy = ref(false)
  const entityState = ref<AiState>('idle')
  const active = computed(() => busy.value || answer.value.length > 0)

  // Last UI action emitted by the agent — DashboardView watches this and
  // dispatches it (open terminal, dev mode, settings, etc.). Bumped via id
  // so the same action twice in a row still triggers a re-dispatch.
  const lastUiAction = useState<{ id: number; action: UiAction } | null>('olwen:uiaction', () => null)
  let uiActionCounter = 0
  function emitUiAction(a: UiAction) {
    uiActionCounter += 1
    lastUiAction.value = { id: uiActionCounter, action: a }
  }

  async function ask(message: string, displayLabel?: string): Promise<void> {
    const q = message.trim()
    if (busy.value || !q) return

    lastQuestion.value = displayLabel ?? q
    answer.value = ''
    busy.value = true
    entityState.value = 'thinking'

    const token = import.meta.client ? localStorage.getItem('olwen_access') : null

    try {
      const res = await fetch(`${apiBase}/api/chat/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ message: q }),
      })
      if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`)

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let started = false

      for (;;) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })

        const parts = buffer.split('\n\n')
        buffer = parts.pop() ?? ''
        for (const part of parts) {
          const line = part.trim()
          if (!line.startsWith('data:')) continue
          const evt = JSON.parse(line.slice(5).trim())
          if (evt.type === 'delta') {
            if (!started) {
              started = true
              entityState.value = 'speaking'
            }
            answer.value += evt.text
          } else if (evt.type === 'ui_action') {
            // The agent decided to open something — dispatch it now.
            emitUiAction(evt as UiAction)
          } else if (evt.type === 'error') {
            answer.value += `\n[Olwen hit an error: ${evt.message}]`
          }
        }
      }
    } catch {
      answer.value = answer.value || 'I could not reach my backend. Is it running?'
    } finally {
      busy.value = false
      entityState.value = 'idle'
    }
  }

  function reset(): void {
    answer.value = ''
    lastQuestion.value = ''
    entityState.value = 'idle'
  }

  return { answer, lastQuestion, busy, entityState, active, ask, reset, lastUiAction }
}
