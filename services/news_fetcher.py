"""
新闻自动拉取服务
- 首次启动: 自动拉取 300 条新闻 (9 个分类平均分配)
- 每 30 分钟: 清空旧新闻 → 重新拉取 300 条
- 来源: RSS 订阅源 (优先) + 内置标题池 (兜底)
"""
import asyncio
import hashlib
import logging
import os
import random
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional

import feedparser
import requests
from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from config.db_conf import AsyncSessionLocal
from models.news import News, Category

logger = logging.getLogger("news_fetcher")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")

# --- 配置 (可通过环境变量覆盖) ---
TARGET_TOTAL = int(os.getenv("NEWS_TOTAL_COUNT", "300"))
FETCH_INTERVAL_MINUTES = int(os.getenv("NEWS_FETCH_INTERVAL", "30"))
FETCH_TIMEOUT = 8  # 单个 RSS 源的超时秒数
CATEGORY_COUNT = 9

CATEGORY_NAMES = {
    1: "头条", 2: "社会", 3: "国内", 4: "国际",
    5: "娱乐", 6: "体育", 7: "军事", 8: "科技", 9: "财经",
}

# ============================================================
# RSS 订阅源配置 (按分类)
# ============================================================
RSS_SOURCES: Dict[int, List[str]] = {
    1: [  # 头条
        "http://www.xinhuanet.com/rss/tt.xml",
        "http://www.people.com.cn/rss/10.xml",
    ],
    2: [  # 社会
        "http://www.people.com.cn/rss/11.xml",
        "http://society.people.com.cn/rss/society.xml",
    ],
    3: [  # 国内
        "http://www.xinhuanet.com/rss/gn.xml",
        "http://politics.people.com.cn/rss/politics.xml",
    ],
    4: [  # 国际
        "http://www.xinhuanet.com/rss/world.xml",
        "http://world.people.com.cn/rss/world.xml",
    ],
    5: [  # 娱乐
        "http://ent.people.com.cn/rss/ent.xml",
    ],
    6: [  # 体育
        "http://sports.people.com.cn/rss/sports.xml",
    ],
    7: [  # 军事
        "http://military.people.com.cn/rss/military.xml",
    ],
    8: [  # 科技
        "https://36kr.com/feed",
        "https://www.solidot.org/index.rss",
        "https://sspai.com/feed",
    ],
    9: [  # 财经
        "https://www.cls.cn/rss",
        "http://finance.people.com.cn/rss/finance.xml",
    ],
}

# ============================================================
# 内容生成模板 (用于扩充 RSS 摘要为完整文章)
# ============================================================
CONTENT_TEMPLATES = [
    # 模板 1: 事件报道型
    lambda t, c: (
        f"近日，{t}成为社会各界关注的焦点。\n\n"
        f"据多方消息源证实，相关事件在过去一周内持续发酵，引发了业内外的广泛讨论。"
        f"多位权威人士在接受采访时表示，这一发展态势对于{c}领域具有深远影响。\n\n"
        f"记者从相关部门了解到，目前已有多项配套措施正在积极推进中。"
        f"业内专家指出，此次事件或将推动相关政策的进一步完善与落地执行。\n\n"
        f"截至发稿时，各方仍在密切关注后续进展，预计未来数日内将有更多细节对外公布。"
    ),
    # 模板 2: 数据分析型
    lambda t, c: (
        f"最新数据显示，{t}。这一趋势在过去几个月中逐步显现，目前已引起行业内外的高度重视。\n\n"
        f"统计报告指出，相关指标较上年同期增长了约15%，显示出稳健的上升势头。"
        f"分析人士认为，这一变化的背后是多重因素共同作用的结果，包括政策利好、市场需求回升以及技术创新驱动。\n\n"
        f"展望未来，行业观察家普遍持乐观态度，预计相关领域在接下来的一段时间内将继续保持积极向好的发展态势。"
        f"不过，也有专家提醒需要关注潜在的风险因素，做到未雨绸缪。"
    ),
    # 模板 3: 政策解读型
    lambda t, c: (
        f"针对{t}这一热点话题，相关部门日前作出了权威回应。\n\n"
        f"在例行新闻发布会上，发言人详细阐述了当前的政策立场和工作部署。"
        f"他强调了此项工作的重要性和紧迫性，并表示将进一步加强统筹协调，确保各项任务落实到位。\n\n"
        f"多位政策研究学者在接受采访时指出，这一表态释放了积极的信号，"
        f"预计后续将有一系列具体措施陆续出台，对{c}行业产生实质性的推动作用。\n\n"
        f"普通民众对此也表达了高度关注，许多市民表示期待相关政策能够尽快惠及日常生活。"
    ),
    # 模板 4: 行业观察型
    lambda t, c: (
        f"在{c}领域，{t}正成为一个不可忽视的新趋势。\n\n"
        f"行业数据显示，越来越多的企业和机构开始在这一方向上布局，投入了可观的资源和精力。"
        f"某知名企业的负责人表示，这一趋势代表了行业未来的发展方向，公司将坚定不移地推进相关战略。\n\n"
        f"消费者端同样展现出了积极的反馈。市场调研表明，超过七成的受访者对此持正面态度，"
        f"并愿意为相关产品或服务支付合理溢价。\n\n"
        f"可以预见，在供需两端的共同推动下，这一趋势有望在未来几年内持续加速发展。"
    ),
    # 模板 5: 综合报道型
    lambda t, c: (
        f"{t}——这一消息自公布以来迅速引发刷屏效应。\n\n"
        f"从多个渠道汇总的信息来看，此次事件涉及的层面较为广泛，影响范围覆盖了多个关联领域。"
        f"一线从业者普遍认为，这对{c}行业的现有格局将产生重塑效应。\n\n"
        f"与此同时，社会各界也表达了对后续进展的关切。"
        f"某社会团体负责人表示，希望能够在推进过程中充分考虑到各方利益诉求，实现多方共赢。\n\n"
        f"本报将持续跟踪此事的最新动态，为读者带来第一时间的报道。"
    ),
]


def _generate_content(title: str, category_id: int) -> str:
    """根据标题和分类生成完整的新闻正文"""
    cat_name = CATEGORY_NAMES.get(category_id, "相关")
    template = random.choice(CONTENT_TEMPLATES)
    return template(title, cat_name)


# ============================================================
# 内置标题池 — 兜底用，确保始终能生成 300 条新闻
# ============================================================
FALLBACK_HEADLINES: Dict[int, List[Dict[str, str]]] = {
    1: [  # 头条 (55条)
        {"title": "全国两会代表委员热议高质量发展新路径", "author": "新华社"},
        {"title": "2026年经济'半年报'出炉 GDP同比增长5.2%", "author": "经济日报"},
        {"title": "中央经济工作会议部署下一阶段重点任务", "author": "新华社"},
        {"title": "我国数字经济规模突破60万亿元大关", "author": "人民日报"},
        {"title": "'十四五'规划中期评估结果公布 多项指标超预期", "author": "央视新闻"},
        {"title": "国务院常务会议审议通过多项惠企政策", "author": "中国政府网"},
        {"title": "我国成功发射天舟九号货运飞船", "author": "央视新闻"},
        {"title": "全国高考报名人数再创历史新高", "author": "教育部"},
        {"title": "中欧班列累计开行突破10万列", "author": "新华社"},
        {"title": "我国建成全球最大5G独立组网网络", "author": "科技日报"},
        {"title": "国家文化公园建设取得阶段性成果", "author": "人民日报"},
        {"title": "全国粮食产量连续9年稳定在1.3万亿斤以上", "author": "农业农村部"},
        {"title": "中国空间站科学实验取得重大突破", "author": "中国航天报"},
        {"title": "第三届'一带一路'国际合作高峰论坛成果丰硕", "author": "新华社"},
        {"title": "我国可再生能源装机占比首次超过煤电", "author": "国家能源局"},
        {"title": "全国统一大市场建设加速推进", "author": "经济日报"},
        {"title": "教育部发布'人工智能+教育'行动计划", "author": "中国教育报"},
        {"title": "我国成功研制新一代超级计算机", "author": "科技日报"},
        {"title": "全面深化改革委员会审议通过多项改革方案", "author": "新华社"},
        {"title": "我国快递年业务量突破1500亿件", "author": "国家邮政局"},
        {"title": "全国生态环境保护大会在京召开", "author": "生态环境部"},
        {"title": "我国首座商业化运行的四代核电站投产", "author": "中国能源报"},
        {"title": "2026世界人工智能大会在上海开幕", "author": "科技日报"},
        {"title": "我国人均预期寿命达到79.5岁", "author": "国家卫健委"},
        {"title": "全国碳市场交易额突破百亿元", "author": "经济日报"},
        {"title": "中国科学家首次实现远距离量子通信", "author": "中国科学报"},
        {"title": "全国安全生产形势持续稳定向好", "author": "应急管理部"},
        {"title": "我国最大海上风电场全容量并网发电", "author": "国家能源局"},
        {"title": "粤港澳大湾区建设迎来新一轮政策利好", "author": "新华社"},
        {"title": "我国自主研发的新冠特效药获批上市", "author": "中国医药报"},
        {"title": "全国新型城镇化建设现场会在成都召开", "author": "人民日报"},
        {"title": "中国与东盟自贸区3.0版谈判取得突破", "author": "商务部"},
        {"title": "我国完成首次火星采样返回任务", "author": "国家航天局"},
        {"title": "全国智慧城市建设评估报告发布", "author": "住建部"},
        {"title": "中国女科学家获联合国教科文组织杰出奖", "author": "科技日报"},
        {"title": "我国高速公路通车里程突破20万公里", "author": "交通运输部"},
        {"title": "全国医保支付改革覆盖所有统筹地区", "author": "国家医保局"},
        {"title": "全球首个商用高温气冷堆在山东投运", "author": "中国核能"},
        {"title": "中国代表团在巴黎奥运会取得境外最好成绩", "author": "新华社"},
        {"title": "我国IPv6活跃用户数突破8亿", "author": "中国信息通信研究院"},
        {"title": "全国首个国家级数据交易所挂牌运营", "author": "经济日报"},
        {"title": "中国科学家揭示衰老分子机制获重大突破", "author": "中国科学报"},
        {"title": "我国自主研发大型客机C929完成首飞", "author": "中国商飞"},
        {"title": "全国海水稻种植面积突破100万亩", "author": "农业农村部"},
        {"title": "中俄东线天然气管道全线贯通", "author": "中国石油报"},
        {"title": "我国成功发射首个大型空间巡天望远镜", "author": "国家航天局"},
        {"title": "全国基本养老保险参保人数达10.8亿", "author": "人社部"},
        {"title": "中国科学家利用AI破解蛋白质折叠难题", "author": "中国科学报"},
        {"title": "我国建成世界最大规模职业教育体系", "author": "教育部"},
        {"title": "全面取消制造业领域外资准入限制措施落地", "author": "国家发改委"},
        {"title": "全国汛期地质灾害防治工作取得显著成效", "author": "自然资源部"},
        {"title": "我国首条跨海高铁全线开通运营", "author": "中国铁路"},
        {"title": "中国企业文化出海论坛在北京举办", "author": "中国日报"},
        {"title": "全国首批无人驾驶出租车商业化运营启动", "author": "科技日报"},
        {"title": "国家生物安全战略研究中心正式成立", "author": "新华社"},
    ],
    2: [  # 社会 (55条)
        {"title": "多地社区创新养老服务模式获居民点赞", "author": "人民日报"},
        {"title": "全国反诈骗专项行动为群众挽回损失超百亿", "author": "公安部"},
        {"title": "年轻人'反向就业'趋势引关注 三四线城市吸引力增强", "author": "中国青年报"},
        {"title": "共享单车停放管理新规实施 违停将影响信用", "author": "北京日报"},
        {"title": "城市'口袋公园'建设超额完成年度目标", "author": "住建部"},
        {"title": "全国多地推行'落叶不扫' 保留城市秋意", "author": "人民日报"},
        {"title": "适老化改造让更多老年人享受便利生活", "author": "中国社会报"},
        {"title": "公益助学行动帮助万名困难学子圆大学梦", "author": "中国青年报"},
        {"title": "新款电动车充电桩进社区 解决'飞线充电'难题", "author": "应急管理报"},
        {"title": "全国'无废城市'建设试点扩大至100个", "author": "生态环境部"},
        {"title": "装修噪音扰民问题整治取得明显效果", "author": "法治日报"},
        {"title": "多地加强外卖食品安全监管 推广'食安封签'", "author": "市场监管总局"},
        {"title": "城市轨道交通'一码通行'覆盖更多城市", "author": "交通运输部"},
        {"title": "灵活就业者社保参保更加方便快捷", "author": "人社部"},
        {"title": "中小学课后延时服务内容更加丰富多元", "author": "中国教育报"},
        {"title": "绿色低碳生活成为更多年轻人的时尚选择", "author": "中国环境报"},
        {"title": "全国首批'一刻钟便民生活圈'试点成效显著", "author": "商务部"},
        {"title": "无障碍环境建设让残障人士出行更便捷", "author": "中国残疾人联合会"},
        {"title": "多地推出'妈妈岗'助力女性灵活就业", "author": "中国妇女报"},
        {"title": "二手交易平台规范化发展获政策支持", "author": "经济日报"},
        {"title": "加强犬只管理 多地推行'文明养犬'新举措", "author": "法治日报"},
        {"title": "社区食堂三年行动计划惠及更多老年人", "author": "民政部"},
        {"title": "全国城市生活垃圾分类覆盖率超过90%", "author": "住建部"},
        {"title": "'零工市场'线上线下一体化建设提速", "author": "人社部"},
        {"title": "防暑降温措施升级 保障户外劳动者安全", "author": "工人日报"},
        {"title": "全国首个'儿童友好城市'标准发布", "author": "国家发改委"},
        {"title": "医疗保障异地结算更加顺畅便捷", "author": "国家医保局"},
        {"title": "假期文旅市场火爆 多地游客量创历史新高", "author": "文化和旅游部"},
        {"title": "志愿服务融入社会治理 注册志愿者超2.5亿", "author": "中国社会报"},
        {"title": "打击整治养老诈骗专项行动再升级", "author": "公安部"},
        {"title": "新能源汽车充电基础设施建设全面提速", "author": "国家能源局"},
        {"title": "各地积极应对极端天气 保障群众生产生活", "author": "应急管理部"},
        {"title": "城市'夜经济'消费新场景不断涌现", "author": "经济日报"},
        {"title": "新就业形态劳动者权益保障制度逐步完善", "author": "全国总工会"},
        {"title": "生活垃圾焚烧发电厂变身'城市客厅'", "author": "中国环境报"},
        {"title": "多地学校体育场馆向公众开放获好评", "author": "中国教育报"},
        {"title": "老旧小区加装电梯工作跑出'加速度'", "author": "住建部"},
        {"title": "全国法律援助机构实现县级全覆盖", "author": "司法部"},
        {"title": "智能快递柜进农村 打通物流'最后一公里'", "author": "国家邮政局"},
        {"title": "各地优化生育政策配套措施相继落地", "author": "国家卫健委"},
        {"title": "高温津贴发放力度加大 覆盖范围拓宽", "author": "人社部"},
        {"title": "互联网平台企业加强算法透明度建设", "author": "国家网信办"},
        {"title": "我国注册护士总数突破600万人", "author": "国家卫健委"},
        {"title": "城市慢行交通系统建设提升出行品质", "author": "交通运输部"},
        {"title": "退役军人就业创业扶持政策效果显著", "author": "退役军人事务部"},
        {"title": "公共图书馆延长开放时间 打造'夜读'空间", "author": "文化和旅游部"},
        {"title": "各地探索'时间银行'互助养老新模式", "author": "中国社会报"},
        {"title": "全国铁路暑运发送旅客量创历史新高", "author": "中国铁路"},
        {"title": "无障碍电影让视障人士共享文化盛宴", "author": "中国残疾人联合会"},
        {"title": "未成年人网络保护取得阶段性成效", "author": "国家网信办"},
        {"title": "城市'边角地'变身运动健身空间", "author": "国家体育总局"},
        {"title": "婚姻登记'跨省通办'覆盖面进一步扩大", "author": "民政部"},
        {"title": "全国首批'零碳社区'试点名单公布", "author": "住建部"},
        {"title": "各地开展校园食品安全排查整治行动", "author": "市场监管总局"},
        {"title": "外卖骑手权益保障专项行动全面展开", "author": "全国总工会"},
    ],
    3: [  # 国内 (55条)
        {"title": "长三角生态绿色一体化发展再出新举措", "author": "新华社"},
        {"title": "雄安新区启动区城市框架全面拉开", "author": "河北日报"},
        {"title": "成渝双城经济圈重大项目集中开工", "author": "四川日报"},
        {"title": "海南自贸港封关运作准备工作基本就绪", "author": "海南日报"},
        {"title": "粤港澳大湾区'一小时生活圈'加速形成", "author": "南方日报"},
        {"title": "黄河流域生态保护和高质量发展成效显著", "author": "人民日报"},
        {"title": "京津冀协同发展交通一体化实现新突破", "author": "北京日报"},
        {"title": "西部陆海新通道铁海联运班列突破万列", "author": "新华社"},
        {"title": "东北振兴战略实施20周年交出亮眼成绩单", "author": "经济日报"},
        {"title": "长江十年禁渔成效显现 江豚种群数量回升", "author": "农业农村部"},
        {"title": "中部地区高质量发展指数稳步提升", "author": "国家统计局"},
        {"title": "横琴粤澳深度合作区建设进入快车道", "author": "新华社"},
        {"title": "浙江省共同富裕示范区建设取得阶段性成果", "author": "浙江日报"},
        {"title": "前海深港现代服务业合作区扩容提质", "author": "深圳特区报"},
        {"title": "北部湾城市群发展规划获批复", "author": "国家发改委"},
        {"title": "川藏铁路全线贯通进入倒计时", "author": "中国铁路"},
        {"title": "浦东社会主义现代化建设引领区改革深化", "author": "解放日报"},
        {"title": "大运河文化带建设成果丰硕", "author": "文化和旅游部"},
        {"title": "三北防护林工程六期全面启动", "author": "国家林草局"},
        {"title": "郑州航空港经济综合实验区扩容升级", "author": "河南日报"},
        {"title": "粤港澳联合实验室增至50家", "author": "科技日报"},
        {"title": "长株潭都市圈发展规划落地实施", "author": "湖南日报"},
        {"title": "南水北调后续工程加快推进", "author": "水利部"},
        {"title": "上海国际金融中心建设能级持续提升", "author": "金融时报"},
        {"title": "国家级新区引领高质量发展新格局", "author": "经济日报"},
        {"title": "青岛上合示范区建设取得新突破", "author": "大众日报"},
        {"title": "京津冀氢能走廊示范应用场景不断丰富", "author": "中国能源报"},
        {"title": "苏州工业园区人工智能产业规模破千亿", "author": "新华日报"},
        {"title": "北京城市副中心三大文化建筑对外开放", "author": "北京日报"},
        {"title": "深圳综合改革试点第二批清单落地", "author": "深圳特区报"},
        {"title": "西电东送特高压直流工程全面投产", "author": "国家电网"},
        {"title": "京雄高速全线通车 北京到雄安仅需1小时", "author": "交通运输部"},
        {"title": "成渝中线高铁开工建设", "author": "中国铁路"},
        {"title": "海南热带雨林国家公园生态修复成效显著", "author": "国家林草局"},
        {"title": "粤港澳大湾区量子科学中心揭牌", "author": "科技日报"},
        {"title": "西安国家中心城市能级不断提升", "author": "陕西日报"},
        {"title": "环渤海高铁网建设全面提速", "author": "中国铁路"},
        {"title": "云南面向南亚东南亚辐射中心建设加速", "author": "云南日报"},
        {"title": "海峡两岸数字经济融合发展试验区揭牌", "author": "福建日报"},
        {"title": "黄河口国家公园创建进入冲刺阶段", "author": "国家林草局"},
        {"title": "合肥综合性国家科学中心再添新平台", "author": "安徽日报"},
        {"title": "赣粤运河前期工作取得重要进展", "author": "交通运输部"},
        {"title": "武汉光谷科技创新大走廊建设提速", "author": "湖北日报"},
        {"title": "兰州新区绿色化工产业园蓬勃发展", "author": "甘肃日报"},
        {"title": "厦门金砖国家新工业革命伙伴关系创新基地成果丰硕", "author": "福建日报"},
        {"title": "贵州大数据综合试验区建设迈上新台阶", "author": "贵州日报"},
        {"title": "青藏高原生态保护法实施成效显著", "author": "新华社"},
        {"title": "南通长江口产业创新协同区揭牌", "author": "新华日报"},
        {"title": "郑洛新国家自主创新示范区发展提速", "author": "河南日报"},
        {"title": "重庆两江新区汽车产业迈向万亿级", "author": "重庆日报"},
        {"title": "平陆运河全线贯通 打通西南出海新通道", "author": "广西日报"},
        {"title": "宁波舟山港年货物吞吐量蝉联全球第一", "author": "浙江日报"},
        {"title": "呼包鄂榆城市群发展规划获批", "author": "国家发改委"},
        {"title": "天山北坡城市群大气污染治理成效显著", "author": "新疆日报"},
        {"title": "哈尔滨新区对俄合作全面升级", "author": "黑龙江日报"},
    ],
    4: [  # 国际 (55条)
        {"title": "联合国大会通过全球人工智能治理决议", "author": "新华社"},
        {"title": "金砖国家扩员后首次峰会取得重要共识", "author": "央视新闻"},
        {"title": "欧盟通过新一轮绿色新政一揽子方案", "author": "经济日报"},
        {"title": "东盟与中日韩深化产业链供应链合作", "author": "新华社"},
        {"title": "世界银行上调2026年全球经济增长预期", "author": "经济日报"},
        {"title": "RCEP全面生效一周年 成员国贸易额显著增长", "author": "商务部"},
        {"title": "上合组织成员国安全合作迈上新台阶", "author": "新华社"},
        {"title": "G20峰会聚焦全球粮食安全与气候融资", "author": "央视新闻"},
        {"title": "亚太经合组织贸易部长会议达成多项共识", "author": "经济日报"},
        {"title": "美国大选初选结果出炉 两党对决格局初定", "author": "环球时报"},
        {"title": "俄乌和平谈判出现建设性进展", "author": "新华社"},
        {"title": "中日韩领导人会议时隔多年重启", "author": "央视新闻"},
        {"title": "英国与欧盟关系回暖 签署新合作协议", "author": "环球时报"},
        {"title": "法国总统推动欧盟战略自主倡议", "author": "人民日报"},
        {"title": "非洲大陆自贸区建设取得实质性进展", "author": "经济日报"},
        {"title": "印度成功发射载人飞船 成为第四个载人航天国家", "author": "科技日报"},
        {"title": "巴西承办2026年气候峰会筹备工作全面启动", "author": "新华社"},
        {"title": "中东多国关系正常化进程持续推进", "author": "环球时报"},
        {"title": "全球央行协调行动应对通胀回落", "author": "金融时报"},
        {"title": "CPTPP扩员谈判取得积极进展", "author": "商务部"},
        {"title": "世界卫生组织宣布新冠疫情不再构成全球紧急状态", "author": "新华社"},
        {"title": "朝鲜半岛局势出现缓和信号", "author": "环球时报"},
        {"title": "全球半导体供应链重构趋势明显", "author": "经济日报"},
        {"title": "欧洲央行连续降息 欧元区经济温和复苏", "author": "金融时报"},
        {"title": "上海合作组织地区反恐合作成果显著", "author": "新华社"},
        {"title": "北极航道商业化运营迎来新机遇", "author": "央视新闻"},
        {"title": "全球可再生能源投资首次超过化石能源", "author": "国际能源署"},
        {"title": "国际移民组织发布全球移民趋势报告", "author": "联合国新闻"},
        {"title": "东盟数字经济框架协议谈判接近尾声", "author": "经济日报"},
        {"title": "全球粮食价格指数连续三个月下降", "author": "联合国粮农组织"},
        {"title": "世界贸易组织改革谈判取得突破", "author": "新华社"},
        {"title": "国际空间站迎来首位非洲宇航员", "author": "科技日报"},
        {"title": "德国经济温和增长 制造业订单回暖", "author": "经济日报"},
        {"title": "伊核问题新一轮谈判在维也纳举行", "author": "环球时报"},
        {"title": "全球海洋塑料污染治理协议达成", "author": "联合国环境署"},
        {"title": "中亚五国元首峰会聚焦互联互通", "author": "新华社"},
        {"title": "国际货币基金组织完成新一轮份额改革", "author": "金融时报"},
        {"title": "东南亚数字经济报告发布 印尼领跑区域增长", "author": "经济日报"},
        {"title": "全球南方国家合作机制日益成熟", "author": "人民日报"},
        {"title": "北极科考队发现重大气候变化证据", "author": "中国科学报"},
        {"title": "中日经济高层对话达成多项合作共识", "author": "新华社"},
        {"title": "国际刑事法院迎来成立以来重要改革", "author": "环球时报"},
        {"title": "澜湄合作机制第七次领导人会议召开", "author": "人民日报"},
        {"title": "全球电动汽车销量占比首次突破25%", "author": "国际能源署"},
        {"title": "中欧班列助推沿线国家经济繁荣", "author": "新华社"},
        {"title": "中阿合作论坛第十届部长级会议成果丰硕", "author": "央视新闻"},
        {"title": "国际海底管理局通过深海采矿新规", "author": "中国海洋报"},
        {"title": "全球数字贸易规则谈判进入关键阶段", "author": "经济日报"},
        {"title": "巴以和平进程出现新的转机", "author": "环球时报"},
        {"title": "东盟旅游复苏强劲 中国游客贡献最大", "author": "文化和旅游部"},
        {"title": "全球生物多样性保护资金缺口有望缩小", "author": "联合国开发计划署"},
        {"title": "国际能源论坛聚焦全球能源转型路径", "author": "中国能源报"},
        {"title": "中国-中亚天然气管道D线全线贯通", "author": "新华社"},
        {"title": "世界经济论坛发布全球竞争力报告", "author": "经济日报"},
        {"title": "国际海事组织通过航运减排新目标", "author": "交通运输部"},
    ],
    5: [  # 娱乐 (55条)
        {"title": "国产科幻电影票房突破60亿 刷新影史纪录", "author": "新浪娱乐"},
        {"title": "知名导演张艺谋新作入围戛纳电影节主竞赛", "author": "1905电影网"},
        {"title": "现象级网剧续集定档 预约观看人数破千万", "author": "腾讯娱乐"},
        {"title": "华语乐坛新生代歌手巡回演唱会场场爆满", "author": "网易娱乐"},
        {"title": "国潮文化综艺节目收视率持续走高", "author": "央视综艺"},
        {"title": "中国动画电影在国际电影节斩获大奖", "author": "1905电影网"},
        {"title": "短剧市场迎来精品化转型元年", "author": "新浪娱乐"},
        {"title": "著名演员获颁终身成就奖 从艺50年", "author": "中国电影报"},
        {"title": "AI虚拟偶像演唱会创下线上观看新纪录", "author": "腾讯娱乐"},
        {"title": "国风音乐节吸引数万乐迷 传统文化焕新彩", "author": "网易娱乐"},
        {"title": "国产互动式电影游戏全球销量突破百万", "author": "搜狐娱乐"},
        {"title": "知名编剧新作引发社会价值观讨论热潮", "author": "新京报"},
        {"title": "头部视频平台加大原创内容投入力度", "author": "经济日报"},
        {"title": "纪录片《中国村落》获国际纪录片节大奖", "author": "央视纪录"},
        {"title": "数字人演员首次在商业大片中担任重要角色", "author": "科技日报"},
        {"title": "经典老歌翻唱在短视频平台意外走红", "author": "抖音娱乐"},
        {"title": "中国独立电影在国际影展大放异彩", "author": "1905电影网"},
        {"title": "网络文学IP全链路开发模式日趋成熟", "author": "中国出版传媒商报"},
        {"title": "综艺节目引入AI评委引发行业讨论", "author": "新浪娱乐"},
        {"title": "国产动漫《深海2》定档暑期 预售破亿", "author": "1905电影网"},
        {"title": "中国歌手首次登上格莱美颁奖礼舞台", "author": "网易娱乐"},
        {"title": "微短剧出海成绩亮眼 东南亚市场表现强劲", "author": "国家广电总局"},
        {"title": "传统戏曲数字化传承项目获联合国表彰", "author": "中国文化报"},
        {"title": "院线电影窗口期进一步缩短 流媒体同步上映", "author": "经济日报"},
        {"title": "中国电影工业化水平显著提升 特效不输好莱坞", "author": "中国电影报"},
        {"title": "影视取景地带动地方旅游经济快速增长", "author": "文化和旅游部"},
        {"title": "脱口秀行业规范化发展迈入新阶段", "author": "新京报"},
        {"title": "明星公益基金会影响力日益扩大", "author": "中国社会报"},
        {"title": "虚拟拍摄技术革命改变影视制作流程", "author": "科技日报"},
        {"title": "电影衍生品市场蓝海待掘 规模潜力巨大", "author": "经济日报"},
        {"title": "国民级综艺节目迎来第十季 情怀满满", "author": "腾讯娱乐"},
        {"title": "国产音乐剧市场呈现井喷式增长", "author": "中国文化报"},
        {"title": "沉浸式戏剧体验成为年轻人社交新选择", "author": "北京日报"},
        {"title": "网络音频平台用户规模突破6亿", "author": "CNNIC"},
        {"title": "经典IP翻拍潮来袭 致敬与创新如何平衡", "author": "新浪娱乐"},
        {"title": "华语电影海外发行渠道不断拓宽", "author": "中国电影报"},
        {"title": "数字藏品与影视IP跨界融合探索新模式", "author": "经济日报"},
        {"title": "青年导演扶持计划孵化出多部精品力作", "author": "国家电影局"},
        {"title": "短剧出海成为文化输出的新力量", "author": "人民日报"},
        {"title": "演唱会经济带动相关产业链全面复苏", "author": "经济日报"},
        {"title": "国产科幻IP宇宙初具规模 多部联动作品筹备中", "author": "1905电影网"},
        {"title": "电子竞技题材影视作品关注度持续攀升", "author": "腾讯娱乐"},
        {"title": "乡村音乐教师培养计划让艺术之花绽放山野", "author": "中国教育报"},
        {"title": "综艺节目'去流量化'回归内容本质", "author": "新京报"},
        {"title": "中国动漫产业总产值突破3000亿元", "author": "中国动漫集团"},
        {"title": "电影分线发行模式试点范围扩大", "author": "国家电影局"},
        {"title": "AI作曲工具降低音乐创作门槛", "author": "科技日报"},
        {"title": "沉浸式文旅演艺项目成为景区新标配", "author": "文化和旅游部"},
        {"title": "中国电影银幕数量稳居全球第一", "author": "中国电影报"},
        {"title": "名家书画数字版权交易日渐活跃", "author": "中国文化报"},
        {"title": "头部MCN机构加速布局海外市场", "author": "经济日报"},
        {"title": "非遗手工艺与时尚品牌跨界合作成风潮", "author": "人民日报"},
        {"title": "音乐节下沉三四线城市 激活县域文旅消费", "author": "文化和旅游部"},
        {"title": "国产精品短剧集获得艾美奖提名", "author": "国家广电总局"},
        {"title": "中国电影拍摄制作基地国际化进程加速", "author": "1905电影网"},
    ],
    6: [  # 体育 (55条)
        {"title": "中国男篮世界杯预选赛取得关键胜利", "author": "体坛周报"},
        {"title": "郑钦文法网女单闯入四强 创个人最佳", "author": "新浪体育"},
        {"title": "中超联赛战至中程 争冠集团形势胶着", "author": "体坛周报"},
        {"title": "中国女篮亚洲杯决赛逆转夺冠", "author": "新华社"},
        {"title": "苏炳添复出首秀跑出10秒05", "author": "新浪体育"},
        {"title": "中国游泳队世锦赛收获5金创历届最佳", "author": "央视体育"},
        {"title": "冬奥场馆赛后利用成效显著 四季运营", "author": "人民日报"},
        {"title": "国乒包揽世乒赛全部五项金牌", "author": "体坛周报"},
        {"title": "中国选手首获世界摩托车锦标赛分站冠军", "author": "新浪体育"},
        {"title": "校园足球联赛参赛人数突破百万大关", "author": "教育部"},
        {"title": "中国电竞战队夺得英雄联盟世界赛冠军", "author": "腾讯电竞"},
        {"title": "马拉松赛事经济带动举办地消费增长", "author": "中国体育报"},
        {"title": "中国女排世界联赛豪取十连胜", "author": "新浪体育"},
        {"title": "青少年体育培训市场规范化管理加强", "author": "国家体育总局"},
        {"title": "中国羽毛球混双组合登顶世界排名第一", "author": "体坛周报"},
        {"title": "田径钻石联赛上海站多项纪录被刷新", "author": "央视体育"},
        {"title": "冬奥冠军创办冰雪运动公益基金", "author": "中国体育报"},
        {"title": "中国男子网球选手首进ATP前十", "author": "新浪体育"},
        {"title": "全国全民健身运动参与人数突破5亿", "author": "国家体育总局"},
        {"title": "CBA联赛改革新赛季推出多项创新举措", "author": "体坛周报"},
        {"title": "中国帆船运动员完成环球航行壮举", "author": "中国体育报"},
        {"title": "匹克球运动在国内迅速走红", "author": "人民日报"},
        {"title": "体操世锦赛中国小将包揽男子全能冠亚军", "author": "央视体育"},
        {"title": "户外运动产业规模预计突破3万亿元", "author": "国家体育总局"},
        {"title": "中国击剑队奥运积分赛表现亮眼", "author": "体坛周报"},
        {"title": "街舞入奥后中国选手训练体系全面升级", "author": "中国体育报"},
        {"title": "世界大学生运动会在成都圆满落幕", "author": "新华社"},
        {"title": "中国冰球联赛吸引北美外援加盟", "author": "新浪体育"},
        {"title": "体育科技融合加速 AI辅助训练系统普及", "author": "科技日报"},
        {"title": "中国跆拳道选手世锦赛斩获三金", "author": "体坛周报"},
        {"title": "群众冰雪运动'南展西扩东进'成效显著", "author": "国家体育总局"},
        {"title": "国家步道体系建设规划发布 总里程逾万公里", "author": "国家发改委"},
        {"title": "中国柔道队完成新老交替 年轻选手崭露头角", "author": "中国体育报"},
        {"title": "体育赛事直播引入XR沉浸式观赛体验", "author": "科技日报"},
        {"title": "中国跳水'梦之队'世锦赛包揽全部金牌", "author": "央视体育"},
        {"title": "运动康复产业发展进入快车道", "author": "经济日报"},
        {"title": "中国选手在斯诺克世锦赛实现突破", "author": "新浪体育"},
        {"title": "县级'三大球'联赛体系全面建成", "author": "国家体育总局"},
        {"title": "铁人三项运动参与人数年增长率超30%", "author": "中国体育报"},
        {"title": "中国射箭队打破尘封十年的世界纪录", "author": "体坛周报"},
        {"title": "虚拟体育赛事参与人次突破千万", "author": "中国体育报"},
        {"title": "中国选手首夺UFC金腰带", "author": "新浪体育"},
        {"title": "多地推出'体育消费券'激发运动热情", "author": "国家体育总局"},
        {"title": "中国皮划艇激流回旋项目实现世锦赛突破", "author": "体坛周报"},
        {"title": "青少年脊柱健康筛查纳入学校体育工作", "author": "教育部"},
        {"title": "武术入奥努力持续推进 国际武联扩大影响", "author": "中国体育报"},
        {"title": "中国自由式滑雪运动员实现高难度动作突破", "author": "央视体育"},
        {"title": "体育旅游精品线路带动乡村振兴", "author": "文化和旅游部"},
        {"title": "中国举重队完成新老交替 年轻力量崛起", "author": "体坛周报"},
        {"title": "全国智能健身房数量三年增长五倍", "author": "经济日报"},
        {"title": "中国拳击运动员在世界拳王争霸赛中卫冕", "author": "新浪体育"},
        {"title": "体育仲裁委员会正式运行 纠纷解决机制完善", "author": "国家体育总局"},
        {"title": "中国团队完成无动力横渡太平洋壮举", "author": "中国体育报"},
        {"title": "民族传统体育运动会参赛规模创历届之最", "author": "国家民委"},
        {"title": "飞盘运动规范化发展 首届全国联赛启动", "author": "中国体育报"},
    ],
    7: [  # 军事 (55条)
        {"title": "中国第三艘国产航母完成首次远海训练", "author": "解放军报"},
        {"title": "空军歼-35隐身战斗机正式列装作训部队", "author": "环球时报"},
        {"title": "海军新型万吨大驱编队赴远海演练", "author": "解放军报"},
        {"title": "火箭军新型战略导弹试射成功", "author": "央视军事"},
        {"title": "陆军合成旅信息化作战能力大幅提升", "author": "解放军报"},
        {"title": "国防科技大学研制出新型量子雷达", "author": "科技日报"},
        {"title": "中国维和部队获联合国特别表彰", "author": "新华社"},
        {"title": "空军'红剑'体系对抗演习规模创纪录", "author": "央视军事"},
        {"title": "海军陆战队全域作战能力建设提速", "author": "解放军报"},
        {"title": "我国新一代远程轰炸机完成首飞", "author": "环球时报"},
        {"title": "北斗三号全球系统军用定位精度再提升", "author": "中国航天报"},
        {"title": "中俄'海上联合-2026'军演圆满结束", "author": "解放军报"},
        {"title": "陆军航空兵列装新型武装直升机", "author": "央视军事"},
        {"title": "战略支援部队网络防御能力全面提升", "author": "解放军报"},
        {"title": "中国军工企业研制的无人战车通过测试", "author": "中国国防报"},
        {"title": "海警部队大型巡逻舰批量列装", "author": "央视军事"},
        {"title": "空军无人机部队实弹打靶命中率100%", "author": "解放军报"},
        {"title": "我国高超声速武器技术达世界领先水平", "author": "环球时报"},
        {"title": "国防动员体制改革全面深化", "author": "中国国防报"},
        {"title": "海军潜艇部队新型潜艇正式入列", "author": "解放军报"},
        {"title": "空降兵部队全域直达作战能力显著增强", "author": "央视军事"},
        {"title": "国产大型运输机运-20批量列装", "author": "中国航空报"},
        {"title": "中巴'雄鹰'空军联合训练圆满完成", "author": "解放军报"},
        {"title": "新型单兵作战系统全面提升士兵战斗力", "author": "中国国防报"},
        {"title": "我军首支网络空间部队正式亮相", "author": "环球时报"},
        {"title": "电磁炮武器系统实弹测试获重大突破", "author": "科技日报"},
        {"title": "海军航空兵歼-15舰载机夜间起降训练常态化", "author": "解放军报"},
        {"title": "中国军事医学研究取得多项突破", "author": "中国科学报"},
        {"title": "武警部队反恐处突能力建设全面升级", "author": "央视军事"},
        {"title": "国产新型预警机性能达国际领先水平", "author": "中国航空报"},
        {"title": "我军后勤保障智能化水平大幅提升", "author": "解放军报"},
        {"title": "中国与东盟举行首次联合海上演习", "author": "新华社"},
        {"title": "军用人工智能辅助决策系统投入实战化应用", "author": "科技日报"},
        {"title": "陆军装甲部队换装新型主战坦克", "author": "解放军报"},
        {"title": "我国反导拦截系统实现技术跨越", "author": "环球时报"},
        {"title": "海军新型补给舰大幅提升远洋保障能力", "author": "解放军报"},
        {"title": "空军地空导弹部队全时域战备值班", "author": "央视军事"},
        {"title": "中国航天部队快速响应发射能力获突破", "author": "中国航天报"},
        {"title": "军民融合深度发展格局基本形成", "author": "经济日报"},
        {"title": "新型隐身无人机完成作战效能评估", "author": "中国航空报"},
        {"title": "我军联合作战指挥体系改革成效显著", "author": "解放军报"},
        {"title": "边防部队智能化巡逻体系全面建成", "author": "央视军事"},
        {"title": "国产新型两栖攻击舰正式服役", "author": "环球时报"},
        {"title": "军事院校教育改革培养新型指挥人才", "author": "解放军报"},
        {"title": "我国激光武器技术发展取得重大进展", "author": "科技日报"},
        {"title": "火箭军某新型导弹旅形成全面作战能力", "author": "解放军报"},
        {"title": "海军扫雷舰队换装新型无人扫雷系统", "author": "央视军事"},
        {"title": "中国参加国际军事比赛获多项冠军", "author": "中国国防报"},
        {"title": "陆军航空兵高原作战训练水平显著提升", "author": "解放军报"},
        {"title": "国产新型电子战机亮相 性能先进", "author": "环球时报"},
        {"title": "军事物流体系智能化改造全面完成", "author": "解放军报"},
        {"title": "我国首艘核动力破冰船完成极地测试", "author": "中国船舶报"},
        {"title": "空军'金头盔'竞赛考核难度升级", "author": "央视军事"},
        {"title": "中国与中亚国家边防合作机制日趋完善", "author": "新华社"},
        {"title": "新型战场救护系统大幅降低战伤死亡率", "author": "中国国防报"},
    ],
    8: [  # 科技 (55条)
        {"title": "国产大模型在多项国际基准测试中刷新纪录", "author": "科技日报"},
        {"title": "中国科学家实现室温超导材料重大突破", "author": "中国科学报"},
        {"title": "华为发布下一代芯片 性能提升300%", "author": "IT之家"},
        {"title": "我国量子计算机'九章四号'实现算力飞跃", "author": "科技日报"},
        {"title": "全球最大海上漂浮式风电机组并网发电", "author": "中国能源报"},
        {"title": "中国脑机接口技术首次实现人脑意念打字", "author": "中国科学报"},
        {"title": "国产操作系统生态应用突破500万款", "author": "IT之家"},
        {"title": "钠离子电池量产技术取得关键突破", "author": "科技日报"},
        {"title": "我国成功研制出2纳米芯片制造设备", "author": "中国电子报"},
        {"title": "人工智能大模型在医疗诊断中准确率超95%", "author": "健康报"},
        {"title": "中国建成全球首个6G试验卫星网络", "author": "通信世界"},
        {"title": "第三代半导体材料规模化生产实现国产替代", "author": "科技日报"},
        {"title": "全球首款消费级AR眼镜在国内发售", "author": "IT时报"},
        {"title": "中国科学家开发出可降解塑料新技术", "author": "中国科学报"},
        {"title": "液流电池储能技术效率突破85%", "author": "中国能源报"},
        {"title": "我国成功研发全球首个通用AI智能体平台", "author": "科技日报"},
        {"title": "自动驾驶L4级别在全国多个城市开放运营", "author": "中国交通报"},
        {"title": "中国光伏组件转换效率再创世界纪录", "author": "中国能源报"},
        {"title": "开源中国社区注册开发者突破5000万", "author": "IT之家"},
        {"title": "科学家发现新型基因编辑工具 精准度更高", "author": "中国科学报"},
        {"title": "国内首条全固态电池生产线投产", "author": "科技日报"},
        {"title": "元宇宙标准化工作组成立 行业规范待出", "author": "工信部"},
        {"title": "中国科学家首次合成新型碳基材料", "author": "中国科学报"},
        {"title": "AI蛋白质结构预测准确率接近100%", "author": "科技日报"},
        {"title": "我国完成全球首次低轨卫星与手机直连通话", "author": "通信世界"},
        {"title": "国产工业软件市场占有率首次突破40%", "author": "中国电子报"},
        {"title": "仿生机器人行走能力接近人类水平", "author": "科技日报"},
        {"title": "全球最大深远海养殖平台在青岛交付", "author": "中国海洋报"},
        {"title": "中国科学家开发出高效碳捕集新方法", "author": "中国科学报"},
        {"title": "柔性显示屏量产良率突破90%大关", "author": "中国电子报"},
        {"title": "大模型驱动的科学发现平台上线运行", "author": "科技日报"},
        {"title": "国内首台E级超算系统正式投入运行", "author": "中国科学报"},
        {"title": "中国人形机器人实现后空翻等高难度动作", "author": "科技日报"},
        {"title": "钙钛矿太阳能电池稳定性难题获解", "author": "中国能源报"},
        {"title": "全球首个大型语言模型安全评估体系发布", "author": "国家网信办"},
        {"title": "中国科学家在火星水冰资源探测中获新发现", "author": "国家航天局"},
        {"title": "类脑芯片商业化应用取得里程碑进展", "author": "科技日报"},
        {"title": "国内云计算市场规模突破万亿元", "author": "中国信息通信研究院"},
        {"title": "中国团队实现远距离无线电力传输", "author": "中国科学报"},
        {"title": "5G+工业互联网融合应用案例超万个", "author": "工信部"},
        {"title": "中国成功建设全球最大量子保密通信网络", "author": "科技日报"},
        {"title": "AI发现新抗生素 对抗耐药菌显奇效", "author": "中国科学报"},
        {"title": "固态储氢技术实现车载应用突破", "author": "中国能源报"},
        {"title": "中国科学家首次实现器官3D打印移植", "author": "中国科学报"},
        {"title": "国家级人工智能算力中心集群建成", "author": "科技日报"},
        {"title": "我国自主研发的深海采矿车完成海试", "author": "中国海洋报"},
        {"title": "大数据精准农业技术覆盖亿亩农田", "author": "农业农村部"},
        {"title": "中国成功发射太阳极轨探测卫星", "author": "国家航天局"},
        {"title": "可穿戴设备无创血糖监测技术获准上市", "author": "中国医药报"},
        {"title": "空间太阳能电站关键技术验证成功", "author": "科技日报"},
        {"title": "中国开源大模型下载量全球第一", "author": "IT之家"},
        {"title": "智能网联汽车测试里程突破1亿公里", "author": "工信部"},
        {"title": "中国科学家首次观测到暗物质存在证据", "author": "中国科学报"},
        {"title": "数字孪生技术助力智慧城市建设提速", "author": "住建部"},
        {"title": "我国建成全球最大的光纤宽带网络", "author": "工信部"},
    ],
    9: [  # 财经 (55条)
        {"title": "央行宣布定向降准 释放长期流动性约万亿", "author": "金融时报"},
        {"title": "A股市场迎来增量资金 沪指重回3500点", "author": "证券时报"},
        {"title": "人民币国际化指数创历史新高", "author": "经济日报"},
        {"title": "全面注册制改革深化 新股发行效率提升", "author": "证券时报"},
        {"title": "数字人民币跨境支付试点城市达30个", "author": "金融时报"},
        {"title": "新能源汽车产业链上市公司业绩亮眼", "author": "经济日报"},
        {"title": "北交所上市公司数量突破300家", "author": "证券时报"},
        {"title": "绿色债券发行规模同比增长35%", "author": "金融时报"},
        {"title": "跨境电商进出口额首次突破3万亿元", "author": "商务部"},
        {"title": "公募基金管理规模站上30万亿元", "author": "中国基金报"},
        {"title": "科创板硬科技企业研发投入持续加大", "author": "证券时报"},
        {"title": "粤港澳大湾区跨境理财通额度翻倍", "author": "金融时报"},
        {"title": "中国与沙特签署货币互换协议", "author": "经济日报"},
        {"title": "个人养老金制度全面推开 参与人数破亿", "author": "人社部"},
        {"title": "民营经济促进法草案公开征求意见", "author": "国家发改委"},
        {"title": "保险资金入市比例上限提高至40%", "author": "中国银保监会"},
        {"title": "中国制造业PMI连续六个月位于扩张区间", "author": "国家统计局"},
        {"title": "中美审计监管合作取得积极进展", "author": "证监会"},
        {"title": "城投平台市场化转型取得实质性突破", "author": "经济日报"},
        {"title": "最新CPI数据显示物价保持温和上涨", "author": "国家统计局"},
        {"title": "REITs市场扩容至消费基础设施领域", "author": "证券时报"},
        {"title": "光伏企业海外建厂步伐加快", "author": "经济日报"},
        {"title": "多地调整购房政策 楼市成交量回暖", "author": "住建部"},
        {"title": "中国外汇储备规模连续三月回升", "author": "中国人民银行"},
        {"title": "ESG投资理念在国内基金行业加速普及", "author": "中国基金报"},
        {"title": "氢能产业投资热度不减 一季度超500亿", "author": "经济日报"},
        {"title": "跨境数据流动安全管理框架初步建立", "author": "国家网信办"},
        {"title": "商业航天投融资持续活跃 多家企业IPO", "author": "证券时报"},
        {"title": "中资企业海外并购质量明显提升", "author": "经济日报"},
        {"title": "普惠金融覆盖率和服务质量双提升", "author": "金融时报"},
        {"title": "中国半导体设备国产化率首次超过30%", "author": "中国电子报"},
        {"title": "期货市场国际化步伐加快 境外参与度提升", "author": "中国期货业协会"},
        {"title": "全国碳排放权交易市场扩容在即", "author": "生态环境部"},
        {"title": "独角兽企业数量中国稳居全球第二", "author": "经济日报"},
        {"title": "供应链金融数字化转型成效显著", "author": "金融时报"},
        {"title": "资本市场对外开放政策持续加码", "author": "证监会"},
        {"title": "中国品牌汽车出口单价稳步提升", "author": "中国汽车工业协会"},
        {"title": "多地发放消费券 促进服务业快速回暖", "author": "商务部"},
        {"title": "银行理财子公司资产管理规模稳步增长", "author": "中国银保监会"},
        {"title": "科创板做市商制度运行平稳 流动性提升", "author": "证券时报"},
        {"title": "地方政府专项债发行使用进度加快", "author": "财政部"},
        {"title": "中国东盟自贸区3.0版关税减让落地", "author": "商务部"},
        {"title": "生物医药企业海外授权交易金额创新高", "author": "中国医药报"},
        {"title": "数字货币桥项目多边央行合作深化", "author": "金融时报"},
        {"title": "消费类基础设施公募REITs正式上市", "author": "证券时报"},
        {"title": "中国制造业数字化转型投入年均增长15%", "author": "工信部"},
        {"title": "跨境贸易人民币结算占比持续提高", "author": "中国人民银行"},
        {"title": "新能源车企盈利拐点普遍到来", "author": "经济日报"},
        {"title": "社保基金投资运营年均收益率超7%", "author": "全国社保基金理事会"},
        {"title": "大宗商品价格走势分化 能源类上涨明显", "author": "中国期货业协会"},
        {"title": "中欧投资协定后续谈判取得进展", "author": "商务部"},
        {"title": "中国经济增速在全球主要经济体中保持领先", "author": "国家统计局"},
        {"title": "金融科技监管沙盒试点项目落地率超80%", "author": "中国人民银行"},
        {"title": "创投基金投资早期科创企业占比提升", "author": "中国基金业协会"},
        {"title": "中国债券市场成为全球第二大债券市场", "author": "金融时报"},
    ],
}


# ============================================================
# 核心逻辑
# ============================================================

def _fetch_rss_entries(sources: List[str]) -> List[dict]:
    """从 RSS 源列表中拉取新闻条目"""
    entries = []
    for url in sources:
        try:
            resp = requests.get(url, timeout=FETCH_TIMEOUT, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
            if resp.status_code != 200:
                logger.warning(f"RSS 源返回 {resp.status_code}: {url}")
                continue
            feed = feedparser.parse(resp.content)
            for entry in feed.entries:
                entries.append({
                    "title": entry.get("title", "").strip(),
                    "description": entry.get("summary", entry.get("description", "")).strip(),
                    "link": entry.get("link", ""),
                    "published": entry.get("published", entry.get("updated", "")),
                })
            logger.info(f"  RSS 源 [{url}] → 获取 {len(feed.entries)} 条")
        except Exception as e:
            logger.warning(f"RSS 源获取失败 [{url}]: {e}")
    return entries


def _clean_html(text: str) -> str:
    """简单去除 HTML 标签"""
    import re
    clean = re.sub(r'<[^>]+>', '', text)
    return clean.strip()


def _build_news_items(
    rss_entries: List[dict],
    fallback_headlines: List[Dict[str, str]],
    category_id: int,
    target_count: int,
) -> List[dict]:
    """将 RSS 条目 + 兜底标题池混合，生成指定数量的新闻条目"""
    items = []
    cat_name = CATEGORY_NAMES.get(category_id, "综合")

    # 1. 优先使用 RSS 条目
    for entry in rss_entries:
        title = _clean_html(entry["title"])
        description = _clean_html(entry.get("description", ""))
        if not title or len(title) < 4:
            continue
        content = description if len(description) > 100 else _generate_content(title, category_id)
        items.append({
            "title": title[:255],
            "description": description[:500] if description else title,
            "content": content,
            "author": "综合报道",
            "category_id": category_id,
        })
        if len(items) >= target_count:
            break

    # 2. 不足则用兜底标题池补充
    remaining = target_count - len(items)
    if remaining > 0 and fallback_headlines:
        # 随机打乱，每次取不同的
        pool = random.sample(fallback_headlines, min(remaining, len(fallback_headlines)))
        for h in pool:
            items.append({
                "title": h["title"][:255],
                "description": h["title"][:500],
                "content": _generate_content(h["title"], category_id),
                "author": h.get("author", "综合报道"),
                "category_id": category_id,
            })

    # 3. 如果还不够（标题池也不够 target），补充更多
    while len(items) < target_count and fallback_headlines:
        h = random.choice(fallback_headlines)
        items.append({
            "title": f"{h['title']}（续报）",
            "description": h["title"][:500],
            "content": _generate_content(h["title"], category_id),
            "author": h.get("author", "综合报道"),
            "category_id": category_id,
        })

    return items[:target_count]


async def fetch_and_replace_news():
    """
    核心任务: 拉取新闻并替换数据库中的全部新闻。
    - 9 个分类平均分配
    - 总计精确等于 TARGET_TOTAL
    - 先删后插 (事务性替换)
    """
    logger.info(f"=" * 50)
    logger.info(f"开始拉取新闻... 目标总量: {TARGET_TOTAL}")

    # 计算每个分类的目标数量
    base_per_category = TARGET_TOTAL // CATEGORY_COUNT  # 33
    remainder = TARGET_TOTAL % CATEGORY_COUNT  # 3
    targets = {}
    for cid in range(1, CATEGORY_COUNT + 1):
        targets[cid] = base_per_category + (1 if cid <= remainder else 0)
    logger.info(f"各分类目标: {targets}")

    # 从 RSS 拉取所有条目 (按分类)
    all_rss: Dict[int, List[dict]] = {}
    for cid, sources in RSS_SOURCES.items():
        entries = _fetch_rss_entries(sources)
        all_rss[cid] = entries
        logger.info(f"  分类 {cid} ({CATEGORY_NAMES[cid]}): RSS 获取 {len(entries)} 条")

    total_rss = sum(len(v) for v in all_rss.values())
    logger.info(f"RSS 总计获取: {total_rss} 条")

    # 为每个分类构建新闻条目
    all_news = []
    for cid in range(1, CATEGORY_COUNT + 1):
        items = _build_news_items(
            rss_entries=all_rss.get(cid, []),
            fallback_headlines=FALLBACK_HEADLINES.get(cid, []),
            category_id=cid,
            target_count=targets[cid],
        )
        all_news.extend(items)
        logger.info(f"  分类 {cid} ({CATEGORY_NAMES[cid]}): 最终 {len(items)} 条")

    # 如果总数不足（极端情况），从所有分类的兜底池补充
    shortfall = TARGET_TOTAL - len(all_news)
    if shortfall > 0:
        logger.warning(f"总数不足 {TARGET_TOTAL}，差 {shortfall} 条，从全局兜底补充")
        all_headlines = []
        for cid, headlines in FALLBACK_HEADLINES.items():
            for h in headlines:
                all_headlines.append({**h, "category_id": cid})
        random.shuffle(all_headlines)
        for i in range(shortfall):
            h = all_headlines[i % len(all_headlines)]
            all_news.append({
                "title": h["title"][:255],
                "description": h["title"][:500],
                "content": _generate_content(h["title"], h["category_id"]),
                "author": h.get("author", "综合报道"),
                "category_id": h["category_id"],
            })

    # 精确截断到 TARGET_TOTAL
    all_news = all_news[:TARGET_TOTAL]
    logger.info(f"最终新闻总数: {len(all_news)}")

    # --- 数据库写入: 先删后插 ---
    async with AsyncSessionLocal() as db:
        try:
            # 删除全部旧新闻
            del_result = await db.execute(delete(News))
            logger.info(f"已清除 {del_result.rowcount} 条旧新闻")

            # 批量插入新新闻
            now = datetime.now()
            news_objs = []
            for i, item in enumerate(all_news):
                # 错开发布时间 (最近 24 小时内)
                offset_minutes = int((len(all_news) - i) * (24 * 60 / len(all_news)))
                publish_time = now - timedelta(minutes=offset_minutes)
                news_objs.append(News(
                    title=item["title"],
                    description=item.get("description", ""),
                    content=item.get("content", ""),
                    image=f"https://picsum.photos/seed/news{i+int(time.time())}/400/300",
                    author=item.get("author", "综合报道"),
                    category_id=item["category_id"],
                    views=random.randint(100, 50000),
                    publish_time=publish_time,
                ))

            db.add_all(news_objs)
            await db.commit()
            logger.info(f"✓ 成功插入 {len(news_objs)} 条新闻")
        except Exception as e:
            await db.rollback()
            logger.error(f"数据库写入失败: {e}")
            raise

    # 清除 Redis 中的新闻缓存（数据已更新，旧缓存失效）
    try:
        from services.cache import invalidate_news_cache
        await invalidate_news_cache()
    except Exception:
        pass

    logger.info(f"新闻库刷新完成! 当前保有 {TARGET_TOTAL} 条")
    logger.info(f"=" * 50)


# ============================================================
# 调度器集成
# ============================================================

_scheduler_started = False


def start_scheduler():
    """在 FastAPI 启动时调用，初始化 APScheduler"""
    global _scheduler_started
    if _scheduler_started:
        return
    _scheduler_started = True

    from apscheduler.schedulers.background import BackgroundScheduler

    scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
    scheduler.start()
    logger.info(f"新闻调度器已启动 — 每 {FETCH_INTERVAL_MINUTES} 分钟拉取一次")

    # 首次拉取: 用线程异步执行，延迟 3 秒等一切就绪
    import threading
    def _initial_fetch():
        import time as _time
        _time.sleep(3)
        asyncio.run(_safe_fetch())
    t = threading.Thread(target=_initial_fetch, daemon=True)
    t.start()
    logger.info("首次新闻拉取将在 3 秒后开始...")

    # 定时任务: 每 FETCH_INTERVAL_MINUTES 分钟执行
    scheduler.add_job(
        lambda: asyncio.run(_safe_fetch()),
        "interval",
        minutes=FETCH_INTERVAL_MINUTES,
        id="news_fetch_periodic",
    )


async def _safe_fetch():
    """带异常保护的拉取函数"""
    try:
        await fetch_and_replace_news()
    except Exception as e:
        logger.error(f"新闻拉取异常: {e}", exc_info=True)
