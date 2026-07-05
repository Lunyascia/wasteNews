# 🗞️ 新闻脉动 — 全栈新闻资讯平台

全栈新闻资讯应用，后端 **FastAPI + MySQL + Redis**，前端 **Vue 3 + Vant 4**，Docker Compose 一键部署。

> 前端仓库：[xwzx-news](https://github.com/Lunyascia/xwzx-news)（Vue 3 + Vite + Pinia + Vant 4）

---

## ✨ 功能特性

- **用户系统** — 注册 / 登录 / 个人信息修改 / 密码修改，Token 认证（7 天有效期）
- **新闻浏览** — 9 大分类、分页列表、详情页、相关推荐、浏览量统计
- **收藏 & 历史** — 新闻收藏、浏览历史记录
- **RSS 自动抓取** — APScheduler 定时从多 RSS 源拉取新闻，数据库恒定维持 300 条，每 30 分钟全量刷新
- **Redis 缓存加速** — 新闻分类/列表/详情缓存、Token 快速鉴权、浏览量 Redis 计数器 + 每 5 分钟批量入库
- **国际化** — 中 / 英文切换（vue-i18n）
- **AI 智能对话** — 接入阿里通义千问大模型，SSE 流式传输实时对话（前端集成）
- **Docker 一键部署** — MySQL + Redis + FastAPI + Nginx 四容器编排，`docker compose up -d` 即用

---

## 🛠️ 技术栈

| 层级 | 技术 |
|------|------|
| **后端框架** | FastAPI 0.136 (异步) |
| **ORM** | SQLAlchemy 2.0 (异步) + aiomysql |
| **数据库** | MySQL 8.0 |
| **缓存** | Redis 7 (redis-py 异步) |
| **定时任务** | APScheduler 3.10 |
| **RSS 解析** | feedparser 6.0 |
| **密码加密** | passlib + bcrypt |
| **前端框架** | Vue 3 (Composition API) + Vite 7 |
| **UI 组件** | Vant 4 (移动端) |
| **状态管理** | Pinia 3 + 持久化插件 |
| **国际化** | vue-i18n |
| **AI 大模型** | 阿里 DashScope（通义千问）+ SSE 流式 |
| **部署** | Docker + Docker Compose + Nginx |

---

## 📁 项目结构

```
wasteNews/
├── main.py                   # FastAPI 入口 + 应用生命周期
├── requirements.txt          # Python 依赖
├── init_db.py                # 数据库初始化（建表 + 分类 + 测试用户）
├── docker-compose.yml        # Docker 四服务编排
├── Dockerfile.backend        # 后端镜像
├── docker-entrypoint.sh      # 容器启动脚本
├── init.sql                  # MySQL 初始化 SQL
│
├── config/
│   ├── db_conf.py            # 数据库连接（环境变量注入）
│   └── redis_conf.py         # Redis 异步客户端 + 连接池
│
├── models/                   # SQLAlchemy ORM 模型
│   ├── users.py              #   User + UserToken
│   ├── news.py               #   Category + News
│   ├── favorite.py           #   Favorite
│   └── history.py            #   History
│
├── schemas/                  # Pydantic 请求/响应模型
│   └── users.py
│
├── crud/                     # 数据库操作层
│   ├── users.py              #   用户 CRUD + Token 鉴权（Redis 优先）
│   ├── news.py               #   新闻 CRUD
│   ├── favorite.py           #   收藏 CRUD
│   └── history.py            #   历史 CRUD
│
├── routers/                  # API 路由
│   ├── users.py              #   /api/user/*
│   ├── news.py               #   /api/news/*
│   ├── favorite.py           #   /api/favorite/*
│   └── history.py            #   /api/history/*
│
├── services/                 # 业务服务
│   ├── cache.py              #   Redis 缓存封装
│   └── news_fetcher.py       #   RSS 新闻自动抓取调度器
│
└── utils/
    └── security.py           # 密码哈希工具
```

---

## 🚀 快速开始

### 方式一：Docker Compose（推荐）

```bash
# 1. 克隆仓库
git clone https://github.com/Lunyascia/wasteNews.git
cd wasteNews

# 2. 配置环境变量（可选，默认值即可运行）
cp .env.example .env

# 3. 一键启动（MySQL + Redis + FastAPI + Nginx）
docker compose up -d

# 4. 查看日志
docker compose logs -f backend
```

启动后访问：
- **后端 API 文档**：http://localhost:8000/docs （Swagger 自动生成）
- **前端页面**：http://localhost:8080

### 方式二：本地开发

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 确保 MySQL + Redis 已运行，修改 config/db_conf.py 中的连接信息

# 3. 初始化数据库
python init_db.py

# 4. 启动后端
uvicorn main:app --reload

# 5. 启动前端（在 xwzx-news 目录）
cd ../xwzx-news
npm install && npm run dev
```

后端 http://localhost:8000，前端 http://localhost:5173。

> 本地开发需自行启动 MySQL 和 Redis，Docker 方式无需手动配置。

---

## 📡 API 概览

所有接口返回统一格式：

```json
{
  "code": 200,
  "message": "操作成功",
  "data": { ... }
}
```

### 用户模块 `/api/user`

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| POST | `/register` | 用户注册 | ❌ |
| POST | `/login` | 用户登录 | ❌ |
| GET | `/info` | 获取当前用户信息 | ✅ |
| PUT | `/update` | 更新个人简介 | ✅ |
| PUT | `/password` | 修改密码 | ✅ |

### 新闻模块 `/api/news`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/categories` | 获取新闻分类列表 |
| GET | `/list` | 分页新闻列表（支持分类筛选） |
| GET | `/detail` | 新闻详情 + 相关推荐 |

### 收藏 & 历史

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| POST | `/api/favorite/add` | 收藏新闻 | ✅ |
| DELETE | `/api/favorite/remove` | 取消收藏 | ✅ |
| GET | `/api/favorite/list` | 收藏列表 | ✅ |
| POST | `/api/history/add` | 添加浏览记录 | ✅ |
| GET | `/api/history/list` | 浏览历史 | ✅ |

> 完整接口文档见 `API文档.txt`，使用教程见 `使用文档.txt`。

---

## 🏗️ 架构亮点

```
浏览器 / 移动端
      │
      ▼
   Nginx (前端静态 + /api 反向代理)
      │
      ▼
   FastAPI 后端
      │
      ├── Redis 缓存层 ────── 新闻分类/列表/详情缓存
      │                     Token 快速鉴权
      │                     浏览量计数器（异步批量入库）
      │
      ├── MySQL 数据库 ───── 用户、新闻、收藏、历史
      │
      └── APScheduler ───── RSS 新闻自动抓取（每 30 分钟刷新）
                            浏览量批量入库（每 5 分钟）
```

- **Redis 优先鉴权**：Token 验证先查 Redis 缓存，未命中再查 MySQL 并回写缓存
- **浏览量优化**：详情页浏览量写入 Redis 计数器，APScheduler 每 5 分钟批量 UPDATE，避免高并发下频繁写库
- **新闻自动刷新**：首次启动自动拉取 300 条新闻，之后每 30 分钟全量刷新并自动失效相关缓存
- **缓存 TTL 分级**：分类 1 小时 / 列表 3 分钟 / 详情 10 分钟，平衡实时性与性能

---

## 🧪 测试账号

| 用户名 | 密码 |
|--------|------|
| admin | 123456 |

（`init_db.py` 自动创建，Docker 启动时自动执行）

---

## 📄 License

MIT
