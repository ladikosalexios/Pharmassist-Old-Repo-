from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.pharmacy import Pharmacy


async def find_pharmacy_by_name(session: AsyncSession, pharmacy_name: str) -> Pharmacy:
    return (
        await session.scalars(select(Pharmacy).where(Pharmacy.name == pharmacy_name))
    ).one_or_none()
