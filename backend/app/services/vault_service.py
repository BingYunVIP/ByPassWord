"""金库同步业务逻辑。

设计要点：
- 每个用户一个全局递增 `rev`（vault_state），写入时自增并打到记录上；
- 客户端用 `since` 拉增量，用记录 `rev` 做乐观锁；
- 删除是软删除，增量拉取会把「墓碑」一起下发，避免多端同步时数据复活。
"""

import asyncio
from functools import wraps
from uuid import uuid4

from sqlalchemy import insert, select, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.errors import ApiError, not_found
from ..models import Folder, Item, UserSettings, VaultState
from ..models.base import utcnow
from ..schemas.vault import (
    FolderIn,
    FolderPatch,
    ImportRequest,
    ItemIn,
    ItemPatch,
    SettingsIn,
)


def _folder_out(folder: Folder) -> dict:
    return {
        "id": folder.id,
        "ciphertext": folder.ciphertext,
        "nonce": folder.nonce,
        "sortOrder": folder.sort_order,
        "rev": folder.rev,
        "updatedAt": folder.updated_at.isoformat(),
        "deletedAt": folder.deleted_at.isoformat() if folder.deleted_at else None,
    }


def _item_out(item: Item) -> dict:
    return {
        "id": item.id,
        "ciphertext": item.ciphertext,
        "nonce": item.nonce,
        "rev": item.rev,
        "updatedAt": item.updated_at.isoformat(),
        "deletedAt": item.deleted_at.isoformat() if item.deleted_at else None,
    }


async def _current_rev(session: AsyncSession, user_id: str) -> int:
    rev = await session.scalar(select(VaultState.rev).where(VaultState.user_id == user_id))
    return rev if rev is not None else 0


async def _lock_vault(session: AsyncSession, user_id: str) -> None:
    """Serialize a user's writes in the database, including first initialization.

    The no-op UPDATE holds the row/write lock until commit or rollback. This
    works across processes; a Python lock would only protect one worker.
    """
    values = {"user_id": user_id, "rev": 0, "updated_at": utcnow()}
    dialect = session.get_bind().dialect.name
    if dialect in {"sqlite", "postgresql"}:
        if dialect == "sqlite":
            from sqlalchemy.dialects.sqlite import insert as upsert
        else:
            from sqlalchemy.dialects.postgresql import insert as upsert
        await session.execute(upsert(VaultState).values(**values).on_conflict_do_nothing(
            index_elements=[VaultState.user_id]))
    else:
        try:
            async with session.begin_nested():
                await session.execute(insert(VaultState).values(**values))
        except IntegrityError:
            pass
    await session.execute(update(VaultState).where(VaultState.user_id == user_id)
                          .values(rev=VaultState.rev, updated_at=VaultState.updated_at)
                          .execution_options(synchronize_session=False))


def _vault_write(function):
    @wraps(function)
    async def serialized(session: AsyncSession, user_id: str, *args, **kwargs):
        for attempt in range(3):
            try:
                await _lock_vault(session, user_id)
                return await function(session, user_id, *args, **kwargs)
            except OperationalError as exc:
                await session.rollback()
                # Retry only SQLite lock contention, never arbitrary DB errors.
                if (getattr(exc.orig, "sqlite_errorcode", 0) & 255) not in {5, 6}:
                    raise
                if attempt == 2:
                    raise ApiError(409, "vault_busy", "金库正在更新，请稍后重新同步再试") from exc
                await asyncio.sleep(.02 * (attempt + 1))
            except IntegrityError as exc:
                # Includes record-ID collisions with another user's concurrent
                # create. Never expose database errors or commit partial imports.
                await session.rollback()
                raise _conflict(0) from exc
            except Exception:
                await session.rollback()
                raise
    return serialized


async def _bump_rev(session: AsyncSession, user_id: str) -> int:
    await session.flush()
    result = await session.execute(update(VaultState).where(VaultState.user_id == user_id)
                                   .values(rev=VaultState.rev + 1, updated_at=utcnow())
                                   .returning(VaultState.rev)
                                   .execution_options(synchronize_session=False))
    return result.scalar_one()


async def _record(session, model, record_id):
    # Refresh any identity-map entry so a preceding authentication/read does not
    # leave stale state after waiting for another transaction's write lock.
    return await session.scalar(select(model).where(model.id == record_id)
                                .execution_options(populate_existing=True))


def _conflict(current_rev: int) -> ApiError:
    return ApiError(
        409,
        "rev_conflict",
        "数据已在别处更新，请重新拉取后再试",
        {"rev": current_rev},
    )


# ============================================================
# 拉取
# ============================================================


async def get_vault(session: AsyncSession, user_id: str, since: int | None) -> dict:
    rev = await _current_rev(session, user_id)

    folder_stmt = select(Folder).where(Folder.user_id == user_id)
    item_stmt = select(Item).where(Item.user_id == user_id)

    if since is None:
        # 全量：只给未删除的（客户端会用全量结果覆盖本地）
        folder_stmt = folder_stmt.where(Folder.deleted_at.is_(None))
        item_stmt = item_stmt.where(Item.deleted_at.is_(None))
    else:
        # 增量：包含软删除墓碑
        folder_stmt = folder_stmt.where(Folder.rev > since)
        item_stmt = item_stmt.where(Item.rev > since)

    folders = (await session.scalars(folder_stmt.order_by(Folder.sort_order, Folder.id))).all()
    items = (await session.scalars(item_stmt.order_by(Item.id))).all()

    return {
        "rev": rev,
        "folders": [_folder_out(f) for f in folders],
        "items": [_item_out(i) for i in items],
    }


# ============================================================
# 文件夹
# ============================================================


@_vault_write
async def create_folder(session: AsyncSession, user_id: str, payload: FolderIn) -> dict:
    existing = await _record(session, Folder, payload.id)
    if existing is not None:
        if existing.user_id != user_id:
            raise _conflict(0)
        if (existing.deleted_at is None and existing.ciphertext == payload.ciphertext
                and existing.nonce == payload.nonce
                and existing.sort_order == payload.sortOrder):
            return {"id": existing.id, "rev": existing.rev}  # 幂等
        raise _conflict(existing.rev)

    rev = await _bump_rev(session, user_id)
    folder = Folder(
        id=payload.id,
        user_id=user_id,
        ciphertext=payload.ciphertext,
        nonce=payload.nonce,
        sort_order=payload.sortOrder,
        rev=rev,
    )
    session.add(folder)
    await session.commit()
    return {"id": folder.id, "rev": folder.rev}


@_vault_write
async def patch_folder(
    session: AsyncSession, user_id: str, folder_id: str, payload: FolderPatch
) -> dict:
    folder = await _record(session, Folder, folder_id)
    if folder is None or folder.user_id != user_id or folder.deleted_at is not None:
        raise not_found("文件夹不存在")
    if folder.rev != payload.rev:
        raise _conflict(folder.rev)

    next_rev = await _bump_rev(session, user_id)
    values = {"ciphertext": payload.ciphertext, "nonce": payload.nonce,
              "rev": next_rev, "updated_at": utcnow()}
    if payload.sortOrder is not None:
        values["sort_order"] = payload.sortOrder
    changed = await session.execute(update(Folder).where(
        Folder.id == folder_id, Folder.user_id == user_id, Folder.rev == payload.rev,
        Folder.deleted_at.is_(None)).values(**values).execution_options(synchronize_session=False))
    if changed.rowcount != 1:
        raise _conflict(folder.rev)
    await session.commit()
    return {"id": folder_id, "rev": next_rev}


@_vault_write
async def delete_folder(
    session: AsyncSession, user_id: str, folder_id: str, rev: int | None
) -> dict:
    folder = await _record(session, Folder, folder_id)
    if folder is None or folder.user_id != user_id or folder.deleted_at is not None:
        raise not_found("文件夹不存在")
    if rev is not None and folder.rev != rev:
        raise _conflict(folder.rev)

    next_rev = await _bump_rev(session, user_id)
    deleted_at = utcnow()
    changed = await session.execute(update(Folder).where(
        Folder.id == folder_id, Folder.user_id == user_id, Folder.rev == folder.rev,
        Folder.deleted_at.is_(None)).values(deleted_at=deleted_at, rev=next_rev, updated_at=deleted_at)
        .execution_options(synchronize_session=False))
    if changed.rowcount != 1:
        raise _conflict(folder.rev)
    await session.commit()
    return {"id": folder_id, "rev": next_rev, "deletedAt": deleted_at.isoformat()}


# ============================================================
# 条目
# ============================================================


@_vault_write
async def create_item(session: AsyncSession, user_id: str, payload: ItemIn) -> dict:
    existing = await _record(session, Item, payload.id)
    if existing is not None:
        if existing.user_id != user_id:
            raise _conflict(0)
        if (existing.deleted_at is None and existing.ciphertext == payload.ciphertext
                and existing.nonce == payload.nonce):
            return {"id": existing.id, "rev": existing.rev}
        raise _conflict(existing.rev)

    rev = await _bump_rev(session, user_id)
    item = Item(
        id=payload.id,
        user_id=user_id,
        ciphertext=payload.ciphertext,
        nonce=payload.nonce,
        rev=rev,
    )
    session.add(item)
    await session.commit()
    return {"id": item.id, "rev": item.rev}


@_vault_write
async def patch_item(
    session: AsyncSession, user_id: str, item_id: str, payload: ItemPatch
) -> dict:
    item = await _record(session, Item, item_id)
    if item is None or item.user_id != user_id or item.deleted_at is not None:
        raise not_found("条目不存在")
    if item.rev != payload.rev:
        raise _conflict(item.rev)

    next_rev = await _bump_rev(session, user_id)
    changed = await session.execute(update(Item).where(
        Item.id == item_id, Item.user_id == user_id, Item.rev == payload.rev,
        Item.deleted_at.is_(None)).values(ciphertext=payload.ciphertext, nonce=payload.nonce,
                                          rev=next_rev, updated_at=utcnow())
        .execution_options(synchronize_session=False))
    if changed.rowcount != 1:
        raise _conflict(item.rev)
    await session.commit()
    return {"id": item_id, "rev": next_rev}


@_vault_write
async def delete_item(session: AsyncSession, user_id: str, item_id: str, rev: int | None) -> dict:
    item = await _record(session, Item, item_id)
    if item is None or item.user_id != user_id or item.deleted_at is not None:
        raise not_found("条目不存在")
    if rev is not None and item.rev != rev:
        raise _conflict(item.rev)

    next_rev = await _bump_rev(session, user_id)
    deleted_at = utcnow()
    changed = await session.execute(update(Item).where(
        Item.id == item_id, Item.user_id == user_id, Item.rev == item.rev,
        Item.deleted_at.is_(None)).values(deleted_at=deleted_at, rev=next_rev, updated_at=deleted_at)
        .execution_options(synchronize_session=False))
    if changed.rowcount != 1:
        raise _conflict(item.rev)
    await session.commit()
    return {"id": item_id, "rev": next_rev, "deletedAt": deleted_at.isoformat()}


# ============================================================
# 批量导入
# ============================================================


@_vault_write
async def import_vault(session: AsyncSession, user_id: str, payload: ImportRequest) -> dict:
    imported = {"folders": 0, "items": 0}
    skipped = 0
    for model, rows, label in [(Folder, payload.folders, "folders"), (Item, payload.items, "items")]:
        for incoming in rows:
            existing = await _record(session, model, incoming.id)
            if existing is not None and existing.user_id != user_id:
                # Global record IDs must never turn a collision into a 500 or
                # mutate another user's ciphertext; rollback the whole import.
                raise _conflict(0)
            if existing is not None and payload.strategy == "skip":
                skipped += 1
                continue
            values = {"ciphertext": incoming.ciphertext, "nonce": incoming.nonce,
                      "rev": await _bump_rev(session, user_id)}
            if model is Folder:
                values["sort_order"] = incoming.sortOrder
            if existing is not None and payload.strategy == "overwrite":
                changed = await session.execute(update(model).where(
                    model.id == incoming.id, model.user_id == user_id, model.rev == existing.rev)
                    .values(**values, deleted_at=None, updated_at=utcnow())
                    .execution_options(synchronize_session=False))
                if changed.rowcount != 1:
                    raise _conflict(existing.rev)
            else:
                session.add(model(id=str(uuid4()) if existing else incoming.id,
                                  user_id=user_id, **values))
            # Repeated IDs in this same request must see the preceding write.
            await session.flush()
            imported[label] += 1
    final_rev = await _current_rev(session, user_id)
    await session.commit()
    return {"imported": imported, "skipped": skipped, "rev": final_rev}


# ============================================================
# 设置（整块密文）
# ============================================================


async def get_settings(session: AsyncSession, user_id: str) -> dict:
    row = await session.get(UserSettings, user_id)
    if row is None:
        return {"ciphertext": None, "nonce": None, "updatedAt": None}
    return {
        "ciphertext": row.ciphertext,
        "nonce": row.nonce,
        "updatedAt": row.updated_at.isoformat(),
    }


@_vault_write
async def put_settings(session: AsyncSession, user_id: str, payload: SettingsIn) -> dict:
    row = await session.get(UserSettings, user_id, populate_existing=True)
    if row is None:
        row = UserSettings(user_id=user_id, ciphertext=payload.ciphertext, nonce=payload.nonce)
        session.add(row)
    else:
        row.ciphertext = payload.ciphertext
        row.nonce = payload.nonce
        row.updated_at = utcnow()
    await session.commit()
    return {"ok": True, "updatedAt": row.updated_at.isoformat()}
