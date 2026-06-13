from datetime import datetime

from sqlalchemy import Integer, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column

from models.users import Base


class Favorite(Base):
    __tablename__ = "favorite"

    __table_args__ = (
        Index("fk_favorite_user_idx", "user_id"),
        Index("uq_favorite_user_news", "user_id", "news_id", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="收藏ID")
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id"), nullable=False, comment="用户ID")
    news_id: Mapped[int] = mapped_column(Integer, ForeignKey("news.id"), nullable=False, comment="新闻ID")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, comment="收藏时间")
