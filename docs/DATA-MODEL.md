# 数据模型（SQLite）

> 配套：`docs/ARCHITECTURE.md`（安全模型）、`docs/API.md`（接口契约）
> 原则：**条目数据零知识**（服务端不可解）；**认证类密钥**（2FA secret、SMTP 授权码）服务端必须可读，用 `SERVER_SECRET` 加密存储。

---

## 1. 设计原则

1. 主键统一 **UUID v4 字符串**（客户端生成，便于离线创建与幂等重试）。
2. 条目/文件夹/设置内容一律进 `ciphertext`，服务端不可解。
3. 删除采用**软删除**（`deleted_at`），保证多端同步。
4. 每条记录带 `rev`（自增版本号），用于乐观锁。
5. 时间统一存 **UTC ISO8601 字符串**。

---

## 2. 表结构

### 2.1 users

```sql
CREATE TABLE users (
  id             TEXT PRIMARY KEY,
  email          TEXT NOT NULL UNIQUE,          -- 小写规范化
  auth_hash      TEXT NOT NULL,                 -- Argon2id(authKey)
  kdf_algo       TEXT NOT NULL DEFAULT 'argon2id',
  kdf_salt       TEXT NOT NULL,                 -- base64(16B)
  kdf_memory_kib INTEGER NOT NULL DEFAULT 65536,
  kdf_time       INTEGER NOT NULL DEFAULT 3,
  kdf_parallel   INTEGER NOT NULL DEFAULT 1,
  wrapped_dek    TEXT NOT NULL,                 -- AESGCM(encKey, DEK)
  dek_nonce      TEXT NOT NULL,

  -- 恢复能力
  recovery_wrapped_dek TEXT,                    -- 恢复码包裹的 DEK（唯一恢复手段）

  -- 账号 2FA（服务端需可读，用 SERVER_SECRET 加密）
  totp_secret_enc TEXT,                         -- base64(AESGCM(SERVER_SECRET, secret))
  totp_secret_nonce TEXT,
  totp_enabled_at TEXT,                         -- 非空 = 已开启

  -- 登录保护
  failed_attempts INTEGER NOT NULL DEFAULT 0,
  locked_until   TEXT,
  last_login_ip  TEXT,
  last_login_at  TEXT,
  created_at     TEXT NOT NULL
);
```

### 2.2 totp_recovery_codes（2FA 一次性备用码）

```sql
CREATE TABLE totp_recovery_codes (
  id         TEXT PRIMARY KEY,
  user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  code_hash  TEXT NOT NULL,        -- SHA-256(code)，不存明文
  used_at    TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX idx_recovery_user ON totp_recovery_codes(user_id, used_at);
```

### 2.3 password_resets（忘记主密码的邮箱验证码）

```sql
CREATE TABLE password_resets (
  id         TEXT PRIMARY KEY,
  user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  code_hash  TEXT NOT NULL,        -- SHA-256(6 位验证码)
  attempts   INTEGER NOT NULL DEFAULT 0,
  expires_at TEXT NOT NULL,        -- 10 分钟
  used_at    TEXT,
  ip         TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX idx_reset_user ON password_resets(user_id, created_at DESC);
```

### 2.4 refresh_tokens

```sql
CREATE TABLE refresh_tokens (
  id         TEXT PRIMARY KEY,
  user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token_hash TEXT NOT NULL UNIQUE,
  expires_at TEXT NOT NULL,
  revoked_at TEXT,
  user_agent TEXT,
  ip         TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX idx_refresh_user ON refresh_tokens(user_id);
```

### 2.5 folders / items（业务数据，全密文）

```sql
CREATE TABLE folders (
  id         TEXT PRIMARY KEY,
  user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  ciphertext TEXT NOT NULL,        -- {name, gIcon, color, customImage, desc}
  nonce      TEXT NOT NULL,
  sort_order INTEGER NOT NULL DEFAULT 0,
  rev        INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  deleted_at TEXT
);
CREATE INDEX idx_folders_user ON folders(user_id, deleted_at);

CREATE TABLE items (
  id         TEXT PRIMARY KEY,
  user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  ciphertext TEXT NOT NULL,        -- {type, folderId, title, url, account, password, totpSecret, ...}
  nonce      TEXT NOT NULL,
  rev        INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  deleted_at TEXT
);
CREATE INDEX idx_items_user ON items(user_id, deleted_at);
```

> 条目 `type` 也在密文内，服务端不知道类型；搜索/筛选/排序全部在前端解密后完成。

### 2.6 user_settings（含邮箱配置与备份策略）

```sql
CREATE TABLE user_settings (
  user_id    TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  ciphertext TEXT NOT NULL,   -- 见下方字段说明
  nonce      TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
```

`ciphertext` 解密后的 JSON：

```jsonc
{
  "cipher": "AES-256-GCM",
  "kdfType": "Argon2id",
  "idleTimeoutMinutes": 15,
  "clipboardClearSeconds": 20,
  "loginEmail": "me@qq.com",
  "fingerprint": "maple-lunar-cobalt-velvet-atomic",

  // 邮箱配置（授权码在服务端另存加密副本，此处不落明文）
  "smtpHost": "smtp.qq.com",
  "smtpPort": 465,
  "smtpSecure": true,
  "smtpUser": "me@qq.com",
  "smtpFrom": "me@qq.com",
  "smtpFromName": "ByPassWord",

  // 备份
  "backupSchedule": "daily-03:00",
  "backupRetentionDays": 30,     // 7 / 14 / 30 / 90 / 0=永久
  "backupNotifyOnFail": true
}
```

> SMTP 授权码**不能**放进上面的密文（服务端要能发信），单独存 `user_secrets` 表（见 2.7）。

### 2.7 user_secrets（服务端密钥加密的凭证）

```sql
CREATE TABLE user_secrets (
  user_id      TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  key          TEXT NOT NULL,          -- 'smtp_password'
  value_enc    TEXT NOT NULL,          -- AESGCM(SERVER_SECRET, value)
  value_nonce  TEXT NOT NULL,
  updated_at   TEXT NOT NULL,
  PRIMARY KEY (user_id, key)
);
```

### 2.8 audit_logs

```sql
CREATE TABLE audit_logs (
  id         TEXT PRIMARY KEY,
  user_id    TEXT REFERENCES users(id) ON DELETE SET NULL,
  action     TEXT NOT NULL,   -- login_success/login_failed/2fa_enabled/password_changed/
                              -- backup_export/backup_import/mail_sent/mail_failed ...
  target     TEXT,            -- 目标 id，不含敏感内容
  ip         TEXT,
  user_agent TEXT,
  meta       TEXT,            -- 可选 JSON（如邮件类型、失败原因）
  created_at TEXT NOT NULL
);
CREATE INDEX idx_audit_user_time ON audit_logs(user_id, created_at DESC);
```

---

## 3. 关系图

```
users 1 ──< refresh_tokens
     1 ──< totp_recovery_codes
     1 ──< password_resets
     1 ──< folders
     1 ──< items
     1 ──< audit_logs
     1 ── 1 user_settings
     1 ──< user_secrets
```

---

## 4. 加密字段总览

| 字段 | 谁能解 | 说明 |
| --- | --- | --- |
| `items.ciphertext` / `folders.ciphertext` | **只有浏览器**（DEK） | 零知识核心 |
| `user_settings.ciphertext` | **只有浏览器**（DEK） | 设置也含隐私（如登录邮箱） |
| `users.wrapped_dek` | 浏览器（encKey） | 主密码派生 |
| `users.recovery_wrapped_dek` | 浏览器（恢复码派生） | 唯一的恢复手段 |
| `users.totp_secret_enc` | **服务端** | 校验 TOTP 必需 |
| `user_secrets.value_enc` | **服务端** | SMTP 授权码 |

`SERVER_SECRET`：32 字节随机值，存 `.env`，**不得入库、不得提交仓库**。轮换需重加密上述三类字段（提供 `scripts/rotate_server_secret.py`）。

---

## 5. SQLite 运行参数

```sql
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;
```

数据库文件：`/var/lib/bypw/vault.db`，属主 `bypw:bypw`，权限 `640`。

---

## 6. 迁移（Alembic）

- 初始迁移：`alembic revision --autogenerate -m "init schema"`
- 规则：
  1. 禁止手改线上库，结构变更必须走迁移。
  2. 每次迁移必须有 `downgrade()`，本地验证 `upgrade → downgrade → upgrade`。
  3. 迁移前自动备份。

---

## 7. 备份与保留

| 项 | 做法 |
| --- | --- |
| 触发 | 按 `backupSchedule` 由服务端定时任务执行；也可手动快照 |
| 方式 | `sqlite3 vault.db ".backup '/backup/vault-<ts>.db'"`（热备） |
| 加密 | `age -r <公钥>` 后落盘 |
| **保留** | 读取 `user_settings.backupRetentionDays`（7/14/30/90/0=永久），清理任务删除超期文件 |
| 手动快照 | 标记 `manual`，**不受保留策略自动删除**，需手动清理 |
| 恢复 | 停服务 → 解密覆盖 → `PRAGMA integrity_check` → 起服务 |

> 保留策略同时作用于「自动备份」与「导入前的自动备份」；`0` 表示永久保留（需自行关注磁盘）。

---

## 8. 数据规模预估

| 指标 | 估算 |
| --- | --- |
| 单条 item 密文 | 0.5–3 KB |
| 1,000 条 | ≈ 2 MB |
| 全量拉取 | < 50 ms |
| 备份体积（30 天保留） | ≈ 60 MB 上限 |
