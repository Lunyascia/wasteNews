from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models.news import Category



async def get_categories(db:AsyncSession,skip: int = 0, limit: int = 100):
    stat = select(Category).offset(skip).limit(limit)
    result = await db.execute(stat)
    return result.scalars().all()
