from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy import func
from models.news import Category,News
from sqlalchemy import update


async def get_categories(db:AsyncSession,skip: int = 0, limit: int = 100):
    stat = select(Category).offset(skip).limit(limit)
    result = await db.execute(stat)
    return result.scalars().all()

async def get_news_list(db:AsyncSession,category_id: int,skip: int = 0,limit: int = 10):
    stat = select(News).where(News.category_id == category_id).offset(skip).limit(limit)
    result = await db.execute(stat)
    return result.scalars().all()

async def get_news_count(db:AsyncSession,category_id: int):
    stat = select(func.count(News.id)).where(News.category_id == category_id)
    result = await db.execute(stat)
    return result.scalar()

async def get_news_detail(db:AsyncSession,news_id: int):
    stat = select(News).where(News.id == news_id)
    result = await db.execute(stat)
    return result.scalar_one_or_none()

async def increase_news_views(db:AsyncSession,news_id: int):
    stat = update(News).where(News.id == news_id).values(views=News.views+1)
    await db.execute(stat)
    await db.commit()


