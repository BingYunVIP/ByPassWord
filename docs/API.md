# API 契约（REST）

> Base URL：`/api`（Nginx 反代到 FastAPI）
> 所有请求/响应 `Content-Type: application/json`；时间均为 UTC ISO8601。
> 鉴权：`Authorization: Bearer <access_token>`（除 `/api/auth/*` 与 `/api/health`）。

---

## 1. 统一约定

### 1.1 错误格式

```json
{ "error": { "code": "invalid_credentials", "message": "邮箱或主密码错误", "detail": null } }
```

| HTTP | code | 含义 |
| --- | --- | --- |
| 400 | `bad_request` | 参数不合法（Pydantic 校验失败） |
| 401 | `unauthorized` | 未登录 / token 过期 |
| 401 | `invalid_credentials` | 邮箱或主密码错误 |
| 401 | `invalid_code` | 2FA 验证码或邮箱验证码错误 |
| 401 | `invalid_recovery_code` | 恢复码无效或已使用 |
| 403 | `forbidden` | 无权访问该资源 |
| 404 | `not_found` | 资源不存在 |
| 409 | `rev_conflict` | 版本冲突（乐观锁失败） |
| 409 | `email_exists` | 邮箱已注册 |
| 409 | `2fa_already_enabled` | 已开启 2FA，重复绑定 |
| 423 | `account_locked` | 连续失败临时锁定 |
| 429 | `rate_limited` | 触发限流 |
| 500 | `internal_error` | 服务端异常（不含堆栈） |
| 502 | `mail_failed` | 邮件发送失败（不阻塞主流程） |

### 1.2 分页

仅审计日志需要：`?limit=50&cursor=<created_at>`，返回 `{ items, next_cursor }`。

---

## 2. 认证 `/api/auth`

### 2.1 预登录（取 KDF 参数）

`POST /api/auth/prelogin`

```json
{ "email": "me@example.com" }
```

```json
{
  "kdf": { "algo": "argon2id", "salt": "base64...", "memoryKib": 65536, "time": 3, "parallel": 1 }
}
```

> 该接口对不存在的邮箱也返回**随机假参数**，避免邮箱枚举。

### 2.2 注册

`POST /api/auth/register`

```json
{
  "email": "me@example.com",
  "kdf": { "algo": "argon2id", "salt": "base64...", "memoryKib": 65536, "time": 3, "parallel": 1 },
  "authHash": "base64(32B)",
  "wrappedDek": "base64(...)",
  "dekNonce": "base64(12B)",
  "recoveryWrappedDek": "base64(...) | null"
}
```

`201` → 与登录成功响应一致（直接进入应用）。

### 2.3 登录

`POST /api/auth/login`

```json
{ "email": "me@qq.com", "authHash": "base64(32B)" }
```

**未开启 2FA** → `200`：

```json
{
  "accessToken": "jwt...",
  "expiresIn": 900,
  "wrappedDek": "base64(...)",
  "dekNonce": "base64(12B)"
}
```

**已开启 2FA** → `200`：

```json
{ "requires2fa": true, "challenge": "base64(32B)", "expiresIn": 300 }
```

> `challenge` 为一次性令牌（5 分钟），只能用于 `/api/auth/2fa/verify`，不能访问其他接口。
> 成功登录后 `Set-Cookie: refresh_token=...; HttpOnly; Secure; SameSite=Strict; Path=/api/auth`

### 2.4 刷新 / 登出 / 当前用户 / 改密

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/auth/refresh` | 用 Cookie 换新 access token（轮换 refresh token） |
| POST | `/api/auth/logout` | 撤销当前 refresh token 并清 Cookie |
| GET | `/api/auth/me` | `{ id, email, twoFactorEnabled, createdAt, lastLoginAt }` |
| POST | `/api/auth/change-password` | `{ oldAuthHash, newAuthHash, newKdf, wrappedDek, dekNonce }`（重新包裹同一 DEK，成功后发邮件通知） |

### 2.5 账号 2FA（TOTP）

| 方法 | 路径 | 请求 | 响应 / 说明 |
| --- | --- | --- | --- |
| POST | `/api/auth/2fa/setup` | — （需登录） | `{ secret, otpauthUrl }`，`otpauth://totp/ByPassWord:me@qq.com?secret=...&issuer=ByPassWord` |
| POST | `/api/auth/2fa/enable` | `{ code }` | `200 { recoveryCodes: ["XXXX-XXXX", ...] }`（10 个，仅此一次返回） |
| POST | `/api/auth/2fa/verify` | `{ challenge, code }` | `200` 同登录成功响应（accessToken + wrappedDek） |
| POST | `/api/auth/2fa/verify-recovery` | `{ challenge, recoveryCode }` | 同上；该恢复码作废 |
| POST | `/api/auth/2fa/disable` | `{ authHash, code }` | 需主密码 + 当前 TOTP；成功后发邮件 |
| GET | `/api/auth/2fa/recovery-codes` | — | `{ remaining: 7 }`（只回数量，不回明文） |
| POST | `/api/auth/2fa/recovery-codes/regenerate` | `{ authHash, code }` | 重新生成 10 个，旧的全部作废 |

### 2.6 忘记主密码（邮箱验证 + 恢复码）

| 方法 | 路径 | 请求 | 说明 |
| --- | --- | --- | --- |
| POST | `/api/auth/forgot` | `{ email }` | 无论邮箱是否存在均返回 `202`；存在则发 6 位验证码（10 分钟有效） |
| POST | `/api/auth/forgot/verify` | `{ email, code }` | 校验通过返回 `{ resetToken }`（10 分钟，一次性） |
| POST | `/api/auth/reset` | `{ resetToken, newKdf, newAuthHash, wrappedDek, dekNonce }` | 客户端先用**恢复码**解出 DEK，再用新 encKey 重新包裹后提交（服务端全程不接触 DEK 明文） |

> 重置成功后会撤销全部 refresh token、清空失败计数、发邮件通知、写审计。
> **不提供**「仅凭邮箱重置」的托管恢复接口——服务端没有任何解密能力。

---

## 3. 金库同步 `/api/vault`

### 3.1 全量拉取

`GET /api/vault?since=<rev>`

```json
{
  "rev": 128,
  "folders": [
    { "id": "uuid", "ciphertext": "base64", "nonce": "base64", "sortOrder": 0, "rev": 12, "updatedAt": "...", "deletedAt": null }
  ],
  "items": [
    { "id": "uuid", "ciphertext": "base64", "nonce": "base64", "rev": 31, "updatedAt": "...", "deletedAt": null }
  ]
}
```

- `since` 省略 = 全量；带上则只返回 `rev > since` 的变更（含软删除墓碑）。

### 3.2 单条写入

| 方法 | 路径 | 请求体 | 成功 |
| --- | --- | --- | --- |
| POST | `/api/folders` | `{ id, ciphertext, nonce, sortOrder? }` | `201 { id, rev }` |
| PATCH | `/api/folders/{id}` | `{ ciphertext, nonce, sortOrder?, rev }` | `200 { id, rev }` |
| DELETE | `/api/folders/{id}?rev=` | — | `200 { id, rev, deletedAt }` |
| POST | `/api/items` | `{ id, ciphertext, nonce }` | `201 { id, rev }` |
| PATCH | `/api/items/{id}` | `{ ciphertext, nonce, rev }` | `200 { id, rev }` |
| DELETE | `/api/items/{id}?rev=` | — | `200 { id, rev, deletedAt }` |

- `rev` 不匹配 → `409 rev_conflict`，响应带服务端当前 `rev`，前端重新拉取。
- `id` 由客户端生成（UUID v4），重复提交同 id 且内容一致 → `200`（幂等）。

### 3.3 批量写入（导入备份时使用）

`POST /api/vault/import`

```json
{ "folders": [...], "items": [...], "strategy": "skip | overwrite | duplicate" }
```

- 服务端**原样存密文**（导入前前端已用当前 DEK 重新加密），不解密、不校验内容。
- `strategy`：`skip` 跳过已存在 id（默认）/ `overwrite` 覆盖同 id / `duplicate` 全部作为新 id 写入。
- 返回 `{ imported: { folders: 8, items: 5 }, skipped: 0, rev }`。
- 导入前服务端自动做一次备份快照（标记 `pre-import`）。

---

## 4. 设置、邮箱、备份与审计

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/settings` | `{ ciphertext, nonce, updatedAt }`（含 SMTP 主机/端口/账号、备份时间与保留天数） |
| PUT | `/api/settings` | `{ ciphertext, nonce }`（整体覆盖） |
| GET | `/api/settings/mail` | `{ host, port, secure, user, from, fromName, hasPassword: true }`（授权码只回布尔） |
| PUT | `/api/settings/mail` | `{ host, port, secure, user, password?, from, fromName }`（`password` 省略则保留原值） |
| POST | `/api/settings/mail/test` | 发一封测试邮件；成功 `200`，失败 `502 mail_failed` |
| GET | `/api/audit?limit=50&cursor=` | 审计日志（含邮件、2FA、导入导出事件） |
| GET | `/api/backup/list` | `{ items: [{ id, createdAt, size, kind: auto/manual/pre-import }] }` |
| POST | `/api/backup/snapshot` | 立即创建手动快照（不受保留策略删除） |
| GET | `/api/backup/{id}/download` | 下载加密备份（`application/octet-stream`，需登录） |
| GET | `/api/health` | `{ status: "ok", version, db: "ok" }`（无需鉴权） |

> 备份保留策略在服务端定时任务中读取 `user_settings.backupRetentionDays` 执行；`manual` 与 `pre-import` 类型不自动清理。

### 4.1 导出备份包格式（前端生成）

```jsonc
{
  "format": "bypw-backup",
  "version": 1,
  "createdAt": "2026-11-01T12:00:00Z",
  "kdf": { "algo": "argon2id", "salt": "base64", "memoryKib": 65536, "time": 3, "parallel": 1 },
  "wrappedDek": "base64",       // 用备份时的主密码包裹
  "dekNonce": "base64",
  "folders": [{ "id": "...", "ciphertext": "...", "nonce": "...", "sortOrder": 0 }],
  "items": [{ "id": "...", "ciphertext": "...", "nonce": "...", "rev": 1 }]
}
```

导入时要求输入**该备份的主密码**，本地解出 DEK 后再用当前账号的 DEK 重新加密上传。

---

## 5. 安全响应头（Nginx 层）

```
Strict-Transport-Security: max-age=63072000; includeSubDomains; preload
Content-Security-Policy: default-src 'self'; img-src 'self' data: https://www.google.com;
                         script-src 'self' 'wasm-unsafe-eval'; style-src 'self' 'unsafe-inline';
                         font-src 'self'; connect-src 'self'; frame-ancestors 'none'
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Referrer-Policy: no-referrer
Permissions-Policy: geolocation=(), microphone=(), camera=()
```

> `'wasm-unsafe-eval'` 是 Argon2id WASM 所需；`img-src` 允许 Google favicon 服务（任意站点图标的运行时兜底）。

---

## 6. 限流策略

| 接口 | 限制 |
| --- | --- |
| `/api/auth/login` | 5 次 / 分钟 / IP；连续失败 10 次锁定 15 分钟 |
| `/api/auth/2fa/verify` | 5 次 / 5 分钟（challenge 作废后需重新登录） |
| `/api/auth/register` | 3 次 / 小时 / IP |
| `/api/auth/prelogin` | 20 次 / 分钟 / IP |
| `/api/auth/forgot` | 3 次 / 小时 / 邮箱 + 10 次 / 小时 / IP（防邮件轰炸） |
| `/api/auth/forgot/verify` | 5 次 / 10 分钟 |
| `/api/settings/mail/test` | 3 次 / 小时 |
| 其他 | 120 次 / 分钟 / 用户 |
