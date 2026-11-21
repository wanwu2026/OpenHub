# OpenHub · 通用后端服务平台

> 🤖 本项目由 AI 生成。

[中文](README.md) | [English](README_EN.md)

一个可**一次性部署到服务器**的通用后端平台：Web 管理后台、APK/产物管理、可插拔业务模块，为现有 CardKey 和未来的客户端 SDK 提供规范化的后端服务。

**核心设计**：内核 + 插件。内核写一次（鉴权/设备/配置/产物/审计），加客户端 = 加一个插件，内核不动。

## 当前状态：内核可用 + 第一个插件已迁移

- ✅ API 契约（`docs/API_CONTRACT.md`）：统一路由/鉴权/响应/错误码/版本 + CardKey 兼容例外
- ✅ 内核（配置、插件协议、注册中心、数据库、鉴权、错误码）
- ✅ **cardkey 插件已迁移**：从 CardKeySDK/demo-backend 迁入签发核心（Base32/payload/sign）+ 状态机（一机一码/次数/封禁/到期），`verify` 兼容既有客户端的扁平格式，管理接口走统一包络
- ✅ 一次性部署三件套（install.sh + Docker Compose + systemd）
- ✅ Web 管理 UI 骨架
- ✅ **鉴权落库 + 审计**：API Key 只存 SHA-256 哈希（明文仅创建时回一次），可管理/吊销；每次请求写审计日志，管理接口可查。bootstrap 凭据保留用于首次安装
- ✅ **端到端验证**：10 项测试全绿（cardkey 4 项 + 内核鉴权/审计 6 项），真起服务在 HTTP 下复验通过（含"库中无明文 key"检查）
- ⚠️ update / crash 插件仍是占位（未来客户端）
- ⚠️ 本机无 Docker，Docker 部署路径未在本机跑过

## 快速看契约

```
docs/API_CONTRACT.md      # 对外规范（最重要）
docs/ARCHITECTURE.md      # 架构与目录职责
```

接口形态示例：
```
GET  /api/v1/core/health          健康检查（含已启用插件列表）
GET  /                            Web 管理后台
GET  /docs                        自动生成的 OpenAPI 契约文档
POST /api/v1/cardkey/verify       发卡验卡（扁平兼容格式）
POST /api/v1/core/keys            创建 API Key（明文仅回一次）
GET  /api/v1/core/audit           查询审计日志（管理接口）
```

## 一次性部署（原型）

```bash
# Docker 模式（服务器需有 docker）
sudo bash deploy/install.sh --mode docker --dir /opt/openhub

# 裸机模式（无 docker，装 Python 3.10+）
sudo bash deploy/install.sh --mode bare --dir /opt/openhub
```

脚本会：检测环境 → 生成管理员 Token 与初始 API Key（`.env`，权限 600）→ 拉起服务。
私钥、数据库、上传的产物都在 `data/`，被 `.gitignore` 排除，不进仓库/镜像层。

## 本地开发（需自行装依赖）

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --reload --port 8080
```

## 下一步

1. ~~确认骨架/契约方向~~ ✅
2. ~~把 CardKeySDK/demo-backend 迁入 `plugins/cardkey`~~ ✅
3. ~~鉴权落库 + 审计写入~~ ✅
4. 填 update / crash 插件（未来客户端）
5. 补 CI、中英双语文档，发布仓库

## License

MIT
