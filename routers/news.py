from http.client import HTTPException
from fastapi import HTTPException
from fastapi import APIRouter,Depends,Query
from sqlalchemy.ext.asyncio import AsyncSession

from config.db_conf import get_db
from crud import news
from services import cache


router = APIRouter( prefix="/api/news", tags=["news"])

@router.get("/categories")
async def get_categories(skip: int = 0, limit: int = 100,db: AsyncSession = Depends(get_db)):
   # 尝试从 Redis 读缓存
   cache_key = f"news:categories:{skip}:{limit}"
   cached = await cache.cache_get(cache_key)
   if cached:
       return {"code": 200, "message": "获取成功", "data": cached}

   categories = await news.get_categories(db, skip, limit)
   # 序列化 ORM 对象
   data = [
       {"id": c.id, "name": c.name, "sortOrder": c.sort_order} for c in categories
   ]
   await cache.cache_set(cache_key, data, cache.CATEGORY_TTL)
   return {"code": 200, "message": "获取成功", "data": data}


@router.get("/list")
async def get_news_list(
        category_id: int = Query(default=1, alias="categoryId"),
        page: int = 1,
        page_size: int = Query(default=10, alias="pageSize", le=100),
        db: AsyncSession = Depends(get_db)
):
    # 尝试从 Redis 读缓存
    cached = await cache.get_cached_news_list(category_id, page, page_size)
    if cached:
        return {"code": 200, "message": "获取成功", "data": cached}

    # 分页逻辑：计算偏移量，并获取指定页的数据，返回结果，添加hasMore字段
    offset = (page - 1) * page_size
    news_list = await news.get_news_list(db, category_id, offset, page_size)
    total = await news.get_news_count(db, category_id)
    has_more = total > offset + page_size
    data = {"list": news_list, "total": total, "hasMore": has_more}

    # 写入 Redis 缓存
    await cache.set_cached_news_list(category_id, page, page_size, data)

    return {"code": 200, "message": "获取成功", "data": data}


@router.get("/detail")
async def get_news_detail(news_id: int = Query(default=1, alias="newsId"), db: AsyncSession = Depends(get_db)):
    # 尝试从 Redis 读缓存
    cached = await cache.get_cached_news_detail(news_id)
    if cached:
        # 缓存命中时仍然累加浏览量（Redis 计数器，不查数据库）
        await cache.incr_news_views_redis(news_id)
        return {"code": 200, "message": "success", "data": cached}

    # 缓存未命中，查数据库
    news_detail = await news.get_news_detail(db, news_id)
    if not news_detail:
        return {"code": 404, "message": "新闻不存在", "data": None}

    # Redis 累加浏览量（不再每次 UPDATE 数据库）
    await cache.incr_news_views_redis(news_id)

    # 获取相关新闻
    related_news = await news.get_related_news(db, news_detail.id, news_detail.category_id)

    data = {
        "id": news_detail.id,
        "title": news_detail.title,
        "content": news_detail.content,
        "image": news_detail.image,
        "author": news_detail.author,
        "publishTime": news_detail.publish_time,
        "categoryId": news_detail.category_id,
        "views": news_detail.views,
        "relatedNews": related_news,
    }

    # 写入 Redis 缓存
    await cache.set_cached_news_detail(news_id, data)

    return {"code": 200, "message": "success", "data": data}