from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import APIRouter, Depends, Header, HTTPException
from starlette import status
from config.db_conf import get_db
from crud.users import (
    get_user_by_username, create_user, create_token, authenticate_user,
    get_current_user, update_user_bio, update_user_password,
)
from schemas.users import UserRequest, BioUpdate, PasswordUpdate
from utils import security

router = APIRouter(prefix="/api/user", tags=["users"])

@router.post("/login")
async def login(user_data: UserRequest, db: AsyncSession = Depends(get_db)):
    user = await authenticate_user(db, user_data.username, user_data.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用户名或密码错误")

    token = await create_token(db, user.id)
    return {
        "code": 200,
        "message": "登录成功",
        "data": {
            "token": token,
            "userInfo": {
                "id": user.id,
                "username": user.username,
                "bio": user.bio,
                "avatar": user.avatar,
            }
        }
    }


@router.get("/info")
async def get_user_info(
    db: AsyncSession = Depends(get_db),
    authorization: str = Header(default=""),
):
    user = await get_current_user(db, authorization)
    return {
        "code": 200,
        "message": "获取成功",
        "data": {
            "id": user.id,
            "username": user.username,
            "bio": user.bio,
            "avatar": user.avatar,
            "nickname": user.nickname,
            "gender": user.gender,
            "phone": user.phone,
        }
    }


@router.put("/update")
async def update_bio(
    bio_data: BioUpdate,
    db: AsyncSession = Depends(get_db),
    authorization: str = Header(default=""),
):
    user = await get_current_user(db, authorization)
    updated_user = await update_user_bio(db, user, bio_data.bio)
    return {
        "code": 200,
        "message": "更新成功",
        "data": {
            "id": updated_user.id,
            "username": updated_user.username,
            "bio": updated_user.bio,
            "avatar": updated_user.avatar,
        }
    }


@router.put("/password")
async def change_password(
    pwd_data: PasswordUpdate,
    db: AsyncSession = Depends(get_db),
    authorization: str = Header(default=""),
):
    user = await get_current_user(db, authorization)
    if not security.verify_password(pwd_data.oldPassword, user.password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="旧密码错误")
    await update_user_password(db, user, pwd_data.newPassword)
    return {
        "code": 200,
        "message": "密码修改成功",
        "data": None,
    }


@router.post ("/register")
async def register (user_data:UserRequest,db: AsyncSession = Depends (get_db),):
        existing_user = await get_user_by_username(db, user_data.username)
        if existing_user:
            raise HTTPException (status_code = status.HTTP_400_BAD_REQUEST, detail = "用户已存在")
        
        # 修正：调用 create_user 函数并传入 Pydantic 对象
        user = await create_user(db, user_data)
        token = await create_token(db, user.id)
        return {
            "code": 200,
            "message": "注册成功",
            "data": {
            "token":token,
            "userInfo": {
            "id": user.id,
            "username": user.username,
            "bio":user.bio,
            "avatar": user.avatar,
            }

    }
    }
