from fastapi import FastAPI
from routers import news


app = FastAPI()

# 挂载路由
app.include_router(news.router)
