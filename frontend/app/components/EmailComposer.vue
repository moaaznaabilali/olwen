<script setup lang="ts">
/* Minimal compose modal — new outgoing email, no thread context. */
import { ref } from 'vue'

const emit = defineEmits<{ close: []; sent: [] }>()

const { compose } = useEmail()

const to = ref('')
const subject = ref('')
const body = ref('')
const sending = ref(false)
const sent = ref(false)
const error = ref('')

function recipients(): string[] {
  return to.value.split(/[,\s;]+/).map(s => s.trim()).filter(Boolean)
}
function valid(): boolean {
  return recipients().length > 0 && subject.value.trim().length > 0 && body.value.trim().length > 0
}

async function submit() {
  if (!valid() || sending.value) return
  sending.value = true; error.value = ''
  try {
    await compose({ to: recipients(), subject: subject.value.trim(), body: body.value.trim() })
    sent.value = true
    setTimeout(() => emit('sent'), 1200)
  } catch (e: unknown) {
    error.value = (e as { data?: { detail?: string } })?.data?.detail || 'Send failed.'
  } finally { sending.value = false }
}
</script>

<template>
  <div class="overlay" @click.self="emit('close')">
    <div class="modal">
      <header class="head">
        <h3 class="title">New email</h3>
        <button class="x" @click="emit('close')">✕</button>
      </header>

      <div v-if="sent" class="sent">
        <div class="sent__check">✓</div>
        <p>Sent.</p>
      </div>

      <template v-else>
        <label class="field">
          <span class="label">To</span>
          <input v-model="to" class="input" placeholder="someone@example.com" autocomplete="off">
        </label>
        <label class="field">
          <span class="label">Subject</span>
          <input v-model="subject" class="input" placeholder="…">
        </label>
        <label class="field">
          <span class="label">Message</span>
          <textarea v-model="body" class="input area" rows="9" placeholder="Type your message…" />
        </label>

        <p v-if="error" class="err">{{ error }}</p>

        <div class="actions">
          <button class="btn" @click="emit('close')">Cancel</button>
          <button class="btn btn--primary" :disabled="!valid() || sending" @click="submit">
            {{ sending ? 'Sending…' : '✈ Send' }}
          </button>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.overlay { position: fixed; inset: 0; z-index: 70; background: rgba(2,6,10,0.7); backdrop-filter: blur(6px); display: grid; place-items: center; padding: 24px; }
.modal { width: min(620px, 100%); background: linear-gradient(180deg, rgba(8,30,38,0.95), rgba(2,6,10,0.95)); border: 0.5px solid rgba(94,234,212,0.3); border-radius: 16px; padding: 22px; display: flex; flex-direction: column; gap: 12px; box-shadow: 0 30px 80px rgba(0,0,0,0.6); }
.head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 4px; }
.title { margin: 0; font-size: 17px; font-weight: 300; color: #ECFEFF; }
.x { background: transparent; border: none; color: rgba(167,243,208,0.5); cursor: pointer; font-size: 14px; }
.x:hover { color: #F87171; }

.field { display: flex; flex-direction: column; gap: 5px; }
.label { font-family: 'JetBrains Mono', monospace; font-size: 9px; letter-spacing: 1.4px; text-transform: uppercase; color: rgba(167,243,208,0.55); }
.input { width: 100%; padding: 11px 14px; border-radius: 10px; border: 0.5px solid rgba(94,234,212,0.22); background: rgba(2,6,10,0.55); color: #ECFEFF; font-family: inherit; font-size: 13px; outline: none; }
.input:focus { border-color: #5EEAD4; box-shadow: 0 0 18px rgba(94,234,212,0.15); }
.area { resize: vertical; min-height: 140px; line-height: 1.6; }

.err { margin: 0; font-size: 12px; color: #FCA5A5; border-left: 2px solid #F87171; padding-left: 9px; }

.actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 6px; }
.btn { padding: 9px 18px; border-radius: 999px; cursor: pointer; border: 0.5px solid rgba(94,234,212,0.25); background: transparent; color: #A7F3D0; font-family: 'JetBrains Mono', monospace; font-size: 10.5px; letter-spacing: 1.2px; text-transform: uppercase; }
.btn:hover:not(:disabled) { border-color: #5EEAD4; color: #ECFEFF; }
.btn--primary { background: #5EEAD4; color: #02060A; border-color: #5EEAD4; }
.btn--primary:hover:not(:disabled) { background: #67E8F9; box-shadow: 0 0 22px rgba(94,234,212,0.4); }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }

.sent { padding: 40px 0; display: flex; flex-direction: column; align-items: center; gap: 12px; color: #5EEAD4; }
.sent__check { width: 56px; height: 56px; border-radius: 50%; display: grid; place-items: center; background: rgba(94,234,212,0.18); border: 0.5px solid #5EEAD4; color: #5EEAD4; font-size: 28px; box-shadow: 0 0 32px rgba(94,234,212,0.4); }
.sent p { margin: 0; font-size: 14px; color: #ECFEFF; }
</style>
