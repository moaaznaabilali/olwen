<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import type { OlwenSettings, Provider } from '../composables/useSettings'
import type { OlwenMemory } from '../composables/useMemory'

const emit = defineEmits<{ close: [] }>()
const { fetchSettings, connectProvider, disconnectProvider, selectProvider, updateVoice } = useSettings()

// shared with the dashboard so changes apply immediately
const voiceOn = useState<boolean>('voice:on', () => true)
const voiceLang = useState<string>('voice:lang', () => 'en-US')
const langs = [
  { v: 'en-US', label: 'English' },
  { v: 'ar-SA', label: 'Arabic' },
]

async function toggleVoice() {
  voiceOn.value = !voiceOn.value
  try { settings.value = await updateVoice({ enabled: voiceOn.value }) } catch { /* ignore */ }
}
async function setLang(l: string) {
  voiceLang.value = l
  try { settings.value = await updateVoice({ lang: l }) } catch { /* ignore */ }
}

// ---- what Olwen remembers ----
const { list: listMemories, add: addMemory, remove: removeMemory } = useMemory()
const memories = ref<OlwenMemory[]>([])
const newMemory = ref('')
async function loadMemories() {
  try { memories.value = await listMemories() } catch { /* ignore */ }
}
async function saveMemory() {
  const c = newMemory.value.trim()
  if (!c) return
  newMemory.value = ''
  try { await addMemory(c); await loadMemories() } catch { /* ignore */ }
}
async function forget(id: string) {
  try { await removeMemory(id); await loadMemories() } catch { /* ignore */ }
}

const loading = ref(true)
const error = ref('')
const settings = ref<OlwenSettings | null>(null)
const busy = ref<Provider | null>(null)
// key input per provider
const keyInput = reactive<Record<Provider, string>>({ claude: '', gemini: '' })

const meta: Record<Provider, { name: string; tag: string; link: string; placeholder: string }> = {
  groq: {
    name: 'Groq',
    tag: 'free · fast',
    link: 'https://console.groq.com',
    placeholder: 'gsk_…',
  },
  gemini: {
    name: 'Google Gemini',
    tag: 'free tier',
    link: 'https://aistudio.google.com/apikey',
    placeholder: 'AIza…',
  },
  claude: {
    name: 'Claude',
    tag: 'paid API',
    link: 'https://console.anthropic.com/settings/keys',
    placeholder: 'sk-ant-…',
  },
}
const order: Provider[] = ['groq', 'gemini', 'claude']

onMounted(async () => {
  try {
    settings.value = await fetchSettings()
    voiceOn.value = settings.value.voice.enabled
    voiceLang.value = settings.value.voice.lang
  } catch {
    error.value = 'Could not load settings.'
  } finally {
    loading.value = false
  }
  loadMemories()
})

async function connect(p: Provider) {
  if (busy.value) return
  if (keyInput[p].trim().length < 10) {
    error.value = 'Paste a valid API key.'
    return
  }
  busy.value = p
  error.value = ''
  try {
    settings.value = await connectProvider(p, keyInput[p].trim())
    keyInput[p] = ''
  } catch (e: unknown) {
    error.value = (e as { data?: { detail?: string } })?.data?.detail || 'Could not connect.'
  } finally {
    busy.value = null
  }
}

async function disconnect(p: Provider) {
  if (busy.value) return
  busy.value = p
  error.value = ''
  try {
    settings.value = await disconnectProvider(p)
  } catch {
    error.value = 'Could not disconnect.'
  } finally {
    busy.value = null
  }
}

async function use(p: Provider) {
  if (busy.value) return
  busy.value = p
  error.value = ''
  try {
    settings.value = await selectProvider(p)
  } catch (e: unknown) {
    error.value = (e as { data?: { detail?: string } })?.data?.detail || 'Could not switch.'
  } finally {
    busy.value = null
  }
}
</script>

<template>
  <div class="overlay" @click.self="emit('close')">
    <div class="modal" role="dialog" aria-modal="true">
      <header class="modal__head">
        <span class="modal__title">Settings · Your AI</span>
        <button class="modal__close" aria-label="Close" @click="emit('close')">✕</button>
      </header>

      <p class="intro">Choose which AI powers Olwen and connect your own key.</p>

      <p v-if="loading" class="muted">Loading…</p>

      <div v-else class="cards">
        <div
          v-for="p in order"
          :key="p"
          class="card"
          :class="{ active: settings?.active_provider === p }"
        >
          <div class="card__head">
            <div class="card__title">
              {{ meta[p].name }}
              <span class="tag">{{ meta[p].tag }}</span>
            </div>
            <span v-if="settings?.active_provider === p" class="active-badge">In use</span>
          </div>
          <p class="card__model">{{ settings?.[p].model }}</p>

          <!-- connected -->
          <template v-if="settings?.[p].connected">
            <div class="keyrow">
              <span class="keyrow__key">{{ settings[p].key_masked }}</span>
              <span class="keyrow__ok">connected ✓</span>
            </div>
            <div class="actions">
              <button
                v-if="settings.active_provider !== p"
                class="btn btn--primary"
                :disabled="busy !== null"
                @click="use(p)"
              >Use this</button>
              <span v-else class="using">Active brain</span>
              <button class="btn btn--ghost" :disabled="busy !== null" @click="disconnect(p)">
                Disconnect
              </button>
            </div>
          </template>

          <!-- not connected -->
          <template v-else>
            <input
              v-model="keyInput[p]"
              class="key-input"
              type="password"
              autocomplete="off"
              :placeholder="meta[p].placeholder"
              @keyup.enter="connect(p)"
            >
            <div class="actions">
              <button class="btn btn--primary" :disabled="busy !== null" @click="connect(p)">
                {{ busy === p ? 'Verifying…' : 'Connect' }}
              </button>
              <a class="getkey" :href="meta[p].link" target="_blank" rel="noopener">Get a key →</a>
            </div>
          </template>
        </div>
      </div>

      <!-- Voice preferences -->
      <div v-if="!loading && settings" class="voice">
        <div class="voice__row">
          <div>
            <div class="voice__title">Voice replies</div>
            <div class="voice__sub">Olwen speaks its answers aloud</div>
          </div>
          <button class="toggle" :class="{ on: voiceOn }" :aria-pressed="voiceOn" @click="toggleVoice">
            <span class="toggle__knob" />
          </button>
        </div>
        <div class="voice__row">
          <div class="voice__title">Language</div>
          <div class="langs">
            <button
              v-for="l in langs"
              :key="l.v"
              class="langbtn"
              :class="{ active: voiceLang === l.v }"
              @click="setLang(l.v)"
            >{{ l.label }}</button>
          </div>
        </div>
      </div>

      <!-- What Olwen remembers -->
      <div v-if="!loading" class="mem">
        <span class="section__title">What Olwen remembers</span>
        <p class="section__desc">Used naturally in chat. Tip: just say “remember that…”.</p>
        <ul v-if="memories.length" class="mem__list">
          <li v-for="m in memories" :key="m.id" class="mem__item">
            <span class="mem__dot" />
            <span class="mem__text">{{ m.content }}</span>
            <button class="mem__x" title="Forget" @click="forget(m.id)">✕</button>
          </li>
        </ul>
        <p v-else class="muted">Nothing yet — Olwen will learn as you talk.</p>
        <div class="mem__add">
          <input
            v-model="newMemory"
            class="mem__input"
            placeholder="Add something Olwen should know…"
            @keyup.enter="saveMemory"
          >
          <button class="btn btn--primary mem__btn" @click="saveMemory">Add</button>
        </div>
      </div>

      <p v-if="error" class="error">{{ error }}</p>
      <p v-if="settings && !settings.active_provider && !loading" class="hint">
        No AI connected yet — Olwen replies in demo mode until you connect one.
      </p>
    </div>
  </div>
</template>

<style scoped>
.overlay {
  position: fixed; inset: 0; z-index: 50;
  display: grid; place-items: center;
  background: color-mix(in srgb, var(--bg) 60%, transparent); backdrop-filter: blur(4px);
}
.modal {
  width: min(480px, 94%);
  border-radius: 16px;
  border: 0.5px solid var(--border-strong);
  background: var(--surface-2);
  backdrop-filter: blur(16px);
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
}
.modal__head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 18px 20px; border-bottom: 0.5px solid var(--border);
}
.modal__title {
  font-family: 'JetBrains Mono', monospace;
  letter-spacing: 2px; text-transform: uppercase; font-size: 12px; color: var(--accent);
}
.modal__close { border: none; background: transparent; cursor: pointer; color: var(--text-muted); font-size: 14px; }
.modal__close:hover { color: var(--text-strong); }

.intro { margin: 0; padding: 16px 20px 4px; font-size: 12px; color: var(--text-muted); }
.muted { padding: 16px 20px; font-size: 12px; color: var(--text-muted); }

.cards { display: flex; flex-direction: column; gap: 12px; padding: 12px 20px; }
.card {
  border-radius: 12px; padding: 14px;
  border: 0.5px solid var(--border); background: var(--surface);
  display: flex; flex-direction: column; gap: 9px;
  transition: border-color .2s ease;
}
.card.active { border-color: var(--accent); box-shadow: 0 0 16px rgba(94,234,212,0.12); }
.card__head { display: flex; align-items: center; justify-content: space-between; }
.card__title { font-size: 14px; color: var(--text-strong); display: flex; align-items: center; gap: 8px; }
.tag {
  font-family: 'JetBrains Mono', monospace; font-size: 8px; letter-spacing: 1px;
  text-transform: uppercase; color: var(--accent); border: 0.5px solid var(--border-strong);
  border-radius: 999px; padding: 2px 6px;
}
.active-badge {
  font-family: 'JetBrains Mono', monospace; font-size: 9px; letter-spacing: 1px;
  text-transform: uppercase; color: var(--bg); background: var(--accent);
  border-radius: 999px; padding: 3px 9px;
}
.card__model { margin: 0; font-family: 'JetBrains Mono', monospace; font-size: 10px; color: var(--text-muted); }

.keyrow { display: flex; align-items: center; justify-content: space-between; }
.keyrow__key { font-family: 'JetBrains Mono', monospace; font-size: 12px; color: var(--accent-2); }
.keyrow__ok { font-size: 11px; color: var(--accent); }

.key-input {
  padding: 10px 12px; border-radius: 8px;
  border: 0.5px solid var(--border-strong); background: var(--surface);
  color: var(--text); font-size: 13px; outline: none;
}
.key-input:focus { border-color: var(--accent); }
.key-input::placeholder { color: var(--text-muted); }

.actions { display: flex; align-items: center; gap: 10px; }
.btn {
  padding: 8px 14px; border-radius: 8px; cursor: pointer; font-size: 11px;
  letter-spacing: 1px; text-transform: uppercase; transition: all .2s ease;
}
.btn:disabled { opacity: 0.5; cursor: progress; }
.btn--primary { border: 0.5px solid var(--accent); background: rgba(94,234,212,0.16); color: var(--text-strong); }
.btn--primary:hover:not(:disabled) { background: rgba(94,234,212,0.26); }
.btn--ghost { border: 0.5px solid rgba(248,113,113,0.4); background: transparent; color: #FCA5A5; }
.btn--ghost:hover:not(:disabled) { background: rgba(248,113,113,0.12); }
.using { font-size: 11px; color: var(--accent); }
.getkey { font-size: 11px; color: var(--accent); text-decoration: none; }
.getkey:hover { text-decoration: underline; }

/* voice section */
.voice {
  margin: 4px 20px 0; padding: 14px;
  border-radius: 12px; border: 0.5px solid var(--border);
  background: var(--surface); display: flex; flex-direction: column; gap: 14px;
}
.voice__row { display: flex; align-items: center; justify-content: space-between; }
.voice__title { font-size: 13px; color: var(--text-strong); }
.voice__sub { font-size: 11px; color: var(--text-muted); margin-top: 2px; }
.toggle {
  width: 42px; height: 24px; border-radius: 999px; cursor: pointer; position: relative;
  border: 0.5px solid var(--border-strong); background: var(--surface-2); transition: all .2s ease;
}
.toggle.on { background: rgba(94,234,212,0.25); border-color: var(--accent); }
.toggle__knob {
  position: absolute; top: 2px; left: 2px; width: 18px; height: 18px; border-radius: 50%;
  background: var(--text-muted); transition: all .2s ease;
}
.toggle.on .toggle__knob { left: 20px; background: var(--accent); }
.langs { display: flex; gap: 6px; }
.langbtn {
  padding: 6px 12px; border-radius: 8px; cursor: pointer; font-size: 12px;
  border: 0.5px solid var(--border-strong); background: transparent; color: var(--text-muted);
  transition: all .2s ease;
}
.langbtn.active { border-color: var(--accent); background: rgba(94,234,212,0.15); color: var(--text-strong); }

/* memory section */
.mem { margin: 14px 20px 0; padding: 14px; border-radius: 12px; border: 0.5px solid var(--border); background: var(--surface); }
.mem .section__desc { margin: 4px 0 10px; }
.mem__list { list-style: none; margin: 0 0 10px; padding: 0; display: flex; flex-direction: column; gap: 6px; max-height: 160px; overflow-y: auto; }
.mem__item { display: flex; align-items: center; gap: 9px; font-size: 12.5px; color: var(--text); }
.mem__dot { width: 5px; height: 5px; border-radius: 50%; background: var(--accent); flex-shrink: 0; }
.mem__text { flex: 1; line-height: 1.4; }
.mem__x { border: none; background: transparent; color: var(--text-muted); cursor: pointer; font-size: 11px; }
.mem__x:hover { color: #F87171; }
.mem__add { display: flex; gap: 8px; }
.mem__input {
  flex: 1; padding: 9px 11px; border-radius: 8px; outline: none; font-size: 12.5px;
  border: 0.5px solid var(--border-strong); background: var(--surface); color: var(--text);
}
.mem__input:focus { border-color: var(--accent); }
.mem__input::placeholder { color: var(--text-muted); }
.mem__btn { padding: 9px 14px; }

.error { margin: 0; padding: 4px 20px 16px; font-size: 12px; color: #FCA5A5; }
.hint { margin: 0; padding: 8px 20px 18px; font-size: 11px; color: var(--text-muted); }
</style>
