<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import WidgetPanel from './WidgetPanel.vue'
import type { StravaActivity } from '../composables/useStrava'

const emit = defineEmits<{ openSettings: [] }>()
const { configured, account, activities: fetchActivities } = useStrava()

const oauthAvailable = ref(false)
const connected = ref(false)
const athlete = ref('')
const activities = ref<StravaActivity[]>([])
const loading = ref(true)
const error = ref('')

// Soft pink glyph per sport — Strava-ish but on-brand for Olwen
const sportGlyph: Record<string, string> = {
  Run: '↗', TrailRun: '↗', VirtualRun: '↗',
  Ride: '◔', VirtualRide: '◔', EBikeRide: '◔',
  Swim: '~', Hike: '⛰', Walk: '∼',
  Workout: '✦', WeightTraining: '⚒', Yoga: '◯',
}
function glyph(t: string): string { return sportGlyph[t] || '✦' }

async function load() {
  loading.value = true; error.value = ''
  try {
    const [cfg, acc] = await Promise.all([configured(), account()])
    oauthAvailable.value = cfg.configured
    connected.value = acc.connected
    athlete.value = acc.athlete_name || ''
    if (connected.value) {
      const r = await fetchActivities(6)
      activities.value = r.activities
    }
  } catch (e: unknown) {
    error.value = (e as { data?: { detail?: string } })?.data?.detail || 'Could not load Strava.'
  } finally { loading.value = false }
}

const count = computed(() => activities.value.length)
function ago(iso: string): string {
  if (!iso) return ''
  const t = new Date(iso).getTime(); if (!isFinite(t)) return ''
  const s = Math.max(0, (Date.now() - t) / 1000)
  if (s < 3600) return `${Math.floor(s / 60)}m`
  if (s < 86400) return `${Math.floor(s / 3600)}h`
  if (s < 7 * 86400) return `${Math.floor(s / 86400)}d`
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}
onMounted(load)
</script>

<template>
  <WidgetPanel title="Health" :badge="count || undefined" accent="#F472B6">
    <div class="h">
      <p v-if="error" class="error">{{ error }}</p>

      <template v-if="!connected && !loading">
        <p class="empty">Connect Strava to see your runs, rides, and training load.</p>
        <button class="cta" @click="emit('openSettings')">
          <svg viewBox="0 0 24 24" width="13" height="13" fill="currentColor">
            <path d="M15.387 17.944l-2.089-4.116h-3.065L15.387 24l5.15-10.172h-3.066m-7.008-5.599l2.836 5.598h4.172L10.463 0l-7 13.828h4.169" />
          </svg>
          Connect Strava · 1 min
        </button>
      </template>

      <template v-else-if="connected">
        <p v-if="athlete" class="who">{{ athlete }}</p>

        <ul v-if="loading" class="list">
          <li v-for="i in 3" :key="i" class="skel" :style="{ '--d': `${i * 80}ms` }">
            <span class="skel__icon" />
            <div class="skel__main"><span class="skel__line" /><span class="skel__line skel__line--short" /></div>
          </li>
        </ul>

        <p v-else-if="!activities.length" class="muted">No activities yet — go move.</p>

        <ul v-else class="list">
          <li v-for="a in activities" :key="a.id" class="row" :title="a.name">
            <span class="row__icon">{{ glyph(a.type) }}</span>
            <div class="row__main">
              <span class="row__name">{{ a.name }}</span>
              <span class="row__stats">
                {{ a.distance_km > 0 ? a.distance_km + ' km' : '' }}
                <span v-if="a.distance_km > 0 && a.duration_min > 0"> · </span>
                {{ a.duration_min }} min
                <span v-if="a.moving_pace"> · {{ a.moving_pace }}</span>
                <span v-if="a.elevation_gain_m > 50"> · ↑{{ a.elevation_gain_m }}m</span>
                <span v-if="a.average_heartrate"> · {{ Math.round(a.average_heartrate) }} bpm</span>
              </span>
            </div>
            <span class="time">{{ ago(a.start_date) }}</span>
          </li>
        </ul>
      </template>
    </div>
  </WidgetPanel>
</template>

<style scoped>
.h { display: flex; flex-direction: column; gap: 8px; }
.error { margin: 0; font-size: 11.5px; color: #FCA5A5; border-left: 2px solid #F87171; padding-left: 9px; }
.empty { margin: 6px 2px 10px; font-size: 12.5px; line-height: 1.5; color: rgba(167,243,208,0.55); }
.muted { margin: 4px 2px 0; font-size: 11px; color: rgba(167,243,208,0.4); }
.who { margin: 0 0 2px; font-family: 'JetBrains Mono', monospace; font-size: 10px; letter-spacing: 1.4px; color: rgba(244,114,182,0.7); }

.cta { display: inline-flex; align-items: center; gap: 9px; justify-content: center; padding: 9px; border-radius: 9px; cursor: pointer; width: 100%; border: 0.5px solid rgba(244,114,182,0.4); background: rgba(244,114,182,0.12); color: #FBCFE8; font-family: 'JetBrains Mono', monospace; font-size: 10px; letter-spacing: 1.2px; text-transform: uppercase; }
.cta:hover { background: rgba(244,114,182,0.22); border-color: #F472B6; color: #ECFEFF; }

.list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; }
.row { display: flex; align-items: flex-start; gap: 9px; padding: 8px 2px; border-bottom: 0.5px solid rgba(255,255,255,0.04); }
.row:last-child { border-bottom: none; }
.row__icon { width: 22px; text-align: center; color: #F472B6; font-size: 14px; flex-shrink: 0; }
.row__main { flex: 1; display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.row__name { font-size: 12.5px; color: #DCFCF5; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.row__stats { font-family: 'JetBrains Mono', monospace; font-size: 10px; color: rgba(167,243,208,0.55); }
.time { font-family: 'JetBrains Mono', monospace; font-size: 10px; color: rgba(167,243,208,0.4); white-space: nowrap; }

.skel { display: flex; gap: 9px; padding: 8px 2px; opacity: 0; animation: in .35s ease forwards; animation-delay: var(--d); }
.skel__icon { width: 14px; height: 14px; border-radius: 4px; background: rgba(244,114,182,0.18); flex-shrink: 0; margin-top: 3px; }
.skel__main { flex: 1; display: flex; flex-direction: column; gap: 4px; }
.skel__line { height: 9px; border-radius: 3px; background: linear-gradient(90deg, rgba(244,114,182,0.06), rgba(244,114,182,0.22), rgba(244,114,182,0.06)); background-size: 220% 100%; animation: shim 1.5s ease-in-out infinite; }
.skel__line--short { width: 60%; opacity: 0.6; }
@keyframes in { to { opacity: 1; } }
@keyframes shim { 0%,100% { background-position: 100% 0; } 50% { background-position: 0 0; } }
</style>
