.PHONY: api web test smoke payload check-db

# 后端开发服务（8000，启动时自动迁移）
api:
	cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000

# 前端开发服务（899）
web:
	cd frontend && npm run dev

# 后端测试
test:
	cd backend && .venv/bin/pytest

# 真实端到端冒烟：空库 → 启动 → 15 步认证流程 → 收尾
smoke:
	cd backend && ./scripts/smoke.sh

# 生成 Swagger 可用的注册请求体
payload:
	cd backend && .venv/bin/python scripts/gen_register_payload.py

# 查看数据库表/索引/外键/行数
check-db:
	cd backend && .venv/bin/python scripts/check_db.py
