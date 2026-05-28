from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models.users import User
from schemas.users import UserRequest
from utils import security

async def get_user_by_username(db: AsyncSession,username: str):
    query = select(User).where(User.username == username)
    result = await db.execute(query)
    return result.scalar()

async def create_user(db: AsyncSession, user_data: UserRequest):
    # 确保这里没有特殊字符
    hash_password = security.get_hash_password(user_data.password)

    # 确保 User 模型导入正确
    user = User(
        username=user_data.username,
        password=hash_password
    )
    db.add(user)

    # 异步提交
    await db.commit()
    await db.refresh(user)
    return user