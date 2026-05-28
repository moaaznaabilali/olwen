"""Skills marketplace — browse the catalog, install/uninstall per user."""
import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import delete, select

from app.api.deps import CurrentUser, SessionDep
from app.core.security import encrypt_secret
from app.models.custom_skill import CustomSkill
from app.models.installed_skill import InstalledSkill
from app.schemas.skill import CustomSkillCreate, CustomSkillRead
from app.services.skills import catalog_by_key, load_catalog, valid_key

router = APIRouter()
_DEFAULT = "tasks"  # core skill, installed for everyone, not removable


async def _installed_keys(user_id, session: SessionDep) -> list[str]:
    rows = await session.scalars(
        select(InstalledSkill.skill_key).where(InstalledSkill.user_id == user_id)
    )
    keys = list(rows)
    # ensure the core skill is always present
    if _DEFAULT not in keys:
        session.add(InstalledSkill(user_id=user_id, skill_key=_DEFAULT))
        await session.commit()
        keys.append(_DEFAULT)
    return keys


@router.get("/catalog")
async def catalog() -> list[dict]:
    return load_catalog()


@router.get("/installed")
async def installed(user: CurrentUser, session: SessionDep) -> dict:
    return {"installed": await _installed_keys(user.id, session)}


@router.post("/installed/{key}", status_code=status.HTTP_201_CREATED)
async def install(key: str, user: CurrentUser, session: SessionDep) -> dict:
    if not valid_key(key):
        raise HTTPException(status_code=404, detail="Unknown skill")
    existing = await session.scalar(
        select(InstalledSkill).where(
            InstalledSkill.user_id == user.id, InstalledSkill.skill_key == key
        )
    )
    if existing is None:
        session.add(InstalledSkill(user_id=user.id, skill_key=key))
        await session.commit()
    return {"installed": await _installed_keys(user.id, session)}


@router.delete("/installed/{key}")
async def uninstall(key: str, user: CurrentUser, session: SessionDep) -> dict:
    if key == _DEFAULT:
        raise HTTPException(status_code=400, detail="The core skill can't be removed")
    await session.execute(
        delete(InstalledSkill).where(
            InstalledSkill.user_id == user.id, InstalledSkill.skill_key == key
        )
    )
    await session.commit()
    return {"installed": await _installed_keys(user.id, session)}


# ---- custom skills (e.g. a remote MCP server URL) ----
@router.get("/custom", response_model=list[CustomSkillRead])
async def list_custom(user: CurrentUser, session: SessionDep) -> list[CustomSkill]:
    rows = await session.scalars(
        select(CustomSkill).where(CustomSkill.user_id == user.id).order_by(CustomSkill.created_at.desc())
    )
    return list(rows)


@router.post("/custom", response_model=CustomSkillRead, status_code=status.HTTP_201_CREATED)
async def add_custom(data: CustomSkillCreate, user: CurrentUser, session: SessionDep) -> CustomSkill:
    cs = CustomSkill(
        user_id=user.id,
        name=data.name.strip(),
        url=data.url.strip(),
        auth_enc=encrypt_secret(data.auth) if data.auth else None,
    )
    session.add(cs)
    await session.commit()
    await session.refresh(cs)
    return cs


@router.delete("/custom/{custom_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_custom(custom_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> None:
    cs = await session.get(CustomSkill, custom_id)
    if cs is None or cs.user_id != user.id:
        raise HTTPException(status_code=404, detail="Custom skill not found")
    await session.delete(cs)
    await session.commit()
