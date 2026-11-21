"""插件注册中心：扫描 plugins/<name>/plugin.py，加载继承 Plugin 的类。"""
import importlib
import pkgutil
from pathlib import Path

from core.plugin import Plugin


def discover(enabled: list[str]) -> dict[str, Plugin]:
    found: dict[str, Plugin] = {}
    plugins_dir = Path(__file__).resolve().parent.parent / "plugins"
    for mod in pkgutil.iter_modules([str(plugins_dir)]):
        if mod.name not in enabled:
            continue
        try:
            package = importlib.import_module(f"plugins.{mod.name}.plugin")
        except Exception as exc:  # 骨架阶段插件可能尚未实现
            print(f"[OpenHub] 插件 {mod.name} 加载失败，跳过: {exc}")
            continue
        for attr in dir(package):
            obj = getattr(package, attr)
            if (
                isinstance(obj, type)
                and issubclass(obj, Plugin)
                and obj is not Plugin
            ):
                inst = obj()
                found[inst.name] = inst
                break
    return found
