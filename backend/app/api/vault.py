"""金库同步路由：/api/vault、/api/folders、/api/items。"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.db import get_session
from ..core.deps import get_current_user
from ..models import User
from ..schemas.vault import (
    FolderIn,
    FolderPatch,
    ImportOut,
    ImportRequest,
    ItemIn,
    ItemPatch,
    VaultOut,
)
from ..services import vault_service

router = APIRouter(tags=["vault"])


@router.get("/vault", response_model=VaultOut, summary="全量或增量拉取金库密文")
async def get_vault(
    since: int | None = Query(default=None, ge=0, description="上次同步的全局 rev，省略则全量"),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    return await vault_service.get_vault(session, user.id, since)


@router.post("/vault/import", response_model=ImportOut, summary="批量导入（三种合并策略）")
async def import_vault(
    payload: ImportRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    return await vault_service.import_vault(session, user.id, payload)


# ============================================================
# 文件夹
# ============================================================


@router.post("/folders", status_code=201, summary="新建文件夹（同 id 同内容幂等）")
async def create_folder(
    payload: FolderIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    return await vault_service.create_folder(session, user.id, payload)


@router.patch("/folders/{folder_id}", summary="更新文件夹（rev 乐观锁）")
async def patch_folder(
    folder_id: str,
    payload: FolderPatch,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    return await vault_service.patch_folder(session, user.id, folder_id, payload)


@router.delete("/folders/{folder_id}", summary="删除文件夹（软删除）")
async def delete_folder(
    folder_id: str,
    rev: int | None = Query(default=None, ge=1),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    return await vault_service.delete_folder(session, user.id, folder_id, rev)


# ============================================================
# 条目
# ============================================================


@router.post("/items", status_code=201, summary="新建条目（同 id 同内容幂等）")
async def create_item(
    payload: ItemIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    return await vault_service.create_item(session, user.id, payload)


@router.patch("/items/{item_id}", summary="更新条目（rev 乐观锁）")
async def patch_item(
    item_id: str,
    payload: ItemPatch,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    return await vault_service.patch_item(session, user.id, item_id, payload)


@router.delete("/items/{item_id}", summary="删除条目（软删除）")
async def delete_item(
    item_id: str,
    rev: int | None = Query(default=None, ge=1),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    return await vault_service.delete_item(session, user.id, item_id, rev)
