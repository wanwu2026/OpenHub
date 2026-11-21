"""更新检查插件占位——验证「新增客户端 = 新增插件」的扩展性。

本轮不实现业务；留空骨架证明内核不会因空插件崩溃（health 仍 ok）。
未来实现要点见 docs/API_CONTRACT.md §7：更新清单签名 + APK 签名证书指纹双校验。
"""
from fastapi import APIRouter

from core.plugin import Plugin

router = APIRouter()


class UpdatePlugin(Plugin):
    name = "update"
    version = "0.1.0-dev"

    def routes(self) -> APIRouter:
        return router
