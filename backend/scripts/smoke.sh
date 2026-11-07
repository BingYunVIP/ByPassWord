#!/usr/bin/env bash
# 真实端到端冒烟：从「空数据库」开始，启动服务，跑完整认证 + 金库同步流程，然后收尾。
# 用法：./scripts/smoke.sh [端口]
set -euo pipefail

cd "$(dirname "$0")/.."
PORT="${1:-8010}"
DB="smoke.db"
BASE="http://127.0.0.1:${PORT}"

echo "== 1/7 清理旧库（模拟全新部署） =="
rm -f "$DB" "$DB-wal" "$DB-shm"
echo "已删除 $DB（不存在即为全新）"

echo "== 2/7 启动服务（不做任何手动迁移，验证启动自动建表） =="
export RATE_LIMIT_ENABLED=false
export DATABASE_URL="sqlite+aiosqlite:///./${DB}"
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port "$PORT" --log-level warning &
SERVER_PID=$!
cleanup() {
  kill "$SERVER_PID" 2>/dev/null || true
  wait "$SERVER_PID" 2>/dev/null || true
}
trap cleanup EXIT

echo "== 3/7 等待健康检查 =="
READY=0
for _ in $(seq 1 60); do
  if curl -sf "${BASE}/api/health" >/dev/null 2>&1; then READY=1; break; fi
  sleep 0.25
done
if [ "$READY" -ne 1 ]; then
  echo "FAIL | 服务 10 秒内未就绪"
  exit 1
fi
curl -s "${BASE}/api/health"; echo

echo "== 4/7 校验空库已自动建表 =="
.venv/bin/python scripts/check_db.py "$DB" | head -2

echo "== 5/7 认证流程 =="
.venv/bin/python scripts/smoke_auth.py "$BASE"

echo "== 6/7 金库同步流程 =="
.venv/bin/python scripts/smoke_vault.py "$BASE"

echo "== 7/7 设置中心（邮箱/备份/审计） =="
.venv/bin/python scripts/smoke_settings.py "$BASE"
