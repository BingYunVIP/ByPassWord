"""Security regression checks for runtime, SMTP profile boundaries and backups."""
import asyncio
import base64
import hashlib
import os
import sqlite3
import subprocess
import sys
import json
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from app.core.config import Settings, settings
from app.core.db import SessionLocal
from app.main import app
from app.services import backup_service, mailer, secrets
from app.jobs.backup_job import _should_snapshot


def b64(n=32):
    return base64.b64encode(os.urandom(n)).decode()

async def register(client, email):
    response = await client.post('/api/auth/register', json={'email':email,'authHash':b64(), 'kdf':{'salt':b64(16),'memoryKib':8192,'time':1,'parallel':1},'wrappedDek':b64(48),'dekNonce':b64(12)})
    assert response.status_code == 201, response.text
    token = response.json()['accessToken']
    user = (await client.get('/api/auth/me', headers={'Authorization':'Bearer '+token})).json()
    return user['id'], {'Authorization':'Bearer '+token}

@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        yield client

@pytest.fixture
def backup_config(tmp_path, monkeypatch):
    directory=tmp_path/'backups';directory.mkdir(mode=0o700)
    key=tmp_path/'backup.key';key.write_bytes(os.urandom(32));key.chmod(0o600)
    monkeypatch.setattr(settings,'backup_dir',str(directory))
    monkeypatch.setattr(settings,'backup_key_file',str(key))
    return directory,key


def test_deployed_settings_reject_default_same_weak_and_nonlocal_origins():
    for environment in ['local','production']:
        with pytest.raises(ValidationError):
            Settings(_env_file=None,app_env=environment)
    good={'app_env':'local','jwt_secret':'abcXYZ0123456789+-AaBbCcDdEeFfGgHhI','server_secret':'randomAbCDeF0123456789_-qrSTuvwxyz!','backup_key_file':'/private/backup.key','rate_limit_enabled':True}
    assert Settings(_env_file=None,**good).app_env=='local'
    with pytest.raises(ValidationError):Settings(_env_file=None,**{**good,'server_secret':good['jwt_secret']})
    with pytest.raises(ValidationError):Settings(_env_file=None,**{**good,'allowed_origins':'http://public.invalid'})
    with pytest.raises(ValidationError):Settings(_env_file=None,**{**good,'smtp_allow_private_hosts':True})
    with pytest.raises(ValidationError):Settings(_env_file=None,**{**good,'jwt_secret':'a'*40})
    smtp_secret = 'synthetic-smtp-secret-do-not-log'
    cfg = Settings(_env_file=None, **{**good, 'smtp_pass': smtp_secret})
    assert good['jwt_secret'] not in repr(cfg) and good['server_secret'] not in repr(cfg) and smtp_secret not in repr(cfg)
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None, **{**good, 'smtp_pass': smtp_secret, 'rate_limit_enabled': False})
    assert smtp_secret not in str(error.value) and good['server_secret'] not in str(error.value)


def test_backup_key_cannot_be_inside_normalized_backup_path(tmp_path, monkeypatch):
    directory = tmp_path / 'backups'
    directory.mkdir(mode=0o700)
    key = directory / 'backup.key'
    key.write_bytes(os.urandom(32))
    key.chmod(0o600)
    # Equivalent configured paths must not bypass key/snapshot separation.
    monkeypatch.setattr(settings, 'backup_dir', str(tmp_path / 'data' / '..' / 'backups'))
    monkeypatch.setattr(settings, 'backup_key_file', str(key))
    with pytest.raises(RuntimeError, match='outside'):
        backup_service._key()

async def test_global_smtp_not_mixed_or_shared(client,monkeypatch):
    monkeypatch.setattr(settings,'smtp_pass','synthetic-global-password')
    monkeypatch.setattr(settings,'smtp_user','operator@example.com')
    owner,owner_h=await register(client,'owner-smtp@example.com')
    other,other_h=await register(client,'other-smtp@example.com')
    async with SessionLocal() as session:
        assert (await mailer.resolve_config(session,owner))['password']=='synthetic-global-password'
        assert (await mailer.resolve_config(session,other))['password']==''
        await secrets.set_secrets(session,other,{'smtp_host':'attacker.example','smtp_user':'other@example.com'})
        result=await mailer.resolve_config(session,other)
        assert result['host']=='attacker.example' and result['password']==''
    denied=await client.put('/api/settings/mail',headers=other_h,json={'host':'smtp.example.com','port':465,'user':'other@example.com'})
    assert denied.status_code==400
    own={'host':'smtp.example.com','port':465,'user':'other@example.com','password':'synthetic-private-password'}
    assert (await client.put('/api/settings/mail',headers=other_h,json=own)).status_code==200
    own.pop('password');own['host']='changed.example.com'
    assert (await client.put('/api/settings/mail',headers=other_h,json=own)).status_code==400
    assert (await client.get('/api/backup/list',headers=other_h)).status_code==403
    assert (await client.get('/api/settings/backup',headers=other_h)).status_code==403

async def test_smtp_private_host_and_header_rejected_before_authentication(monkeypatch):
    with pytest.raises(ValueError):await mailer._smtp_socket('127.0.0.1',25)
    config={'host':'127.0.0.1','port':25,'user':'audit@example.com','password':'synthetic','secure':True,'from':'audit@example.com'}
    assert not await mailer.send_email(config,'receiver@example.com','bad\nheader','safe')

async def test_security_headers_request_limit_and_validation_redaction(client,monkeypatch):
    r=await client.post('/api/auth/login',json={'email':'bad','authHash':'private-value'})
    assert r.status_code==400 and 'private-value' not in r.text and '"input"' not in r.text
    assert r.headers['cache-control']=='no-store' and r.headers['x-frame-options']=='DENY'
    monkeypatch.setattr(settings,'max_request_bytes',1024)
    r=await client.post('/api/auth/login',content=b'x'*1025)
    assert r.status_code==413 and r.headers['cache-control']=='no-store'

async def test_snapshot_encrypted_verified_private_and_never_third(client,backup_config):
    directory,key=backup_config
    _,headers=await register(client,'backup-owner@example.com')
    a=await client.post('/api/backup/snapshot',headers=headers);assert a.status_code==200,a.text
    meta=a.json();path=directory/meta['id']
    assert meta['verified'] and meta['encrypted'] and path.stat().st_mode&0o777==0o600
    blob=path.read_bytes();assert not blob.startswith(b'SQLite format 3')
    assert hashlib.sha256(blob).hexdigest()==meta['sha256']
    data=backup_service.decrypt_snapshot(path)
    with sqlite3.connect(':memory:') as db:
        db.deserialize(data);assert db.execute('select count(*) from users').fetchone()[0]==1
    cli = Path(__file__).resolve().parents[1] / 'scripts/encrypted_backup.py'
    environment = {**os.environ, 'BACKUP_KEY_FILE': str(key)}
    verified = subprocess.run([sys.executable,str(cli),'verify',str(path)],env=environment,text=True,capture_output=True,check=True)
    assert json.loads(verified.stdout)['sqlite_integrity']=='ok'
    recovered = directory.parent / 'restored' / 'restored.db'
    subprocess.run([sys.executable,str(cli),'decrypt',str(path),'--output',str(recovered)],env=environment,text=True,capture_output=True,check=True)
    assert recovered.stat().st_mode&0o777==0o600 and recovered.read_bytes()==data
    # Only a transient test restore; remove it before creating a second backup.
    recovered.unlink()
    assert (await client.post('/api/backup/snapshot',headers=headers)).status_code==200
    before={p.name:p.read_bytes() for p in directory.iterdir() if p.name.endswith('.enc')}
    assert (await client.post('/api/backup/snapshot',headers=headers)).status_code==409
    assert before=={p.name:p.read_bytes() for p in directory.iterdir() if p.name.endswith('.enc')}
    assert len(backup_service.list_snapshots())==2
    with pytest.raises(Exception):backup_service.decrypt_snapshot(path,os.urandom(32))

async def test_cleanup_only_after_verified_replacement(client,backup_config):
    directory,key=backup_config
    await register(client,'retention-owner@example.com')
    old=directory/'vault-20000101-000000-pre-import.db';old.write_bytes(b'legacy')
    t=time.time()-40*86400;os.utime(old,(t,t))
    assert backup_service._meta(old)['kind']=='pre-import'
    assert backup_service.cleanup(30)==0 and old.exists()
    meta=backup_service.create_snapshot('auto')
    assert backup_service.cleanup(30,validated_snapshot=meta['id'])==1 and not old.exists()
    assert (directory/meta['id']).exists()

async def test_weekly_schedule_respects_weekday_and_timezone(client,backup_config):
    uid,_=await register(client,'schedule-owner@example.com')
    async with SessionLocal() as session:
        await secrets.set_secret(session,uid,'backup_schedule','weekly-02:00')
        zone=ZoneInfo('Asia/Singapore')
        assert not await _should_snapshot(session,datetime(2026,11,7,2,0,tzinfo=zone))
        assert await _should_snapshot(session,datetime(2026,11,8,2,0,tzinfo=zone))
        assert not await _should_snapshot(session,datetime(2026,11,8,3,0,tzinfo=zone))

async def test_static_spa_does_not_mask_api_or_allow_traversal(client,tmp_path,monkeypatch):
    root=tmp_path/'static';root.mkdir();(root/'index.html').write_text('<title>Audit SPA</title>')
    monkeypatch.setattr(settings,'static_dir',str(root))
    assert (await client.get('/vault-view')).status_code==200
    assert (await client.get('/api/no-such-endpoint')).status_code==404
    assert (await client.get('/.env')).status_code==404
    assert (await client.get('/%2e%2e/pyproject.toml')).status_code==404

async def test_local_host_guard_accepts_loopback_rejects_rebinding(client,monkeypatch):
    monkeypatch.setattr(settings,'app_env','local')
    assert (await client.get('/api/health',headers={'Host':'localhost:899'})).status_code==200
    assert (await client.get('/api/health',headers={'Host':'127.0.0.1:899'})).status_code==200
    for host in ['attacker.example','localhost.attacker.example','evil@localhost:899']:
        response=await client.get('/api/health',headers={'Host':host})
        assert response.status_code==400 and response.json()['error']['code']=='invalid_host'

async def test_explicit_backup_delete_preserves_verified_copy(client,backup_config):
    directory,_=backup_config
    await register(client,'delete-owner@example.com')
    first=backup_service.create_snapshot('manual');a=directory/first['id']
    with pytest.raises(RuntimeError):backup_service.delete_snapshot(a)
    second=backup_service.create_snapshot('manual');b=directory/second['id']
    backup_service.delete_snapshot(a)
    assert not a.exists() and b.exists()
    with pytest.raises(RuntimeError):backup_service.delete_snapshot(b)
    with pytest.raises(RuntimeError):backup_service.delete_snapshot(directory.parent/'arbitrary.db.enc')
