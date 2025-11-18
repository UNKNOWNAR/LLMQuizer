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

# Add project root to path to allow importing main
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))


# ─────────────────────────────────────────────
# FIXTURE: Mock Server
# ─────────────────────────────────────────────
@pytest.fixture(scope="session")
def mock_server():
    """Run the mock_server.py in a separate subprocess."""
    python_executable = sys.executable

    # Ensure we run mock_server in a fresh env (so DOCKER_TESTING can be toggled externally)
    env = os.environ.copy()
    # Do not force DOCKER_TESTING here; tests will use whichever mock server mode you start it with.
    process = subprocess.Popen([python_executable, "mock_server.py"], env=env)
    sleep(2)  # allow server to start
    yield "http://localhost:8001"
    process.terminate()
    process.wait()


# ─────────────────────────────────────────────
# FIXTURE: Main App Server with robust readiness polling
# ─────────────────────────────────────────────
@pytest.fixture(scope="session")
def main_app_server():
    """
    Run main.py via uvicorn in a subprocess and wait until it is ready before starting tests.
    """
    python_executable = sys.executable

    # Ensure consistent secret across tests
    env = os.environ.copy()
    env["MY_SECRET"] = "test-secret"

    process = subprocess.Popen(
        [
            python_executable,
            "-m",
            "uvicorn",
            "main:app",
            "--host",
            "0.0.0.0",
            "--port",
            "8000",
            "--log-level",
            "info",
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    base_url = "http://127.0.0.1:8000"
    max_wait = 30
    interval = 0.5
    elapsed = 0.0

    print("\n[main_app_server] Waiting for FastAPI server to become ready...")

    while elapsed < max_wait:
        try:
            resp = httpx.get(f"{base_url}/", timeout=1.0)
            if resp.status_code == 200:
                print("[main_app_server] Server is READY.")
                break
        except Exception:
            pass

        time.sleep(interval)
        elapsed += interval
    else:
        print("[main_app_server] ERROR: Server failed to start in time.")
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
        raise RuntimeError(
            f"Server did not start at {base_url} within {max_wait} seconds"
        )

    yield base_url

    # Shutdown
    print("[main_app_server] Shutting down FastAPI server...")
    process.terminate()
    try:
        process.wait(timeout=5)
        print("[main_app_server] Server terminated cleanly.")
    except subprocess.TimeoutExpired:
        print("[main_app_server] Killing server...")
        process.kill()
        process.wait()


# ─────────────────────────────────────────────
# FIXTURE: httpx async client
# ─────────────────────────────────────────────
@pytest_asyncio.fixture
async def client(main_app_server):
    async with httpx.AsyncClient(base_url=main_app_server) as c:
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
    assert response.json() == {"status": "Hybrid AI Agent is ready"}


@pytest.mark.asyncio
async def test_invalid_secret(client: httpx.AsyncClient):
    payload = {
        "email": "test@example.com",
        "secret": "WRONGSECRET",
        "url": "https://example.com",
    }
    res = await client.post("/quiz", json=payload)
    assert res.status_code == 403
    assert res.json() == {"detail": "Unauthorized: Invalid secret key"}


# ─────────────────────────────────────────────
# FULL QUIZ CHAIN TEST
# ─────────────────────────────────────────────
@pytest.mark.asyncio
async def test_full_quiz_chain(client: httpx.AsyncClient, mock_server):
    initial_quiz_url = f"{mock_server}/"

    payload = {
        "email": "test@example.com",
        "secret": "test-secret",
        "url": initial_quiz_url,
    }

    res = await client.post("/quiz", json=payload)
    assert res.status_code == 200
    assert res.json() == {"message": "Agent started in background"}

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

    assert f"{mock_server}/" in urls
    assert f"{mock_server}/mock-quiz/csv" in urls
    assert f"{mock_server}/mock-quiz/pdf" in urls
    assert f"{mock_server}/mock-quiz/image" in urls
    assert urls.count(f"{mock_server}/mock-quiz/retry-test") == 2
    assert f"{mock_server}/mock-quiz/stop-test" in urls

    # Answer sanity checks
    assert submission_log[0]["answer"] == "start"
    assert isinstance(submission_log[1]["answer"], int)
    assert "supercalifragilisticexpialidocious" in submission_log[2]["answer"]
    assert isinstance(submission_log[3]["answer"], str)
    assert "paris" in str(submission_log[5]["answer"]).lower()
    assert submission_log[6]["answer"] == 4


# ─────────────────────────────────────────────
# 404 TEST
# ─────────────────────────────────────────────
@pytest.mark.asyncio
async def test_404_not_found(client: httpx.AsyncClient):
    res = await client.get("/does-not-exist")
    assert res.status_code == 404


# ─────────────────────────────────────────────
# PAYLOAD VALIDATION TESTS (422)
# ─────────────────────────────────────────────
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload, msg",
    [
        ("this is not json", "JSON decode error"),
        ({"email": "a", "secret": "b"}, "Field required"),
        ({"email": "a", "url": "x"}, "Field required"),
        ({"secret": "b", "url": "x"}, "Field required"),
    ],
)
async def test_422_invalid_payload(client: httpx.AsyncClient, payload, msg):
    if isinstance(payload, str):
        res = await client.post(
            "/quiz", content=payload, headers={"Content-Type": "application/json"}
        )
    else:
        res = await client.post("/quiz", json=payload)

    assert res.status_code == 422
    assert msg in res.text


# ─────────────────────────────────────────────
# BROKEN LINK TEST
# ─────────────────────────────────────────────
@pytest.mark.asyncio
async def test_broken_link_graceful_failure(client: httpx.AsyncClient, mock_server):
    quiz_url = f"{mock_server}/mock-quiz/broken-link"

    payload = {
        "email": "test@example.com",
        "secret": "test-secret",
        "url": quiz_url,
    }

    await client.post("/quiz", json=payload)

    log = []
    for _ in range(10):
        await asyncio.sleep(1)
        log = (await httpx.AsyncClient().get(f"{mock_server}/mock-submit/log")).json()
        if len(log) > 0:
            break

    assert len(log) == 1
    assert "Error" in log[0]["answer"]


# ─────────────────────────────────────────────
# LLM FAIL TEST
# ─────────────────────────────────────────────
@pytest.mark.asyncio
async def test_llm_failure_graceful_handling(client: httpx.AsyncClient, mock_server):
    quiz_url = f"{mock_server}/mock-quiz/llm-fail"

    payload = {
        "email": "test@example.com",
        "secret": "test-secret",
        "url": quiz_url,
    }

    await client.post("/quiz", json=payload)

    log = []
    for _ in range(10):
        await asyncio.sleep(1)
        log = (await httpx.AsyncClient().get(f"{mock_server}/mock-submit/log")).json()
        if len(log) > 0:
            break

    assert len(log) == 1
    assert log[0]["answer"] == "Error: AI could not determine the answer."
