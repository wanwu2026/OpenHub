# OpenHub API 契约 v1

> 这是 OpenHub 的**规范化核心**：所有客户端 SDK（现有 CardKey、未来的更新检查/配置/崩溃上报）都按这一套约定对接。
> 服务端自动生成 OpenAPI 文档：`http://<host>:8080/docs`（FastAPI 自带）。
> 契约变更必须升版本号（`v1` → `v2`），不得在原版本上改字段语义。

## 1. 统一路由前缀

```
/api/v1/<plugin>/<action>
```

- `<plugin>`：插件名，如 `cardkey` / `update` / `crash`；`core` 保留给平台自身（租户、设备、产物、配置）。
- `<action>`：动作名，如 `verify` / `issue` / `health`。
- 示例：`POST /api/v1/cardkey/verify`、`GET /api/v1/core/health`、`POST /api/v1/core/artifacts`。

## 2. 统一鉴权

三种凭据，按场景选：

| 凭据 | 位置 | 用途 | 谁能拿 |
|---|---|---|---|
| API Key | `Authorization: Bearer <key>` | 客户端 SDK 调用业务接口 | 开发者在 UI 生成，下发给 App |
| Admin Token | `Authorization: Bearer <admin-token>` | 管理接口（发卡、上传 APK、改配置） | 仅管理员，UI 登录后签发 |
| 签名请求 | `X-OpenHub-Signature: <hex>` + `X-OpenHub-Timestamp` | 高敏操作（可选，插件可强制） | 持有私钥的服务端 |

> 与 CardKey 一致的原则：**私钥永不进客户端**。客户端只拿公钥验签返回数据。

## 3. 统一响应包络

**成功**（HTTP 200）：
```json
{
  "ok": true,
  "data": { "...": "插件自定义" },
  "meta": { "request_id": "req_xxx", "api_version": "v1" }
}
```

**失败**（HTTP 4xx/5xx）：
```json
{
  "ok": false,
  "error": {
    "code": "CARDKEY_DEVICE_MISMATCH",
    "message": "卡密已绑定其他设备",
    "retryable": false
  },
  "meta": { "request_id": "req_xxx", "api_version": "v1" }
}
```

## 4. 统一错误码

格式 `<SCOPE>_<REASON>`。内核保留前缀 `CORE_`，插件用自己的名字前缀。

| 码 | HTTP | 含义 | retryable |
|---|---|---|---|
| `CORE_UNAUTHORIZED` | 401 | 凭据缺失/无效 | false |
| `CORE_FORBIDDEN` | 403 | 凭据无此权限 | false |
| `CORE_NOT_FOUND` | 404 | 资源不存在 | false |
| `CORE_VALIDATION` | 422 | 参数校验失败 | false |
| `CORE_RATE_LIMITED` | 429 | 触发限流 | true |
| `CORE_INTERNAL` | 500 | 服务端异常 | true |
| `CORE_PLUGIN_DISABLED` | 404 | 插件未启用 | false |

插件自定义码（CardKey 沿用已有语义）：
`CARDKEY_INVALID` / `CARDKEY_USED` / `CARDKEY_EXPIRED` / `CARDKEY_DEVICE_MISMATCH` / `CARDKEY_REVOKED`。

## 5. 内核接口（所有客户端共享）

| 方法 | 路径 | 鉴权 | 说明 |
|---|---|---|---|
| GET | `/api/v1/core/health` | 公开 | 健康检查，`{"ok":true,"version":"...","plugins":[...]}` |
| POST | `/api/v1/core/devices` | API Key | 注册设备 `{"device_id","product","meta"}`，**只存 SHA-256 哈希**，重复注册=更新活跃时间 |
| GET | `/api/v1/core/devices` | Admin | 设备列表（`?limit=&offset=&product=`），只有哈希无原始 device_id |
| GET | `/api/v1/core/config/{product}` | API Key | 拉取签名配置包：`{enabled,rollout_percent,force_update,config,signature,signature_algo}`，停用返回 `config:null` |
| POST | `/api/v1/core/config/{product}` | Admin | 编辑配置 `{"enabled","rollout_percent"0-100,"force_update","config":{...}}`，服务端用私钥签名 |
| GET | `/api/v1/core/configs` | Admin | 配置列表 |
| POST | `/api/v1/core/artifacts` | Admin | 上传产物（multipart：file + version/version_code/channel/signer_fingerprint/product/sha256），落盘 + 入库 |
| GET | `/api/v1/core/artifacts` | Admin | 产物列表（`?product=`） |
| GET | `/api/v1/core/artifacts/latest` | API Key | 最新版本（`?product=&channel=`），含 `signer_fingerprint` 供下载后比对 |
| GET | `/api/v1/core/artifacts/download/{id}` | API Key | 下载产物文件本体 |
| GET | `/api/v1/core/audit` | Admin | 审计日志（`?limit=&offset=&path=` 过滤） |
| GET | `/api/v1/core/keys` | Admin | 列出 API Key（只显哈希前缀，无明文） |
| POST | `/api/v1/core/keys` | Admin | 创建 API Key（`{"label","scope"}`，明文仅此一次返回） |
| POST | `/api/v1/core/keys/{id}/revoke` | Admin | 吊销 API Key |
| GET | `/api/v1/core/overview` | Admin | 管理看板聚合：一次返回 `cardkey/update/announce/crash/devices/configs/artifacts` + `errors`，供 Web UI 单请求渲染 |

**配置签名约定**：客户端拉取配置后，用内置公钥验 `signature`——签名字节 = 对 `{product,enabled,rollout_percent,force_update,config}` 做 `json.dumps(sort_keys=True, separators=(',',':'))`（`ensure_ascii=True`），RSA-SHA256 + Base32（无填充），与 update/announce 清单同法。灰度 `rollout_percent` 与强制开关 `force_update` 的执行在客户端：客户端按设备哈希取模判断是否命中灰度。

**API Key 安全约定**：库中只存 `SHA-256(key)`，永不存明文；明文仅在创建响应里返回一次，之后无法找回，丢失只能新建。审计日志只记匹配到的 `key_id`，不记 token 本身。首次安装时 `.env` 里的 bootstrap 凭据（Admin Token / 初始 API Key）保留，用于 DB 为空时启动并创建更多 key；可随时通过管理接口吊销库内 key，bootstrap 凭据的轮换通过改 `.env` 完成。

## 6. 插件接口约定

每个插件在 `plugins/<name>/plugin.py` 实现 `Plugin` 抽象基类（见 `core/plugin.py`）：

- `name`：插件名，对应路由前缀
- `routes()`：返回该插件的 FastAPI `APIRouter`
- `health()`：插件自检
- `on_enable()` / `on_disable()`：生命周期钩子

**新增客户端 = 新增一个插件目录 + 实现一个类，内核不动。**

## 7. APK/产物的签名指纹（规范化要点）

产物记录含 `signer_fingerprint`（APK 签名证书 SHA-256）。客户端下载更新时**必须同时校验**：
1. 更新清单的服务端签名（防清单被篡改）；
2. APK 签名证书指纹与清单一致（防下载 URL 被中间人替换）。

只做第 1 条不做第 2 条 = 可被换成任意 APK —— 这是更新检查类客户端最常见的漏洞，内核在契约层就把它列为必填字段。

## 7.1 update 插件接口（版本更新检查）

| 方法 | 路径 | 鉴权 | 说明 |
|---|---|---|---|
| POST | `/api/v1/update/publish` | Admin | 发布版本清单：请求含 `product/version/version_code/signer_fingerprint/apk_url/sha256`，服务端用私钥签清单，返回 `manifest_signature` |
| GET | `/api/v1/update/check?product=&current_version_code=&channel=` | API Key | 客户端查更新；有更新时返回签名清单 + `manifest_signature` + `signature_algo`，无更新时 `manifest=null` |
| GET | `/api/v1/update/manifest/{product}?channel=` | API Key | 取最新签名清单 |
| GET | `/api/v1/update/verify/{product}?channel=&public_key_base64=` | Admin | 服务端自检：用公钥验最新清单签名是否有效 |
| GET | `/api/v1/update/list?product=` | Admin | 列出已发布版本 |

`signer_fingerprint` 必须是 64 位十六进制（APK 签名证书 SHA-256），发布时校验。
清单签名算法 `RSA-SHA256`，签名字节 = 对 manifest 的**规范化 JSON**（`sort_keys=True`、无多余空格）做签，客户端按同法重建字节验签。私钥可用 `OPENHUB_UPDATE_PRIVATE_KEY` 单独配置，未配置时回退 `OPENHUB_CARDKEY_PRIVATE_KEY`。

**客户端必须做的双校验**（见 §7）：先验 `manifest_signature`，下载 APK 后再比对 `signer_fingerprint` 与证书实际指纹。服务端只负责提供可验的清单与指纹，不替客户端做下载后校验。

## 7.2 crash 插件接口（崩溃上报）

| 方法 | 路径 | 鉴权 | 说明 |
|---|---|---|---|
| POST | `/api/v1/crash/report` | API Key | 上报崩溃：单条 `{device_id, app_id, stacktrace}` 或批量 `{device_id, reports:[...]}`；返回 `accepted/ids` |
| GET | `/api/v1/crash/reports?app_id=&status=&limit=&offset=` | Admin | 查询崩溃（脱敏后的堆栈 + 设备哈希 + 状态） |
| POST | `/api/v1/crash/{report_id}/resolve` | Admin | 标记为已处理 |

隐私与稳定性约定：
- `device_id` 只存 SHA-256（明文不入库）；
- 堆栈自动脱敏：邮箱 → `[EMAIL]`、手机号 → `[PHONE]`、`Bearer xxx` → `Bearer [REDACTED]`、长十六进制串 → `[HEX]`；
- 设备限流：10 分钟窗口内最多 20 条，超限返回 `CORE_RATE_LIMITED`（retryable=true）。

## 7.3 announce 插件接口（公告）

| 方法 | 路径 | 鉴权 | 说明 |
|---|---|---|---|
| POST | `/api/v1/announce/publish` | Admin | 发布公告：请求含 `product/title/content`，可选 `level(info\|warn\|urgent)`/`force_popup`/`published_at`；服务端签名后返回 `id`/`signature` |
| GET | `/api/v1/announce/list?product=&since=&limit=&offset=` | API Key | 客户端拉公告（含每条 `signature`），`since` 为毫秒时间戳增量过滤 |
| GET | `/api/v1/announce/verify/{id}?public_key_base64=` | Admin | 服务端自检：验某条公告签名是否有效 |

签名与安全约定：
- 每条公告单独签名，算法 `RSA-SHA256`，密钥同 update 插件（`OPENHUB_UPDATE_PRIVATE_KEY`，未配置回退 cardkey）。
- 签名字节 = 对 `{product,title,content,level,force_popup,published_at}` 的规范化 JSON（`sort_keys=True`、紧凑分隔、默认 `ensure_ascii=True`）做签；客户端用同法重建字节验签，逐条验证，防假公告。
- 数据库自增 `id` 不进签名体，仅供客户端做"已读去重"（改 id 最多导致重复弹窗，非安全问题）。
- 客户端应本地记录已展示的公告 id，按 `level` 决定是否强弹；公告内容属服务端数据。

## 8. 兼容例外：CardKey 客户端的扁平响应

为支持**之前已开发的客户端**，有一处有意偏离统一包络：

`POST /api/v1/cardkey/verify` 返回**扁平格式**（不是 `ok/data/meta` 包络）：

```json
// 成功
{"ok":true,"license":"KVL1-...-..."}
// 失败
{"ok":false,"reason":"device_mismatch","message":"设备不匹配"}
```

原因：现有 CardKey SDK 的 `HttpRemoteVerifier` 只解析扁平字段，且客户端已发布、不能强制升级。
这是**有意的兼容例外**，不是疏忽；cardkey 插件的管理接口（`/issue` `/revoke` `/codes`）仍走统一包络。
新客户端一律用统一包络；只有 cardkey 的 verify 保留扁平格式。新增此类例外必须在契约登记，禁止悄悄加。

## 9. 终端用户认证（auth，独立于开发者 API Key）

聊天室等终端用户功能使用**用户体系**，与开发者 API Key（§2）是两套独立凭据：API Key 标识集成方，session token 标识终端用户。

| 方法 | 路径 | 鉴权 | 说明 |
|---|---|---|---|
| POST | `/api/v1/auth/register` | 公开 | `{"username"(3-32),"password"(≥6),"email"?}`，密码存 PBKDF2-HMAC-SHA256 + 随机盐（210k 轮），绝不明文 |
| POST | `/api/v1/auth/login` | 公开 | `{"username","password"}` → `{"token","token_type":"bearer"}`，token 只回一次 |
| GET | `/api/v1/auth/me` | session token | 当前用户 `{"user":{id,username,email}}` |
| POST | `/api/v1/auth/logout` | session token | 使当前会话失效 |
| GET | `/api/v1/auth/user-by-name?username=` | session token | 按用户名查 `{id,username}`（发起单聊/建群用），只回公开字段 |
| GET | `/api/v1/auth/users` | Admin | 用户列表（id/username/email/status/created_at，无密码哈希） |
| POST | `/api/v1/auth/users/{id}/disable` | Admin | 禁用用户（其会话随即失效） |
| POST | `/api/v1/auth/users/{id}/enable` | Admin | 启用用户 |

session token 用 `secrets.token_urlsafe(32)`，库中只存 SHA-256 哈希，7 天过期；禁用用户后其 token 立即失效。

**登录限流**：同一用户名 5 分钟内失败 5 次 → 锁定 15 分钟（返回 `CORE_RATE_LIMITED` / HTTP 429，`retryable=true`）；登录成功清零计数。计数器在内存（单进程），多实例部署需移到共享存储。过期会话可用 `user_store.purge_expired_sessions()` 清理。

## 10. chat 聊天插件（终端用户实时消息）

| 方法 | 路径 | 鉴权 | 说明 |
|---|---|---|---|
| GET | `/api/v1/chat/conversations` | session token | 会话列表（含未读数、末条消息） |
| POST | `/api/v1/chat/direct` | session token | `{"user_id"}` → 单聊 conv_id（幂等，两人得同一 id） |
| POST | `/api/v1/chat/groups` | session token | `{"name","member_ids":[]}` → 群聊 conv_id，创建者为群主 |
| GET | `/api/v1/chat/messages/{cid}?limit=&before_id=` | session token | 历史消息（时间正序，分页；非成员 401） |
| POST | `/api/v1/chat/messages/{cid}` | session token | `{"kind":"text|image|file","content"}` 发消息并广播 |
| POST | `/api/v1/chat/messages/{cid}/read` | session token | `{"message_id"}` 标记已读 |
| WS | `/api/v1/chat/ws/{cid}?token=` | session token（查询参数） | WebSocket 实时：连上先收 `history`，之后收 `message` 广播；非法 token/非成员拒绝 |

单聊 conv_id = `d_` + sha256(两用户 id 排序)[:24]，保证双方一致；群聊 conv_id = `g_` + 随机 hex。
消息落库保证离线可补：WS 连上先推最近 50 条，REST 可分页拉历史。连接表在内存（单进程），多实例部署需接 Redis pub/sub（当前版本边界）。
Web 聊天室页面：`/chat`（浏览器打开，注册登录 + 单聊群聊 + 实时收发）。
