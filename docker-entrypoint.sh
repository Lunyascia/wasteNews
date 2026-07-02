#!/bin/bash
# ============================================================
# wasteNews 后端 Docker 入口脚本
# 1. 等待 MySQL 就绪
# 2. 创建数据库表 + 种子数据
# 3. 启动 uvicorn (新闻调度器在 lifespan 中自动启动)
# ============================================================
set -e

echo "========================================="
echo "  wasteNews 后端启动"
echo "========================================="

# -------- 等待 MySQL --------
echo "[1/3] 等待 MySQL 就绪 (${DB_HOST:-db}:${DB_PORT:-3306})..."
while ! python -c "
import socket, time
s = socket.socket()
s.settimeout(2)
try:
    s.connect(('${DB_HOST:-db}', int('${DB_PORT:-3306}')))
    s.close()
    exit(0)
except Exception:
    exit(1)
" 2>/dev/null; do
    echo "     等待中..."
    sleep 2
done
echo "     MySQL 已就绪 ✓"

# -------- 初始化数据库 --------
echo "[2/3] 初始化数据库表..."
python init_db.py
echo "     初始化完成 ✓"

# -------- 启动应用 --------
echo "[3/3] 启动 FastAPI (uvicorn)..."
exec uvicorn main:app --host 0.0.0.0 --port 8000 --log-level info
