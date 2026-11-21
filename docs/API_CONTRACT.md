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

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/core/health` | 健康检查，`{"ok":true,"version":"..."}` |
| POST | `/api/v1/core/devices` | 注册/上报设备码 |
| GET | `/api/v1/core/config/{product}` | 拉取签名配置包（灰度 + 强制开关 + 缓存兜底） |
| POST | `/api/v1/core/artifacts` | 上传 APK/产物（版本、渠道、签名指纹） |
| GET | `/api/v1/core/artifacts/latest` | 查询最新版本（含 APK 签名证书指纹，供客户端校验） |
| GET | `/api/v1/core/audit` | 审计日志（管理接口，`?limit=&offset=&path=` 过滤） |
| GET | `/api/v1/core/keys` | 列出 API Key（管理接口，只显哈希前缀，无明文） |
| POST | `/api/v1/core/keys` | 创建 API Key（管理接口，`{"label","scope"}`，明文仅此一次返回） |
| POST | `/api/v1/core/keys/{id}/revoke` | 吊销 API Key（管理接口） |

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
