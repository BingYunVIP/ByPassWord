"""Global installation resources belong to an explicit singleton owner."""

from sqlalchemy.ext.asyncio import AsyncSession

from ..models import InstallationOwner


async def get_owner_user_id(session: AsyncSession) -> str | None:
    owner = await session.get(InstallationOwner, 1)
    return owner.owner_user_id if owner else None
