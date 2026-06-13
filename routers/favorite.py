from fastapi import APIRouter, Depends, Header, HTTPException, Query

from config.db_conf import get_db
from crud.users import get_current_user
from crud import favorite

router = APIRouter(prefix="/api/favorite", tags=["favorite"])


@router.get("/check")
async def check_favorite(
    newsId: int = Query(...),
    db=Depends(get_db),
    authorization: str = Header(default=""),
):
    user = await get_current_user(db, authorization)
    is_fav = await favorite.check_favorite(db, user.id, newsId)
    return {"code": 200, "message": "获取成功", "data": {"isFavorite": is_fav}}


@router.post("/add")
async def add_favorite(
    body: dict,
    db=Depends(get_db),
    authorization: str = Header(default=""),
):
    user = await get_current_user(db, authorization)
    news_id = body.get("newsId")
    if not news_id:
        raise HTTPException(status_code=400, detail="缺少 newsId")
    await favorite.add_favorite(db, user.id, news_id)
    return {"code": 200, "message": "收藏成功", "data": None}


@router.delete("/remove")
async def remove_favorite(
    newsId: int = Query(...),
    db=Depends(get_db),
    authorization: str = Header(default=""),
):
    user = await get_current_user(db, authorization)
    await favorite.remove_favorite(db, user.id, newsId)
    return {"code": 200, "message": "取消收藏成功", "data": None}


@router.delete("/clear")
async def clear_favorites(
    db=Depends(get_db),
    authorization: str = Header(default=""),
):
    user = await get_current_user(db, authorization)
    await favorite.clear_favorites(db, user.id)
    return {"code": 200, "message": "清空收藏成功", "data": None}


@router.get("/list")
async def get_favorite_list(
    page: int = Query(default=1),
    pageSize: int = Query(default=10, le=100),
    db=Depends(get_db),
    authorization: str = Header(default=""),
):
    user = await get_current_user(db, authorization)
    offset = (page - 1) * pageSize
    fav_list = await favorite.get_favorite_list(db, user.id, offset, pageSize)
    total = await favorite.get_favorite_count(db, user.id)
    has_more = total > offset + pageSize
    return {
        "code": 200,
        "message": "获取成功",
        "data": {"list": fav_list, "total": total, "hasMore": has_more},
    }
