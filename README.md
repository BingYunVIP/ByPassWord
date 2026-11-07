# 密码库（ByPassWord）

一个 Apple HIG 风格的个人密码管理器：Vue 3 前端 + FastAPI 后端 + SQLite，**零知识加密**（服务端不存明文）。

> 当前状态：前后端安全修复及独立测试完成，支持个人单账号初始化、两步验证、恢复码、加密备份与本机同源部署。

## 目录结构

```
ByPassWord/
├── frontend/     # Vue 3 + Vite + Tailwind（开发端口 899）
├── backend/      # FastAPI + SQLAlchemy + SQLite（开发端口 8000）
├── docs/         # 架构 / 接口 / 数据模型 / 页面 / 部署 / 流程 / 任务
├── scripts/      # 部署与运维脚本
└── Third/        # 原始单文件参考实现（只读）
```

## 当前 WSL 本机部署

本机已安装 `bypassword.service`，浏览器打开 `http://localhost:899`。服务只监听 `127.0.0.1:899`，由专用账号运行，随 WSL 的 systemd 启动；WSL 关闭时不可访问。首次进入创建自己的账号，并独立保存主密码恢复码。

```bash
systemctl status bypassword --no-pager
systemctl restart bypassword
journalctl -u bypassword -n 50 --no-pager
```

运行数据库、密钥和环境配置独立保存在本机受限目录，不随源码上传。外部 SMTP 需自行配置并验证投递。部署与验收细节见 [.codex/Deliver/2026-11-07-安全修复与本机部署交付.md](.codex/Deliver/2026-11-07-安全修复与本机部署交付.md)。

首次 GitHub 发布采用清理演示凭据后的当前源码快照；本地旧开发历史独立保留，未随首次发布上传。`Third/` 仅为不含初始密码条目的参考实现；`ByUI/` 已移除。

## 快速开始

### 一条命令启动前后端（Linux / WSL）

首次运行先在项目根目录准备依赖（Python 3.11+、Node.js/npm、Bash 和 `setsid`）：

```bash
cd /root/ByPassWord           # 替换为你的实际项目路径
npm --prefix frontend ci
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install -e "./backend[dev]"
# 若尚未创建配置：复制 backend/.env.example 为 backend/.env，填写 JWT_SECRET / SERVER_SECRET

npm run dev:all
```

已安装依赖时，直接在根目录执行 `npm run dev:all` 即可。前端地址为 http://localhost:899，后端健康检查为 http://127.0.0.1:8000/api/health；前端 `/api` 请求自动代理到后端。

按 `Ctrl+C` 同时停止两个服务；任一服务退出时，启动脚本会停止另一个服务并返回失败。依赖缺失时会提示安装命令；端口占用时请先确认占用进程，不要重复启动。

根目录 `npm run dev` 仅启动前端，`npm run dev:api` 仅启动后端。依赖仍分别管理在 `frontend/` 和 `backend/`；只在根目录执行 `npm install` 不能安装前后端依赖。

### 分别启动

```bash
# 后端（终端 1）
cd backend
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env          # 填写 JWT_SECRET / SERVER_SECRET
uvicorn app.main:app --reload --port 8000
# 首次启动会自动建表（AUTO_MIGRATE=true），无需手动 alembic upgrade

# 前端（终端 2）
cd frontend
npm install
npm run dev                   # http://localhost:899
```

也可以用根目录的快捷命令：

```bash
make api      # 后端 8000
make web      # 前端 899
make test     # 后端测试
make smoke    # 真实端到端冒烟（空库 → 启动 → 15 步认证流程）
make payload  # 生成 Swagger 可直接粘贴的注册请求体
make check-db # 查看表/索引/外键/行数
```

前端 `/api/*` 请求会经 Vite 代理到 `127.0.0.1:8000`；生产环境由 Nginx 反代。

## 文档

| 文档 | 内容 |
| --- | --- |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 总体架构、技术选型、零知识加密、ADR |
| [docs/DATA-MODEL.md](docs/DATA-MODEL.md) | 数据库表结构、加密字段、备份保留 |
| [docs/API.md](docs/API.md) | 接口契约 |
| [docs/PAGES.md](docs/PAGES.md) | 路由与页面设计 |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | VPS 部署、QQ 邮箱、运维 |
| [docs/DEV-WORKFLOW.md](docs/DEV-WORKFLOW.md) | 开发流程与规范 |
| [docs/TASKS.md](docs/TASKS.md) | 任务看板（唯一任务源） |
| [docs/UI-DESIGN-SYSTEM.md](docs/UI-DESIGN-SYSTEM.md) | UI 风格基准 |

## 安全说明

- 主密码只在浏览器内存中派生密钥，服务端只保存密文与包裹后的数据密钥。
- **忘记主密码且没有恢复码时，数据无法恢复**（零知识的必然代价）。
- 本项目不做托管恢复：服务端在任何情况下都不具备解密能力。

## 许可

个人项目，未授权公开发布。
