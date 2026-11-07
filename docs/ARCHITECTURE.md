# 项目架构设计

> 状态：设计稿 v2（2026-11-01，补充登录/2FA/邮件/路由/备份策略）
> 目标：把当前的纯前端「密码库」升级为可部署在 Linux VPS 上的**前后端一体应用**，安全模型达到密码管理器应有的水准。
> 读者：项目所有者（非专业后端）+ 后续接手的开发者/Agent。

---

## 1. 现状与目标

| | 现状（半成品） | 目标 |
| --- | --- | --- |
| 数据 | 明文 JSON 存浏览器 `localStorage` | 加密后存服务端 SQLite，本地只缓存密文 |
| 多设备 | 不支持，换浏览器即丢 | 支持，登录即同步 |
| 账号 | 无 | 邮箱 + 主密码注册/登录 |
| 登录 2FA | 无（只有条目级 TOTP） | **账号级 TOTP 二次验证 + 一次性恢复码** |
| 邮件 | 无 | **QQ 邮箱 SMTP**：改密通知、风险告警、找回密码验证码 |
| 页面 | 单页 | **`/login`（含 2FA 步骤）、`/admin`（现有主界面）、`/reset-password`** |
| 备份 | 只能手动导出 JSON | 自动备份 + **可设置保留天数** + 手动快照 + 导入/导出按钮 |
| 部署 | 只能本地 `npm run dev` | VPS 上 Nginx + systemd 常驻，HTTPS |
| 安全 | 明文、无鉴权 | 零知识加密、JWT、限流、审计 |

**核心约束**：前端现有 UI 与交互已定型（见 `docs/UI-DESIGN-SYSTEM.md`），后端改造**不得改变 `/admin` 的视觉与操作习惯**，只替换数据层；新增页面必须沿用同一设计语言。

**用户规模**：**单用户**（你自己）。表结构保留 `user_id`，但产品上不提供多用户注册入口。

---

## 2. 总体架构

```
                    ┌────────────────────────────────────┐
   浏览器            │  Vue 3 SPA (Vite)                  │
   (唯一信任边界)     │  ├ router/  /login /admin /reset   │
                    │  ├ pages/   登录页、后台页、重置页    │
                    │  ├ components/ 现有 UI（视觉不改）   │
                    │  ├ stores/  useVault()             │
                    │  ├ crypto/  WebCrypto + Argon2 WASM│
                    │  └ api/     fetch 封装 + 自动刷新    │
                    └───────────┬────────────────────────┘
                                │ HTTPS  /api/*
                    ┌───────────▼────────────────────┐
                    │  Nginx（TLS / 静态资源 / 反代）    │
                    └───────────┬────────────────────┘
                                │ 127.0.0.1:8000
                    ┌───────────▼────────────────────┐        ┌──────────────┐
                    │  FastAPI (Uvicorn, systemd)     │──SMTP─▶│ QQ 邮箱       │
                    │  ├ api/   路由 + 鉴权依赖         │  465   │ smtp.qq.com  │
                    │  ├ core/  配置/安全/DB/限流        │        └──────────────┘
                    │  ├ models/ SQLAlchemy 2.0        │
                    │  ├ schemas/ Pydantic v2          │
                    │  └ services/ 业务 + 邮件 + 备份     │
                    └───────────┬────────────────────┘
                                │ SQLAlchemy(async) + aiosqlite
                    ┌───────────▼────────────────────┐
                    │  SQLite (WAL) /var/lib/bypw/     │
                    │  只存密文；2FA/SMTP 密钥用服务端密钥加密
                    └────────────────────────────────┘
```

**信任边界**：浏览器是唯一可信端。服务端被视为"可能被攻破的存储"，因此**拿不到任何条目明文**。
例外（必须知情）：**账号 2FA 的 TOTP 密钥**与 **SMTP 授权码**服务端必须可读，用 `SERVER_SECRET` 加密存储。

---

## 3. 技术选型

| 层 | 选型 | 为什么 |
| --- | --- | --- |
| 前端框架 | Vue 3.5 + `<script setup>` | 已有 |
| 构建 | Vite 6 | 已有 |
| 样式 | Tailwind 3.4 | 设计系统依赖 |
| **路由** | **vue-router 4** | `/login` `/admin` `/reset-password` 三个页面必须有路由与守卫 |
| 状态 | 自研 `useVault()` | 现有实现够用，避免重构回归；登录态放 `useAuth()` |
| 加密 | WebCrypto + `hash-wasm`(Argon2id) | 原生 AES-GCM；Argon2 用 WASM |
| 净化 | `dompurify` | Markdown 走 `v-html`，必须净化 |
| 二维码 | `qrcode`（本地生成） | 2FA 绑定需要，**不得**调用外部二维码服务 |
| 后端 | FastAPI 0.115+ | 类型安全、异步、自动文档 |
| ORM/迁移 | SQLAlchemy 2.0 async + Alembic | 类型提示 + 可回滚迁移 |
| 邮件 | **aiosmtplib** | 异步发信，配合 QQ 邮箱 SSL 465 |
| 2FA | **pyotp** | 标准 TOTP（RFC 6238） |
| 密码哈希 | argon2-cffi | 服务端只存 authKey 哈希 |
| 令牌 | PyJWT | 短时 access token |
| 限流 | slowapi | 登录/发信防爆破 |
| 数据库 | SQLite（WAL） | 单用户足够，零运维 |
| 部署 | Nginx + systemd + certbot | 标准 VPS 方案 |

---

## 4. 安全模型

### 4.1 密钥体系

```
主密码（只在浏览器内存）
   │ Argon2id(salt, m=64MiB, t=3, p=1) → 64B masterKey
   ├── HKDF(masterKey, "enc")  → encKey  (32B) 包裹 DEK
   └── HKDF(masterKey, "auth") → authKey (32B) 登录认证

DEK (32B 随机，永不离开浏览器明文)
   wrappedDEK = AES-256-GCM(encKey, DEK)      ← 服务端只存这个

每条记录
   ciphertext = AES-256-GCM(DEK, JSON) + 12B nonce
```

### 4.2 注册流程

```
浏览器                                   FastAPI
 1. 生成 salt(16B) → masterKey/authKey/encKey
 2. 生成 DEK + wrappedDEK
 3. 生成恢复码(24 字符) → recoveryKey → wrappedDekRecovery
 ── POST /api/auth/register ───────────▶ 建用户（auth_hash 再哈希）
 ◀── 201 + token + 显示恢复码（仅此一次）──
```

> 恢复码必须由用户抄写/下载保存，界面需强提示"丢失将无法找回数据"。

### 4.3 登录流程（含 2FA）

```
 ── POST /api/auth/prelogin {email} ──▶ 返回 KDF 参数 + salt
 1. 本地算 masterKey → authKey
 ── POST /api/auth/login {email, authHash} ──▶
        ├─ 未开启 2FA → 直接返回 token + wrappedDek
        └─ 已开启 2FA → 返回 { requires2fa: true, challenge: <5min 一次性令牌> }
 ── POST /api/auth/2fa/verify {challenge, code} ──▶ 校验 TOTP
 ◀── access token + wrappedDek ──
 2. encKey 解 wrappedDEK → DEK（仅内存）
 3. GET /api/vault → 解密 → 渲染
```

失败处理：TOTP 连续错 5 次 → challenge 作废并记审计；可改用「恢复码」登录。

### 4.4 会话

- access token：JWT 15 分钟，**只放内存**。
- refresh token：7 天，`httpOnly + Secure + SameSite=Strict` Cookie，服务端存哈希、可撤销、每次刷新轮换。
- 页面刷新时先调 `/api/auth/refresh` 恢复会话；失败则跳 `/login` 并清空内存密钥。

### 4.5 账号 2FA（TOTP）

| 项 | 设计 |
| --- | --- |
| 算法 | TOTP，SHA-1，6 位，30 秒步长（兼容 Google Authenticator / 1Password / 微软验证器） |
| 绑定 | 已登录 → 服务端生成 secret → 前端本地渲染 `otpauth://` 二维码 → 输入 6 位验证码 → 启用 |
| 存储 | `users.totp_secret_enc` = AES-256-GCM(`SERVER_SECRET`, secret)。**服务端可解密**，这是 2FA 校验的必要代价 |
| 关闭 | 需同时提供「主密码 + 当前 TOTP 码」，防会话被劫持后关闭 |
| 备用 | 启用时生成 **10 个一次性恢复码**（哈希存库），可用于登录与关闭 2FA |
| 通知 | 启用/关闭 2FA 一律发邮件告警 |

### 4.6 邮箱与通知（QQ 邮箱）

**默认配置**（可在「安全与设置 → 邮箱配置」中修改）：

```ini
SMTP_HOST=smtp.qq.com
SMTP_PORT=465            # SSL；若用 587 则 STARTTLS
SMTP_USER=<你的QQ邮箱>@qq.com
SMTP_PASS=<SMTP 授权码>   # 注意：不是 QQ 登录密码，需在 QQ 邮箱设置里生成
SMTP_FROM=<你的QQ邮箱>@qq.com
```

用途（四类邮件）：

| 场景 | 触发 | 内容要点 |
| --- | --- | --- |
| 修改主密码通知 | 改密成功 | 时间、IP、设备；"非本人操作请立即重置" |
| 风险通知 | 新设备/异地登录、连续失败锁定、2FA 被关闭 | 时间、IP、地理位置（可选）、设备 UA |
| 找回密码验证码 | 点击"忘记主密码" | 6 位数字，10 分钟有效，最多尝试 5 次 |
| 测试邮件 | 设置页点"发送测试邮件" | 验证 SMTP 配置是否可用 |

实现要点：
- 发送失败**不阻塞**主流程（登录/改密照常），仅记审计 + 站内 Toast 提示。
- 邮件内容用纯文本 + 简单 HTML，不嵌入远程图片（避免被当垃圾邮件、也避免泄露打开行为）。
- 授权码用 `SERVER_SECRET` 加密后存 `user_settings`，接口返回时打码（只回显 `****`）。
- 单用户场景允许在 `.env` 里配置默认值，UI 保存后覆盖。

### 4.7 忘记主密码（零知识的必然取舍）

| 方案 | 数据是否可恢复 | 安全性 | 采用 |
| --- | --- | --- | --- |
| **恢复码** | ✅ 可恢复（用恢复码解 wrappedDekRecovery） | 高：服务端仍无解密能力 | ✅ 唯一方案 |
| 无恢复码 | ❌ 永久丢失 | — | 兜底提示：可清空重建 |

> **明确不做「托管恢复」**（服务端保存 DEK 副本）。服务端在任何情况下都不具备解密能力，这是本项目的安全底线。

**流程**：`/reset-password` → 输入邮箱 → 收验证码 → 校验 → 输入恢复码 → 设置新主密码（新 salt/新 encKey）→ 用恢复码解出 DEK → 用新 encKey 重新包裹 → 提交 → 数据完好。

### 4.8 已知风险与缓解

| 风险 | 缓解 |
| --- | --- |
| XSS 窃取内存密钥 | 严格 CSP、零第三方脚本、Markdown 一律 DOMPurify、禁用 `eval` |
| 忘记主密码 | 仅恢复码；注册与设置页反复提示「丢失即不可恢复」 |
| 服务端被入侵 | 条目全密文；authKey 为随机值；2FA/SMTP 密钥虽有服务端密钥保护，但泄露也无法解开条目（DEK 从不上传） |
| 登录/发信爆破 | slowapi 限流 + 账号失败计数锁定 + 验证码次数限制 |
| 邮件被伪造 | 邮件仅作通知，不作唯一凭证；重置必须叠加恢复码 |
| 中间人 | 强制 HTTPS + HSTS |
| 备份泄露 | age/GPG 加密后落盘，异地存放 |

---

## 5. 前端路由与页面

| 路由 | 页面 | 守卫 | 说明 |
| --- | --- | --- | --- |
| `/` | — | — | 重定向：已登录 → `/admin`，否则 `/login` |
| `/login` | 登录页 | `guestOnly` | 账号 + 主密码 →（若开启）2FA 步骤 |
| `/reset-password` | 重置页 | `guestOnly` | 邮箱验证码 → 恢复码 → 新主密码 |
| `/admin` | 后台主界面 | `requiresAuth` | 现有三栏界面，一行 UI 不改 |

- 守卫逻辑：`beforeEach` 读内存 token；页面刷新后先 `await auth.restore()`（走 refresh cookie）再放行，避免闪回登录页。
- 未登录访问 `/admin` → 重定向 `/login?redirect=/admin`；登录后回跳。
- 2FA 与验证码都是**页面内步骤**，不单独开路由，避免刷新丢失状态。
- 详细交互与视觉见 `docs/PAGES.md`。

---

## 6. 同步策略

- 拉取：登录后 `GET /api/vault` 全量（单用户数据小），响应带全局 `rev`。
- 写入：单条 `POST/PATCH/DELETE`，客户端生成 UUID，服务端返回新 `rev`。
- 冲突：`last-write-wins` + 乐观锁；`rev` 不匹配返回 `409`，前端提示并重新拉取。
- 离线：本地缓存密文（IndexedDB），离线可读；写操作入队（P7 可选）。
- 删除：软删除（`deleted_at`）。

---

## 7. 备份策略

| 项 | 设计 |
| --- | --- |
| 自动备份 | 按设置的时间（默认每日 03:00）由服务端 cron 触发 `sqlite3 .backup` |
| **保留时长** | **可设置：7 / 14 / 30 / 90 天 / 永久**（默认 30 天），清理任务读该设置 |
| 手动快照 | 设置页按钮，立即生成一份（不受保留策略影响，直到手动删除） |
| 导出 | 前端生成**加密备份包**（含 KDF 参数 + 用主密码包裹的 DEK + 全部密文），文件名 `vault-backup-YYYY-MM-DD.json` |
| 导入 | 选择备份包 → 输入该备份的主密码 → 解密 → 预览条数 → 选择合并策略（跳过已存在 / 覆盖 / 全部新增）→ 写入 |
| 服务端备份加密 | age 公钥加密后落盘，异地同步 |
| 恢复演练 | 每季度一次，记录在 `docs/DEPLOYMENT.md` |

> **导入 ≠ 旧数据迁移**：本项目**不做** localStorage 自动迁移（用户决定），导入只针对备份文件。

---

## 8. 目标目录结构

```
ByPassWord/
├── frontend/
│   ├── src/
│   │   ├── router/index.js        # 3 条路由 + 守卫
│   │   ├── pages/
│   │   │   ├── LoginPage.vue      # 账号密码 + 2FA 步骤
│   │   │   ├── ResetPasswordPage.vue
│   │   │   └── AdminPage.vue      # 现有主界面迁入
│   │   ├── components/            # 现有 UI 组件（视觉不改）
│   │   ├── stores/{vault,auth}.js
│   │   ├── crypto/{kdf,aes,vault-crypto}.js
│   │   ├── api/{client,auth,vault,settings}.js
│   │   ├── data/catalog.js
│   │   └── styles/
│   ├── index.html
│   ├── vite.config.js             # 899 端口 + /api 代理
│   └── package.json
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── api/{auth,twofa,vault,folders,items,settings,backup,audit}.py
│   │   ├── core/{config,db,security,server_crypto,deps,rate_limit,mailer}.py
│   │   ├── models/  schemas/  services/
│   │   └── jobs/backup_retention.py
│   ├── migrations/  tests/  pyproject.toml  .env.example
├── docs/  scripts/  Third/
```

---

## 9. 关键决策记录（ADR）

| # | 决策 | 备选 | 结论与理由 |
| --- | --- | --- | --- |
| 1 | 零知识加密 | 服务端加密 | 选零知识。密码库的核心价值 |
| 2 | 登录密码即主密码 | 两套密码 | 选一套，小白友好 |
| 3 | SQLite | PostgreSQL | 单用户，省运维 |
| 4 | 全量同步 | 增量/CRDT | 数据量小，逻辑简单 |
| 5 | 保留自研 store | Pinia | 减少回归风险 |
| 6 | **引入 vue-router** | 单页无路由 | **改判**：需要 `/login` `/admin` `/reset-password` 与守卫，路由是必需品 |
| 7 | 记录级加密 | 字段级 | 实现简单且不泄露结构 |
| 8 | **账号 2FA 用 TOTP** | 邮件验证码 | TOTP 离线可用、不依赖邮箱可用性；邮件只做通知 |
| 9 | **忘记密码默认走恢复码** | 仅邮箱重置 | 仅邮箱重置会摧毁零知识；恢复码兼顾可恢复与安全 |
| 10 | **不做 localStorage 迁移** | 一键导入旧数据 | 用户决定；避免把明文历史带进新体系 |
| 11 | 备份保留可配置 | 固定 14 天 | 用户需要按磁盘容量与合规要求调整 |

---

## 10. 待确认

1. QQ 邮箱的**授权码**由你提供（我无法代填），部署时填入设置页或 `.env`。
2. 是否需要**备份文件异地同步**（如对象存储/另一台机器）？默认只落本机 + 提示手动下载。

---

## 11. 与现有实现的差距清单

| 现状 | 需要改 |
| --- | --- |
| 单页无路由 | 引入 vue-router，拆 `/login` `/admin` `/reset-password` |
| 无登录态 | `useAuth()` + 守卫 + 静默刷新 |
| 无账号 2FA | 绑定/校验/恢复码/关闭 |
| 无邮件 | aiosmtplib + QQ SMTP + 4 类模板 + 测试发送 |
| `useVault()` 直读写 localStorage 明文 | 改 API + 本地密文缓存 |
| `v-html` 未净化 | 接 DOMPurify |
| 密码生成器 `Math.random()` | 改 `crypto.getRandomValues()` |
| 剪贴板清空设置未实现 | 落实 `clipboardClearSeconds` |
| 只有「导出」，无「导入」 | 备份包格式 + 导入合并策略 |
| 只有「自动备份时间」，无保留策略 | 增加保留天数 + 清理任务 |
| 设置里 SMTP 只有主机/端口 | 补账号/授权码/发件人/测试发送 |
