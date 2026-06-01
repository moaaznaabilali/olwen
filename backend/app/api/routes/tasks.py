"""Task management — lists + tasks, per user."""
import json
import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from app.api.deps import CurrentUser, SessionDep
from app.core.security import decrypt_secret
from app.models.task import Task, TaskList
from app.models.user import User
from app.schemas.task import (
    ListReorder,
    TaskCreate,
    TaskListCreate,
    TaskListRead,
    TaskListUpdate,
    TaskRead,
    TaskUpdate,
)
from app.services.olwen_ai import stream_reply

router = APIRouter()
_PRIORITIES = {"high", "med", "low"}


def _resolve_llm(user: User) -> tuple[str | None, str | None]:
    """The user's active provider + decrypted key (or None for mock/fallback)."""
    enc = {
        "claude": user.llm_api_key_enc,
        "gemini": user.gemini_key_enc,
        "groq": user.groq_key_enc,
    }.get(user.llm_provider or "")
    return (user.llm_provider, decrypt_secret(enc)) if enc else (None, None)


def _parse_review(text: str, n: int) -> tuple[list[str], int, str]:
    """Pull {suggestions:[...], start:int, why:str} out of the model's reply.

    Returns (suggestions, start_index_0based, why). Defensive against bad JSON.
    """
    suggestions: list[str] = []
    start_idx = 0
    why = ""
    try:
        s, e = text.index("{"), text.rindex("}") + 1
        obj = json.loads(text[s:e])
        raw = obj.get("suggestions")
        if isinstance(raw, list):
            suggestions = [str(x).strip() for x in raw]
        start = obj.get("start")
        if isinstance(start, (int, float)) and 1 <= int(start) <= n:
            start_idx = int(start) - 1
        why = str(obj.get("why", "")).strip()
    except Exception:
        pass
    while len(suggestions) < n:
        suggestions.append("Break it into a small first step you can do today.")
    return suggestions[:n], start_idx, why


async def _ensure_seed(user_id: uuid.UUID, session: SessionDep) -> None:
    """First-time users get a couple of starter lists so the panel isn't empty."""
    existing = await session.scalar(select(TaskList).where(TaskList.user_id == user_id).limit(1))
    if existing:
        return
    work = TaskList(user_id=user_id, name="Work")
    personal = TaskList(user_id=user_id, name="Personal")
    session.add_all([work, personal])
    await session.flush()
    session.add_all([
        Task(user_id=user_id, list_id=work.id, text="Review Q3 deck for Sarah", priority="high"),
        Task(user_id=user_id, list_id=work.id, text="Reply to investor email", priority="high"),
        Task(user_id=user_id, list_id=work.id, text="Fix login token refresh", priority="med"),
        Task(user_id=user_id, list_id=personal.id, text="Renew olwen.app domain", priority="med"),
    ])
    await session.commit()


async def _to_read(task: Task, list_name: str) -> TaskRead:
    return TaskRead(
        id=task.id, list_id=task.list_id, list_name=list_name,
        text=task.text, priority=task.priority, done=task.done,
        due_date=task.due_date, tags=list(task.tags or []),
        created_at=task.created_at,
    )


@router.get("/lists", response_model=list[TaskListRead])
async def get_lists(user: CurrentUser, session: SessionDep) -> list[TaskList]:
    await _ensure_seed(user.id, session)
    rows = await session.scalars(
        select(TaskList)
        .where(TaskList.user_id == user.id)
        .order_by(TaskList.position, TaskList.created_at)
    )
    return list(rows)


async def _owned_list(list_id: uuid.UUID, user_id: uuid.UUID, session: SessionDep) -> TaskList:
    tl = await session.get(TaskList, list_id)
    if tl is None or tl.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="List not found.")
    return tl


@router.post("/lists", response_model=TaskListRead, status_code=status.HTTP_201_CREATED)
async def create_list(data: TaskListCreate, user: CurrentUser, session: SessionDep) -> TaskList:
    top = await session.scalar(
        select(func.max(TaskList.position)).where(TaskList.user_id == user.id)
    )
    tl = TaskList(user_id=user.id, name=data.name, position=(top or 0) + 1)
    session.add(tl)
    await session.commit()
    await session.refresh(tl)
    return tl


@router.patch("/lists/{list_id}", response_model=TaskListRead)
async def update_list(
    list_id: uuid.UUID, data: TaskListUpdate, user: CurrentUser, session: SessionDep
) -> TaskList:
    tl = await _owned_list(list_id, user.id, session)
    if data.name is not None:
        tl.name = data.name
    if data.position is not None:
        tl.position = data.position
    if data.pos_x is not None:
        tl.pos_x = data.pos_x
    if data.pos_y is not None:
        tl.pos_y = data.pos_y
    if data.width is not None:
        tl.width = data.width
    if data.collapsed is not None:
        tl.collapsed = data.collapsed
    await session.commit()
    await session.refresh(tl)
    return tl


@router.delete("/lists/{list_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_list(list_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> None:
    tl = await _owned_list(list_id, user.id, session)
    await session.delete(tl)  # tasks cascade via FK ondelete=CASCADE
    await session.commit()


@router.post("/lists/reorder", response_model=list[TaskListRead])
async def reorder_lists(
    data: ListReorder, user: CurrentUser, session: SessionDep
) -> list[TaskList]:
    """Persist a new column order. Body is the full ordered list of list ids."""
    owned = await session.scalars(
        select(TaskList).where(TaskList.user_id == user.id)
    )
    by_id = {tl.id: tl for tl in owned}
    for idx, lid in enumerate(data.ids):
        tl = by_id.get(lid)
        if tl is not None:
            tl.position = idx
    await session.commit()
    rows = await session.scalars(
        select(TaskList)
        .where(TaskList.user_id == user.id)
        .order_by(TaskList.position, TaskList.created_at)
    )
    return list(rows)


@router.get("", response_model=list[TaskRead])
async def get_tasks(
    user: CurrentUser, session: SessionDep, list_id: uuid.UUID | None = None
) -> list[TaskRead]:
    """All tasks (combined main view), or one list when list_id is given."""
    await _ensure_seed(user.id, session)
    stmt = (
        select(Task, TaskList.name)
        .join(TaskList, Task.list_id == TaskList.id)
        .where(Task.user_id == user.id)
        .order_by(Task.done, TaskList.position, TaskList.created_at, Task.created_at)
    )
    if list_id is not None:
        stmt = stmt.where(Task.list_id == list_id)
    result = await session.execute(stmt)
    return [await _to_read(task, name) for task, name in result.all()]


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
async def create_task(data: TaskCreate, user: CurrentUser, session: SessionDep) -> TaskRead:
    tl = await session.get(TaskList, data.list_id)
    if tl is None or tl.user_id != user.id:
        raise HTTPException(status_code=404, detail="List not found")
    priority = data.priority if data.priority in _PRIORITIES else "med"
    task = Task(
        user_id=user.id, list_id=data.list_id, text=data.text, priority=priority,
        due_date=data.due_date, tags=(data.tags or None),
    )
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return await _to_read(task, tl.name)


async def _owned_task(task_id: uuid.UUID, user_id: uuid.UUID, session: SessionDep) -> Task:
    task = await session.get(Task, task_id)
    if task is None or task.user_id != user_id:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.patch("/{task_id}", response_model=TaskRead)
async def update_task(
    task_id: uuid.UUID, data: TaskUpdate, user: CurrentUser, session: SessionDep
) -> TaskRead:
    task = await _owned_task(task_id, user.id, session)
    if data.text is not None:
        task.text = data.text
    if data.priority in _PRIORITIES:
        task.priority = data.priority
    if data.done is not None:
        task.done = data.done
    if data.list_id is not None and data.list_id != task.list_id:
        await _owned_list(data.list_id, user.id, session)  # verify target is the user's
        task.list_id = data.list_id
    if data.clear_due:
        task.due_date = None
    elif data.due_date is not None:
        task.due_date = data.due_date
    if data.tags is not None:
        task.tags = data.tags or None
    await session.commit()
    await session.refresh(task)
    tl = await session.get(TaskList, task.list_id)
    return await _to_read(task, tl.name if tl else "")


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(task_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> None:
    task = await _owned_task(task_id, user.id, session)
    await session.delete(task)
    await session.commit()


@router.post("/review")
async def review_tasks(user: CurrentUser, session: SessionDep) -> dict:
    """ONE LLM call: a short concrete suggestion for every open task.

    Powers the cinematic 'work mode' on the frontend without burning tokens
    per task (all suggestions come back in a single request).
    """
    await _ensure_seed(user.id, session)
    result = await session.execute(
        select(Task, TaskList.name)
        .join(TaskList, Task.list_id == TaskList.id)
        .where(Task.user_id == user.id, Task.done.is_(False))
        .order_by(TaskList.created_at, Task.created_at)
    )
    items = result.all()
    if not items:
        return {"tasks": []}

    listing = "\n".join(
        f"{i + 1}. {t.text} (priority {t.priority}, list {name})"
        for i, (t, name) in enumerate(items)
    )
    prompt = (
        "Here are my open tasks:\n" + listing
        + "\n\nReturn ONLY a JSON object with exactly these keys:\n"
        '{"suggestions": [one short concrete next step per task, SAME order, '
        'max ~14 words, imperative], '
        '"start": <the task NUMBER that is most important to do first>, '
        '"why": "<one short sentence on why to start there>"}\n'
        "No text outside the JSON."
    )
    provider, key = _resolve_llm(user)
    chunks: list[str] = []
    async for c in stream_reply(prompt, provider=provider, api_key=key):
        chunks.append(c)
    suggestions, start_idx, why = _parse_review("".join(chunks), len(items))

    return {
        "start_index": start_idx,
        "start_reason": why,
        "tasks": [
            {
                "id": str(t.id),
                "text": t.text,
                "priority": t.priority,
                "list_name": name,
                "suggestion": suggestions[i],
            }
            for i, (t, name) in enumerate(items)
        ],
    }
