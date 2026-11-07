# 2026-11-07：当前 WSL 本机安全部署说明

本节是本轮安全修复的部署依据。下文保留的 VPS/Nginx 历史手册不是当前已启用配置；本轮不会公开监听或修改其他项目的 Nginx。

- 使用 `APP_ENV=local`，仅绑定 `127.0.0.1:899`；主进程同源提供构建后的 SPA 和 `/api`，无需另开 Vite 开发服务。
- `STATIC_DIR` 指向受控构建目录；未知 `/api` 路径返回404，不能落入 SPA。部署环境关闭 OpenAPI/Swagger 页面。
- local 环境只接受 localhost/127.0.0.1/::1 的 Host/Origin，阻断 DNS 重绑定；这是本机模式，不是公网生产的 HTTPS 配置。
- `JWT_SECRET` 与 `SERVER_SECRET` 必须是不同、至少32字符的生成秘密；local/production 启动拒绝默认、短值、重复字符占位及禁用限流。**不要仅换 SERVER_SECRET 而丢失旧的服务端加密数据。** 本次用户授权清空旧库后全新初始化，因此不需要旧密钥轮换。
- 数据目录由专用服务账号所有、0700，SQLite及WAL/SHM为0600；部署启动发现旧路径权限不安全会失败，不静默修改其他数据路径。
- 默认首账号成为安装 owner。之后不开放注册；既有非owner账号仍可登录自己的金库，但不能调用全库备份/共享部署邮件凭据。除非明确计划多人模式，不要设置 `ALLOW_REGISTRATION_AFTER_FIRST=true`。
- 每个用户的私有SMTP配置必须完整，新增或变更host/port/user/secure时重输私有密码；绝不拼接部署密码。仅owner在没有私有配置时使用完整部署配置。发送时一次解析DNS、验证所有地址、固定所选IP连接并保留TLS hostname/SNI；拒绝非公网地址，强制TLS或STARTTLS。仅测试环境的显式flags允许隔离内本地SMTP接收器，不应写入部署env。

## 应用内加密快照与恢复

`BACKUP_KEY_FILE` 是独立32字节随机二进制文件（0600），必须在 `BACKUP_DIR` 之外，不复用JWT/SERVER秘密。密钥丢失将无法解开快照；密钥应在单独受限的运维保管位置保存，**不要一起打入快照或源码包**。

owner 创建的全库快照先做 SQLite 一致性内存备份，再用AES-GCM整库加密为 `.db.enc`。磁盘不落明文临时库；落盘前后验证完整性，文件0600、目录0700。包括旧`.db`与未完成`.pending-*`，总计最多两份；已满则409 `backup_limit`，不会先删除旧备份，也不会创建第三份。后台仅在新加密快照验证后才按保留期限清理旧自动/pre-import文件，满额提醒最多每小时一次。

运维 CLI（必须以服务账号、加载正确的非公开env运行；命令行只传路径，不传密钥值）：

```bash
python scripts/encrypted_backup.py verify /private/backups/vault-...-manual.db.enc
python scripts/encrypted_backup.py decrypt /private/backups/vault-...-manual.db.enc --output /private/restore/vault.db
python scripts/encrypted_backup.py delete /private/backups/vault-...-manual.db.enc --confirm-delete
```

`verify`检查认证加密、SQLite可读和integrity_check；`decrypt`只写0700目录下全新0600文件，绝不覆盖现有输出；`delete`只删除BACKUP_DIR中的明确文件，且必须先成功验证另一份加密快照，因此不能删掉最后有效恢复点。恢复时先停止本项目写入，验证新文件和权限，再按已经批准的回退流程切换；脚本不会自动覆盖活动数据库。

正式服务的安装路径、systemd单位、实际入口和本次上线证据，由 `.codex/Deliver/` 的当前任务交付记录给出。历史手册中的 `scripts/rotate_server_secret.py`、APScheduler和自动age链不代表已实现；当前使用本节的加密快照与单调度器实现。

---

# 部署手册（Linux VPS）

> 目标环境：Ubuntu 22.04 / 24.04 LTS，1 核 1G 起（推荐 2G，Argon2 在服务端只用于校验，压力小）。
> 假设域名：`vault.example.com`（请替换成你自己的）。

---

## 1. 一次性初始化

```bash
# 1.1 更新系统 + 基础工具
sudo apt update && sudo apt -y upgrade
sudo apt -y install nginx python3.12 python3.12-venv python3-pip git sqlite3 ufw certbot python3-certbot-nginx age

# 1.2 创建专用系统用户（不要用 root 跑服务）
sudo useradd -r -m -d /opt/bypw -s /bin/bash bypw
sudo mkdir -p /var/lib/bypw /var/backups/bypw /var/www/bypw
sudo chown -R bypw:bypw /opt/bypw /var/lib/bypw /var/backups/bypw /var/www/bypw
sudo chmod 750 /var/lib/bypw

# 1.3 防火墙
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw --force enable
```

---

## 2. 拉取代码与安装依赖

```bash
sudo -u bypw -i
cd /opt/bypw
git clone <你的仓库地址> app && cd app

# 后端
cd backend
python3.12 -m venv .venv
. .venv/bin/activate
pip install -U pip
pip install -e .            # 或 pip install -r requirements.txt
cp .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"   # 生成 JWT_SECRET 填进 .env
alembic upgrade head        # 初始化数据库（生产建议 AUTO_MIGRATE=false，由部署脚本显式迁移）

# 前端
cd ../frontend
npm ci && npm run build     # 产物在 frontend/dist
```

`.env` 关键项：

```ini
APP_ENV=production
DATABASE_URL=sqlite+aiosqlite:////var/lib/bypw/vault.db
JWT_SECRET=<上面生成的随机串>
SERVER_SECRET=<再生成一个，用于加密 2FA secret / SMTP 授权码>
ACCESS_TOKEN_MINUTES=15
REFRESH_TOKEN_DAYS=7
ALLOWED_ORIGINS=https://vault.example.com
TRUSTED_PROXY_IPS=127.0.0.1

# QQ 邮箱默认配置（也可在设置页修改，UI 优先）
SMTP_HOST=smtp.qq.com
SMTP_PORT=465
SMTP_SECURE=true
SMTP_USER=你的QQ号@qq.com
SMTP_PASS=你的SMTP授权码
SMTP_FROM=你的QQ号@qq.com
SMTP_FROM_NAME=ByPassWord
```

> `SERVER_SECRET` 与 `JWT_SECRET` 必须不同；两者都**不得**提交仓库。轮换 `SERVER_SECRET` 需要重加密相关字段（`scripts/rotate_server_secret.py`）。

---

## 2.5 邮件（QQ 邮箱 SMTP）

### 2.5.1 获取授权码

1. 登录 QQ 邮箱网页版 → 设置 → 账号 → 「POP3/IMAP/SMTP/Exchange/CardDAV/CalDAV 服务」。
2. 开启 **SMTP 服务**，按提示验证后获得 16 位**授权码**（不是 QQ 登录密码）。
3. 把授权码填入 `.env` 的 `SMTP_PASS`，或部署后在「安全与设置 → 邮箱配置」里填写。

### 2.5.2 网络要求

| 项 | 说明 |
| --- | --- |
| 出站端口 | **465（SSL）** 或 587（STARTTLS）。多数云厂商封禁 25 端口，本项目默认用 465 |
| 防火墙 | 出站一般默认放行；若自建严格防火墙需 `ufw allow out 465/tcp` |
| DNS | 无需自建 SPF/DKIM（发信方是 QQ 邮箱） |
| 发信频率 | QQ 邮箱有日发信上限，风险通知类邮件已做节流（同类事件 10 分钟内合并） |

### 2.5.3 验证

```bash
# 命令行快速验证（不依赖应用）
printf 'From: you@qq.com\nTo: you@qq.com\nSubject: test\n\nhello\n' | \
  openssl s_client -quiet -connect smtp.qq.com:465 -crlf 2>/dev/null | head -5
# 或部署后在设置页点「发送测试邮件」，看审计日志 mail_sent / mail_failed
```

---

## 3. systemd 托管后端

`/etc/systemd/system/bypw-api.service`：

```ini
[Unit]
Description=ByPassWord API
After=network.target

[Service]
Type=simple
User=bypw
Group=bypw
WorkingDirectory=/opt/bypw/app/backend
EnvironmentFile=/opt/bypw/app/backend/.env
ExecStart=/opt/bypw/app/backend/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 2
Restart=always
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/bypw /var/backups/bypw
CapabilityBoundingSet=
AmbientCapabilities=

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now bypw-api
sudo systemctl status bypw-api --no-pager
curl -s http://127.0.0.1:8000/api/health
```

---

## 4. Nginx 站点配置

`/etc/nginx/sites-available/bypw`：

```nginx
server {
    listen 80;
    server_name vault.example.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name vault.example.com;

    ssl_certificate     /etc/letsencrypt/live/vault.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/vault.example.com/privkey.pem;

    root /var/www/bypw;
    index index.html;

    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;
    add_header X-Content-Type-Options nosniff always;
    add_header X-Frame-Options DENY always;
    add_header Referrer-Policy no-referrer always;
    add_header Content-Security-Policy "default-src 'self'; img-src 'self' data: https://www.google.com; script-src 'self' 'wasm-unsafe-eval'; style-src 'self' 'unsafe-inline'; font-src 'self'; connect-src 'self'; frame-ancestors 'none'" always;

    # 前端（SPA）
    location / {
        try_files $uri $uri/ /index.html;
    }

    # 静态资源长缓存（文件名带 hash）
    location /assets/ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # API 反代
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        client_max_body_size 4m;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/bypw /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d vault.example.com --agree-tos -m you@example.com --redirect
sudo systemctl list-timers | grep certbot    # 自动续期确认
```

---

## 5. 发布前端

```bash
sudo -u bypw bash -c 'cd /opt/bypw/app/frontend && npm ci && npm run build'
sudo rsync -a --delete /opt/bypw/app/frontend/dist/ /var/www/bypw/
sudo chown -R www-data:www-data /var/www/bypw
```

---

## 6. 备份与保留策略

备份由**应用内定时任务**驱动（读设置里的「自动备份时间」与「保留时长」），脚本只做最底层的"导出 + 加密"：

`/opt/bypw/backup.sh`：

```bash
#!/usr/bin/env bash
set -euo pipefail
STAMP=$(date +%Y%m%d-%H%M%S)
KIND="${1:-auto}"                                  # auto | manual | pre-import
OUT=/var/backups/bypw
sqlite3 /var/lib/bypw/vault.db ".backup '$OUT/vault-$STAMP.db'"
age -r "$(cat /opt/bypw/age.pub)" -o "$OUT/vault-$STAMP-$KIND.db.age" "$OUT/vault-$STAMP.db"
rm -f "$OUT/vault-$STAMP.db"

# 保留策略由应用层执行（读 user_settings.backupRetentionDays），
# 这里只清理"已超过最大保留上限（90 天）"的兜底残留，防止磁盘被写满
find "$OUT" -name '*-auto.db.age' -mtime +90 -delete
```

```bash
chmod 750 /opt/bypw/backup.sh
```

调度（二选一）：

- **推荐**：由后端 APScheduler 按用户设置的时间执行（可在 UI 改，无需重启 cron）
- 兜底：`crontab -u bypw -e` 加 `0 3 * * * /opt/bypw/backup.sh auto`

**保留规则**

| 类型 | 是否受「保留时长」影响 |
| --- | --- |
| `auto`（自动备份） | ✅ 超过 N 天自动删除（N 来自设置：7/14/30/90/0=永久） |
| `manual`（手动快照） | ❌ 永久保留，需手动删 |
| `pre-import`（导入前自动备份） | ❌ 保留 30 天后清理 |

> 强烈建议把 `.age` 文件再同步到**另一台机器或对象存储**——同盘备份挡不住磁盘损坏。

---

## 7. 升级发布流程

```bash
sudo -u bypw -i
cd /opt/bypw/app
/opt/bypw/backup.sh                      # 先备份
git pull
cd backend && . .venv/bin/activate && pip install -e . && alembic upgrade head
sudo systemctl restart bypw-api
cd ../frontend && npm ci && npm run build
sudo rsync -a --delete dist/ /var/www/bypw/
sudo systemctl reload nginx
curl -s https://vault.example.com/api/health
```

**回滚**：`git checkout <上一个 tag>` → 重跑迁移 `alembic downgrade -1`（若本次有迁移）→ 重启服务 → 恢复备份。

---

## 8. 日常运维速查

| 需求 | 命令 |
| --- | --- |
| 看后端日志 | `journalctl -u bypw-api -f` |
| 看 Nginx 日志 | `tail -f /var/log/nginx/access.log` |
| 数据库体积 | `ls -lh /var/lib/bypw/vault.db*` |
| 手动备份 | `sudo -u bypw /opt/bypw/backup.sh` |
| 恢复演练 | 见下 |
| 重启服务 | `sudo systemctl restart bypw-api` |

**恢复演练（每季度）**：

```bash
sudo systemctl stop bypw-api
cp /var/lib/bypw/vault.db /var/lib/bypw/vault.db.bak
age -d -i /opt/bypw/age.key -o /tmp/restore.db /var/backups/bypw/vault-2026-11-01.db.age
sqlite3 /tmp/restore.db "PRAGMA integrity_check;"      # 必须返回 ok
cp /tmp/restore.db /var/lib/bypw/vault.db && chown bypw:bypw /var/lib/bypw/vault.db
sudo systemctl start bypw-api && curl -s localhost:8000/api/health
```

---

## 9. 常见故障

| 现象 | 排查 |
| --- | --- |
| 502 Bad Gateway | `systemctl status bypw-api`，多为 `.env` 缺失或端口占用 |
| 登录一直 401 | 检查前端 KDF 参数是否与 `prelogin` 返回一致；服务器时钟是否准确（`timedatectl`） |
| 刷新后掉登录 | Cookie 的 `Secure` 要求 HTTPS；检查反代 `X-Forwarded-Proto` |
| 数据库 locked | 确认 WAL 已开启、`busy_timeout` 生效；避免用 sqlite3 长事务占锁 |
| 图标空白 | CSP `img-src` 是否放行 `https://www.google.com`（任意站点图标兜底） |
| 邮件发不出（`mail_failed`） | ① 授权码是否填的是 QQ **授权码**而非登录密码；② 端口 465 是否被出站策略拦截（`nc -vz smtp.qq.com 465`）；③ 是否触发 QQ 日发信上限；④ 看 `journalctl -u bypw-api | grep -i smtp` |
| 收不到重置验证码 | 检查垃圾箱；QQ 邮箱可能拦截自建发信，可把发件地址加入白名单；确认 `password_resets` 表有记录 |
| 2FA 验证码总是不对 | 服务器时间偏差需 < 30s：`sudo timedatectl set-ntp true`；确认手机时区自动同步 |
