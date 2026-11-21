# OpenHub 架构说明

## 核心矛盾与解法

需求是「通用，支持之前和未来任何客户端」+「一次性部署到服务器」。
通用与好用有张力：什么都服务的后端容易每个业务都半吊子。
解法是**内核 + 插件**：

- **内核**（`core/` + `api/`）：所有客户端共享，写一次——鉴权、设备、配置下发、产物托管、审计、插件引擎。
- **插件**（`plugins/<name>/`）：各客户端差异化部分。加客户端 = 加插件，内核不动。

## 分层

```
HTTP 请求
  → 中间件（request_id + 审计写入）
  → 路由层（api/core_routes.py + plugins/*/plugin.py）
  → 鉴权（core/auth.py：bootstrap 或查库哈希）
  → 内核服务（core/）
  → 数据层（core/db.py, SQLite）
```

## 目录职责

| 目录 | 职责 |
|---|---|
| `core/` | 配置、错误码、插件协议、注册中心、数据库、鉴权、密钥管理、审计、Web UI 路由 |
| `api/` | 内核 API 路由（`/api/v1/core/*`，含 keys/audit） |
| `plugins/cardkey/` | 发卡插件（已从 CardKeySDK/demo-backend 迁入：签发核心 + 状态机 + 4 路由） |
| `plugins/update/` | 更新检查插件占位 |
| `plugins/crash/` | 崩溃上报插件占位 |
| `templates/`, `static/` | 管理后台 UI |
| `deploy/` | 一键安装、Docker Compose、systemd 单元 |
| `tests/` | 内核鉴权/审计测试 + cardkey 端到端测试（共 10 项） |
| `docs/` | 本说明 + API 契约 |

## 插件是怎么被加载的

`app.py` 启动时调用 `core.registry.discover(enabled)`：
1. 扫 `plugins/` 下的包，只看 `OPENHUB_ENABLED_PLUGINS` 列出的；
2. 导入 `plugins.<name>.plugin`，找 `Plugin` 的子类并实例化；
3. 调 `on_enable()`，把 `routes()` 挂到 `/api/v1/<name>`。

空插件（如本轮的 update/crash）只有类没有路由，加载后 health 正常——这本身就验证了扩展性。

## 规范化契约

对外约定集中在 `docs/API_CONTRACT.md`：统一路由前缀、统一鉴权、统一响应包络、统一错误码、版本化。
FastAPI 的 `/docs` 自动生成 OpenAPI，直接当契约文档用。

**重点**：产物记录强制带 `signer_fingerprint`（APK 签名证书 SHA-256）。客户端更新时必须双校验（清单签名 + APK 指纹），只做前者可被中间人换 URL——契约层就把它列为必填。

## 部署

`deploy/install.sh [--mode docker|bare]` 一条命令：检测环境 → 生成凭据（`.env`，600）→ 拉起服务。
- Docker：compose 构建 + 卷挂载数据/私钥；
- 裸机：venv + pip + systemd（无 systemd 时给手动启动命令）。

私钥与数据库都在 `data/`，被 `.gitignore` 排除，不进镜像层、不进仓库。

## 当前状态（诚实标注）

- ✅ 已真启动服务（本地 uvicorn + TestClient），cardkey 发卡/验卡/一机一码/封禁全链路通过；10 项测试全绿。
- ✅ 鉴权落库：API Key 只存 SHA-256 哈希，明文仅创建时返回一次，可管理/吊销；bootstrap 凭据保留用于首次安装。
- ✅ 审计写入：每次请求记 method/path/status/key_id（不记 token），管理接口可查。
- ✅ CI：`.github/workflows/test.yml` 在 push/PR 跑 compileall + pytest。
- ⚠️ 本机无 Docker，Docker 部署路径未在本机跑过；update/crash 仍是空插件。
- 下一步：填 update/crash 插件 → 中英双语文档 → git 初始化发布。
