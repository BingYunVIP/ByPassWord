# 本次修复决策

| 日期 | 决定 | 原因与证据 |
| --- | --- | --- |
| 2026-11-03 | 根目录 npm 只提供启动入口，依赖仍在 frontend 和 backend | 现有 `frontend/package.json`、`backend/pyproject.toml` 已分别管理依赖；不为启动功能引入第三方包。 |
| 2026-11-03 | Bash + setsid 管理两个服务进程组 | 当前目标为 Linux/WSL；需要同时清理 npm/Vite 和 Uvicorn reload 子进程，并处理任一服务退出。 |
| 2026-11-03 | 保留现有 Git 状态，不创建 Commit | 用户在本次会话中明确选择；7 份既有未跟踪文档不改动。 |
