<script setup lang="ts">
/* The Terminal app — xterm.js connected to /api/apps/terminal/ws.
   Run claude, git, anything in your shell, from inside Olwen. */
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import AppWindow from './AppWindow.vue'

const props = defineProps<{ cwd?: string | null; title?: string; autoStart?: string | null; embedded?: boolean }>()
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
let outBuf = ''           // rolling plain-text capture for the conductor
let lastDataAt = 0        // ms timestamp of the last byte (for idle detection)
let reconnectTimer: ReturnType<typeof setTimeout> | null = null
let manualClose = false
let reconnects = 0

function connect() {
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
    reconnects = 0
    ws?.send(JSON.stringify({ type: 'resize', cols: term!.cols, rows: term!.rows }))
    // Auto-run the starting command (e.g. claude) so a reconnect relaunches it too.
    if (props.autoStart) {
      const cmd = props.autoStart.trim() + '\n'
      setTimeout(() => { if (ws?.readyState === WebSocket.OPEN) ws.send(cmd) }, 650)
    }
  }
  ws.onmessage = (ev) => {
    let s: string
    if (typeof ev.data === 'string') { s = ev.data; term!.write(s) }
    else { const u = new Uint8Array(ev.data); term!.write(u); s = new TextDecoder().decode(u) }
    // Rolling plain-text buffer so Olwen's conductor can read what Claude Code shows.
    outBuf += s
    if (outBuf.length > 60000) outBuf = outBuf.slice(-60000)
    lastDataAt = Date.now()
  }
  ws.onclose = (ev) => {
    isConnected.value = false
    if (manualClose) return
    if (ev.code === 4401) { statusText.value = 'auth rejected'; return }
    // Unexpected drop (backend reload, network blip) — keep the terminal LIVE by
    // reconnecting and relaunching, so what Olwen runs is always visible here.
    if (reconnects < 8) {
      reconnects++
      statusText.value = 'reconnecting…'
      term?.write('\r\n\x1b[2;36m── reconnecting… ──\x1b[0m\r\n')
      reconnectTimer = setTimeout(connect, 1200)
    } else {
      statusText.value = 'disconnected'
      term?.write('\r\n\x1b[2;31m── disconnected ──\x1b[0m\r\n')
    }
  }
  ws.onerror = () => { statusText.value = 'error' }
}

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

  connect()

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

// Let a host (Dev Studio) type into this terminal — e.g. relay a prompt into the
// running Claude Code session. Claude Code's TUI (Ink) only treats Enter as
// "submit" when it arrives as its OWN keystroke, a beat after the text — glued on
// the same chunk it's swallowed as a newline. So type the text, then send Enter
// separately (twice, with delays, to be robust).
function sendInput(data: string, submit = false) {
  if (ws?.readyState !== WebSocket.OPEN) return false
  ws.send(data)
  if (submit) {
    setTimeout(() => { if (ws?.readyState === WebSocket.OPEN) ws.send('\r') }, 180)
    setTimeout(() => { if (ws?.readyState === WebSocket.OPEN) ws.send('\r') }, 420)
  }
  term?.focus()
  return true
}
// ANSI/control-stripped view of the recent terminal, for Olwen to read.
function getOutput(): string {
  return outBuf
    .replace(/\x1b\][^\x07\x1b]*(\x07|\x1b\\)/g, '')   // OSC
    .replace(/\x1b\[[0-9;?]*[ -/]*[@-~]/g, '')          // CSI
    .replace(/\x1b[()][AB0-2]/g, '')                    // charset
    .replace(/\x1b[=>]/g, '')
    .replace(/[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]/g, '')    // other control chars (keep \n, \t)
    .split('\n').map(l => l.replace(/\s+$/, '')).filter((l, i, a) => !(l === '' && a[i - 1] === '')).join('\n')
    .slice(-8000)
}
function idleFor(): number { return lastDataAt ? Date.now() - lastDataAt : 0 }
defineExpose({ sendInput, getOutput, idleFor })

onMounted(async () => { await nextTick(); await mountTerminal() })
onBeforeUnmount(() => {
  manualClose = true
  if (reconnectTimer) clearTimeout(reconnectTimer)
  resizeObs?.disconnect()
  try { ws?.close() } catch { /* */ }
  try { term?.dispose() } catch { /* */ }
})
</script>

<template>
  <!-- Embedded: just the terminal + a slim toolbar, filling its parent (the host
       provides the window chrome / drag / close). -->
  <div v-if="embedded" class="term-embed">
    <div class="embed-tools">
      <span class="status" :class="{ on: isConnected }">{{ statusText }}</span>
      <button class="tool" title="Launch Claude Code" @click="startClaude">✦ claude</button>
      <button class="tool" title="Send Ctrl+C" @click="sendCtrlC">⌃C</button>
    </div>
    <div ref="containerRef" class="term" />
  </div>

  <AppWindow v-else :title="title || 'Terminal'" glyph="▢" color="#5EEAD4" :initial-width="920" :initial-height="540" @close="emit('close')">
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
  text-transform: uppercase; color: var(--text-muted);
  padding: 3px 8px; border-radius: 999px; border: 0.5px solid var(--text-muted);
}
.status.on { color: var(--accent); border-color: var(--border-strong); background: var(--border); }

.tool {
  padding: 5px 10px; border-radius: 999px; cursor: pointer;
  border: 0.5px solid var(--border-strong); background: var(--border);
  color: var(--accent-2); font-family: 'JetBrains Mono', monospace; font-size: 9.5px;
  letter-spacing: 1.1px; text-transform: uppercase;
}
.tool:hover { background: var(--border-strong); color: var(--text-strong); border-color: var(--accent); }

.term { width: 100%; height: 100%; padding: 8px 4px 0 10px; box-sizing: border-box; background: var(--bg); }

/* Embedded mode — fill the host window, slim toolbar, no chrome. */
.term-embed { display: flex; flex-direction: column; width: 100%; height: 100%; background: var(--bg); }
.embed-tools { display: flex; align-items: center; gap: 8px; padding: 5px 10px; border-bottom: 1px solid var(--border); flex-shrink: 0; }
.term-embed .term { flex: 1; height: auto; min-height: 0; }
</style>
