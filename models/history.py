from datetime import datetime

from sqlalchemy import Integer, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column

from models.users import Base


class History(Base):
    __tablename__ = "history"

    __table_args__ = (
        Index("fk_history_user_idx", "user_id"),
        Index("uq_history_user_news", "user_id", "news_id", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="历史ID")
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id"), nullable=False, comment="用户ID")
    news_id: Mapped[int] = mapped_column(Integer, ForeignKey("news.id"), nullable=False, comment="新闻ID")
    view_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, comment="浏览时间")
