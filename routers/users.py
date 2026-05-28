from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import APIRouter,Depends
from config.db_conf import get_db
from schemas.users import UserRequest

router = APIRouter ( prefix = "/api/user" , tags = [ "users" ])

@router.post ("/register")
async def register (user_data:UserRequest,db: AsyncSession = Depends (get_db),):
        return {
            "code": 200,
            "message": "注册成功",
            "data": {
            "token":"用户访问名牌",
            "userinfo": {
            "id": 1,
            "username": user_data.username,
            "bio":"签名",
            "avatar": "https://fastly.jsdelivr.net/npm/@vant/assets/cat.jpeg",
            }

    }
    }
