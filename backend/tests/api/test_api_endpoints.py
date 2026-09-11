import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_health_endpoints():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/health")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"
        assert data["db"] == "ok"


@pytest.mark.asyncio
async def test_replay_health_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/health/replay")
        assert res.status_code == 200
        data = res.json()
        assert "running" in data
        assert "total_sequences" in data


@pytest.mark.asyncio
async def test_trains_search_and_pagination():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/v1/trains?query=&limit=10")
        assert res.status_code == 200
        data = res.json()
        assert "items" in data
        assert "total" in data
        assert "offset" in data
        assert "limit" in data
        assert len(data["items"]) <= 10


@pytest.mark.asyncio
async def test_stations_list():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/v1/stations")
        assert res.status_code == 200
        data = res.json()
        assert "items" in data
        assert "total" in data
        assert len(data["items"]) > 0


@pytest.mark.asyncio
async def test_user_auth_flow():
    import uuid
    unique_email = f"test_{uuid.uuid4().hex[:8]}@example.com"
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 1. Register
        reg_res = await ac.post("/api/v1/auth/register", json={
            "email": unique_email,
            "password": "Password123!",
            "full_name": "Test Passenger"
        })
        assert reg_res.status_code == 201
        reg_data = reg_res.json()
        assert "token" in reg_data
        assert "access_token" in reg_data["token"]
        token = reg_data["token"]["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 2. Get Me
        me_res = await ac.get("/api/v1/auth/me", headers=headers)
        assert me_res.status_code == 200
        me_data = me_res.json()
        assert me_data["email"] == unique_email
        assert me_data["full_name"] == "Test Passenger"

        # 3. Login
        login_res = await ac.post("/api/v1/auth/login", json={
            "email": unique_email,
            "password": "Password123!"
        })
        assert login_res.status_code == 200
        assert "access_token" in login_res.json()["token"]


@pytest.mark.asyncio
async def test_passthrough_endpoints():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Weather
        w_res = await ac.get("/api/v1/weather?lat=28.6139&lon=77.2090")
        assert w_res.status_code in (200, 502)  # 502 if ML service offline

        # Directions
        d_res = await ac.get("/api/v1/directions?origin=NDLS&destination=CNB")
        assert d_res.status_code in (200, 502)
