from fastapi import APIRouter,Depends,Query
from sqlalchemy.ext.asyncio import AsyncSession

from config.db_conf import get_db
from crud import news


router = APIRouter( prefix="/api/news", tags=["news"])

@router.get("/categories")
async def get_categories(skip: int = 0, limit: int = 100,db: AsyncSession = Depends(get_db)):
   categories = await news.get_categories(db,skip, limit)
   return {
        "code":200,
        "message":"获取成功",
        "data":categories

    }


@router.get("/list")
async def get_news_list(
        category_id: int = Query(default=1, alias="categoryId"),
        page: int = 1,
        page_size: int = Query(default=10, alias="pageSize", le=100),
        db: AsyncSession = Depends(get_db)
):

# 分页逻辑：计算偏移量，并获取指定页的数据，返回结果，添加hasMore字段
    offset = (page - 1) * page_size
    news_list = await news.get_news_list(db, category_id, offset, page_size)
    total = await news.get_news_count(db, category_id)
    has_more = total > offset + page_size
    return {
        "code": 200,
        "message": "获取成功",
        "data": {
            "list": news_list,
            "total": total,
            "hasMore": has_more,
        }
    }

@router.get("/detail")
async def get_news_detail(news_id: int = Query(default=1, alias="newsId"), db: AsyncSession = Depends(get_db)):
    # 获取新闻详情 + 浏览量+1 + 相关新闻
    news_detail = await news.get_news_detail(db, news_id)
    if not news_detail:
        return {
            "code": 404,
            "message": "新闻不存在",
            "data": None
        }

    await news.increase_news_views(db, news_detail.id)

    return {
        "code": 200,
        "message": "success",
        "data": {
            "id": news_detail,
            "title":news_detail.title,
    "content":news_detail.content,
    "image": news_detail.image,
    "author":news_detail.author,
    "publishTime": news_detail.publish_time,
    "categoryId": news_detail.category_id,
    "views": news_detail.views,
    "relatedNews": []
    }
         }