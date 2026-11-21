"""数据库骨架：SQLAlchemy 引擎与会话，SQLite 起步 / PostgreSQL 可切。"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from core.config import settings

engine = create_engine(
    f"sqlite:///{settings.db_path}",
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False)


class Base(DeclarativeBase):
    pass


def init_db():
    settings.ensure_dirs()
    # 内核表：函数内导入避免 core.models -> core.db 的循环导入
    from core import models  # noqa: F401
    Base.metadata.create_all(engine)
