<script setup lang="ts">
/* Tasks board — a full-screen FREE-CANVAS view of every task under each list.
 * Lists float on an absolutely-positioned canvas and can be dragged anywhere by
 * their grip (positions persisted via moveListTo). Tasks can be dragged between
 * lists (HTML5 DnD); each carries a due date + tags. Lists rename inline or are
 * removed from their ⋯ menu. Add / edit / complete / delete in place. */
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useTasks, type OlwenTask } from '../composables/useTasks'

const emit = defineEmits<{ close: [] }>()
const vFocus = { mounted: (el: HTMLElement) => el.focus() }

const {
  tasks, lists, load, add, update, moveTask,
  addList, renameList, deleteList, moveListTo, resizeList, setCollapsed, toggle, remove,
} = useTasks()
const entered = ref(false)

// ── free-canvas positioning ───────────────────────────────────────────────
const LIST_W = 290
const MIN_W = 220
const MAX_W = 720
function defaultX(i: number) { return 24 + (i % 5) * 312 }
function defaultY(i: number) { return 24 + Math.floor(i / 5) * 380 }

// live position overrides during/after a drag: { [id]: {x,y} }
const override = reactive<Record<string, { x: number; y: number }>>({})
// live width overrides during/after a resize drag: { [id]: width }
const widthOverride = reactive<Record<string, number>>({})
// transient focus view (not persisted)
const maximizedId = ref<string | null>(null)

const columns = computed(() =>
  lists.value.map((l, i) => {
    const items = tasks.value.filter(t => t.list_id === l.id)
    const ov = override[l.id]
    const x = ov?.x ?? l.pos_x ?? defaultX(i)
    const y = ov?.y ?? l.pos_y ?? defaultY(i)
    const w = widthOverride[l.id] ?? l.width ?? LIST_W
    return {
      id: l.id, name: l.name, x, y, w,
      collapsed: !!l.collapsed,
      open: items.filter(t => !t.done),
      done: items.filter(t => t.done),
    }
  }),
)

// ── list: pointer drag from the grip ──────────────────────────────────────
const draggingListId = ref<string | null>(null)
let dragStartPointer = { x: 0, y: 0 }
let dragStartPos = { x: 0, y: 0 }

function gripDown(c: { id: string; x: number; y: number }, e: PointerEvent) {
  draggingListId.value = c.id
  dragStartPointer = { x: e.clientX, y: e.clientY }
  dragStartPos = { x: c.x, y: c.y }
  ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
  e.preventDefault()
}
function gripMove(id: string, e: PointerEvent) {
  if (draggingListId.value !== id) return
  const nx = Math.max(0, dragStartPos.x + (e.clientX - dragStartPointer.x))
  const ny = Math.max(0, dragStartPos.y + (e.clientY - dragStartPointer.y))
  override[id] = { x: nx, y: ny }
}
function gripUp(id: string, e: PointerEvent) {
  if (draggingListId.value !== id) return
  try { (e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId) } catch { /* noop */ }
  draggingListId.value = null
  const pos = override[id]
  if (pos) moveListTo(id, pos.x, pos.y)   // leave override in place — matches optimistic write
}

// ── list: window-style resize from the right edge ──────────────────────────
const resizingId = ref<string | null>(null)
let resizeStartX = 0
let resizeStartW = 0

function clampW(w: number) { return Math.max(MIN_W, Math.min(MAX_W, Math.round(w))) }

function resizeDown(id: string, startW: number, e: PointerEvent) {
  e.stopPropagation(); e.preventDefault()
  resizingId.value = id
  resizeStartX = e.clientX
  resizeStartW = startW
  ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
}
function resizeMove(id: string, e: PointerEvent) {
  if (resizingId.value !== id) return
  e.stopPropagation()
  widthOverride[id] = clampW(resizeStartW + (e.clientX - resizeStartX))
}
function resizeUp(id: string, e: PointerEvent) {
  if (resizingId.value !== id) return
  e.stopPropagation()
  try { (e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId) } catch { /* noop */ }
  resizingId.value = null
  const w = widthOverride[id]
  if (w != null) resizeList(id, w)   // leave override in place — matches optimistic write
}

// ── minimize / restore (persisted) ─────────────────────────────────────────
function toggleCollapsed(c: { id: string; collapsed: boolean }) {
  menuId.value = null
  setCollapsed(c.id, !c.collapsed)
}

// ── maximize / restore (transient focus view, not persisted) ────────────────
function toggleMax(id: string) {
  menuId.value = null
  maximizedId.value = maximizedId.value === id ? null : id
}

// ── auto-arrange: masonry-pack every list into the shortest column ──────────
const scrollEl = ref<HTMLElement | null>(null)
const listEls = new Map<string, HTMLElement>()
function setListEl(id: string, el: Element | null) {
  if (el) listEls.set(id, el as HTMLElement)
  else listEls.delete(id)
}
const arranging = ref(false)

async function arrange() {
  const GAP = 22
  const MARGIN = 24
  const containerWidth = scrollEl.value?.clientWidth ?? (LIST_W + MARGIN * 2)

  // Cumulative-x row packing that respects each list's ACTUAL width.
  // Lists flow left→right; when the next list would overflow, wrap to a new
  // row whose top is the bottom of the tallest list in the row just closed.
  const plan: { id: string; x: number; y: number }[] = []
  let x = MARGIN
  let rowTop = MARGIN
  let rowBottom = MARGIN

  for (const l of lists.value) {
    if (l.id === maximizedId.value) continue   // a maximized list is excluded from arrange
    const el = listEls.get(l.id)
    const count = tasks.value.filter(t => t.list_id === l.id).length
    const h = el?.getBoundingClientRect().height || (l.collapsed ? 56 : 140 + count * 40)
    const w = widthOverride[l.id] ?? l.width ?? LIST_W

    // wrap if this list won't fit on the current row (but always place at least one per row)
    if (x !== MARGIN && x + w > containerWidth - MARGIN) {
      rowTop = rowBottom + GAP
      x = MARGIN
    }
    plan.push({ id: l.id, x, y: rowTop })
    rowBottom = Math.max(rowBottom, rowTop + h)
    x += w + GAP
  }

  // Turn on the glide transition BEFORE positions change, then apply + persist.
  arranging.value = true
  await nextTick()
  for (const p of plan) { override[p.id] = { x: p.x, y: p.y }; moveListTo(p.id, p.x, p.y) }
  if (scrollEl.value) { scrollEl.value.scrollLeft = 0; scrollEl.value.scrollTop = 0 }
  setTimeout(() => { arranging.value = false }, 520)
}

// ── add-a-task input per column ────────────────────────────────────────────
const draft = reactive<Record<string, string>>({})
function addTo(listId: string) {
  const text = (draft[listId] || '').trim()
  if (!text) return
  draft[listId] = ''
  add(listId, text)
}

// ── inline task edit ───────────────────────────────────────────────────────
const editingId = ref<string | null>(null)
const editText = ref('')
function startEdit(t: OlwenTask) { editingId.value = t.id; editText.value = t.text }
function saveEdit(t: OlwenTask) {
  const v = editText.value.trim()
  editingId.value = null
  if (v && v !== t.text) update(t, { text: v })
}

// click the priority dot to cycle high → med → low
const _next: Record<string, string> = { high: 'med', med: 'low', low: 'high' }
function cyclePriority(t: OlwenTask) { update(t, { priority: _next[t.priority] || 'med' }) }

// ── due dates ──────────────────────────────────────────────────────────────
// Parse from parts to get LOCAL midnight (avoids UTC off-by-one).
function dueInfo(due?: string | null): { label: string; tone: 'over' | 'soon' | 'far' } | null {
  if (!due) return null
  const [y, m, d] = due.split('-').map(Number)
  if (!y || !m || !d) return null
  const date = new Date(y, m - 1, d)
  const today = new Date(); today.setHours(0, 0, 0, 0)
  const diff = Math.round((date.getTime() - today.getTime()) / 86400000)
  if (diff < 0) return { label: 'Overdue', tone: 'over' }
  if (diff === 0) return { label: 'Today', tone: 'soon' }
  if (diff === 1) return { label: 'Tomorrow', tone: 'soon' }
  return { label: date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }), tone: 'far' }
}
function onDate(t: OlwenTask, e: Event) {
  const v = (e.target as HTMLInputElement).value
  if (v) update(t, { due_date: v })
  else update(t, { clear_due: true })
}
function clearDate(t: OlwenTask) { update(t, { clear_due: true }) }

// Full due label (for the popover header) — distinct from the compact chip.
function dueFull(due?: string | null): string | null {
  if (!due) return null
  const [y, m, d] = due.split('-').map(Number)
  if (!y || !m || !d) return null
  return new Date(y, m - 1, d).toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })
}

// ── editor popover (due + tags) ──────────────────────────────────────────────
const editorId = ref<string | null>(null)
const showDatePick = ref(false)
const tagText = ref('')
function openEditor(t: OlwenTask) {
  editorId.value = editorId.value === t.id ? null : t.id
  showDatePick.value = false
  tagText.value = ''
}
function closeEditor() { editorId.value = null; showDatePick.value = false; tagText.value = '' }

// Quick-pick: compute the ISO date from LOCAL parts (no UTC off-by-one).
function isoIn(days: number): string {
  const d = new Date(); d.setHours(0, 0, 0, 0); d.setDate(d.getDate() + days)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
function pickQuick(t: OlwenTask, days: number) { update(t, { due_date: isoIn(days) }) }

// ── tags ───────────────────────────────────────────────────────────────────
function addTag(t: OlwenTask) {
  const v = tagText.value.trim()
  tagText.value = ''
  if (!v) return
  const cur = t.tags || []
  if (cur.includes(v)) return
  update(t, { tags: [...cur, v] })
}
function removeTag(t: OlwenTask, tag: string) {
  update(t, { tags: (t.tags || []).filter(x => x !== tag) })
}

// ── list: rename inline ────────────────────────────────────────────────────
const renamingId = ref<string | null>(null)
const renameText = ref('')
function startRename(id: string, name: string) {
  menuId.value = null
  renamingId.value = id; renameText.value = name
}
function saveRename(id: string, original: string) {
  const v = renameText.value.trim()
  renamingId.value = null
  if (v && v !== original) renameList(id, v)
}

// ── list: ⋯ options menu + delete ──────────────────────────────────────────
const menuId = ref<string | null>(null)
function toggleMenu(id: string) { menuId.value = menuId.value === id ? null : id }
function removeList(id: string, name: string) {
  menuId.value = null
  // eslint-disable-next-line no-alert
  if (window.confirm(`Delete the "${name}" list and all its tasks?`)) deleteList(id)
}

// ── new list ───────────────────────────────────────────────────────────────
const newListName = ref('')
const addingList = ref(false)
function createList() {
  const n = newListName.value.trim()
  if (!n) { addingList.value = false; return }
  newListName.value = ''; addingList.value = false
  addList(n)
}

// ── drag & drop: move tasks between lists (HTML5 DnD) ──────────────────────
const dragTask = ref<OlwenTask | null>(null)
const overListId = ref<string | null>(null)

function taskDragStart(t: OlwenTask, e: DragEvent) {
  dragTask.value = t
  e.dataTransfer?.setData('text/plain', t.id)
  if (e.dataTransfer) e.dataTransfer.effectAllowed = 'move'
}
function colDragOver(id: string, e: DragEvent) {
  if (!dragTask.value) return
  e.preventDefault()
  if (e.dataTransfer) e.dataTransfer.dropEffect = 'move'
  overListId.value = id
}
function colDrop(targetId: string) {
  if (dragTask.value) moveTask(dragTask.value, targetId)
  resetDrag()
}
function resetDrag() { dragTask.value = null; overListId.value = null }

// ── shell ──────────────────────────────────────────────────────────────────
function close() { entered.value = false; setTimeout(() => emit('close'), 300) }
function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    if (editorId.value) { closeEditor(); return }
    if (menuId.value) { menuId.value = null; return }
    if (maximizedId.value) { maximizedId.value = null; return }
    if (renamingId.value || editingId.value) return
    if ((document.activeElement as HTMLElement)?.closest?.('.tb-add, .tb-edit, .tb-newlist, .tb-tag-input, .tb-date-input')) return
    close()
  }
}
function onDocClick() { menuId.value = null; closeEditor() }

onMounted(() => {
  load()
  requestAnimationFrame(() => { entered.value = true })
  document.addEventListener('keydown', onKey)
  document.addEventListener('click', onDocClick)
})
onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKey)
  document.removeEventListener('click', onDocClick)
})
</script>

<template>
  <div class="tb" :class="{ entered }">
    <header class="tb-bar">
      <div class="tb-brand"><span class="tb-dot" /> TASKS</div>
      <div class="tb-meta">{{ tasks.filter(t => !t.done).length }} open · {{ lists.length }} lists · drag lists anywhere</div>
      <button class="tb-arrange-btn" title="Tidy the board" @click.stop="arrange">
        <span class="tb-arrange-icon">▦</span> Arrange
      </button>
      <button v-if="!addingList" class="tb-newlist-btn" @click.stop="addingList = true">＋ New list</button>
      <input v-else v-model="newListName" class="tb-newlist" placeholder="list name…"
             @keyup.enter="createList" @blur="createList" @keyup.esc="addingList = false" @click.stop v-focus>
      <button class="tb-x" title="Close (Esc)" @click="close">✕</button>
    </header>

    <div v-if="maximizedId" class="tb-backdrop" @click="maximizedId = null" />
    <div ref="scrollEl" class="tb-scroll">
      <div class="tb-canvas">
        <section
          v-for="c in columns"
          :key="c.id"
          :ref="el => setListEl(c.id, el as Element | null)"
          class="tb-col"
          :class="{ 'tb-col--over': overListId === c.id, 'tb-col--dragging': draggingListId === c.id, 'tb-col--editing': editorId && c.open.some(t => t.id === editorId), 'tb-col--collapsed': c.collapsed && maximizedId !== c.id, 'tb-col--max': maximizedId === c.id, 'tb-col--resizing': resizingId === c.id, arranging }"
          :style="maximizedId === c.id ? {} : { left: c.x + 'px', top: c.y + 'px', width: c.w + 'px' }"
          @dragover="colDragOver(c.id, $event)"
          @drop="colDrop(c.id)"
        >
          <div class="tb-col-head">
            <span
              class="tb-grip"
              title="Drag to move this list"
              @pointerdown="gripDown(c, $event)"
              @pointermove="gripMove(c.id, $event)"
              @pointerup="gripUp(c.id, $event)"
            >⠿</span>

            <input
              v-if="renamingId === c.id"
              v-model="renameText"
              class="tb-rename"
              @keyup.enter="saveRename(c.id, c.name)"
              @blur="saveRename(c.id, c.name)"
              @keyup.esc="renamingId = null"
              v-focus
            >
            <span v-else class="tb-col-name" title="Click to rename" @click="startRename(c.id, c.name)">{{ c.name }}</span>

            <span class="tb-col-count">{{ c.open.length }}</span>
            <span v-if="c.collapsed && maximizedId !== c.id" class="tb-col-pill">{{ c.open.length + c.done.length }} task{{ (c.open.length + c.done.length) === 1 ? '' : 's' }}</span>

            <div class="tb-wctrls">
              <button
                class="tb-wbtn"
                :title="c.collapsed ? 'Restore' : 'Minimize'"
                @click.stop="toggleCollapsed(c)"
              >{{ c.collapsed ? '▢' : '–' }}</button>
              <button
                class="tb-wbtn"
                :title="maximizedId === c.id ? 'Restore (Esc)' : 'Maximize'"
                @click.stop="toggleMax(c.id)"
              >{{ maximizedId === c.id ? '❐' : '□' }}</button>
            </div>

            <div class="tb-menu-wrap" @click.stop>
              <button class="tb-menu-btn" title="List options" @click="toggleMenu(c.id)">⋯</button>
              <div v-if="menuId === c.id" class="tb-menu">
                <button @click="startRename(c.id, c.name)">Rename</button>
                <button @click="toggleCollapsed(c)">{{ c.collapsed ? 'Restore' : 'Minimize' }}</button>
                <button class="tb-menu-del" @click="removeList(c.id, c.name)">Delete list</button>
              </div>
            </div>
          </div>

          <template v-if="maximizedId === c.id || !c.collapsed">
          <ul class="tb-list">
            <li
              v-for="t in c.open"
              :key="t.id"
              class="tb-task"
              :data-p="t.priority"
              :class="{ 'tb-task--drag': dragTask?.id === t.id }"
              draggable="true"
              @dragstart.stop="taskDragStart(t, $event)"
              @dragend="resetDrag"
            >
              <div class="tb-task-main">
                <button class="tb-check" title="Complete" @click="toggle(t)" />
                <span class="tb-pri" :data-p="t.priority" title="Priority — click to change" @click="cyclePriority(t)" />
                <input v-if="editingId === t.id" v-model="editText" class="tb-edit"
                       @keyup.enter="saveEdit(t)" @blur="saveEdit(t)" @keyup.esc="editingId = null" v-focus>
                <span v-else class="tb-text" @click="startEdit(t)">{{ t.text }}</span>

                <button
                  class="tb-edit-trigger"
                  :class="{ 'is-open': editorId === t.id }"
                  title="Due date & tags"
                  @click.stop="openEditor(t)"
                >⋯</button>
                <button class="tb-del" title="Delete" @click="remove(t)">✕</button>
              </div>

              <div v-if="dueInfo(t.due_date) || (t.tags && t.tags.length)" class="tb-meta-row">
                <span
                  v-if="dueInfo(t.due_date)"
                  class="tb-due"
                  :data-tone="dueInfo(t.due_date)!.tone"
                >{{ dueInfo(t.due_date)!.label }}</span>
                <span v-for="tag in (t.tags || [])" :key="tag" class="tb-tag">{{ tag }}</span>
              </div>

              <!-- editor popover: due + tags -->
              <div v-if="editorId === t.id" class="tb-editor" @click.stop>
                <section class="tb-ed-sec">
                  <div class="tb-ed-label">
                    Due
                    <span v-if="dueFull(t.due_date)" class="tb-ed-current">{{ dueFull(t.due_date) }}</span>
                  </div>
                  <div class="tb-ed-chips">
                    <button class="tb-ed-chip" @click="pickQuick(t, 0)">Today</button>
                    <button class="tb-ed-chip" @click="pickQuick(t, 1)">Tomorrow</button>
                    <button class="tb-ed-chip" @click="pickQuick(t, 7)">+1 week</button>
                    <button class="tb-ed-chip" :class="{ 'is-on': showDatePick }" @click="showDatePick = !showDatePick">Pick…</button>
                    <button v-if="t.due_date" class="tb-ed-chip tb-ed-chip--clear" @click="clearDate(t)">Clear</button>
                  </div>
                  <input
                    v-if="showDatePick"
                    class="tb-date-input"
                    type="date"
                    :value="t.due_date || ''"
                    @change="onDate(t, $event)"
                  >
                </section>

                <section class="tb-ed-sec">
                  <div class="tb-ed-label">Tags</div>
                  <div v-if="t.tags && t.tags.length" class="tb-ed-chips">
                    <span v-for="tag in t.tags" :key="tag" class="tb-tag tb-tag--editable">
                      {{ tag }}
                      <button class="tb-tag-x" title="Remove tag" @click="removeTag(t, tag)">✕</button>
                    </span>
                  </div>
                  <input
                    v-model="tagText"
                    class="tb-tag-input"
                    placeholder="add tag…"
                    @keyup.enter="addTag(t)"
                  >
                </section>
              </div>
            </li>

            <li v-for="t in c.done" :key="t.id" class="tb-task tb-task--done">
              <div class="tb-task-main">
                <button class="tb-check tb-check--on" title="Reopen" @click="toggle(t)">✓</button>
                <span class="tb-text">{{ t.text }}</span>
                <button class="tb-del" title="Delete" @click="remove(t)">✕</button>
              </div>
            </li>

            <li v-if="!c.open.length && !c.done.length" class="tb-empty">Nothing here yet — drop a task or add one.</li>
          </ul>

          <div class="tb-add">
            <input v-model="draft[c.id]" placeholder="+ add a task…" @keyup.enter="addTo(c.id)">
          </div>
          </template>

          <span
            v-if="maximizedId !== c.id"
            class="tb-resize"
            title="Drag to resize"
            @pointerdown="resizeDown(c.id, c.w, $event)"
            @pointermove="resizeMove(c.id, $event)"
            @pointerup="resizeUp(c.id, $event)"
          />
        </section>
      </div>
    </div>
  </div>
</template>

<style scoped>
.tb { position: fixed; inset: 0; z-index: 70; background: var(--bg); color: var(--text);
  font-family: system-ui, -apple-system, 'Segoe UI', sans-serif; display: flex; flex-direction: column;
  opacity: 0; transition: opacity .3s ease; }
.tb.entered { opacity: 1; }
.tb-bar { display: flex; align-items: center; gap: 1rem; padding: .9rem 1.4rem; border-bottom: 1px solid var(--border-strong); }
.tb-brand { display: flex; align-items: center; gap: .55rem; font-family: 'JetBrains Mono', monospace; letter-spacing: .3em; font-size: .82rem; color: var(--accent); }
.tb-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--accent); box-shadow: var(--glow); }
.tb-meta { font-family: 'JetBrains Mono', monospace; font-size: .72rem; color: var(--text-muted); letter-spacing: .06em; }
.tb-x { background: none; border: 1px solid var(--border-strong); color: var(--text-muted); border-radius: 8px; width: 30px; height: 30px; cursor: pointer; font-size: .9rem; }
.tb-x:hover { color: #FCA5A5; border-color: #7F1D1D; }

/* arrange + new-list in the toolbar */
.tb-arrange-btn { margin-left: auto; display: inline-flex; align-items: center; gap: .4rem; background: none; border: 1px solid var(--border-strong); color: var(--text-muted); font: inherit; font-size: .78rem; cursor: pointer; padding: .35rem .7rem; border-radius: 8px; transition: color .15s ease, border-color .15s ease; }
.tb-arrange-btn:hover { color: var(--accent); border-color: var(--accent); }
.tb-arrange-icon { font-size: .9rem; line-height: 1; opacity: .85; }
.tb-newlist-btn { background: none; border: 1px solid var(--border-strong); color: var(--accent); font: inherit; font-size: .78rem; cursor: pointer; padding: .35rem .7rem; border-radius: 8px; }
.tb-newlist-btn:hover { color: var(--accent-2); border-color: var(--accent); }
.tb-newlist { background: var(--bg); border: 1px solid var(--accent); border-radius: 8px; color: var(--text-strong); font: inherit; font-size: .8rem; padding: .35rem .6rem; outline: none; }

/* ── free canvas ── */
.tb-scroll { flex: 1; overflow: auto; }
.tb-canvas { position: relative; min-width: 2400px; min-height: 1400px; }

.tb-col { position: absolute; width: 290px; background: var(--surface-solid); border: 1px solid var(--border-strong); border-radius: 14px; padding: .9rem; display: flex; flex-direction: column; min-height: 120px;
  transition: border-color .15s ease, box-shadow .15s ease, transform .12s ease; }
.tb-col--over { border-color: var(--accent); box-shadow: 0 0 0 2px color-mix(in srgb, var(--accent) 35%, transparent); }
.tb-col--dragging { z-index: 50; transform: scale(1.02); box-shadow: 0 18px 48px rgba(0,0,0,.45); }
.tb-col--editing { z-index: 40; }
.tb-col--resizing { z-index: 50; transition: none; }
.tb-col--collapsed { min-height: 0; padding-bottom: .9rem; }
.tb-col--collapsed .tb-col-head { margin-bottom: 0; }

/* maximized: a focus panel filling the visible board, above everything */
.tb-col--max { position: fixed; inset: 32px; width: auto !important; z-index: 62; min-height: 0; overflow: hidden;
  box-shadow: 0 30px 80px rgba(0,0,0,.55); transition: none; }
.tb-col--max .tb-list { overflow: auto; }
.tb-col--max .tb-text { white-space: normal; overflow: visible; text-overflow: clip; }
.tb-col--max .tb-task { padding: .6rem .65rem; }
.tb-backdrop { position: fixed; inset: 0; z-index: 61; background: color-mix(in srgb, var(--bg) 72%, transparent); backdrop-filter: blur(2px); }
/* glide into place during auto-arrange, then drop the transition so dragging stays snappy */
.tb-col.arranging { transition: left .5s cubic-bezier(.22,.61,.36,1), top .5s cubic-bezier(.22,.61,.36,1), border-color .15s ease, box-shadow .15s ease; }
.tb-col-head { display: flex; align-items: center; gap: .5rem; margin-bottom: .7rem; }
.tb-grip { cursor: grab; color: var(--text-muted); font-size: .9rem; line-height: 1; user-select: none; opacity: .6; touch-action: none; }
.tb-grip:hover { opacity: 1; color: var(--accent); }
.tb-grip:active { cursor: grabbing; }
.tb-col-name { font-family: 'JetBrains Mono', monospace; font-size: .72rem; letter-spacing: .18em; text-transform: uppercase; color: var(--accent-2); cursor: text; }
.tb-col-name:hover { color: var(--accent); }
.tb-rename { font-family: 'JetBrains Mono', monospace; font-size: .72rem; letter-spacing: .12em; text-transform: uppercase; background: var(--bg); border: 1px solid var(--accent); border-radius: 6px; color: var(--text-strong); padding: .15rem .4rem; outline: none; width: 60%; }
.tb-col-count { font-family: 'JetBrains Mono', monospace; font-size: .66rem; color: var(--text-muted); background: var(--surface-2); border-radius: 999px; padding: .05rem .5rem; }
.tb-col-pill { font-family: 'JetBrains Mono', monospace; font-size: .62rem; letter-spacing: .04em; color: var(--accent-2); background: color-mix(in srgb, var(--accent) 10%, transparent); border: 1px solid var(--border); border-radius: 999px; padding: .05rem .5rem; }

/* window controls — minimize + maximize, faint, solid on hover */
.tb-wctrls { display: inline-flex; align-items: center; gap: .1rem; margin-left: auto; }
.tb-wbtn { display: inline-flex; align-items: center; justify-content: center; width: 20px; height: 20px; background: none; border: none; color: var(--text-muted); cursor: pointer; font-size: .82rem; line-height: 1; border-radius: 6px; opacity: .55; transition: opacity .15s ease, color .15s ease, background .15s ease; }
.tb-wbtn:hover { opacity: 1; color: var(--accent); background: var(--surface-2); }

.tb-menu-wrap { position: relative; }
.tb-menu-btn { background: none; border: none; color: var(--text-muted); cursor: pointer; font-size: 1.1rem; line-height: 1; padding: 0 .2rem; border-radius: 6px; }
.tb-menu-btn:hover { color: var(--accent); background: var(--surface-2); }
.tb-menu { position: absolute; top: 1.5rem; right: 0; z-index: 5; min-width: 130px; background: var(--surface-solid); border: 1px solid var(--border-strong); border-radius: 10px; padding: .3rem; display: flex; flex-direction: column; box-shadow: 0 12px 30px rgba(0,0,0,.4); }
.tb-menu button { text-align: left; background: none; border: none; color: var(--text); font: inherit; font-size: .8rem; padding: .45rem .55rem; border-radius: 7px; cursor: pointer; }
.tb-menu button:hover { background: var(--surface-2); }
.tb-menu-del { color: #FCA5A5; }
.tb-menu-del:hover { background: rgba(248,113,113,.12) !important; color: #F87171; }

.tb-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: .35rem; flex: 1; }
.tb-task { position: relative; display: flex; flex-direction: column; gap: .3rem; padding: .45rem .5rem; border-radius: 9px; border: 1px solid transparent; cursor: grab; }
.tb-task:hover { background: var(--surface-2); border-color: var(--border-strong); }
.tb-task:active { cursor: grabbing; }
.tb-task--drag { opacity: .4; }
.tb-task-main { display: flex; align-items: center; gap: .55rem; }
.tb-check { width: 17px; height: 17px; flex-shrink: 0; border-radius: 6px; border: 1.5px solid var(--text-muted); background: none; cursor: pointer; color: #34D399; font-size: .7rem; line-height: 1; }
.tb-check:hover { border-color: var(--accent); }
.tb-check--on { border-color: #34D399; }
.tb-pri { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; background: var(--text-muted); cursor: pointer; }
.tb-pri[data-p='high'] { background: #FB7185; box-shadow: 0 0 8px rgba(251,113,133,.5); }
.tb-pri[data-p='med'] { background: var(--accent); }
.tb-pri[data-p='low'] { background: var(--text-muted); }
.tb-text { flex: 1; font-size: .88rem; color: var(--text); cursor: text; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tb-edit { flex: 1; background: var(--bg); border: 1px solid var(--accent); border-radius: 6px; color: var(--text-strong); font: inherit; font-size: .86rem; padding: .25rem .45rem; outline: none; }
.tb-task--done .tb-text { color: var(--text-muted); text-decoration: line-through; }
.tb-del { background: none; border: none; color: var(--text-muted); cursor: pointer; font-size: .72rem; opacity: 0; transition: opacity .15s; }
.tb-task:hover .tb-del { opacity: 1; }
.tb-del:hover { color: #FCA5A5; }
.tb-empty { color: var(--text-muted); font-size: .82rem; padding: .4rem .3rem; }

/* the single subtle trigger — faint, solid on hover/open */
.tb-edit-trigger { flex-shrink: 0; background: none; border: none; color: var(--text-muted); cursor: pointer; font-size: 1rem; line-height: 1; padding: 0 .25rem; border-radius: 6px; opacity: 0; transition: opacity .15s ease, color .15s ease, background .15s ease; }
.tb-task:hover .tb-edit-trigger { opacity: .55; }
.tb-edit-trigger:hover { opacity: 1; color: var(--accent); background: var(--surface-2); }
.tb-edit-trigger.is-open { opacity: 1; color: var(--accent); background: var(--surface-2); }

/* meta row: due chip + tags (display only) */
.tb-meta-row { display: flex; flex-wrap: wrap; align-items: center; gap: .3rem; padding-left: 1.4rem; }
.tb-due { display: inline-flex; align-items: center; font-family: 'JetBrains Mono', monospace; font-size: .64rem; letter-spacing: .04em; padding: .1rem .45rem; border-radius: 999px; border: 1px solid; }
.tb-due[data-tone='over'] { color: #F87171; border-color: color-mix(in srgb, #F87171 45%, transparent); background: color-mix(in srgb, #F87171 12%, transparent); }
.tb-due[data-tone='soon'] { color: #FBBF24; border-color: color-mix(in srgb, #FBBF24 45%, transparent); background: color-mix(in srgb, #FBBF24 12%, transparent); }
.tb-due[data-tone='far'] { color: var(--accent-2); border-color: var(--border-strong); background: var(--surface-2); }

.tb-tag { display: inline-flex; align-items: center; gap: .25rem; font-size: .66rem; padding: .1rem .45rem; border-radius: 999px; background: var(--surface-2); border: 1px solid var(--border); color: var(--text-muted); }
.tb-tag-x { background: none; border: none; color: inherit; cursor: pointer; font-size: .58rem; opacity: .55; padding: 0; line-height: 1; }
.tb-tag-x:hover { opacity: 1; color: #FCA5A5; }

/* ── editor popover ── */
.tb-editor { position: absolute; left: 50%; bottom: calc(100% + 6px); transform: translateX(-50%); z-index: 60; width: 240px; display: flex; flex-direction: column; gap: .8rem;
  background: var(--surface-solid); border: 1px solid var(--border-strong); border-radius: 12px; padding: .85rem .9rem;
  box-shadow: 0 16px 40px rgba(0,0,0,.45); cursor: default; }
.tb-ed-sec { display: flex; flex-direction: column; gap: .5rem; }
.tb-ed-label { display: flex; align-items: center; gap: .5rem; font-family: 'JetBrains Mono', monospace; font-size: .62rem; letter-spacing: .14em; text-transform: uppercase; color: var(--text-muted); }
.tb-ed-current { font-family: system-ui, sans-serif; letter-spacing: 0; text-transform: none; font-size: .68rem; color: var(--accent-2); }
.tb-ed-chips { display: flex; flex-wrap: wrap; gap: .35rem; }
.tb-ed-chip { background: var(--surface-2); border: 1px solid var(--border); color: var(--text); font: inherit; font-size: .7rem; padding: .2rem .55rem; border-radius: 999px; cursor: pointer; transition: color .15s ease, border-color .15s ease, background .15s ease; }
.tb-ed-chip:hover { color: var(--accent); border-color: var(--accent); }
.tb-ed-chip.is-on { color: var(--accent); border-color: var(--accent); background: color-mix(in srgb, var(--accent) 12%, transparent); }
.tb-ed-chip--clear { color: var(--text-muted); }
.tb-ed-chip--clear:hover { color: #F87171; border-color: color-mix(in srgb, #F87171 50%, transparent); }
.tb-tag--editable { gap: .3rem; padding: .12rem .5rem; }
.tb-tag--editable .tb-tag-x { font-size: .6rem; }
.tb-date-input { width: 100%; background: var(--bg); border: 1px solid var(--border-strong); border-radius: 8px; color: var(--text-strong); font: inherit; font-size: .76rem; padding: .35rem .5rem; outline: none; color-scheme: dark light; }
.tb-date-input:focus { border-color: var(--accent); }
.tb-tag-input { width: 100%; background: var(--bg); border: 1px solid var(--border-strong); border-radius: 8px; color: var(--text-strong); font: inherit; font-size: .76rem; padding: .35rem .5rem; outline: none; }
.tb-tag-input:focus { border-color: var(--accent); }

.tb-add { margin-top: .6rem; }
.tb-add input { width: 100%; background: var(--bg); border: 1px solid var(--border-strong); border-radius: 8px; color: var(--text); font: inherit; font-size: .84rem; padding: .45rem .6rem; outline: none; }
.tb-add input:focus { border-color: var(--accent); }

/* window-style resize grabber on the right edge */
.tb-resize { position: absolute; top: 8px; bottom: 8px; right: -3px; width: 6px; border-radius: 3px; cursor: ew-resize; touch-action: none; background: var(--border-strong); opacity: 0; transition: opacity .15s ease, background .15s ease; }
.tb-col:hover .tb-resize { opacity: .4; }
.tb-resize:hover { opacity: 1; background: var(--accent); }
.tb-col--resizing .tb-resize { opacity: 1; background: var(--accent); }
</style>
