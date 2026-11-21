# OpenHub · 通用后端服务平台

> 🤖 本项目由 AI 生成。

[中文](README.md) | [English](README_EN.md)

一个可**一次性部署到服务器**的通用后端平台：Web 管理后台、APK/产物管理、可插拔业务模块，为现有 CardKey 和未来的客户端 SDK 提供规范化的后端服务。

**核心设计**：内核 + 插件。内核写一次（鉴权/设备/配置/产物/审计），加客户端 = 加一个插件，内核不动。

## 当前状态：内核可用 + 三个插件已落地

- ✅ API 契约（`docs/API_CONTRACT.md`）：统一路由/鉴权/响应/错误码/版本 + CardKey 兼容例外
- ✅ 内核（配置、插件协议、注册中心、数据库、鉴权、错误码）
- ✅ **cardkey 插件**：从 CardKeySDK/demo-backend 迁入签发核心 + 状态机（一机一码/次数/封禁/到期），`verify` 兼容既有客户端的扁平格式，管理接口走统一包络
- ✅ **update 插件**：版本清单发布/查询/验签，强制记录 APK 签名证书指纹（契约 §7 双校验）
- ✅ **crash 插件**：崩溃上报，PII 脱敏（邮箱/手机号/Bearer token/长 hex）+ 设备限流 + 批量 + 处理状态
- ✅ 一次性部署三件套（install.sh + Docker Compose + systemd），Dockerfile 非 root 加固 + `.dockerignore`
- ✅ Web 管理 UI 骨架
- ✅ **鉴权落库 + 审计**：API Key 只存 SHA-256 哈希（明文仅创建时回一次），可管理/吊销；每次请求写审计日志，管理接口可查。bootstrap 凭据保留用于首次安装
- ✅ **端到端验证**：17 项测试全绿（cardkey 4 + 内核鉴权/审计 6 + update/crash 7）
- ⚠️ 本机无 Docker daemon，Docker 路径靠 GitHub Actions（ubuntu runner 自带 docker）真构建 + 冒烟验证

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
4. ~~填 update / crash 插件~~ ✅
5. ~~补 CI、中英双语文档~~ ✅
6. 发布仓库（需用户确认凭据与仓库名，**尚未 push**）

## License

MIT
