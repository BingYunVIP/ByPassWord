#!/usr/bin/env bash
# Linux / WSL：同时启动开发服务，退出时关闭各自进程组（包括 reload 子进程）。
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

if ! command -v setsid >/dev/null 2>&1; then
  echo '缺少 setsid，请安装 util-linux 后重试（本脚本适用于 Linux / WSL）。' >&2
  exit 1
fi

if [[ ! -x frontend/node_modules/.bin/vite ]]; then
  echo '缺少前端依赖，请在项目根目录执行：npm --prefix frontend ci' >&2
  exit 1
fi

if [[ ! -x backend/.venv/bin/python ]] || ! backend/.venv/bin/python -m uvicorn --version >/dev/null 2>&1; then
  echo '缺少后端虚拟环境或 Uvicorn，请在项目根目录执行：' >&2
  echo '  python3 -m venv backend/.venv' >&2
  echo '  backend/.venv/bin/python -m pip install -e "./backend[dev]"' >&2
  exit 1
fi

pids=()
cleanup() {
  trap '' INT TERM
  for pid in "${pids[@]}"; do
    kill -TERM -- "-$pid" 2>/dev/null || true
  done
  for pid in "${pids[@]}"; do
    wait "$pid" 2>/dev/null || true
  done
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

echo '正在启动前端 http://localhost:899 和后端 http://127.0.0.1:8000'
echo '按 Ctrl+C 同时停止两个服务；任一服务退出时将停止另一个。'

setsid npm run dev:api &
pids+=("$!")
setsid npm run dev &
pids+=("$!")

status=0
wait -n "${pids[@]}" || status=$?
echo '一个开发服务已退出，正在停止所有开发服务。' >&2
# 开发服务应持续运行，意外正常退出也视为启动失败。
if [[ "$status" -eq 0 ]]; then
  status=1
fi
exit "$status"
