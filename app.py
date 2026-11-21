"""OpenHub 应用入口。"""
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from core import audit
from core.config import settings, BASE_DIR
from core.db import init_db
from core.errors import ApiError
from core.registry import discover
from core import web
from api import core_routes

app = FastAPI(title=settings.app_name, version="1.0.0")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# 这些路径不写审计（噪音：文档、静态资源、favicon）
_AUDIT_SKIP = ("/docs", "/openapi.json", "/redoc", "/static", "/favicon.ico")


@app.middleware("http")
async def request_id_and_audit(request: Request, call_next):
    request.state.request_id = request.headers.get("X-Request-ID", "req_local")
    response = await call_next(request)
    path = request.url.path
    if not path.startswith(_AUDIT_SKIP):
        try:
            audit.record(
                request_id=request.state.request_id,
                method=request.method,
                path=path,
                status=response.status_code,
                key_id=getattr(request.state, "key_id", None),
            )
        except Exception as exc:  # 审计失败不能影响业务响应
            print(f"[OpenHub] 审计写入失败: {exc}")
    return response


@app.exception_handler(ApiError)
async def api_error_handler(request: Request, exc: ApiError):
    return exc.response(request)


@app.on_event("startup")
def startup():
    init_db()
    plugins = discover(settings.enabled_plugins)
    for name, plugin in plugins.items():
        plugin.on_enable()
        app.include_router(plugin.routes(), prefix=f"/api/v1/{name}")
        app.state.plugins = plugins


# 健康检查与内核接口统一由 core_routes 提供（含插件列表）
app.include_router(core_routes.router, prefix="/api/v1/core")

# Web 管理后台（/ 提供界面；JSON 信息在 /api/v1/core/health）
app.include_router(web.router)
