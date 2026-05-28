import { ref } from 'vue'

/**
 * Voice in/out via the browser's free Web Speech API.
 *  - listen(): speech → text (Chrome/Edge; needs mic permission + localhost/HTTPS)
 *  - speak():  text → speech (text-to-speech)
 * Phase 2 can swap in Whisper + ElevenLabs for nicer quality.
 */
export function useVoice() {
  const listening = ref(false)
  const speaking = ref(false)
  const supported = ref(false)

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let recognition: any = null

  if (import.meta.client) {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
    supported.value = !!SR && 'speechSynthesis' in window
  }

  function startListening(onResult: (text: string) => void, lang = 'en-US'): void {
    if (!import.meta.client) return
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
    if (!SR) return
    cancelSpeak() // don't listen to ourselves
    recognition = new SR()
    recognition.lang = lang
    recognition.interimResults = false
    recognition.maxAlternatives = 1
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    recognition.onresult = (e: any) => {
      const text = e.results[0][0].transcript as string
      if (text) onResult(text)
    }
    recognition.onend = () => { listening.value = false }
    recognition.onerror = () => { listening.value = false }
    listening.value = true
    recognition.start()
  }

  function stopListening(): void {
    try { recognition?.stop() } catch { /* ignore */ }
    listening.value = false
  }

  function pickVoice(lang: string): SpeechSynthesisVoice | undefined {
    const voices = window.speechSynthesis.getVoices()
    const byLang = voices.filter(v => v.lang.toLowerCase().startsWith(lang.slice(0, 2)))
    // prefer nicer-sounding voices when available
    return (
      byLang.find(v => /google|natural|samantha|premium|enhanced/i.test(v.name))
      || byLang[0]
      || voices[0]
    )
  }

  interface SpeakOpts {
    onBoundary?: (charIndex: number) => void
    onEnd?: () => void
  }

  function speak(text: string, lang = 'en-US', opts: SpeakOpts = {}): void {
    // Original, simple form — the same one that worked when voice first came online.
    if (!import.meta.client || !('speechSynthesis' in window) || !text.trim()) {
      opts.onEnd?.()
      return
    }
    window.speechSynthesis.cancel()
    const u = new SpeechSynthesisUtterance(text)
    u.lang = lang
    u.rate = 1
    u.pitch = 1
    const v = pickVoice(lang)
    if (v) u.voice = v
    u.onstart = () => { speaking.value = true }
    u.onboundary = (e: SpeechSynthesisEvent) => opts.onBoundary?.(e.charIndex)
    u.onend = () => { speaking.value = false; opts.onEnd?.() }
    u.onerror = () => { speaking.value = false; opts.onEnd?.() }
    window.speechSynthesis.speak(u)
  }

  function cancelSpeak(): void {
    if (import.meta.client && 'speechSynthesis' in window) window.speechSynthesis.cancel()
    speaking.value = false
  }

  /* ---------- server-side TTS (Edge neural voice → MP3 → <audio>) ----------
     Bypasses the browser's local speech daemon entirely. Works on any device
     where YouTube plays sound. */
  let currentAudio: HTMLAudioElement | null = null

  interface SpeakAudioOpts {
    onStart?: (durationMs: number) => void  // fires when audio actually begins playing
    onEnd?: () => void
    rate?: string
  }

  function speakAudio(text: string, opts: SpeakAudioOpts = {}): void {
    if (!import.meta.client || !text.trim()) { opts.onEnd?.(); return }
    cancelAudio()
    const apiBase = useRuntimeConfig().public.apiBase as string
    const params = new URLSearchParams({ text })
    if (opts.rate) params.set('rate', opts.rate)
    const audio = new Audio(`${apiBase}/api/voice/speak?${params.toString()}`)
    audio.preload = 'auto'
    audio.onplay = () => {
      speaking.value = true
      // duration may still be NaN at onplay on some browsers; fall back to estimate
      const dur = isFinite(audio.duration) ? audio.duration * 1000 : Math.max(1200, text.length * 55)
      opts.onStart?.(dur)
    }
    audio.onended  = () => { speaking.value = false; opts.onEnd?.(); if (currentAudio === audio) currentAudio = null }
    audio.onerror  = () => { speaking.value = false; opts.onEnd?.(); if (currentAudio === audio) currentAudio = null }
    currentAudio = audio
    audio.play().catch(() => { /* autoplay block — ignore */ })
  }

  function cancelAudio(): void {
    if (!currentAudio) return
    try { currentAudio.pause(); currentAudio.src = '' } catch { /* ignore */ }
    currentAudio = null
    speaking.value = false
  }

  return {
    listening, speaking, supported,
    startListening, stopListening,
    speak, cancelSpeak,
    speakAudio, cancelAudio,
  }
}
