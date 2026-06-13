"""
数据库初始化脚本：建表 + 种子数据
运行方式：python init_db.py
"""
import asyncio
from datetime import datetime

from sqlalchemy import select

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

SAMPLE_NEWS = [
    {"title": "全国科技创新大会在京召开", "description": "2026年度全国科技创新大会在北京人民大会堂隆重召开", "content": "6月12日，2026年度全国科技创新大会在北京人民大会堂隆重召开。大会总结了'十四五'期间我国科技事业取得的历史性成就，部署了下一阶段科技创新重点任务。\n\n会议强调，要坚持把科技自立自强作为国家发展的战略支撑，加快实现高水平科技自立自强。要以国家战略需求为导向，集聚力量进行原创性引领性科技攻关。\n\n多位院士和科技工作者代表参加了大会。", "image": "https://picsum.photos/seed/tech1/400/300", "author": "新华社", "category_id": 1, "views": 15230, "publish_time": datetime(2026, 6, 12, 8, 0)},
    {"title": "我国新能源汽车出口量再创新高", "description": "今年前五个月新能源汽车出口同比增长45%", "content": "据海关总署最新数据显示，2026年1至5月我国新能源汽车出口量达到120万辆，同比增长45%，再创历史新高。\n\n其中，纯电动乘用车出口占比超过80%，主要出口目的地包括欧洲、东南亚和南美市场。\n\n业内人士分析，我国新能源汽车在技术、品质和性价比方面具有明显优势，预计全年出口量有望突破300万辆。", "image": "https://picsum.photos/seed/car1/400/300", "author": "经济日报", "category_id": 1, "views": 8920, "publish_time": datetime(2026, 6, 12, 10, 30)},
    {"title": "社区志愿者助力老年人跨越数字鸿沟", "description": "多地社区开展智慧助老志愿服务活动", "content": "近日，全国多地社区组织开展智慧助老志愿服务活动，帮助老年人学习使用智能手机和互联网应用。\n\n在北京市朝阳区某社区，青年志愿者们每周定期为老年人开设手机使用培训课程，内容包括微信聊天、网上挂号、移动支付等日常生活常用功能。\n\n据统计，我国60岁以上老年人口已超3亿，其中约半数存在不同程度的数字技能不足问题。", "image": "https://picsum.photos/seed/elder1/400/300", "author": "人民日报", "category_id": 2, "views": 3450, "publish_time": datetime(2026, 6, 11, 15, 0)},
    {"title": "长三角一体化发展取得新进展", "description": "长三角生态绿色一体化发展示范区发布三年行动计划", "content": "长三角生态绿色一体化发展示范区近日发布三年行动计划（2026-2028年），涵盖科技创新、生态环保、基础设施、公共服务等八大领域，共128个重点项目。\n\n计划提出，到2028年示范区GDP总量力争突破1万亿元，研发投入强度达到4.5%以上。\n\n示范区涵盖上海青浦、江苏吴江、浙江嘉善三地，总面积约2300平方公里。", "image": "https://picsum.photos/seed/yangtze/400/300", "author": "央视新闻", "category_id": 3, "views": 5670, "publish_time": datetime(2026, 6, 11, 9, 15)},
    {"title": "联合国气候变化大会达成新协议", "description": "各缔约方就2035年减排目标达成共识", "content": "经过两周紧张谈判，联合国气候变化框架公约缔约方大会于当地时间6月10日在日内瓦闭幕，各缔约方就2035年中期减排目标达成新的共识。\n\n根据协议，发达国家承诺在2035年前将温室气体排放量较2019年减少55%，并每年向发展中国家提供不低于3000亿美元的气候资金支持。\n\n中国代表团在大会上重申了'双碳'承诺，表示将坚定不移走绿色低碳发展道路。", "image": "https://picsum.photos/seed/climate/400/300", "author": "环球时报", "category_id": 4, "views": 12300, "publish_time": datetime(2026, 6, 10, 20, 0)},
    {"title": "暑期档电影票房突破50亿元", "description": "国产科幻大片领跑暑期档，多部新片即将上映", "content": "据电影局统计，2026年暑期档自6月1日启动以来，全国电影票房已突破50亿元，较去年同期增长23%。\n\n国产科幻大片《星际征途》以18亿票房领跑，好莱坞超级英雄续集《雷霆战警》以12亿紧随其后。\n\n业内人士预计，7月份还将有超过10部重量级新片上映，暑期档有望冲击150亿总票房。", "image": "https://picsum.photos/seed/movie1/400/300", "author": "新浪娱乐", "category_id": 5, "views": 28900, "publish_time": datetime(2026, 6, 12, 14, 0)},
    {"title": "国足世预赛2:1逆转战胜日本队", "description": "中国队在下半场连入两球完成逆转", "content": "6月11日晚，2026年世界杯亚洲区预选赛关键一战在沈阳奥体中心打响，中国男足主场2:1逆转战胜日本队。\n\n上半场日本队凭借一次快速反击先拔头筹。下半场中国队调整战术，第65分钟由武磊头球扳平比分，第82分钟替补登场的张玉宁远射绝杀。\n\n此役过后，国足在小组积分榜上升至第二位，出线形势大为改善。", "image": "https://picsum.photos/seed/football/400/300", "author": "体坛周报", "category_id": 6, "views": 98500, "publish_time": datetime(2026, 6, 11, 22, 0)},
    {"title": "中国第三艘国产航母正式下水", "description": "命名'福建舰'姊妹舰，采用电磁弹射技术", "content": "6月10日上午，中国第三艘国产航空母舰在大连造船厂正式下水，命名为'浙江舰'。\n\n该舰是我国自主设计建造的第二艘电磁弹射型航母，满载排水量约8万吨，可搭载各型舰载机70余架。\n\n军事专家表示，浙江舰的服役将进一步提升中国海军的远洋作战能力，标志着我国航母技术已经完全成熟。", "image": "https://picsum.photos/seed/carrier/400/300", "author": "解放军报", "category_id": 7, "views": 156000, "publish_time": datetime(2026, 6, 10, 8, 0)},
    {"title": "国产大模型在多项国际评测中超越GPT-5", "description": "中国AI企业在自然语言处理和代码生成等评测中表现优异", "content": "据最新发布的国际AI评测报告，国产大模型在多项权威评测中表现优异，在部分任务上首次超越OpenAI的GPT-5。\n\n在代码生成评测HumanEval+中，国产模型得分率达到94.3%，领先GPT-5的92.1%。在中文理解评测C-Eval中，国产模型优势更为明显。\n\n业内专家认为，这标志着中国在通用人工智能领域已达到国际领先水平。", "image": "https://picsum.photos/seed/ai1/400/300", "author": "科技日报", "category_id": 8, "views": 45200, "publish_time": datetime(2026, 6, 12, 7, 30)},
    {"title": "央行宣布定向降准0.5个百分点", "description": "释放长期流动性约8000亿元，支持实体经济发展", "content": "中国人民银行今日宣布，决定于6月20日下调金融机构存款准备金率0.5个百分点（不含已执行5%存款准备金率的金融机构）。\n\n此次降准预计释放长期流动性约8000亿元，旨在加大对中小微企业和科技创新的金融支持力度。\n\n分析人士指出，此次降准体现了货币政策稳增长、促发展的导向，有助于降低实体经济融资成本。", "image": "https://picsum.photos/seed/finance1/400/300", "author": "金融时报", "category_id": 9, "views": 22100, "publish_time": datetime(2026, 6, 12, 9, 45)},
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

        # 3. 种子新闻
        existing = await db.execute(select(News))
        if existing.scalars().first():
            print("新闻数据已存在，跳过")
        else:
            for news in SAMPLE_NEWS:
                db.add(News(**news))
            await db.commit()
            print(f"已插入 {len(SAMPLE_NEWS)} 条新闻 ✓")

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
