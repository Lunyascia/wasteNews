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
    # 1. 密码加密处理
    hash_password = security.get_hash_password(user_data.password)

    # 2. 创建 ORM 对象
    user = User(
        username=user_data.username,
        password=hash_password,
        nickname=user_data.nickname,
        phone=user_data.phone
    )

    # 3. 添加到会话并提交
    db.add(user)
    await db.commit()

    # 4. 【关键步骤】刷新对象，确保 ID 和默认字段同步到内存中
    await db.refresh(user)

    return user