"""
Redis 连接配置
使用 redis[hiredis] 高性能解析器，连接 docker-compose 中的 redis 容器
"""
import os

import redis.asyncio as aioredis
from redis.asyncio import Redis

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# 全局 Redis 连接池（应用启动时初始化）
redis_client: Redis | None = None


async def init_redis():
    """初始化 Redis 连接（在 FastAPI lifespan 中调用）"""
    global redis_client
    redis_client = aioredis.from_url(
        REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
        max_connections=20,
    )
    # 测试连接
    await redis_client.ping()
    return redis_client


async def close_redis():
    """关闭 Redis 连接"""
    global redis_client
    if redis_client:
        await redis_client.close()
        redis_client = None


async def get_redis() -> Redis:
    """获取 Redis 客户端（依赖注入用）"""
    if redis_client is None:
        raise RuntimeError("Redis 未初始化，请检查 init_redis() 调用")
    return redis_client
