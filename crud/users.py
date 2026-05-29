import uuid
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from models.users import User, UserToken
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
    )

    # 3. 添加到会话并提交
    db.add(user)
    await db.flush()


    # 4. 【关键步骤】刷新对象，确保 ID 和默认字段同步到内存中
    await db.refresh(user)
    await db.commit()
    return user

async def create_token(db: AsyncSession,user_id: int):
    token = str(uuid.uuid4())
    expires_at = datetime.now() + timedelta(days=7)
    query = select(UserToken).where(UserToken.user_id == user_id)
    result = await db.execute(query)
    user_token = result.scalar_one_or_none()
    if user_token:
        user_token.token = token
        user_token.expires_at = expires_at
    else:
        user_token = UserToken(
            user_id=user_id,
            token=token,
            expires_at=expires_at
        )
        db.add(user_token)
        await db.commit()

    return token