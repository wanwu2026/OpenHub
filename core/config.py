"""配置：环境变量优先，提供开发默认值。"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


class Settings:
    app_name = os.getenv("OPENHUB_APP_NAME", "OpenHub")
    api_version = "v1"
    host = os.getenv("OPENHUB_HOST", "0.0.0.0")
    port = _int("OPENHUB_PORT", 8080)

    data_dir = Path(os.getenv("OPENHUB_DATA_DIR", str(BASE_DIR / "data")))
    db_path = data_dir / "openhub.db"

    # 管理 token 与初始 API key 由 install.sh 生成后写入 .env
    admin_token = os.getenv("OPENHUB_ADMIN_TOKEN", "dev-admin-token-CHANGE-ME")
    initial_api_key = os.getenv("OPENHUB_INITIAL_API_KEY", "ohk_dev-CHANGE-ME")
    enabled_plugins = [
        p.strip()
        for p in os.getenv("OPENHUB_ENABLED_PLUGINS", "cardkey,update,crash").split(",")
        if p.strip()
    ]

    # CardKey 插件：私钥只在服务器（环境变量给路径，绝不进仓库/客户端）
    cardkey_private_key = os.getenv("OPENHUB_CARDKEY_PRIVATE_KEY", "")
    cardkey_product = os.getenv("OPENHUB_CARDKEY_PRODUCT", "demo_app")

    # update 插件：清单签名密钥。未配置时回退到 cardkey 私钥；公钥给客户端验签
    update_private_key = os.getenv("OPENHUB_UPDATE_PRIVATE_KEY", "")
    update_public_key_base64 = os.getenv("OPENHUB_UPDATE_PUBLIC_KEY_BASE64", "")

    def ensure_dirs(self):
        self.data_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
