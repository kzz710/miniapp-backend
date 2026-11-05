"""FastAPI 应用入口：两个核心接口 + 健康检查 + CORS + 本地托管文档。"""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.staticfiles import StaticFiles

from app import config
from app.api import auth as auth_api
from app.api import posts as posts_api
from app.db.session import init_db
from app.engine import run_plan
from app.services.car_price import get_car_price
from app.types import CalcParams, CalcResult, CarPriceResult

_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

@asynccontextmanager
def _check_secrets() -> None:
    """默认密钥可用于本地开发，但绝不允许带进生产。"""
    if config.JWT_SECRET != config.DEFAULT_JWT_SECRET:
        return
    if config.WX_MOCK_LOGIN or not (config.WX_APPID and config.WX_SECRET):
        print("[警告] JWT_SECRET 仍为默认值，仅限本地开发；生产必须配置随机密钥")
        return
    raise RuntimeError(
        "JWT_SECRET 仍为默认值，拒绝启动：请配置随机密钥（如 openssl rand -hex 32）"
    )


async def lifespan(app: FastAPI):
    _check_secrets()
    print(f"[启动] LLM 来源：{config.llm_label()}")
    if config.LLM_PROVIDER == "deepseek":
        print(f"[启动] 检索来源(搜索)：{config.search_label()}")
    if config.WX_MOCK_LOGIN or not (config.WX_APPID and config.WX_SECRET):
        print("[启动] 微信登录：mock 模式（生产环境请配置 WX_APPID / WX_SECRET）")
    init_db()
    print(f"[启动] 数据库：{config.DATABASE_URL}")
    yield


# 关闭默认的 /docs、/redoc（它们走 jsdelivr CDN，国内常超时）；改为本地托管。
app = FastAPI(
    title="买车决策小程序 · 后端",
    description="车型价格检索增强 + 购车费用测算 + 可负担性评估。",
    version="0.1.0",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
)

# 挂载本地静态资源（含 Swagger UI / Redoc 的 JS、CSS）。
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui():
    """本地托管的 Swagger UI，不依赖任何外部 CDN。"""
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=f"{app.title} - Swagger UI",
        swagger_js_url="/static/swagger/swagger-ui-bundle.js",
        swagger_css_url="/static/swagger/swagger-ui.css",
    )


@app.get("/redoc", include_in_schema=False)
async def custom_redoc():
    """本地托管的 Redoc，不依赖任何外部 CDN。"""
    return get_redoc_html(
        openapi_url=app.openapi_url,
        title=f"{app.title} - ReDoc",
        redoc_js_url="/static/swagger/redoc.standalone.js",
    )

# 开发期放开 CORS（H5 / 本地联调）。生产应限定具体域名。
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "live_mode": config.live_mode()}


@app.post("/api/queryCarPrice", response_model=CarPriceResult)
async def query_car_price(body: dict) -> CarPriceResult:
    """查询车型价格：缓存 -> 实时 RAG -> 示例库兜底。"""
    keyword = body.get("keyword", "")
    return await get_car_price(keyword)


@app.post("/api/calcPlan", response_model=CalcResult)
async def calc_plan(params: CalcParams) -> CalcResult:
    """费用测算 + 可负担性评估（纯函数，确定性计算结果）。"""
    return run_plan(params)


# 用户系统 / 广场 / 审批
app.include_router(auth_api.router)
app.include_router(posts_api.router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=config.PORT, reload=True)
