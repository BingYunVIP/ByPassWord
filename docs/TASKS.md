# 任务看板（唯一任务源）

> 规则见 `docs/DEV-WORKFLOW.md` 第 3 节。
> 状态：`TODO` / `DOING` / `DONE` / `BLOCKED` —— **即时更新，不批量补记**。

最后更新：2026-11-01（v2：补充登录/2FA/邮件/路由/备份保留，取消 localStorage 迁移）

---

## 0. 总览

| 阶段 | 主题 | 任务数 | 状态 |
| --- | --- | --- | --- |
| P0 | 架构与文档 | 5 | ✅ DONE |
| P1 | 工程拆分与后端骨架 | 5 | ✅ DONE |
| P2 | 认证、2FA、找回密码、邮件 | 8 | ✅ DONE |
| P3 | 加密层与同步 API | 5 | ✅ DONE |
| P4 | 前端路由、页面与安全修补 | 7 | ✅ DONE |
| P5 | 设置、备份、导入导出、审计 | 6 | ✅ DONE |
| P6 | VPS 部署 | 4 | ⏳ TODO |
| P7 | 加固与可选增强 | 4 | ⏳ TODO |

---

## P0 架构与文档 ✅

| ID | 任务 | 验收标准 | 状态 |
| --- | --- | --- | --- |
| P0-1 | 总体架构 | `ARCHITECTURE.md` 含架构图、零知识、2FA、邮件、找回、ADR | DONE |
| P0-2 | 数据模型 | `DATA-MODEL.md` 含全部表、加密字段归属、备份保留 | DONE |
| P0-3 | API 契约 | `API.md` 含 auth/2fa/forgot/vault/backup/settings | DONE |
| P0-4 | 页面与路由 | `PAGES.md` 含 /login /reset-password /admin 与设置项线框 | DONE |
| P0-5 | 部署与流程 | `DEPLOYMENT.md`（含 QQ 邮箱）、`DEV-WORKFLOW.md`、本文件 | DONE |

---

## P1 工程拆分与后端骨架

| ID | 任务 | 目标 | 验收标准 | 依赖 | 状态 |
| --- | --- | --- | --- | --- | --- |
| P1-0 | 目录拆分 | 现有前端迁入 `frontend/`，新建 `backend/` | `cd frontend && npm run build` 通过（产物 hash 与拆分前一致）；899 页面回归 68+15 项全绿；`Third/` 未动；README 建立 | — | DONE |
| P1-1 | FastAPI 骨架 | `app/main.py` + `/api/health` | `curl :8000/api/health` → `{"status":"ok","db":"ok"}`；`/api/docs` 返回 200 | P1-0 | DONE |
| P1-2 | 配置与 DB 层 | `core/config.py`、`core/db.py` | 读 `.env`；`journal_mode=wal`、`foreign_keys=1`、`busy_timeout=5000` 实测生效 | P1-1 | DONE |
| P1-3 | Alembic 初始迁移 | 全部 9 张表一次建好 | `upgrade → downgrade base → upgrade` 实测均成功；7 个索引、8 条外键齐全 | P1-2 | DONE |
| P1-4 | 测试基线 | pytest + httpx | `pytest` 5 项全绿（health / openapi / PRAGMA / 级联删除 / 时间往返） | P1-3 | DONE |

---

## P2 认证、2FA、找回密码、邮件

| ID | 任务 | 目标 | 验收标准 | 依赖 | 状态 |
| --- | --- | --- | --- | --- | --- |
| P2-1 | 注册 | `POST /api/auth/register` | 建用户并返回 token；重复邮箱 409；非法 base64 400；恢复码副本落库 | P1-4 | DONE |
| P2-2 | 预登录/登录 | `prelogin`、`login`（无 2FA 分支） | 正确凭证返回 token+wrappedDek；错误 401；未知邮箱返回随机 KDF | P2-1 | DONE |
| P2-3 | 令牌与刷新 | JWT + refresh 轮换 | refresh 换新且旧 token 立即失效；登出后 refresh 401 | P2-2 | DONE |
| P2-4 | 锁定与限流 | slowapi + 账号锁定 | 连续 10 次失败 → 423 锁定 15 分钟；限流可用开关关闭（测试/冒烟） | P2-2 | DONE |
| P2-5 | 修改主密码 | 重包裹同一 DEK | 旧密码失效、新密码可登录、全部会话被撤销、发通知邮件 | P2-3 | DONE |
| P2-6 | **账号 2FA** | setup/enable/verify/disable + 10 个恢复码 | 登录需二次验证；恢复码一次性；重新生成后旧码作废；关闭需主密码+TOTP | P2-3 | DONE |
| P2-7 | **忘记主密码** | 邮箱验证码 + 恢复码重置 | 验证码→resetToken→重置→新密码可登录；未知邮箱仍返回 202 | P2-6 | DONE |
| P2-8 | **邮件服务** | QQ SMTP（465）+ 4 类模板 + 测试发送 | 4 类模板就绪；未配置 SMTP 时静默降级不阻塞主流程；**真实发信待授权码**（P6-4） | P2-1 | DONE（实现） |

---

## P3 加密层与同步 API

| ID | 任务 | 目标 | 验收标准 | 依赖 | 状态 |
| --- | --- | --- | --- | --- | --- |
| P3-1 | 前端 crypto | `crypto/kdf.js`、`aes.js`、`vault-crypto.js` | Argon2id→HKDF 拆 encKey/authKey；AES-GCM 记录加解密；DEK 包裹/恢复码；**vitest 16 项全绿** | P1-0 | DONE |
| P3-2 | 全量/增量拉取 | `GET /api/vault?since=` | 全局 rev（vault_state 表）；全量排除已删、增量含墓碑 | P1-4 | DONE |
| P3-3 | 单条增删改 | folders/items CRUD | `rev` 冲突 409（带服务端 rev）；同 id 同内容幂等；软删除 | P3-2 | DONE |
| P3-4 | 设置读写 | `/api/settings` GET/PUT | 密文往返；未登录 401 | P3-2 | DONE |
| P3-5 | 批量写入 | `POST /api/vault/import` | skip/overwrite/duplicate 三策略实测正确；上限 5000 条 | P3-3 | DONE |

---

## P4 前端路由、页面与安全修补

| ID | 任务 | 目标 | 验收标准 | 依赖 | 状态 |
| --- | --- | --- | --- | --- | --- |
| P4-0 | **路由骨架** | `/login` `/admin` `/reset-password` + 守卫 | 未登录访问 `/admin` 跳登录；已登录访问 `/login` 跳后台；刷新先恢复会话再放行 | P3-1 | DONE |
| P4-1 | API 客户端 | 自动刷新、统一错误 | 401 自动刷新并重试一次；失败抛 ApiError；统一 `{code,message}` | P2-3 | DONE |
| P4-2 | 登录页 | 账号 + 主密码 + 2FA + 恢复码登录 + 注册 | 四条路径可用；KDF 进度提示；注册后强制展示恢复码 | P4-0 | DONE |
| P4-3 | 重置页 | 三步向导 | 邮箱验证码 → 恢复码解 DEK → 新主密码重新包裹 → 可登录 | P4-2 | DONE |
| P4-4 | 数据层改造 | `useVault()` 接 API | 全量拉取后解密；增删改走接口并回写 rev；刷新进入锁定态、解锁后数据完整 | P4-2 | DONE |
| P4-5 | **XSS 修补** | Markdown 接 DOMPurify | 注入 `<img onerror>` 不执行、属性被剥离（浏览器实测） | P4-4 | DONE |
| P4-6 | **随机数修补** | 密码生成器改 `crypto.getRandomValues` | 全仓 0 处 `Math.random`；拒绝采样避免取模偏差 | P4-4 | DONE |
| P4-7 | 剪贴板清空 | 落实 `clipboardClearSeconds` | 复制后按设置秒数清空剪贴板并提示 | P4-4 | DONE |

---

## P5 设置、备份、导入导出、审计

| ID | 任务 | 目标 | 验收标准 | 依赖 | 状态 |
| --- | --- | --- | --- | --- | --- |
| P5-1 | 设置持久化 | 安全设置存服务端 | 换设备登录后设置一致；解锁时自动解密载入 | P3-4 | DONE |
| P5-2 | **邮箱配置 UI** | SMTP 主机/端口/账号/授权码/发件人 + 测试发送 | 保存后 `hasPassword=true`；授权码不回显；未配置时测试发信返回 502 并提示 | P5-1 | DONE |
| P5-3 | **备份保留策略** | 保留天数下拉 + 服务端清理任务 | 7/14/30/90/永久可选并持久化；后台每小时清理 auto，manual 不清理（单测覆盖） | P5-1 | DONE |
| P5-4 | **导出按钮** | 备份包（加密 JSON）导出 | 包内只有密文 + 包裹后的 DEK，无明文；可被同一主密码解开（单测覆盖） | P3-2 | DONE |
| P5-5 | **导入按钮** | 选文件 → 输备份主密码 → 选策略 | 三种策略结果正确；导入后用当前 DEK 重新加密；错误密码有明确提示 | P5-4 | DONE |
| P5-6 | 审计日志展示 | `/api/audit` 接入设置中心 | 注册/邮箱配置/备份/导入等事件可见，倒序 + 游标分页 | P3-2 | DONE |

---

## P6 VPS 部署

| ID | 任务 | 目标 | 验收标准 | 依赖 | 状态 |
| --- | --- | --- | --- | --- | --- |
| P6-1 | 初始化脚本 | `scripts/provision.sh` | 新机器一条命令装好依赖、用户、防火墙 | P1-4 | TODO |
| P6-2 | systemd + Nginx + HTTPS | 按 `DEPLOYMENT.md` | 公网 HTTPS 可访问；`/api/health` 正常；安全响应头齐全 | P6-1 | TODO |
| P6-3 | 备份与恢复演练 | cron + age + 保留策略 | 自动备份成功；恢复后数据完整；保留策略按设置执行 | P6-2 | TODO |
| P6-4 | QQ 邮箱联通验证 | 生产环境发信 | 测试邮件 + 找回验证码均可达；审计有记录 | P6-2 | TODO |

---

## P7 加固与可选增强

| ID | 任务 | 目标 | 验收标准 | 依赖 | 状态 |
| --- | --- | --- | --- | --- | --- |
| P7-1 | 图标字体子集化 | 1.4MB → ~60KB | 视觉不变；构建体积下降 | P6-2 | TODO |
| P7-2 | ~~托管恢复开关~~ | 已决定**不做**（服务端永不解密） | — | — | CANCELLED |
| P7-3 | PWA / 离线写队列 | 可选 | 断网可读；恢复网络自动同步 | P4-4 | TODO |
| P7-4 | 监控与告警 | uptime + 错误告警 | 服务挂了能收到通知 | P6-2 | TODO |
| P7-5 | 一次性 challenge | 2FA / 重置凭证单次有效 | 同一 challenge 第二次使用返回 401；有测试 | P2-6 | TODO |
| P7-6 | 邮件节流与合并 | 同类风险通知 10 分钟内合并 | 连续触发只发一封；审计可查 | P2-8 | TODO |

---

## 对账清单（你的需求 → 任务）

| 需求 | 任务 | 状态 |
| --- | --- | --- |
| 单用户使用 | 已确认，无多用户入口；表保留 user_id | DONE（设计） |
| 邮箱配置默认 QQ 邮箱 | P2-8、P5-2 | 设计完成 |
| 邮箱用于改密/找回/风险通知 | P2-5、P2-7、P2-8 | 设计完成 |
| 新增账号 2FA | P2-6、P4-2 | 设计完成 |
| `/login` `/admin` 路由页面 | P4-0、P4-2 | 设计完成 |
| 导入/导出按钮 | P5-4、P5-5 | 设计完成 |
| 备份保留时间 | P5-3、P6-3 | 设计完成 |
| 目录拆分 frontend/backend | P1-0（已批准） | TODO |
| 不做 localStorage 迁移 | 已从任务中移除，仅保留备份文件导入 | DONE（决策） |
