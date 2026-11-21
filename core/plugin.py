"""插件协议：新增客户端 = 新增一个实现 Plugin 的目录，内核不动。"""
from abc import ABC, abstractmethod

from fastapi import APIRouter


class Plugin(ABC):
    name: str = "unnamed"
    version: str = "0.1.0"

    @abstractmethod
    def routes(self) -> APIRouter:
        """返回该插件的路由，内核挂到 /api/v1/<name> 下。"""

    def health(self) -> dict:
        return {"ok": True, "plugin": self.name, "version": self.version}

    def on_enable(self):
        """启用钩子：建表、初始化私钥引用等（骨架留空）。"""

    def on_disable(self):
        """停用钩子。"""
