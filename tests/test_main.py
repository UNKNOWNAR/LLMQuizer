import pytest
import pytest_asyncio
import httpx
import asyncio
import subprocess
import sys
import os
import time
from time import sleep
from unittest.mock import patch, AsyncMock
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add project root to path to allow importing main
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


# ─────────────────────────────────────────────
# FIXTURE: Mock Server
# ─────────────────────────────────────────────
@pytest.fixture(scope="session")
def mock_server():
    """
    Return the Ngrok URL for the mock server.
    Assumes the mock server is running externally and exposed via Ngrok.
    """
    ngrok_url = "https://unhasty-felica-vigilant.ngrok-free.dev"
    print(f"\n[mock_server] Using Ngrok URL: {ngrok_url}")
    yield ngrok_url


# ─────────────────────────────────────────────
# FIXTURE: Main App Server (Railway)
# ─────────────────────────────────────────────
@pytest.fixture(scope="session")
def main_app_server():
    """
    Use Railway deployment for all tests.
    """
    railway_url = "https://llm-quizer.up.railway.app"
    print(f"\n[main_app_server] Using Railway deployment: {railway_url}")
    yield railway_url


# ─────────────────────────────────────────────
# FIXTURE: httpx async client
# ─────────────────────────────────────────────
@pytest_asyncio.fixture
async def client(main_app_server):
    async with httpx.AsyncClient(base_url=main_app_server, timeout=60.0) as c:
        yield c


# ─────────────────────────────────────────────
# ALWAYS CLEAR MOCK LOG BEFORE EACH TEST
# ─────────────────────────────────────────────
@pytest_asyncio.fixture(autouse=True)
async def clear_mock_server_log(mock_server):
    async with httpx.AsyncClient() as client:
        await client.get(f"{mock_server}/mock-submit/clear")


# ─────────────────────────────────────────────
# BASIC TESTS
# ─────────────────────────────────────────────
@pytest.mark.asyncio
async def test_root_endpoint(client: httpx.AsyncClient):
    response = await client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "Hybrid AI Agent is ready"
    assert data["service"] == "LLMQuizer"


@pytest.mark.asyncio
async def test_health_endpoint(client: httpx.AsyncClient):
    """Test the health endpoint"""
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_invalid_secret(client: httpx.AsyncClient):
    payload = {
        "email": "test@example.com",
        "secret": "WRONGSECRET",
        "url": "https://example.com",
    }
    res = await client.post("/quiz", json=payload)
    assert res.status_code == 403
    assert res.json() == {"detail": "Invalid Secret"}


@pytest.mark.asyncio
async def test_400_invalid_payload(client: httpx.AsyncClient):
    """Test that invalid JSON returns 400"""
    res = await client.post(
        "/quiz", 
        content="this is not json", 
        headers={"Content-Type": "application/json"}
    )
    assert res.status_code == 400
    assert "JSON decode error" in res.json()["detail"]


@pytest.mark.asyncio
async def test_missing_fields(client: httpx.AsyncClient):
    """Test that missing required fields returns 400"""
    payload = {
        "email": "test@example.com",
        "secret": "test-secret",
        # Missing 'url'
    }
    res = await client.post("/quiz", json=payload)
    assert res.status_code == 400
    assert "Missing fields" in res.json()["detail"]


# ─────────────────────────────────────────────
# FULL QUIZ CHAIN TEST
# ─────────────────────────────────────────────
@pytest.mark.asyncio
async def test_full_quiz_chain(client: httpx.AsyncClient, mock_server):
    initial_quiz_url = f"{mock_server}/"

    payload = {
        "email": "test@example.com",
        "secret": os.getenv("MY_SECRET", "my-secret-value"),
        "url": initial_quiz_url,
    }

    res = await client.post("/quiz", json=payload)
    assert res.status_code == 200
    assert res.json() == {"message": "Agent started"}

    # Poll the mock server until the chain finishes
    max_polls = 40
    poll_interval = 2

    submission_log = []
    for i in range(max_polls):
        await asyncio.sleep(poll_interval)
        log_resp = await httpx.AsyncClient().get(f"{mock_server}/mock-submit/log")
        submission_log = log_resp.json()

        if len(submission_log) >= 7:
            break

    assert len(submission_log) >= 7, (
        f"Expected at least 7 submissions, got {len(submission_log)}"
    )

    # Normalize any host.docker.internal -> localhost to make assertions robust
    def _normalize(url: str) -> str:
        return url.replace("http://host.docker.internal:8001", "http://localhost:8001")

    urls = [_normalize(item["url"]) for item in submission_log]

    # Check for expected URLs in the chain
    # Note: Exact URLs depend on the mock server logic
    assert any(f"{mock_server}/" in u for u in urls)
    
    # Answer sanity checks
    assert submission_log[0]["answer"] == "start"


# ─────────────────────────────────────────────
# 404 TEST
# ─────────────────────────────────────────────
@pytest.mark.asyncio
async def test_404_not_found(client: httpx.AsyncClient):
    res = await client.get("/does-not-exist")
    assert res.status_code == 404


# ─────────────────────────────────────────────
# BROKEN LINK TEST
# ─────────────────────────────────────────────
@pytest.mark.asyncio
async def test_broken_link_graceful_failure(client: httpx.AsyncClient, mock_server):
    quiz_url = f"{mock_server}/mock-quiz/broken-link"

    payload = {
        "email": "test@example.com",
        "secret": os.getenv("MY_SECRET", "my-secret-value"),
        "url": quiz_url,
    }

    await client.post("/quiz", json=payload)

    log = []
    for _ in range(15):
        await asyncio.sleep(1)
        log = (await httpx.AsyncClient().get(f"{mock_server}/mock-submit/log")).json()
        if len(log) > 0:
            break

    assert len(log) >= 1
    # The agent submits "Not Found" when it encounters a 404
    assert "Not Found" in str(log[0]["answer"])


# ─────────────────────────────────────────────
# LLM FAIL TEST
# ─────────────────────────────────────────────
@pytest.mark.asyncio
async def test_llm_failure_graceful_handling(client: httpx.AsyncClient, mock_server):
    quiz_url = f"{mock_server}/mock-quiz/llm-fail"

    payload = {
        "email": "test@example.com",
        "secret": os.getenv("MY_SECRET", "my-secret-value"),
        "url": quiz_url,
    }

    await client.post("/quiz", json=payload)

    log = []
    for _ in range(15):
        await asyncio.sleep(1)
        log = (await httpx.AsyncClient().get(f"{mock_server}/mock-submit/log")).json()
        if len(log) > 0:
            break

    assert len(log) >= 1
    # The agent submits None or "None" when LLM fails
    assert str(log[0]["answer"]) == "None" or log[0]["answer"] is None
