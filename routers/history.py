from fastapi import APIRouter, Depends, Header

from config.db_conf import get_db
from crud.users import get_current_user
from crud import history

router = APIRouter(prefix="/api/history", tags=["history"])


@router.post("/add")
async def add_history(
    body: dict,
    db=Depends(get_db),
    authorization: str = Header(default=""),
):
    user = await get_current_user(db, authorization)
    news_id = body.get("newsId")
    if not news_id:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="缺少 newsId")
    await history.add_history(db, user.id, news_id)
    return {"code": 200, "message": "添加成功", "data": None}


@router.get("/list")
async def get_history_list(
    db=Depends(get_db),
    authorization: str = Header(default=""),
):
    user = await get_current_user(db, authorization)
    hist_list = await history.get_history_list(db, user.id)
    return {"code": 200, "message": "获取成功", "data": {"list": hist_list}}


@router.delete("/delete/{news_id}")
async def delete_history(
    news_id: int,
    db=Depends(get_db),
    authorization: str = Header(default=""),
):
    user = await get_current_user(db, authorization)
    await history.remove_history(db, user.id, news_id)
    return {"code": 200, "message": "删除成功", "data": None}


@router.delete("/clear")
async def clear_history(
    db=Depends(get_db),
    authorization: str = Header(default=""),
):
    user = await get_current_user(db, authorization)
    await history.clear_history(db, user.id)
    return {"code": 200, "message": "清空成功", "data": None}
