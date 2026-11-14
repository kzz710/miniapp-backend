"""数据库连接与会话管理。

默认 SQLite（文件位于 ./data/app.db），生产可通过 DATABASE_URL 切换到 MySQL。
注意：SQLite 并发写能力有限，gunicorn 多 worker 部署时应切到 MySQL，
或保持单 worker 运行。
"""
import os
from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app import config
from app.db.base import Base


def _build_engine():
    url = config.DATABASE_URL
    kwargs: dict = {"pool_pre_ping": True, "future": True}
    if url.startswith("sqlite"):
        # 确保 SQLite 文件所在目录存在
        path = url.split("///", 1)[-1]
        if path and path != ":memory:":
            directory = os.path.dirname(os.path.abspath(path))
            if directory:
                os.makedirs(directory, exist_ok=True)
        # timeout：拿不到写锁时等待而非立即报错（并发写场景）
        kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
    return create_engine(url, **kwargs)


def _enable_sqlite_wal(dbapi_connection, _record) -> None:
    """SQLite 开启 WAL 与 busy_timeout，提升并发读写稳定性。"""
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
    finally:
        cursor.close()


engine = _build_engine()
if config.DATABASE_URL.startswith("sqlite"):
    event.listen(engine, "connect", _enable_sqlite_wal)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """建表（MVP 用；生产改用 Alembic 迁移）。"""
    import app.db.models  # noqa: F401  确保模型已注册
    from app.db.migrate import migrate_users_platform

    Base.metadata.create_all(bind=engine)
    migrate_users_platform(engine)
