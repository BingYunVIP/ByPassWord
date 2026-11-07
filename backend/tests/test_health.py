"""健康检查接口测试。"""

from httpx import ASGITransport, AsyncClient

from app.main import app


async def test_health_returns_ok() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["db"] == "ok"
    assert body["version"]
    assert body["env"] == "test"


async def test_openapi_available() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/openapi.json")

    assert response.status_code == 200
    assert response.json()["info"]["title"] == "ByPassWord API"
