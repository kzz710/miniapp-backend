"""pytest 公共配置：统一内存 SQLite，测试不访问真实大模型与本地数据库。"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.db.models  # noqa: F401  注册 ORM 模型
from app import config as app_config
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.utils.cache import cache

# 默认关闭实时取价，避免测试调用外部大模型；需要时用 monkeypatch 打开
app_config.LLM_PROVIDER = "deepseek"
app_config.DEEPSEEK_API_KEY = ""
app_config.LOGIN_RATE_LIMIT_PER_MINUTE = 0

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(
    bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
)


def _override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = _override_get_db


@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    cache.clear()
    yield


@pytest.fixture
def session_factory():
    """供需要自行开 session 的服务（如后台刷新）在测试中替换使用。"""
    return TestingSessionLocal
