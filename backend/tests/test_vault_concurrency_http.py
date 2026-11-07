"""Database write isolation exercised through real Uvicorn TCP HTTP + SQLite."""
import asyncio
import uuid

import pytest

from test_auth_security_http import b64, http_client, material, signup, authorization


def record(record_id=None):
    return {"id": record_id or str(uuid.uuid4()), "ciphertext": b64(), "nonce": b64(12)}


async def owner(client):
    _, body = await signup(client)
    return authorization(body)


@pytest.mark.parametrize("kind", ["items", "folders"])
async def test_http_first_concurrent_creates_and_existing_state_revisions(http_client, kind):
    headers = await owner(http_client)
    created = await asyncio.gather(*[
        http_client.post('/api/' + kind, headers=headers, json=record()) for _ in range(6)
    ])
    assert [r.status_code for r in created] == [201] * 6
    assert sorted(r.json()['rev'] for r in created) == list(range(1, 7))
    again = await asyncio.gather(*[
        http_client.post('/api/' + kind, headers=headers, json=record()) for _ in range(6)
    ])
    assert [r.status_code for r in again] == [201] * 6
    assert sorted(r.json()['rev'] for r in again) == list(range(7, 13))
    vault = (await http_client.get('/api/vault', headers=headers)).json()
    assert vault['rev'] == 12 and len(vault[kind]) == 12


@pytest.mark.parametrize("kind", ["items", "folders"])
async def test_http_same_revision_patches_only_one_winner(http_client, kind):
    headers = await owner(http_client)
    payload = record()
    created = await http_client.post('/api/' + kind, headers=headers, json=payload)
    revision = created.json()['rev']
    patches = [{**record(payload['id']), 'rev': revision} for _ in range(4)]
    responses = await asyncio.gather(*[
        http_client.patch('/api/' + kind + '/' + payload['id'], headers=headers, json=p) for p in patches
    ])
    assert sorted(r.status_code for r in responses) == [200, 409, 409, 409]
    winner = next(i for i, r in enumerate(responses) if r.status_code == 200)
    vault = (await http_client.get('/api/vault', headers=headers)).json()
    assert vault['rev'] == revision + 1
    assert vault[kind][0]['ciphertext'] == patches[winner]['ciphertext']
    assert all(r.json()['error']['detail']['rev'] == revision + 1 for r in responses if r.status_code == 409)


@pytest.mark.parametrize("kind", ["items", "folders"])
async def test_http_patch_delete_and_duplicate_delete_preserve_tombstones(http_client, kind):
    headers = await owner(http_client)
    payload = record()
    created = await http_client.post('/api/' + kind, headers=headers, json=payload)
    revision = created.json()['rev']
    path = '/api/' + kind + '/' + payload['id']
    responses = await asyncio.gather(
        http_client.patch(path, headers=headers, json={**record(payload['id']), 'rev': revision}),
        http_client.delete(path, headers=headers, params={'rev': revision}),
    )
    assert sum(r.status_code == 200 for r in responses) == 1
    assert all(r.status_code in {200, 404, 409} for r in responses)
    delta = (await http_client.get('/api/vault', headers=headers, params={'since': 0})).json()
    assert delta['rev'] == revision + 1
    current = delta[kind][0]
    if current['deletedAt'] is None:
        deletes = await asyncio.gather(*[
            http_client.delete(path, headers=headers, params={'rev': current['rev']}) for _ in range(2)
        ])
        assert sorted(r.status_code for r in deletes) == [200, 404]
    else:
        assert (await http_client.patch(path, headers=headers, json={**record(payload['id']), 'rev': current['rev']})).status_code == 404
    tombstone = (await http_client.get('/api/vault', headers=headers, params={'since': 0})).json()
    assert tombstone[kind][0]['deletedAt'] is not None
    before = tombstone['rev']
    # Retried create must not quietly pretend an existing tombstone is active.
    assert (await http_client.post('/api/' + kind, headers=headers, json=payload)).status_code == 409
    assert (await http_client.get('/api/vault', headers=headers)).json()['rev'] == before


@pytest.mark.parametrize("kind", ["items", "folders"])
async def test_http_same_id_create_idempotent_or_conflict(http_client, kind):
    headers = await owner(http_client)
    payload = record()
    same = await asyncio.gather(*[
        http_client.post('/api/' + kind, headers=headers, json=payload) for _ in range(3)
    ])
    assert [r.status_code for r in same] == [201] * 3
    assert {r.json()['rev'] for r in same} == {1}
    changed = await asyncio.gather(*[
        http_client.post('/api/' + kind, headers=headers, json=record(payload['id'])) for _ in range(2)
    ])
    assert [r.status_code for r in changed] == [409] * 2
    assert (await http_client.get('/api/vault', headers=headers)).json()['rev'] == 1


async def test_http_import_create_and_duplicate_id_have_unique_revisions(http_client):
    headers = await owner(http_client)
    folder = record()
    first = record()
    result, created = await asyncio.gather(
        http_client.post('/api/vault/import', headers=headers, json={
            'folders': [folder], 'items': [first, first], 'strategy': 'skip'}),
        http_client.post('/api/items', headers=headers, json=record()),
    )
    assert result.status_code == 200 and created.status_code == 201
    assert result.json()['imported'] == {'folders': 1, 'items': 1}
    assert result.json()['skipped'] == 1
    vault = (await http_client.get('/api/vault', headers=headers)).json()
    assert vault['rev'] == 3
    assert sorted(r['rev'] for r in vault['items'] + vault['folders']) == [1, 2, 3]


async def test_http_import_cross_user_collision_rolls_back_all_changes(http_client):
    headers = await owner(http_client)
    _, other = await signup(http_client, material('second@example.com'))
    other_headers = authorization(other)
    private = record()
    assert (await http_client.post('/api/items', headers=other_headers, json=private)).status_code == 201
    before = (await http_client.get('/api/vault', headers=headers)).json()
    attempted = await http_client.post('/api/vault/import', headers=headers, json={
        'folders': [record()], 'items': [private], 'strategy': 'overwrite'})
    assert attempted.status_code == 409
    assert (await http_client.get('/api/vault', headers=headers)).json() == before
    for method in ['patch', 'delete']:
        path = '/api/items/' + private['id']
        if method == 'patch':
            response = await http_client.patch(path, headers=headers, json={**record(private['id']), 'rev': 1})
        else:
            response = await http_client.delete(path, headers=headers, params={'rev': 1})
        assert response.status_code == 404
    other_vault = (await http_client.get('/api/vault', headers=other_headers)).json()
    assert other_vault['items'][0]['ciphertext'] == private['ciphertext'] and other_vault['rev'] == 1


async def test_http_concurrent_initial_settings_no_unique_key_failure(http_client):
    headers = await owner(http_client)
    payloads = [{'ciphertext': b64(), 'nonce': b64(12)} for _ in range(4)]
    results = await asyncio.gather(*[
        http_client.put('/api/settings', headers=headers, json=p) for p in payloads
    ])
    assert [r.status_code for r in results] == [200] * 4
    result = (await http_client.get('/api/settings', headers=headers)).json()
    assert any(result['ciphertext'] == p['ciphertext'] and result['nonce'] == p['nonce'] for p in payloads)
    assert (await http_client.get('/api/vault', headers=headers)).json()['rev'] == 0


@pytest.mark.parametrize("kind", ["items", "folders"])
async def test_http_import_overwrite_serializes_against_optimistic_patch(http_client, kind):
    headers = await owner(http_client)
    original = record()
    assert (await http_client.post('/api/' + kind, headers=headers, json=original)).status_code == 201
    replacement = record(original['id'])
    imported, patched = await asyncio.gather(
        http_client.post('/api/vault/import', headers=headers, json={
            'folders': [replacement] if kind == 'folders' else [],
            'items': [replacement] if kind == 'items' else [], 'strategy': 'overwrite'}),
        http_client.patch('/api/' + kind + '/' + original['id'], headers=headers,
                          json={**record(original['id']), 'rev': 1}),
    )
    assert imported.status_code == 200
    assert patched.status_code in {200, 409}
    final = (await http_client.get('/api/vault', headers=headers)).json()
    # Explicit overwrite is allowed after a successful earlier edit, but an edit
    # with the old rev cannot overwrite an import that committed first.
    assert final[kind][0]['ciphertext'] == replacement['ciphertext']
    assert final['rev'] == (3 if patched.status_code == 200 else 2)
    assert final[kind][0]['rev'] == final['rev']


async def test_http_independent_worker_processes_share_atomic_revision(http_client):
    """Two OS processes share SQLite; no process-local mutex can pass this."""
    import socket
    import sys
    import httpx

    headers = await owner(http_client)
    listeners, processes, clients = [], [], []
    code = ('import sys,uvicorn;from app.main import app;'
            'uvicorn.run(app,fd=int(sys.argv[1]),lifespan="off",'
            'proxy_headers=False,access_log=False,log_level="error")')
    try:
        for _ in range(2):
            listener = socket.socket()
            listener.bind(('127.0.0.1', 0))
            listeners.append(listener)
            process = await asyncio.create_subprocess_exec(
                sys.executable, '-c', code, str(listener.fileno()),
                pass_fds=(listener.fileno(),), stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE)
            processes.append(process)
            client = httpx.AsyncClient(base_url='http://127.0.0.1:' + str(listener.getsockname()[1]),
                                       trust_env=False, timeout=10)
            clients.append(client)
            for _ in range(100):
                if process.returncode is not None:
                    output, error = await process.communicate()
                    pytest.fail('worker failed: ' + (output + error).decode()[-2000:])
                try:
                    response = await client.get('/api/health')
                    if response.status_code == 200:
                        break
                except httpx.ConnectError:
                    pass
                await asyncio.sleep(.02)
            else:
                pytest.fail('worker did not start')
        rows = await asyncio.gather(*[
            clients[i % 2].post('/api/items', headers=headers, json=record()) for i in range(8)
        ])
        assert [r.status_code for r in rows] == [201] * 8
        assert sorted(r.json()['rev'] for r in rows) == list(range(1, 9))
        target = rows[0].json()
        patches = await asyncio.gather(*[
            client.patch('/api/items/' + target['id'], headers=headers,
                         json={**record(target['id']), 'rev': target['rev']}) for client in clients
        ])
        assert sorted(r.status_code for r in patches) == [200, 409]
        assert (await http_client.get('/api/vault', headers=headers)).json()['rev'] == 9
    finally:
        for client in clients:
            await client.aclose()
        for process in processes:
            if process.returncode is None:
                process.terminate()
                try:
                    await asyncio.wait_for(process.communicate(), timeout=5)
                except asyncio.TimeoutError:
                    process.kill()
                    await process.communicate()
        for listener in listeners:
            listener.close()
