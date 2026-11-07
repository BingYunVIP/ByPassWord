"""Real local HTTP and SMTP protocol regression: no mocked transport or sender."""
import asyncio
import base64
import os
import secrets
import signal
import socket
import subprocess
import sys
import httpx
import uvicorn
from app.main import app
from app.core.config import settings


async def test_real_local_lifespan_migrates_private_db_and_serves_spa(tmp_path):
    """Exercise deployed settings, migrations and lifespan in a separate server."""
    data_dir = tmp_path / 'data'
    data_dir.mkdir(mode=0o700)
    backup_dir = tmp_path / 'backups'
    backup_dir.mkdir(mode=0o700)
    key = data_dir / 'backup.key'
    key.write_bytes(os.urandom(32))
    key.chmod(0o600)
    static = tmp_path / 'static'
    static.mkdir()
    (static / 'index.html').write_text('<title>Real deployment test</title>')
    database = data_dir / 'vault.db'
    environment = {
        **os.environ,
        'APP_ENV': 'local',
        'AUTO_MIGRATE': 'true',
        'DATABASE_URL': f'sqlite+aiosqlite:///{database}',
        'BACKUP_DIR': str(backup_dir),
        'BACKUP_KEY_FILE': str(key),
        'STATIC_DIR': str(static),
        'JWT_SECRET': secrets.token_urlsafe(48),
        'SERVER_SECRET': secrets.token_urlsafe(48),
        'RATE_LIMIT_ENABLED': 'true',
        'ALLOW_REGISTRATION_AFTER_FIRST': 'false',
        'SMTP_ALLOW_PRIVATE_HOSTS': 'false',
        'SMTP_ALLOW_INSECURE_TEST': 'false',
        'SMTP_USER': '',
        'SMTP_PASS': '',
    }
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    listener.listen(16)
    port = listener.getsockname()[1]
    output = tmp_path / 'server.log'
    with output.open('w') as log:
        process = subprocess.Popen(
            [sys.executable, '-m', 'uvicorn', 'app.main:app', '--fd', str(listener.fileno()),
             '--no-proxy-headers', '--log-level', 'warning', '--no-access-log'],
            env=environment, stdout=log, stderr=subprocess.STDOUT,
            pass_fds=(listener.fileno(),),
        )
        try:
            async with httpx.AsyncClient(base_url=f'http://127.0.0.1:{port}', trust_env=False, timeout=2) as client:
                for _ in range(100):
                    assert process.poll() is None, output.read_text()
                    try:
                        if (await client.get('/api/health')).status_code == 200:
                            break
                    except httpx.TransportError:
                        pass
                    await asyncio.sleep(.05)
                else:
                    raise AssertionError('local server did not become healthy')
                response = await client.get('/vault')
                assert response.status_code == 200 and 'Real deployment test' in response.text
                assert response.headers['cache-control'] == 'no-store'
                assert "connect-src 'self'" in response.headers['content-security-policy']
                for path in ['/api/docs', '/api/openapi.json', '/api/no-such-route', '/.env']:
                    assert (await client.get(path)).status_code == 404
                assert (await client.get('/api/health', headers={'Host': 'rebound.example'})).status_code == 400
                account = {'email': 'local-owner@example.com', 'authHash': b64(),
                           'kdf': {'salt': b64(16), 'memoryKib': 8192, 'time': 1, 'parallel': 1},
                           'wrappedDek': b64(48), 'dekNonce': b64(12)}
                registered = await client.post('/api/auth/register', json=account)
                assert registered.status_code == 201, registered.text
                account['email'] = 'not-owner@example.com'
                denied = await client.post('/api/auth/register', json=account)
                assert denied.status_code == 403, denied.text
                assert database.is_file() and database.stat().st_mode & 0o777 == 0o600
                for suffix in ['-wal', '-shm']:
                    companion = database.with_name(database.name + suffix)
                    if companion.exists():
                        assert companion.stat().st_mode & 0o777 == 0o600
                assert not list(backup_dir.glob('*.db*'))
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            listener.close()
    # Uvicorn restores and re-raises SIGTERM after graceful shutdown.
    assert process.returncode in (0, -signal.SIGTERM), output.read_text()


def b64(n=32):return base64.b64encode(os.urandom(n)).decode()

async def test_real_http_smtp_private_credentials_do_not_mix(monkeypatch):
    credentials=[]
    async def receive(reader,writer):
        writer.write(b'220 audit-only ESMTP\r\n');await writer.drain();data=False
        try:
            while line:=await reader.readline():
                if data:
                    if line==b'.\r\n':data=False;writer.write(b'250 queued\r\n')
                    else:continue
                elif line.upper().startswith(b'EHLO'):writer.write(b'250-audit-only\r\n250 AUTH PLAIN\r\n')
                elif line.upper().startswith(b'AUTH PLAIN '):
                    credentials.append(base64.b64decode(line.strip().split(b' ',2)[2]).split(b'\0')[-1].decode())
                    writer.write(b'235 authenticated\r\n')
                elif line.upper().startswith((b'MAIL',b'RCPT')):writer.write(b'250 ok\r\n')
                elif line.upper().startswith(b'DATA'):data=True;writer.write(b'354 send\r\n')
                elif line.upper().startswith(b'QUIT'):writer.write(b'221 bye\r\n');await writer.drain();break
                else:writer.write(b'250 ok\r\n')
                await writer.drain()
        finally:
            writer.close();await writer.wait_closed()
    smtp=await asyncio.start_server(receive,'127.0.0.1',0)
    port=smtp.sockets[0].getsockname()[1]
    import socket
    sock=socket.socket();sock.bind(('127.0.0.1',0));sock.listen(16);sock.setblocking(False)
    http_port=sock.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(app,log_level='error',access_log=False,proxy_headers=False,lifespan='off'))
    task=asyncio.create_task(server.serve(sockets=[sock]))
    try:
        for _ in range(100):
            if server.started:break
            if task.done():await task
            await asyncio.sleep(.01)
        assert server.started
        monkeypatch.setattr(settings,'smtp_allow_private_hosts',True)
        monkeypatch.setattr(settings,'smtp_allow_insecure_test',True)
        async with httpx.AsyncClient(base_url=f'http://127.0.0.1:{http_port}',trust_env=False,timeout=10) as client:
            async def reg(email):
                r=await client.post('/api/auth/register',json={'email':email,'authHash':b64(),'kdf':{'salt':b64(16),'memoryKib':8192,'time':1,'parallel':1},'wrappedDek':b64(48),'dekNonce':b64(12)})
                assert r.status_code==201,r.text
                return {'Authorization':'Bearer '+r.json()['accessToken']}
            owner=await reg('http-owner@example.com');other=await reg('http-other@example.com')
            monkeypatch.setattr(settings,'smtp_user','operator@example.com')
            monkeypatch.setattr(settings,'smtp_pass','synthetic-global-password')
            endpoint={'host':'127.0.0.1','port':port,'secure':False,'user':'other@example.com'}
            denied=await client.put('/api/settings/mail',headers=other,json=endpoint)
            assert denied.status_code==400
            assert credentials==[]
            endpoint['password']='synthetic-private-password'
            assert (await client.put('/api/settings/mail',headers=other,json=endpoint)).status_code==200
            sent=await client.post('/api/settings/mail/test',headers=other,json={'to':'sink@example.com'})
            assert sent.status_code==200,sent.text
            assert credentials==['synthetic-private-password']
            assert 'synthetic-global-password' not in credentials
            assert (await client.get('/api/backup/list',headers=other)).status_code==403
            assert (await client.get('/api/vault',headers=other)).headers['cache-control']=='no-store'
            monkeypatch.setattr(settings,'app_env','local')
            assert (await client.get('/api/health',headers={'Host':f'localhost:{http_port}'})).status_code==200
            injected=await client.get('/api/health',headers={'Host':'rebound.example'})
            assert injected.status_code==400 and injected.json()['error']['code']=='invalid_host'
            monkeypatch.setattr(settings,'request_body_timeout_seconds',0.1)
            reader,writer=await asyncio.open_connection('127.0.0.1',http_port)
            try:
                writer.write(f'POST /api/auth/login HTTP/1.1\r\nHost: localhost:{http_port}\r\nContent-Length: 100\r\nContent-Type: application/json\r\n\r\nx'.encode())
                await writer.drain()
                response=await asyncio.wait_for(reader.readuntil(b'\r\n\r\n'),timeout=2)
                assert b'408' in response.split(b'\r\n')[0]
            finally:
                writer.close();await writer.wait_closed()
    finally:
        server.should_exit=True
        await task
        smtp.close();await smtp.wait_closed()
        sock.close()
