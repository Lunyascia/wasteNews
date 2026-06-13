from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from models.history import History
from models.news import News


async def add_history(db: AsyncSession, user_id: int, news_id: int):
    """添加或更新浏览历史（同一用户+同一新闻只保留一条，更新浏览时间）"""
    query = select(History).where(History.user_id == user_id, History.news_id == news_id)
    result = await db.execute(query)
    record = result.scalar_one_or_none()

    if record:
        record.view_time = datetime.now()
    else:
        record = History(user_id=user_id, news_id=news_id, view_time=datetime.now())
        db.add(record)
    await db.commit()


async def get_history_list(db: AsyncSession, user_id: int):
    """按浏览时间倒序返回历史记录（含新闻信息）"""
    query = (
        select(History, News)
        .join(News, History.news_id == News.id)
        .where(History.user_id == user_id)
        .order_by(History.view_time.desc())
    )
    result = await db.execute(query)
    rows = result.all()
    return [
        {
            "id": news.id,
            "title": news.title,
            "image": news.image,
            "author": news.author,
            "publishTime": news.publish_time,
            "categoryId": news.category_id,
            "views": news.views,
            "viewTime": str(hist.view_time),
        }
        for hist, news in rows
    ]


async def remove_history(db: AsyncSession, user_id: int, news_id: int) -> bool:
    stmt = delete(History).where(History.user_id == user_id, History.news_id == news_id)
    result = await db.execute(stmt)
    await db.commit()
    return result.rowcount > 0


async def clear_history(db: AsyncSession, user_id: int):
    stmt = delete(History).where(History.user_id == user_id)
    await db.execute(stmt)
    await db.commit()
