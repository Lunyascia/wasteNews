from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete

from models.favorite import Favorite
from models.news import News


async def check_favorite(db: AsyncSession, user_id: int, news_id: int) -> bool:
    query = select(Favorite).where(Favorite.user_id == user_id, Favorite.news_id == news_id)
    result = await db.execute(query)
    return result.scalar() is not None


async def add_favorite(db: AsyncSession, user_id: int, news_id: int):
    fav = Favorite(user_id=user_id, news_id=news_id)
    db.add(fav)
    await db.commit()


async def remove_favorite(db: AsyncSession, user_id: int, news_id: int) -> bool:
    stmt = delete(Favorite).where(Favorite.user_id == user_id, Favorite.news_id == news_id)
    result = await db.execute(stmt)
    await db.commit()
    return result.rowcount > 0


async def clear_favorites(db: AsyncSession, user_id: int):
    stmt = delete(Favorite).where(Favorite.user_id == user_id)
    await db.execute(stmt)
    await db.commit()


async def get_favorite_list(db: AsyncSession, user_id: int, offset: int, limit: int):
    query = (
        select(News)
        .join(Favorite, Favorite.news_id == News.id)
        .where(Favorite.user_id == user_id)
        .order_by(Favorite.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(query)
    news_list = result.scalars().all()
    return [
        {
            "id": n.id,
            "title": n.title,
            "image": n.image,
            "author": n.author,
            "publishTime": n.publish_time,
            "categoryId": n.category_id,
            "views": n.views,
        }
        for n in news_list
    ]


async def get_favorite_count(db: AsyncSession, user_id: int) -> int:
    query = select(func.count(Favorite.id)).where(Favorite.user_id == user_id)
    result = await db.execute(query)
    return result.scalar()
