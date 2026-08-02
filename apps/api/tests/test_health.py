import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_health_live() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_health_ready() -> None:
    # This test actually hits the DB and Redis if they are up,
    # or fails gracefully if they are down (returns 503).
    # Since we don't mock here, we just check that it returns a valid JSON response structure.
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health/ready")

    assert response.status_code in (200, 503)
    body = response.json()
    assert "status" in body
    assert "details" in body
    assert "database" in body["details"]
    assert "redis" in body["details"]
