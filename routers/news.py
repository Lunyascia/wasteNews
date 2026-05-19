from fastapi import APIRouter

router = APIRouter( prefix="/api/news", tags=["news"])

@router.get("/categories")
def get_news_categories():
    return {"msg": "news categories"}
