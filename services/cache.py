"""
缓存工具层 — 基于 Redis 实现
- 新闻列表缓存 (key: news:list:{category_id}:{page}:{pageSize})
- 新闻详情缓存 (key: news:detail:{news_id})
- Token 缓存 (key: token:{token} → user_info)
- 浏览量累加器 (key: news:views:{news_id} → count)
"""
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from redis.asyncio import Redis

from config.redis_conf import get_redis

logger = logging.getLogger("cache")

# ============================================================
# 缓存 TTL 配置
# ============================================================
NEWS_LIST_TTL = 300       # 新闻列表缓存 5 分钟
NEWS_DETAIL_TTL = 600     # 新闻详情缓存 10 分钟
TOKEN_TTL = 7 * 86400     # Token 缓存 7 天（与数据库一致）
CATEGORY_TTL = 3600       # 分类列表缓存 1 小时

# ============================================================
# 通用缓存装饰器
# ============================================================

async def cache_get(key: str) -> Optional[Any]:
    """从 Redis 读缓存，自动反序列化 JSON"""
    try:
        r = await get_redis()
        data = await r.get(key)
        return json.loads(data) if data else None
    except Exception as e:
        logger.warning(f"Redis GET 失败 [{key}]: {e}")
        return None


async def cache_set(key: str, value: Any, ttl: int = 300):
    """写 Redis 缓存，自动序列化 JSON"""
    try:
        r = await get_redis()
        await r.setex(key, ttl, json.dumps(value, ensure_ascii=False, default=str))
    except Exception as e:
        logger.warning(f"Redis SET 失败 [{key}]: {e}")


async def cache_delete(pattern: str):
    """删除匹配 pattern 的所有缓存键"""
    try:
        r = await get_redis()
        keys = await r.keys(pattern)
        if keys:
            await r.delete(*keys)
            logger.info(f"已清除缓存: {pattern} → {len(keys)} 个键")
    except Exception as e:
        logger.warning(f"Redis DELETE 失败 [{pattern}]: {e}")


# ============================================================
# 新闻缓存
# ============================================================

async def get_cached_news_list(category_id: int, page: int, page_size: int) -> Optional[dict]:
    """获取缓存的新闻列表"""
    key = f"news:list:{category_id}:{page}:{page_size}"
    return await cache_get(key)


async def set_cached_news_list(category_id: int, page: int, page_size: int, data: dict):
    """设置新闻列表缓存"""
    key = f"news:list:{category_id}:{page}:{page_size}"
    await cache_set(key, data, NEWS_LIST_TTL)


async def get_cached_news_detail(news_id: int) -> Optional[dict]:
    """获取缓存的新闻详情"""
    key = f"news:detail:{news_id}"
    return await cache_get(key)


async def set_cached_news_detail(news_id: int, data: dict):
    """设置新闻详情缓存"""
    key = f"news:detail:{news_id}"
    await cache_set(key, data, NEWS_DETAIL_TTL)


async def invalidate_news_cache():
    """清除所有新闻相关缓存（新闻刷新后调用）"""
    await cache_delete("news:list:*")
    await cache_delete("news:detail:*")
    logger.info("已清除全部新闻缓存")


# ============================================================
# Token 缓存
# ============================================================

TOKEN_USER_KEY = "token:user:{token}"
USER_TOKEN_KEY = "user:token:{user_id}"


async def get_cached_token_user(token: str) -> Optional[dict]:
    """从 Redis 获取 Token 对应的用户信息"""
    key = TOKEN_USER_KEY.format(token=token)
    return await cache_get(key)


async def set_cached_token_user(token: str, user_info: dict):
    """缓存 Token → 用户信息"""
    key = TOKEN_USER_KEY.format(token=token)
    await cache_set(key, user_info, TOKEN_TTL)


async def remove_cached_token(token: str):
    """删除缓存的 Token"""
    key = TOKEN_USER_KEY.format(token=token)
    await cache_delete(key)


# ============================================================
# 浏览量批量计数器
# ============================================================

VIEWS_KEY = "news:views:batch"


async def incr_news_views_redis(news_id: int) -> int:
    """Redis 中累加浏览量（不每次都写数据库）"""
    try:
        r = await get_redis()
        return await r.hincrby(VIEWS_KEY, str(news_id), 1)
    except Exception as e:
        logger.warning(f"Redis 浏览量累加失败 [{news_id}]: {e}")
        return 0


async def flush_views_to_db():
    """
    将 Redis 中累计的浏览量批量写入数据库
    由定时任务每 5 分钟调用一次
    """
    try:
        r = await get_redis()
        batch = await r.hgetall(VIEWS_KEY)
        if not batch:
            return

        from config.db_conf import AsyncSessionLocal
        from models.news import News

        async with AsyncSessionLocal() as db:
            for news_id_str, count_str in batch.items():
                news_id = int(news_id_str)
                count = int(count_str)
                # 用原生 SQL update 避免先查后改
                from sqlalchemy import update
                await db.execute(
                    update(News).where(News.id == news_id).values(views=News.views + count)
                )
            await db.commit()

        # 清除已入库的计数
        await r.delete(VIEWS_KEY)
        logger.info(f"浏览量批量入库: {len(batch)} 条新闻, 总计 {sum(int(v) for v in batch.values())} 次")
    except Exception as e:
        logger.error(f"浏览量批量入库失败: {e}")
