from fastapi import APIRouter

router = APIRouter( prefix="/api/news", tags=["news"])

@router.get("/categories")
async def get_categories(skip: int = 0, limit: int = 100):
    return {
        "code":200,
        "message":"获取成功",
        "data":"新闻分类列表"

    }
