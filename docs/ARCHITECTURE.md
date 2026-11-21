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
| `plugins/update/` | 更新检查插件（清单签名 + 指纹双校验：store.py + plugin.py，5 路由） |
| `plugins/crash/` | 崩溃上报插件（PII 脱敏 + 限流 + 批量 + 状态：store.py + plugin.py，3 路由） |
| `templates/`, `static/` | 管理后台 UI |
| `deploy/` | 一键安装、Docker Compose、systemd 单元、加固 Dockerfile |
| `tests/` | 内核鉴权/审计 + cardkey + update/crash 端到端（共 17 项） |
| `docs/` | 本说明 + API 契约 |

## 插件是怎么被加载的

`app.py` 启动时调用 `core.registry.discover(enabled)`：
1. 扫 `plugins/` 下的包，只看 `OPENHUB_ENABLED_PLUGINS` 列出的；
2. 导入 `plugins.<name>.plugin`，找 `Plugin` 的子类并实例化；
3. 调 `on_enable()`，把 `routes()` 挂到 `/api/v1/<name>`。

早期 update/crash 曾是空插件（只有类没有路由），加载后 health 正常——这本身验证了扩展性。现已填实为标准插件：各自带 `store.py`（独立建表）+ `plugin.py`（路由+业务），复用内核鉴权/包络/错误码，复用 `plugins.cardkey.signing` 的签名原语，不重复造轮子。

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

- ✅ 已真启动服务（本地 uvicorn + TestClient），cardkey 发卡/验卡/一机一码/封禁全链路通过；17 项测试全绿（cardkey 4 + 内核 6 + update/crash 7）。
- ✅ 鉴权落库：API Key 只存 SHA-256 哈希，明文仅创建时返回一次，可管理/吊销；bootstrap 凭据保留用于首次安装。
- ✅ 审计写入：每次请求记 method/path/status/key_id（不记 token），管理接口可查。
- ✅ CI：`.github/workflows/test.yml` 跑 compileall + pytest；`.github/workflows/docker-build.yml` 在 ubuntu runner 上真跑 `docker build` + compose 配置校验 + 冒烟健康检查。
- ✅ update/crash 已填实（详见契约 §7.1/§7.2）。
- ⚠️ 本机无 Docker daemon（无 docker/podman/任意运行时、无 socket、非 root），Docker 路径靠 Actions 真机构建验证，本机只做静态语法校验（pyyaml + bash -n）。
- 下一步：git 初始化发布（需用户确认凭据与仓库名，**尚未 push**）。
