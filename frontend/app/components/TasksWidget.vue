<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import WidgetPanel from './WidgetPanel.vue'
import type { OlwenTask } from '../composables/useTasks'

const emit = defineEmits<{ suggest: [OlwenTask]; review: [] }>()

const { tasks, lists, error, load, add, toggle, remove } = useTasks()

const newText = ref('')
const newList = ref('')

const openCount = computed(() => tasks.value.filter(t => !t.done).length)
// combined view, but grouped under each list so structure is visible
// main view shows only OPEN tasks — completed ones drop off
const groups = computed(() =>
  lists.value
    .map(l => ({ id: l.id, name: l.name, items: tasks.value.filter(t => t.list_id === l.id && !t.done) }))
    .filter(g => g.items.length > 0),
)

watch(lists, (l) => { if (!newList.value && l.length) newList.value = l[0].id }, { immediate: true })

onMounted(load)

function addTask() {
  const text = newText.value.trim()
  if (!text || !newList.value) return
  newText.value = ''
  add(newList.value, text)
}
</script>

<template>
  <WidgetPanel title="Tasks" :badge="openCount">
    <div class="tasks">
      <button v-if="openCount" class="review-cta" @click="emit('review')">
        <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12 3l1.8 4.7L18.5 9.5 13.8 11.3 12 16l-1.8-4.7L5.5 9.5l4.7-1.8L12 3z" />
        </svg>
        Review all with Olwen
      </button>

      <p v-if="error" class="tasks__error">{{ error }}</p>

      <p v-if="!error && !groups.length" class="tasks__empty">
        Nothing on your plate. Add a task below — I'll keep watch.
      </p>

      <div v-for="g in groups" :key="g.id" class="group">
        <div class="group__head">
          <span class="group__name">{{ g.name }}</span>
          <span class="group__count">{{ g.items.filter(i => !i.done).length }}</span>
        </div>

        <ul class="rows">
          <li
            v-for="t in g.items"
            :key="t.id"
            class="row"
            :class="[`p-${t.priority}`, { done: t.done }]"
          >
            <button
              class="check"
              :class="{ on: t.done }"
              :aria-label="t.done ? 'Mark not done' : 'Mark done'"
              @click="toggle(t)"
            >
              <svg v-if="t.done" viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="20 6 9 17 4 12" />
              </svg>
            </button>

            <span class="row__text">{{ t.text }}</span>

            <div class="row__acts">
              <button class="act" title="Ask Olwen about this" @click="emit('suggest', t)">
                <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M12 3l1.8 4.7L18.5 9.5 13.8 11.3 12 16l-1.8-4.7L5.5 9.5l4.7-1.8L12 3z" />
                </svg>
              </button>
              <button class="act del" title="Delete" @click="remove(t)">
                <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M4 7h16M9 7V5h6v2M6 7l1 13h10l1-13" />
                </svg>
              </button>
            </div>
          </li>
        </ul>
      </div>

      <!-- add task -->
      <form class="add" @submit.prevent="addTask">
        <span class="add__plus">+</span>
        <input v-model="newText" class="add__input" placeholder="Add a task…">
        <select v-model="newList" class="add__list" aria-label="List">
          <option v-for="l in lists" :key="l.id" :value="l.id">{{ l.name }}</option>
        </select>
      </form>
    </div>
  </WidgetPanel>
</template>

<style scoped>
.tasks { display: flex; flex-direction: column; gap: 14px; }
.review-cta {
  display: flex; align-items: center; justify-content: center; gap: 8px;
  width: 100%; padding: 9px; border-radius: 9px; cursor: pointer;
  border: 0.5px solid rgba(94,234,212,0.25); background: rgba(94,234,212,0.08);
  color: #5EEAD4; font-family: 'JetBrains Mono', monospace; font-size: 10px;
  letter-spacing: 1.2px; text-transform: uppercase; transition: all .2s ease;
}
.review-cta:hover { background: rgba(94,234,212,0.16); border-color: #5EEAD4; box-shadow: 0 0 16px rgba(94,234,212,0.18); }
.tasks__error {
  margin: 0; font-size: 11.5px; color: #FCA5A5;
  border-left: 2px solid #F87171; padding-left: 9px;
}
.tasks__empty {
  margin: 8px 2px; font-size: 12.5px; line-height: 1.5; color: rgba(167, 243, 208, 0.5);
}

/* list group */
.group { display: flex; flex-direction: column; gap: 4px; }
.group__head {
  display: flex; align-items: center; gap: 8px; padding: 0 2px 2px;
}
.group__name {
  font-family: 'JetBrains Mono', monospace; font-size: 9px; letter-spacing: 1.8px;
  text-transform: uppercase; color: rgba(94, 234, 212, 0.7);
}
.group__count {
  font-family: 'JetBrains Mono', monospace; font-size: 9px;
  color: rgba(167, 243, 208, 0.4);
  border: 0.5px solid rgba(94, 234, 212, 0.15); border-radius: 999px; padding: 0 6px;
}

.rows { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 4px; }

/* task row */
.row {
  display: flex; align-items: center; gap: 11px;
  padding: 9px 10px 9px 11px;
  border-radius: 9px;
  border: 0.5px solid rgba(255, 255, 255, 0.04);
  border-left: 2px solid var(--p, rgba(94, 234, 212, 0.4));
  background: rgba(255, 255, 255, 0.015);
  transition: background .18s ease, border-color .18s ease;
}
.row:hover { background: rgba(94, 234, 212, 0.05); }
.row.p-high { --p: #F87171; }
.row.p-med  { --p: #FBBF24; }
.row.p-low  { --p: #5EEAD4; }

.check {
  flex-shrink: 0; width: 18px; height: 18px; border-radius: 6px; cursor: pointer; padding: 0;
  display: grid; place-items: center;
  border: 1px solid rgba(94, 234, 212, 0.4); background: transparent; color: #02060A;
  transition: all .18s ease;
}
.check:hover { border-color: #5EEAD4; }
.check.on { background: #5EEAD4; border-color: #5EEAD4; }

.row__text { flex: 1; min-width: 0; font-size: 13px; color: #DCFCF5; line-height: 1.35; }
.row.done .row__text { color: rgba(167, 243, 208, 0.35); text-decoration: line-through; }
.row.done { border-left-color: rgba(94, 234, 212, 0.15); opacity: 0.8; }

.row__acts { display: flex; gap: 2px; flex-shrink: 0; }
.act {
  display: grid; place-items: center; width: 26px; height: 26px; border-radius: 7px;
  border: none; background: transparent; color: rgba(167, 243, 208, 0.45);
  cursor: pointer; opacity: 0; transition: all .15s ease;
}
.row:hover .act { opacity: 1; }
.act:hover { color: #5EEAD4; background: rgba(94, 234, 212, 0.1); }
.act.del:hover { color: #F87171; background: rgba(248, 113, 113, 0.1); }

/* add task */
.add {
  display: flex; align-items: center; gap: 8px;
  margin-top: 2px; padding: 9px 10px; border-radius: 9px;
  border: 0.5px solid rgba(94, 234, 212, 0.16); background: rgba(2, 6, 10, 0.4);
  transition: border-color .18s ease;
}
.add:focus-within { border-color: rgba(94, 234, 212, 0.5); }
.add__plus { color: #5EEAD4; font-size: 16px; line-height: 1; }
.add__input {
  flex: 1; min-width: 0; background: transparent; border: none; outline: none;
  color: #E2F5F1; font-size: 13px;
}
.add__input::placeholder { color: rgba(167, 243, 208, 0.35); }
.add__list {
  background: rgba(8, 51, 68, 0.4); color: #A7F3D0; cursor: pointer;
  border: 0.5px solid rgba(94, 234, 212, 0.18); border-radius: 7px;
  font-family: 'JetBrains Mono', monospace; font-size: 9.5px; letter-spacing: 0.5px;
  text-transform: uppercase; padding: 5px 7px; outline: none;
}
</style>
