"""
数据库初始化脚本：建表 + 种子数据
运行方式：python init_db.py

Docker 启动时自动执行: 建表 + 分类 + 测试用户
新闻数据由 services/news_fetcher.py 调度器负责拉取
"""
import asyncio
from datetime import datetime

from sqlalchemy import select, func

from config.db_conf import async_engine, AsyncSessionLocal

# 导入所有模型，确保表注册到 Base.metadata
from models.users import Base, User, UserToken
from models.news import Category, News
from models.favorite import Favorite
from models.history import History
from utils import security


CATEGORIES = [
    {"id": 1, "name": "头条", "sort_order": 1},
    {"id": 2, "name": "社会", "sort_order": 2},
    {"id": 3, "name": "国内", "sort_order": 3},
    {"id": 4, "name": "国际", "sort_order": 4},
    {"id": 5, "name": "娱乐", "sort_order": 5},
    {"id": 6, "name": "体育", "sort_order": 6},
    {"id": 7, "name": "军事", "sort_order": 7},
    {"id": 8, "name": "科技", "sort_order": 8},
    {"id": 9, "name": "财经", "sort_order": 9},
]


async def init_database():
    # 1. 建表
    print("正在创建数据库表...")
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("表创建完成 ✓")

    async with AsyncSessionLocal() as db:
        # 2. 种子分类
        existing = await db.execute(select(Category))
        if existing.scalars().first():
            print("分类数据已存在，跳过")
        else:
            for cat in CATEGORIES:
                db.add(Category(**cat))
            await db.commit()
            print(f"已插入 {len(CATEGORIES)} 个分类 ✓")

        # 3. 检查新闻数量，提示但不插入 (由调度器负责)
        news_count = await db.execute(select(func.count(News.id)))
        count = news_count.scalar()
        if count == 0:
            print(f"新闻表为空 — 应用启动后调度器将自动拉取新闻")
        else:
            print(f"新闻数据已存在: {count} 条")

        # 4. 创建测试账号 admin / 123456
        existing_user = await db.execute(select(User).where(User.username == "admin"))
        if existing_user.scalar():
            print("测试账号已存在，跳过")
        else:
            admin = User(
                username="admin",
                password=security.get_hash_password("123456"),
                nickname="管理员",
                bio="欢迎来到新闻资讯平台",
            )
            db.add(admin)
            await db.commit()
            print("测试账号 admin / 123456 已创建 ✓")

    print("\n数据库初始化完成！")
    await async_engine.dispose()


if __name__ == "__main__":
    asyncio.run(init_database())
