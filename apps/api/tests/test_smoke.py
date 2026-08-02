"""Smoke tests for the FastAPI application scaffold."""

from httpx import ASGITransport, AsyncClient

from app.main import app


async def test_service_info() -> None:
    """GET / returns the service name and scaffold status."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "support-agent-api"
    assert "status" in body
