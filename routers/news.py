from email.policy import default

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
        category_id: int = Query(default:=0,alias="categoryId"),
        page: int = 0,
        page_size: int = Query(default=10,alias="pageSize",le=100),
        db: AsyncSession = Depends(get_db))\
        :
    return {
        "list":"新闻列表",
        "total": "总量",
        "hasmore":"是否有更多",
    }
