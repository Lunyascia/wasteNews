from fastapi import APIRouter,Depends
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
