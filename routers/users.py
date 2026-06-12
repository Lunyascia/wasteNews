from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import APIRouter, Depends, HTTPException
from starlette import status
from config.db_conf import get_db
from crud.users import get_user_by_username, create_user,create_token
from schemas.users import UserRequest

router = APIRouter ( prefix = "/api/user" , tags = [ "users" ])

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
