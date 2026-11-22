# OpenHub · 通用后端服务平台

> 🤖 本项目由 AI 生成。

[中文](README.md) | [English](README_EN.md)

一个可**一次性部署到服务器**的通用后端平台：Web 管理后台、APK/产物管理、可插拔业务模块，为现有 CardKey 和未来的客户端 SDK 提供规范化的后端服务。

**核心设计**：内核 + 插件。内核写一次（鉴权/设备/配置/产物/审计），加客户端 = 加一个插件，内核不动。

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
POST /api/v1/update/publish       发布版本清单（管理接口，带签名）
GET  /api/v1/update/check         客户端查更新（验签 + 指纹双校验）
POST /api/v1/crash/report         崩溃上报（脱敏 + 限流）
GET  /api/v1/crash/reports        查询崩溃（管理接口）
POST /api/v1/announce/publish     发布公告（服务端签名，管理接口）
GET  /api/v1/announce/list        客户端拉公告（逐条验签）
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

## License

MIT
