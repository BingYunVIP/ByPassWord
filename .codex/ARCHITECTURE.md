# 项目架构摘要

更新时间：2026-11-03（Asia/Singapore）。既有完整设计见 [架构文档](../docs/ARCHITECTURE.md)，现有业务任务见 [任务看板](../docs/TASKS.md)。

- 前端：`frontend/`，Vue 3 + Vite；开发端口 899，`/api` 代理到 `127.0.0.1:8000`（证据：`frontend/package.json`、`frontend/vite.config.js`）。
- 后端：`backend/`，FastAPI + SQLite；通过 `backend/.venv` 运行，开发端口 8000（证据：`backend/pyproject.toml`、`Makefile`）。
- 启动时默认自动迁移数据库，验证必须使用临时库，避免影响现有数据（证据：`backend/app/main.py`、`backend/app/core/config.py`）。
- 本次仅补充根目录开发启动入口，保持既有端口、配置及业务逻辑；详见 [启动修复任务](Task/2026-11-03-dev-all.md)。

## 2026-11-04：管理入口补充

本节更新时间：2026-11-04（Asia/Singapore）。上文为保留的历史记录，描述的是原启动修复任务；本次仅更新协作技能和管理文档，未改变应用架构。

- 项目管理总入口：[文档与历史索引](INDEX.md)。管理记录使用 `Require/`、`Task/`、`Test/`、`Memory/`、`Permissions/`、`Deliver/` 六个目录；新建子文档采用 `YYYY-MM-DD-简要说明.md`。
- 原 `docs/` 文档和 `.codex/` 历史记录保留原路径并由索引关联，不将设计说明当作当前运行验证。
- 本次重新读取的证据：`../package.json`、`../frontend/package.json`、`../frontend/vite.config.js`、`../backend/pyproject.toml`、`../backend/app/main.py`。前端仍为 Vue 3 + Vite，后端为 FastAPI；开发配置使用 899/8000 端口。
- 运行观察：本次检查时 899/8000 没有监听；未启动应用，未确认生产入口或线上健康，也未重跑历史业务测试。启动应用可能触发自动迁移，因此本次文档任务不执行启动。
- 本地技能入口为 `/root/.agents/skills/ai-project-manager/SKILL.md`，不属于项目 Git 跟踪范围；本次更新有独立文件清单和恢复快照，详见 [管理更新任务](Task/2026-11-04-技能更新与管理目录初始化.md)。

## 2026-11-07：安全修复架构（当前代码）

- 个人模式通过单例installation_owner确定首账号所有者；默认完成初始化后拒绝追加注册。共享SMTP部署配置和加密全库快照仅所有者可访问。
- access token关联sid会话家族与credential_version，受保护API检查数据库有效会话；refresh与挑战/邮箱码使用数据库条件更新实现单次消费。TOTP时间步跨登录、解锁和安全设置共享单调消费状态。
- 主密码恢复码在浏览器包裹同一DEK，并用不同HKDF用途派生服务端恢复认证值；服务端同时要求邮箱凭证和恢复证明。旧账号未升级恢复配置时只禁用邮箱重置，不改变原正常登录/密文。
- 快照为AES-GCM加密的SQLite一致性备份，32字节独立备份密钥在快照目录外；创建后真实解密及SQLite完整性校验。运行数据0700/0600，两份容量上限满额拒绝创建第三份；未验证替代副本前不删除旧备份。
- 前端锁定/会话失效撤销异步结果并清空敏感状态；条目动态码采用真实HMAC-SHA1/30秒算法；默认离线图标，外链仅HTTP/HTTPS，导入先限制大小及KDF参数再解密。
- 仅本机正式运行将由FastAPI同源服务构建SPA及API，专用服务账号/只读发布目录/独立受限数据目录，单进程监听127.0.0.1:899；当前代码与测试证据见[修复任务](Task/2026-11-07-安全修复与WSL本机部署.md)，部署运行状态以交付记录为准，不将设计当作已经上线。

本轮部署已实际完成：bypassword.service（专用账号UID997，仅CAP_NET_BIND_SERVICE绑定899），/opt/bypassword/current指向20261107T033324Z发布；/var/lib/bypassword/data/vault.db、backups与keys分目录0700/0600；/etc/bypassword/runtime.env root0600。服务仅127.0.0.1:899，实际健康和初始浏览器检查通过，空库未创建账号；详见[部署验证](Test/2026-11-07-本机部署验证.md)。F16金库写入现在使用数据库事务写锁与原子rev/条件更新，跨进程并发已真实验证，兼容原客户端协议。
