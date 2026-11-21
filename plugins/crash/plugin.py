"""崩溃上报插件占位——离线队列 + 重试退避 + 批量上报 + PII 脱敏（待实现）。"""
from fastapi import APIRouter

from core.plugin import Plugin

router = APIRouter()


class CrashPlugin(Plugin):
    name = "crash"
    version = "0.1.0-dev"

    def routes(self) -> APIRouter:
        return router
