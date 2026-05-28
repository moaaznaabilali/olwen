<script setup lang="ts">
/* The Terminal app — xterm.js connected to /api/apps/terminal/ws.
   Run claude, git, anything in your shell, from inside Olwen. */
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import AppWindow from './AppWindow.vue'

const props = defineProps<{ cwd?: string | null; title?: string; autoStart?: string | null }>()
const emit = defineEmits<{ close: [] }>()

const containerRef = ref<HTMLElement>()
const statusText = ref('Connecting…')
const isConnected = ref(false)

interface XTerminal {
  open: (el: HTMLElement) => void
  write: (data: string | Uint8Array) => void
  onData: (cb: (d: string) => void) => void
  onResize: (cb: (size: { cols: number; rows: number }) => void) => void
  cols: number
  rows: number
  dispose: () => void
  loadAddon: (a: unknown) => void
  focus: () => void
}
interface XFitAddon { fit: () => void }

let term: XTerminal | null = null
let fitAddon: XFitAddon | null = null
let ws: WebSocket | null = null
let resizeObs: ResizeObserver | null = null

async function mountTerminal() {
  if (!containerRef.value) return
  // Dynamic import — xterm.js is browser-only and large, lazy-load it.
  const { Terminal } = await import('@xterm/xterm')
  const { FitAddon } = await import('@xterm/addon-fit')
  const { WebLinksAddon } = await import('@xterm/addon-web-links')
  await import('@xterm/xterm/css/xterm.css')

  term = new Terminal({
    fontFamily: '"JetBrains Mono", ui-monospace, Menlo, monospace',
    fontSize: 13,
    lineHeight: 1.25,
    cursorBlink: true,
    allowProposedApi: true,
    scrollback: 5000,
    theme: {
      background: '#02060A',
      foreground: '#ECFEFF',
      cursor: '#5EEAD4',
      cursorAccent: '#02060A',
      selectionBackground: 'rgba(94,234,212,0.35)',
      black: '#0A1419',
      red: '#F87171',
      green: '#5EEAD4',
      yellow: '#FBBF24',
      blue: '#67E8F9',
      magenta: '#F472B6',
      cyan: '#22D3EE',
      white: '#DCFCF5',
      brightBlack: 'rgba(167,243,208,0.4)',
      brightRed: '#FCA5A5',
      brightGreen: '#A7F3D0',
      brightYellow: '#FDE68A',
      brightBlue: '#A5F3FC',
      brightMagenta: '#FBCFE8',
      brightCyan: '#67E8F9',
      brightWhite: '#ECFEFF',
    },
  }) as unknown as XTerminal
  fitAddon = new FitAddon() as unknown as XFitAddon
  term.loadAddon(fitAddon)
  term.loadAddon(new WebLinksAddon())
  term.open(containerRef.value)
  fitAddon.fit()
  term.focus()

  // Connect WebSocket — JWT in query string (browser WS can't set headers)
  const token = localStorage.getItem('olwen_access') || ''
  const apiBase = useRuntimeConfig().public.apiBase as string
  const wsBase = apiBase.replace(/^http/, 'ws')
  const q = new URLSearchParams({ token })
  if (props.cwd) q.set('cwd', props.cwd)
  ws = new WebSocket(`${wsBase}/api/apps/terminal/ws?${q.toString()}`)
  ws.binaryType = 'arraybuffer'

  ws.onopen = () => {
    isConnected.value = true
    statusText.value = 'connected'
    // Send initial size so the shell knows the window dims
    ws?.send(JSON.stringify({ type: 'resize', cols: term!.cols, rows: term!.rows }))
    // Auto-run a starting command (e.g. "claude --dangerously-skip-permissions")
    // after a short delay so the user's shell init (zshrc, etc.) finishes first.
    if (props.autoStart) {
      const cmd = props.autoStart.trim() + '\n'
      setTimeout(() => { if (ws?.readyState === WebSocket.OPEN) ws.send(cmd) }, 650)
    }
  }
  ws.onmessage = (ev) => {
    if (typeof ev.data === 'string') term!.write(ev.data)
    else term!.write(new Uint8Array(ev.data))
  }
  ws.onclose = (ev) => {
    isConnected.value = false
    statusText.value = ev.code === 4401 ? 'auth rejected' : 'disconnected'
    term?.write(`\r\n\x1b[2;36m── session ended ──\x1b[0m\r\n`)
  }
  ws.onerror = () => { statusText.value = 'error' }

  term.onData(d => { if (ws?.readyState === WebSocket.OPEN) ws.send(d) })
  term.onResize(({ cols, rows }) => {
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'resize', cols, rows }))
    }
  })

  // Auto-fit when the window or container resizes
  resizeObs = new ResizeObserver(() => {
    try { fitAddon?.fit() } catch { /* */ }
  })
  resizeObs.observe(containerRef.value)
}

function sendCtrlC() {
  if (ws?.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: 'signal', name: 'SIGINT' }))
  }
}
function startClaude() {
  if (ws?.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: 'input', data: 'claude\n' }))
    term?.focus()
  }
}

onMounted(async () => { await nextTick(); await mountTerminal() })
onBeforeUnmount(() => {
  resizeObs?.disconnect()
  try { ws?.close() } catch { /* */ }
  try { term?.dispose() } catch { /* */ }
})
</script>

<template>
  <AppWindow :title="title || 'Terminal'" glyph="▢" color="#5EEAD4" :initial-width="920" :initial-height="540" @close="emit('close')">
    <template #header>
      <div class="tools">
        <span class="status" :class="{ on: isConnected }">{{ statusText }}</span>
        <button class="tool" title="Launch Claude Code" @click="startClaude">✦ claude</button>
        <button class="tool" title="Send Ctrl+C" @click="sendCtrlC">⌃C</button>
      </div>
    </template>
    <div ref="containerRef" class="term" />
  </AppWindow>
</template>

<style scoped>
.tools { display: flex; align-items: center; gap: 8px; margin-left: 14px; }
.status {
  font-family: 'JetBrains Mono', monospace; font-size: 9px; letter-spacing: 1.3px;
  text-transform: uppercase; color: rgba(167,243,208,0.5);
  padding: 3px 8px; border-radius: 999px; border: 0.5px solid rgba(167,243,208,0.2);
}
.status.on { color: #5EEAD4; border-color: rgba(94,234,212,0.45); background: rgba(94,234,212,0.06); }

.tool {
  padding: 5px 10px; border-radius: 999px; cursor: pointer;
  border: 0.5px solid rgba(94,234,212,0.3); background: rgba(94,234,212,0.06);
  color: #A7F3D0; font-family: 'JetBrains Mono', monospace; font-size: 9.5px;
  letter-spacing: 1.1px; text-transform: uppercase;
}
.tool:hover { background: rgba(94,234,212,0.16); color: #ECFEFF; border-color: #5EEAD4; }

.term { width: 100%; height: 100%; padding: 8px 4px 0 10px; box-sizing: border-box; background: #02060A; }
</style>
