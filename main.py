import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from routers import news, users, favorite, history
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("main")


# ============================================================
# 应用生命周期: 启动时初始化 Redis + 调度器, 关闭时清理
# ============================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- 启动阶段 ---
    logger.info("初始化 Redis 连接...")
    try:
        from config.redis_conf import init_redis
        await init_redis()
        logger.info("Redis 连接成功")
    except Exception as e:
        logger.error(f"Redis 连接失败: {e}")
        raise

    logger.info("初始化新闻自动拉取调度器...")
    try:
        from services.news_fetcher import start_scheduler
        start_scheduler()
        logger.info("新闻调度器初始化完成")
    except Exception as e:
        logger.error(f"调度器初始化失败: {e}")

    logger.info("启动浏览量批量入库定时任务...")
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from services.cache import flush_views_to_db
        import asyncio

        views_scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
        views_scheduler.add_job(
            lambda: asyncio.run(_safe_flush()),
            "interval",
            minutes=5,
            id="views_flush",
        )
        views_scheduler.start()
        logger.info("浏览量定时任务已启动 — 每 5 分钟批量入库")
    except Exception as e:
        logger.error(f"浏览量定时任务启动失败: {e}")

    yield  # 应用运行中

    # --- 关闭阶段 ---
    logger.info("应用关闭，清理连接...")
    try:
        from config.redis_conf import close_redis
        await close_redis()
    except Exception:
        pass
    logger.info("应用已关闭")


async def _safe_flush():
    """安全执行浏览量批量入库"""
    try:
        from services.cache import flush_views_to_db
        await flush_views_to_db()
    except Exception as e:
        logger.error(f"浏览量批量入库异常: {e}")


app = FastAPI(lifespan=lifespan)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 挂载路由
app.include_router(news.router)
app.include_router(users.router)
app.include_router(favorite.router)
app.include_router(history.router)
