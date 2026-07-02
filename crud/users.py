import uuid
from datetime import datetime, timedelta
from fastapi import Header, HTTPException
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

async def authenticate_user(db: AsyncSession, username: str, password: str):
    """验证用户名密码，成功返回 user，失败返回 None"""
    user = await get_user_by_username(db, username)
    if not user:
        return None
    if not security.verify_password(password, user.password):
        return None
    return user


async def create_token(db: AsyncSession, user_id: int):
    token = str(uuid.uuid4())
    expires_at = datetime.now() + timedelta(days=7)
    query = select(UserToken).where(UserToken.user_id == user_id)
    result = await db.execute(query)
    user_token = result.scalar_one_or_none()
    old_token = user_token.token if user_token else None
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

    # 删除旧 Token 的 Redis 缓存
    if old_token:
        try:
            from services.cache import remove_cached_token
            await remove_cached_token(old_token)
        except Exception:
            pass

    await db.commit()

    # 缓存新 Token → 用户信息到 Redis
    try:
        from services.cache import set_cached_token_user
        user = await get_user_by_id(db, user_id)
        if user:
            await set_cached_token_user(token, {
                "id": user.id,
                "username": user.username,
                "bio": user.bio,
                "avatar": user.avatar,
                "nickname": user.nickname,
            })
    except Exception:
        pass

    return token


async def get_user_by_id(db: AsyncSession, user_id: int):
    query = select(User).where(User.id == user_id)
    result = await db.execute(query)
    return result.scalar()


async def get_current_user(
    db: AsyncSession,
    authorization: str = Header(default=""),
):
    """从 Authorization header 提取 token 并返回当前用户（Redis 优先）"""
    if not authorization:
        raise HTTPException(status_code=401, detail="未提供认证信息")

    token = authorization.strip()

    # 1. 优先查 Redis 缓存
    try:
        from services.cache import get_cached_token_user
        cached_user = await get_cached_token_user(token)
        if cached_user:
            user = await get_user_by_id(db, cached_user["id"])
            if user:
                return user
    except Exception:
        pass  # Redis 不可用时降级到数据库

    # 2. Redis 未命中，查数据库
    query = select(UserToken).where(UserToken.token == token)
    result = await db.execute(query)
    user_token = result.scalar_one_or_none()

    if not user_token:
        raise HTTPException(status_code=401, detail="无效的认证信息")
    if user_token.expires_at < datetime.now():
        raise HTTPException(status_code=401, detail="认证信息已过期")

    user = await get_user_by_id(db, user_token.user_id)
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")

    # 3. 写回 Redis 缓存
    try:
        from services.cache import set_cached_token_user
        await set_cached_token_user(token, {
            "id": user.id,
            "username": user.username,
            "bio": user.bio,
            "avatar": user.avatar,
            "nickname": user.nickname,
        })
    except Exception:
        pass

    return user


async def update_user_bio(db: AsyncSession, user: User, bio: str):
    user.bio = bio
    await db.commit()
    await db.refresh(user)
    return user


async def update_user_password(db: AsyncSession, user: User, new_password: str):
    user.password = security.get_hash_password(new_password)
    await db.commit()